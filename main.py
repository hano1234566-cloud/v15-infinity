import os, time, json, logging, threading
from datetime import datetime, timezone, date
import ccxt, pandas as pd
from flask import Flask, jsonify

CONFIG = {
    "RISK": 0.01,
    "MAX_POS": 2,
    "LEV": 3,
    "TIMEFRAME": "15m",
    "TIMEFRAME_HTF": "1h",
    "LIMIT": 300,
    "SCAN": 25,
    "SL": 0.011,
    "TP": 0.025,
    "MIN_SCORE": 7,
    "STATE": "bot_state.json",
}

API_KEY=os.getenv("OKX_API_KEY","").strip()
API_SECRET=os.getenv("OKX_API_SECRET","").strip() or os.getenv("OKX_SECRET","").strip()
API_PASS=os.getenv("OKX_API_PASSWORD","").strip() or os.getenv("OKX_PASSPHRASE","").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log=logging.getLogger("FIXED")
app=Flask(__name__)
exchange=ccxt.okx({"apiKey":API_KEY,"secret":API_SECRET,"password":API_PASS,"enableRateLimit":True,"options":{"defaultType":"swap"}})

def load_state():
    try:
        with open(CONFIG["STATE"],"r") as f: return json.load(f)
    except: return {}
saved=load_state()
state={"running":True,"started":datetime.now(timezone.utc).isoformat(),"last_scan":None,"scanned":0,"signals":[],"loop":0,"btc_trend":"unknown","btc_vol":0.0,"open_trades":saved.get("open_trades",{}),"errors":[]}

def save_state():
    try:
        with open(CONFIG["STATE"],"w") as f: json.dump({"open_trades":state["open_trades"]},f)
    except: pass

# ===== FIX USDT 0.00 =====
def get_free():
    try:
        bal=exchange.fetch_balance({"type":"swap"})
        data=bal.get("info",{}).get("data",[])
        for d in data:
            if d.get("ccy")=="USDT":
                v=d.get("availBal") or d.get("availEq")
                if v: return float(v)
        if bal.get("USDT",{}).get("free"): return float(bal["USDT"]["free"])
        b2=exchange.fetch_balance()
        return float(b2.get("USDT",{}).get("free",0) or b2.get("USDT",{}).get("total",0) or 0)
    except:
        return 0.0

def get_equity():
    free=get_free()
    try:
        bal=exchange.fetch_balance()
        spot=0.0
        for coin, amt in bal.get("total",{}).items():
            if coin=="USDT": continue
            try:
                a=float(amt or 0)
                if a>0:
                    pr=float(exchange.fetch_ticker(f"{coin}/USDT")["last"])
                    if a*pr>=0.3: spot+=a*pr
            except: pass
        return {"free":free,"spot":spot,"total":free+spot}
    except: return {"free":free,"spot":0,"total":free}

def get_positions():
    try:
        p=exchange.fetch_positions()
        lst=[x for x in p if float(x.get("contracts") or 0)>0]
        return len(lst), lst
    except: return 0,[]

def fetch_df(sym,tf):
    try:
        c=exchange.fetch_ohlcv(sym,timeframe=tf,limit=CONFIG["LIMIT"])
        df=pd.DataFrame(c,columns=["t","o","h","l","c","v"])
        if len(df)<200: return None
        df=df.iloc[:-1].copy()
        if df["c"].iloc[-1]<0.005: return None
        df["ema9"]=df["c"].ewm(span=9).mean()
        df["ema21"]=df["c"].ewm(span=21).mean()
        df["ema50"]=df["c"].ewm(span=50).mean()
        df["ema200"]=df["c"].ewm(span=200).mean()
        d=df["c"].diff(); g=d.clip(lower=0); l=-d.clip(upper=0)
        ag=g.ewm(alpha=1/14,adjust=False).mean(); al=l.ewm(alpha=1/14,adjust=False).mean()
        rs=ag/al.replace(0,1e-8); df["rsi"]=100-(100/(1+rs))
        df["vol_avg"]=df["v"].rolling(20).mean()
        hl=df["h"]-df["l"]; df["atr"]=hl.rolling(14).mean()
        return df.dropna()
    except: return None

def get_btc():
    try:
        df=fetch_df("BTC/USDT","15m")
        if df is None: return "neutral",0
        cur=df.iloc[-1]
        atr=cur["atr"]/cur["c"]
        if cur["c"]>cur["ema200"] and cur["ema9"]>cur["ema21"]: t="bull"
        elif cur["c"]<cur["ema200"] and cur["ema9"]<cur["ema21"]: t="bear"
        else: t="neutral"
        return t,atr
    except: return "neutral",0

def analyze(sym,btc):
    try:
        df=fetch_df(sym,"15m"); dfh=fetch_df(sym,"1h")
        if df is None or dfh is None: return None
        cur=df.iloc[-1]; prev=df.iloc[-2]; curh=dfh.iloc[-1]
        if cur["v"]<cur["vol_avg"]*1.2: return None
        atrp=cur["atr"]/cur["c"]
        if atrp>0.05 or atrp<0.0008: return None
        ls=0; ss=0
        if cur["ema9"]>cur["ema21"]>cur["ema50"] and cur["c"]>cur["ema200"]:
            if 48<cur["rsi"]<70:
                if curh["c"]<curh["ema200"] and btc=="bear": return None
                ls+=6
                if prev["ema9"]<=prev["ema21"] and cur["ema9"]>cur["ema21"]: ls+=3
                if btc=="bull": ls+=1
        if cur["ema9"]<cur["ema21"]<cur["ema50"] and cur["c"]<cur["ema200"]:
            if 28<cur["rsi"]<50:
                if curh["c"]>curh["ema200"] and btc=="bull": return None
                ss+=6
                if prev["ema9"]>=prev["ema21"] and cur["ema9"]<cur["ema21"]: ss+=3
                if btc=="bear": ss+=1
        if ls>=ss and ls>=7: return {"symbol":sym,"direction":"long","score":ls,"price":float(cur["c"]),"rsi":round(float(cur["rsi"]),1)}
        if ss>ls and ss>=7: return {"symbol":sym,"direction":"short","score":ss,"price":float(cur["c"]),"rsi":round(float(cur["rsi"]),1)}
    except: return None

def get_amount(sym,margin,price):
    try:
        m=exchange.market(sym); cs=float(m.get("contractSize") or 1); lev=CONFIG["LEV"]; raw=(margin*lev)/(price*cs)
        return float(exchange.amount_to_precision(sym,raw))
    except: return 0

def place(sym_sig):
    cnt,_=get_positions()
    if cnt>=CONFIG["MAX_POS"]: return
    base=sym_sig["symbol"].split("/")[0]; swap=base+"/USDT:USDT"
    try:
        free=get_free()
        if free<2: free=9
        margin=round(max(2,min((free*CONFIG["RISK"]/CONFIG["SL"])/CONFIG["LEV"],6)),2)
        amount=get_amount(swap,margin,sym_sig["price"])
        if amount==0: return
        try: exchange.set_leverage(CONFIG["LEV"],swap,{"mgnMode":"isolated"})
        except: pass
        side="buy" if sym_sig["direction"]=="long" else "sell"
        ps="long" if sym_sig["direction"]=="long" else "short"
        order=exchange.create_order(swap,"market",side,amount,None,{"tdMode":"isolated","posSide":ps})
        avg=float(order.get("average") or sym_sig["price"]); filled=float(order.get("filled") or amount)
        sl=avg*(1-CONFIG["SL"]) if sym_sig["direction"]=="long" else avg*(1+CONFIG["SL"])
        for _ in range(2):
            try: exchange.create_order(swap,"market","sell" if sym_sig["direction"]=="long" else "buy",filled,None,{"tdMode":"isolated","posSide":ps,"stopLoss":{"triggerPrice":sl,"orderPrice":"-1"}}); break
            except: time.sleep(1)
        state["open_trades"][swap]={"entry":avg,"direction":sym_sig["direction"],"amount":filled,"sl_moved":0}; save_state()
        log.info(f"ENTER {swap} {sym_sig['direction']} {avg}")
    except Exception as e: state["errors"].append(str(e)[-80:]); log.info(f"place err {e}")

def trailing():
    while state["running"]:
        try:
            _,plist=get_positions()
            for p in plist:
                sym=p["symbol"]; tr=state["open_trades"].get(sym)
                if not tr: continue
                entry=tr["entry"]; dir=tr["direction"]; amt=float(p.get("contracts") or tr["amount"])
                mark=float(p.get("markPrice") or entry); lev=CONFIG["LEV"]
                pnl=(entry-mark)/entry*100*lev if dir=="short" else (mark-entry)/entry*100*lev
                if pnl>=0.8 and tr["sl_moved"]<1:
                    sl=entry*1.0005 if dir=="short" else entry*0.9995
                    try: exchange.create_order(sym,"market","buy" if dir=="short" else "sell",amt,None,{"tdMode":"isolated","posSide":dir,"stopLoss":{"triggerPrice":sl,"orderPrice":"-1"}}); tr["sl_moved"]=1; save_state()
                    except: pass
                elif pnl>=1.5 and tr["sl_moved"]<2:
                    sl=entry*(1-0.007) if dir=="short" else entry*(1+0.007)
                    try: exchange.create_order(sym,"market","buy" if dir=="short" else "sell",amt,None,{"tdMode":"isolated","posSide":dir,"stopLoss":{"triggerPrice":sl,"orderPrice":"-1"}}); tr["sl_moved"]=2; save_state()
                    except: pass
                elif pnl>=2.5 and tr["sl_moved"]<3:
                    sl=entry*(1-0.015) if dir=="short" else entry*(1+0.015)
                    try: exchange.create_order(sym,"market","buy" if dir=="short" else "sell",amt,None,{"tdMode":"isolated","posSide":dir,"stopLoss":{"triggerPrice":sl,"orderPrice":"-1"}}); tr["sl_moved"]=3; save_state()
                    except: pass
            time.sleep(8)
        except: time.sleep(10)

def scan():
    while state["running"]:
        try:
            btc,vol=get_btc(); state["btc_trend"]=btc; state["btc_vol"]=round(vol*100,3)
            cnt,_=get_positions()
            if cnt>=CONFIG["MAX_POS"]:
                time.sleep(CONFIG["SCAN"]); continue
            TOP=["BTC/USDT","ETH/USDT","SOL/USDT","AVAX/USDT","LINK/USDT","FET/USDT","TAO/USDT","RENDER/USDT","SUI/USDT","ENA/USDT"]
            sigs=[]
            for s in TOP:
                sg=analyze(s,btc)
                if sg: sigs.append(sg)
                time.sleep(0.2)
            sigs.sort(key=lambda x:x["score"],reverse=True)
            state["signals"]=sigs[:5]; state["last_scan"]=datetime.now(timezone.utc).isoformat(); state["scanned"]=len(TOP); state["loop"]+=1
            if sigs: place(sigs[0])
        except Exception as e: state["errors"].append(str(e)[-60:])
        time.sleep(CONFIG["SCAN"])

HTML="""
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>V100003 TRAILING FIXED</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{background:#0a0e14;color:#e5e7eb}.card{background:#111827;border:1px solid #1f2937}</style>
</head><body class="p-3"><div class="max-w-6xl mx-auto">
<div class="flex justify-between mb-4"><h1 class="text-xl font-bold">V100003 <span class="text-emerald-400">TRAILING FIXED</span></h1><span class="w-3 h-3 bg-green-500 rounded-full animate-pulse mt-2"></span></div>
<div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">USDT</p><p id="bal" class="font-bold">--</p><p id="tot" class="text-[10px] text-gray-500"></p></div>
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">BTC</p><p id="btc" class="font-bold text-xs">--</p></div>
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">صفقات</p><p id="pos" class="font-bold">--</p></div>
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">إشارات</p><p id="sig" class="font-bold">--</p></div>
</div>
<div id="list" class="card rounded-xl p-4 text-sm"></div>
</div>
<script>
async function ld(){
 const r=await fetch('/api/status'); const d=await r.json();
 document.getElementById('bal').textContent=d.free.toFixed(4)+' USDT';
 document.getElementById('tot').textContent='Total '+d.total.toFixed(2)+' Spot '+d.spot.toFixed(2);
 document.getElementById('btc').textContent=d.btc_trend+' '+d.btc_vol+'%';
 document.getElementById('pos').textContent=d.open_count+' / 2';
 document.getElementById('sig').textContent=d.signals.length;
 document.getElementById('list').innerHTML=d.signals.length? d.signals.map(s=>`<div class="flex justify-between py-2 border-b border-gray-800"><span>${s.symbol} ${s.direction} ${s.score}/10</span><span>rsi ${s.rsi}</span></div>`).join('') : 'ينتظر 7/10 + تريلينق 0.8% / 1.5% / 2.5% نشط';
}
ld(); setInterval(ld,8000);
</script></body></html>
"""

@app.route("/")
def home(): return HTML,200,{'Content-Type':'text/html; charset=utf-8'}
@app.route("/api/status")
def api_status():
    cnt,plist=get_positions(); eq=get_equity()
    return jsonify({"free":eq["free"],"spot":eq["spot"],"total":eq["total"],"btc_trend":state["btc_trend"],"btc_vol":state["btc_vol"],"open_count":cnt,"signals":state["signals"],"positions":plist})
@app.route("/ping")
def ping(): return jsonify({"pong":True})

if __name__=="__main__":
    threading.Thread(target=scan,daemon=True).start()
    threading.Thread(target=trailing,daemon=True).start()
    log.info("V100003 TRAILING FIXED started")
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
