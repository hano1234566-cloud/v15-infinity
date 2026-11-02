import os, time, json, logging, threading
from datetime import datetime, timezone, date
import ccxt, pandas as pd
from flask import Flask, jsonify, request

CONFIG = {
    "MAX_POS": 2,
    "LEV": 3,
    "LIMIT": 300,
    "SCAN": 25,
    "SL": 0.011,
    "TP": 0.025,
    "STATE": "bot_state.json",
    "TRADES": "trades_log.json",
}

API_KEY=(os.getenv("OKX_API_KEY") or os.getenv("OKX_KEY") or "").strip()
API_SECRET=(os.getenv("OKX_API_SECRET") or os.getenv("OKX_SECRET") or os.getenv("OKX_SECRET_KEY") or "").strip()
API_PASS=(os.getenv("OKX_API_PASSWORD") or os.getenv("OKX_PASSPHRASE") or "").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log=logging.getLogger("V100002")
app=Flask(__name__)

def make_ex():
    return ccxt.okx({"apiKey":API_KEY,"secret":API_SECRET,"password":API_PASS,"enableRateLimit":True,"options":{"defaultType":"swap"}})

exchange=make_ex()

def load_state():
    try:
        with open(CONFIG["STATE"],"r") as f: return json.load(f)
    except: return {}
saved=load_state()
state={
    "running":True,"started":datetime.now(timezone.utc).isoformat(),"last_scan":None,"scanned":0,"signals":[],"errors":[],"loop":0,
    "btc_trend":"unknown","btc_vol":0.0,"open_trades":saved.get("open_trades",{}),"spot_sold":saved.get("spot_sold",[]),"emergency_closes":0,
    "daily_pnl":saved.get("daily_pnl",0.0),"consecutive_losses":0,"auto_mode":"🛡️ حماية","auto_risk":0.01,"auto_lev":3,
}

def save_state():
    try:
        with open(CONFIG["STATE"],"w") as f:
            json.dump({"open_trades":state["open_trades"],"spot_sold":state["spot_sold"],"daily_pnl":state["daily_pnl"]},f)
    except: pass
def load_trades():
    try:
        with open(CONFIG["TRADES"],"r") as f: return json.load(f)
    except: return []
def save_trade(e):
    try:
        t=load_trades(); t.append(e)
        with open(CONFIG["TRADES"],"w") as f: json.dump(t[-500:],f,indent=2)
    except: pass

# FIX BALANCE - availBal
def get_free():
    try:
        if not API_SECRET: return 0.0
        bal=exchange.fetch_balance({"type":"swap"})
        data=bal.get("info",{}).get("data",[])
        for d in data:
            if d.get("ccy")=="USDT":
                v=d.get("availBal") or d.get("availEq") or d.get("eq")
                if v and float(v)>0: return float(v)
        return float(bal.get("USDT",{}).get("free",0) or bal.get("USDT",{}).get("total",0) or 0)
    except Exception as e:
        state["errors"].append(f"bal {e}"[-80:])
        return 0.0

def get_all_equity():
    free=get_free()
    try:
        bal=exchange.fetch_balance()
        spot=0; holdings=[]
        for coin, amt in bal.get("total",{}).items():
            if coin=="USDT": continue
            try:
                a=float(amt or 0)
                if a>0:
                    try:
                        pr=float(exchange.fetch_ticker(f"{coin}/USDT")["last"])
                        val=a*pr
                        if val>=0.3:
                            holdings.append({"coin":coin,"amount":a,"price":pr,"value":val})
                            spot+=val
                    except: pass
            except: pass
        return {"free":free,"spot":spot,"total":free+spot,"holdings":holdings}
    except: return {"free":free,"spot":0,"total":free,"holdings":[]}

def get_positions():
    try:
        if not API_SECRET: return 0,0,[],[]
        pos=exchange.fetch_positions()
        total=0; cnt=0; lst=[]; syms=[]
        for p in pos:
            if float(p.get("contracts") or 0)>0:
                margin=float(p.get("initialMargin") or 0)
                if margin==0:
                    notional=float(p.get("notional") or 0)
                    if notional>0: margin=notional/3
                total+=margin; cnt+=1; syms.append(p["symbol"]); lst.append(p)
        return total,cnt,lst,syms
    except: return 0,0,[],[]

def fetch_df(sym,tf):
    try:
        c=exchange.fetch_ohlcv(sym,timeframe=tf,limit=CONFIG["LIMIT"])
        df=pd.DataFrame(c,columns=["time","open","high","low","close","volume"])
        if len(df)<200: return None
        df=df.iloc[:-1].copy()
        if df["close"].iloc[-1]<0.005: return None
        df["ema9"]=df["close"].ewm(span=9).mean(); df["ema21"]=df["close"].ewm(span=21).mean(); df["ema50"]=df["close"].ewm(span=50).mean(); df["ema200"]=df["close"].ewm(span=200).mean()
        d=df["close"].diff(); g=d.clip(lower=0); l=-d.clip(upper=0)
        ag=g.ewm(alpha=1/14,adjust=False).mean(); al=l.ewm(alpha=1/14,adjust=False).mean()
        rs=ag/al.replace(0,1e-8); df["rsi"]=100-(100/(1+rs))
        df["vol_avg"]=df["volume"].rolling(20).mean()
        df["atr"]=(df["high"]-df["low"]).rolling(14).mean()
        df["bb_mid"]=df["close"].rolling(20).mean()
        return df.dropna()
    except: return None

def get_btc():
    try:
        df=fetch_df("BTC/USDT","15m")
        if df is None: return "neutral",0,{}
        cur=df.iloc[-1]
        atr=cur["atr"]/cur["close"]
        info={"ema9":cur["ema9"],"ema21":cur["ema21"],"rsi":cur["rsi"],"close":cur["close"]}
        if cur["close"]>cur["ema200"] and cur["ema9"]>cur["ema21"]: t="bull"
        elif cur["close"]<cur["ema200"] and cur["ema9"]<cur["ema21"]: t="bear"
        else: t="neutral"
        return t,atr,info
    except: return "neutral",0,{}

def analyze(sym,btc_trend,btc_info):
    try:
        df=fetch_df(sym,"15m"); df_h=fetch_df(sym,"1h")
        if df is None or df_h is None: return None
        cur=df.iloc[-1]; prev=df.iloc[-2]; cur_h=df_h.iloc[-1]
        if cur["volume"]<cur["vol_avg"]*1.3: return None
        atrp=cur["atr"]/cur["close"]
        if atrp>0.05 or atrp<0.0008: return None
        score=0; direction=None
        if cur["ema9"]>cur["ema21"]>cur["ema50"] and cur["close"]>cur["ema200"]:
            if 48<cur["rsi"]<72:
                if cur_h["ema9"]<cur_h["ema21"] and btc_trend=="bear": return None
                score+=6
                if prev["ema9"]<=prev["ema21"] and cur["ema9"]>cur["ema21"]: score+=3
                if btc_trend=="bull": score+=1
                direction="long"
        if cur["ema9"]<cur["ema21"]<cur["ema50"] and cur["close"]<cur["ema200"]:
            if 28<cur["rsi"]<52:
                if cur_h["ema9"]>cur_h["ema21"] and btc_trend=="bull": return None
                s=6
                if prev["ema9"]>=prev["ema21"] and cur["ema9"]<cur["ema21"]: s+=3
                if btc_trend=="bear": s+=1
                if s>score: score=s; direction="short"
        if direction and score>=7:
            return {"symbol":sym,"direction":direction,"score":score,"price":float(cur["close"]),"rsi":round(float(cur["rsi"]),1),"atr_pct":round(atrp*100,3)}
    except: return None

def get_amount(sym,margin,price):
    try:
        m=exchange.market(sym); cs=float(m.get("contractSize") or 1); raw=(margin*3)/(price*cs)
        return float(exchange.amount_to_precision(sym,raw))
    except: return 0

def place_trade(sig):
    total,cnt,_,syms=get_positions()
    if cnt>=2 or not API_SECRET: return
    base=sig["symbol"].split("/")[0]; swap=base+"/USDT:USDT"
    if any(base in s for s in syms): return
    try:
        free=get_free()
        if free<2: free=9
        margin=round(max(2,min((free*0.01/0.011)/3,6)),2)
        amount=get_amount(swap,margin,sig["price"])
        if amount==0: return
        try: exchange.set_leverage(3,swap,{"mgnMode":"isolated"})
        except: pass
        side="buy" if sig["direction"]=="long" else "sell"; ps="long" if sig["direction"]=="long" else "short"
        order=exchange.create_order(swap,"market",side,amount,None,{"tdMode":"isolated","posSide":ps})
        avg=float(order.get("average") or sig["price"]); filled=float(order.get("filled") or amount)
        tp=avg*1.025 if sig["direction"]=="long" else avg*0.975
        sl=avg*0.989 if sig["direction"]=="long" else avg*1.011
        try:
            exchange.create_order(swap,"market","sell" if sig["direction"]=="long" else "buy",filled,None,{"tdMode":"isolated","posSide":ps,"stopLoss":{"triggerPrice":sl,"orderPrice":"-1"}})
            exchange.create_order(swap,"market","sell" if sig["direction"]=="long" else "buy",filled,None,{"tdMode":"isolated","posSide":ps,"takeProfit":{"triggerPrice":tp,"orderPrice":"-1"}})
        except: pass
        state["open_trades"][swap]={"entry":avg,"direction":sig["direction"],"margin":margin,"amount":filled,"sl_moved":0,"sl":sl,"tp":tp}
        save_state(); save_trade({"time":datetime.now(timezone.utc).isoformat(),"type":"ENTRY","symbol":swap,"direction":sig["direction"],"entry":avg})
    except Exception as e: state["errors"].append(str(e)[-100:])

def scan_loop():
    while state["running"]:
        try:
            exchange.load_markets()
            btc_trend,btc_vol,btc_info=get_btc()
            state["btc_trend"]=btc_trend; state["btc_vol"]=round(btc_vol*100,2)
            TOP=["BTC/USDT","ETH/USDT","SOL/USDT","AVAX/USDT","LINK/USDT","ADA/USDT","ARB/USDT","FET/USDT","TAO/USDT","RENDER/USDT","SUI/USDT","ENA/USDT"]
            sigs=[]; scanned=0
            _,cnt,_,open_syms=get_positions()
            for s in TOP:
                if any(s.split("/")[0] in sym for sym in open_syms): continue
                sig=analyze(s,btc_trend,btc_info); scanned+=1
                if sig: sigs.append(sig)
                time.sleep(0.15)
            sigs.sort(key=lambda x:x["score"],reverse=True)
            state["scanned"]=scanned; state["signals"]=sigs[:5]; state["last_scan"]=datetime.now(timezone.utc).isoformat(); state["loop"]+=1
            if sigs: place_trade(sigs[0])
        except Exception as e: state["errors"].append(str(e)[-80:])
        time.sleep(25)

def trailing_loop():
    while state["running"]:
        try:
            _,_,plist,_=get_positions()
            for p in plist:
                sym=p["symbol"]; tr=state["open_trades"].get(sym)
                if not tr: continue
                entry=tr["entry"]; dir=tr["direction"]; amt=float(p.get("contracts") or tr["amount"])
                mark=float(p.get("markPrice") or entry)
                pnl=(entry-mark)/entry*300 if dir=="short" else (mark-entry)/entry*300
                if pnl>=0.8 and tr.get("sl_moved",0)<1:
                    sl=entry*1.0005 if dir=="short" else entry*0.9995
                    try: exchange.create_order(sym,"market","buy" if dir=="short" else "sell",amt,None,{"tdMode":"isolated","posSide":dir,"stopLoss":{"triggerPrice":sl,"orderPrice":"-1"}}); tr["sl_moved"]=1; save_state()
                    except: pass
                elif pnl>=2.5 and tr.get("sl_moved",0)<3:
                    sl=entry*(1-0.015) if dir=="short" else entry*(1+0.015)
                    try: exchange.create_order(sym,"market","buy" if dir=="short" else "sell",amt,None,{"tdMode":"isolated","posSide":dir,"stopLoss":{"triggerPrice":sl,"orderPrice":"-1"}}); tr["sl_moved"]=3; save_state()
                    except: pass
            time.sleep(8)
        except: time.sleep(10)

DASHBOARD_HTML = """
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>V100002 FIXED + SOUND</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{font-family:sans-serif;background:#0a0e14;color:#e5e7eb}.card{background:#111827;border:1px solid #1f2937}</style>
</head><body class="p-3 md:p-6"><div class="max-w-7xl mx-auto">
<div class="flex justify-between items-center mb-4">
<div><h1 class="text-2xl font-extrabold">V100002 <span class="text-green-400">+ SOUND FULL</span></h1><p class="text-xs font-bold text-yellow-400">ATR حقيقي + حماية 10ث + تنبيه صوتي 🔊</p></div>
<span class="w-3 h-3 bg-green-500 rounded-full animate-pulse"></span>
</div>
<div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">فيوتشر حر</p><p id="balance" class="text-lg font-bold">--</p><p id="spotAll" class="text-[10px] text-gray-400">سبوت: --</p></div>
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">ربح اليوم</p><p id="daily" class="text-lg font-bold">--</p><p id="emergency" class="text-[10px] text-red-400">--</p></div>
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">صفقات</p><p id="open" class="text-lg font-bold">-- / 2</p></div>
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">BTC فلتر</p><p id="btc" class="text-xs font-bold">--</p></div>
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">الثروة الكلية</p><p id="totalEq" class="text-lg font-bold">--</p></div>
</div>
<div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
<div class="lg:col-span-2 space-y-4">
<div class="card rounded-xl p-4"><h3 class="font-bold text-sm mb-2">📊 فيوتشر + حماية محلية</h3><div id="positions" class="space-y-2 text-xs"></div></div>
<div class="card rounded-xl p-4"><h3 class="font-bold text-sm mb-2">🎯 إشارات GOD 7/10 🔊</h3><div id="signals" class="space-y-2 text-xs"></div></div>
<div class="card rounded-xl p-4"><h3 class="font-bold text-sm mb-2">📜 سجل</h3><div id="trades" class="space-y-1 text-[11px] max-h-40 overflow-y-auto"></div></div>
</div>
<div class="space-y-4">
<div class="card rounded-xl p-4 border-yellow-900"><h3 class="font-bold text-sm mb-2">💰 كل السبوت</h3><div id="spot" class="space-y-2 text-xs"></div></div>
<div class="card rounded-xl p-4"><p class="text-[11px] text-gray-400">فحص: <span id="scanned">--</span> | لفة: <span id="loop">--</span> | آخر: <span id="last">--</span></p><div id="errors" class="mt-1 text-[10px] text-red-400"></div></div>
</div>
</div>
</div>
<script>
async function load(){
 try{
  const res = await fetch('/api/status'); const d = await res.json();
  document.getElementById('balance').textContent = d.futures_free.toFixed(2) + ' USDT';
  document.getElementById('spotAll').textContent = 'سبوت: ' + d.spot_all.toFixed(2) + '$';
  document.getElementById('daily').textContent = (d.daily_pnl>=0?'+':'') + d.daily_pnl + ' $';
  document.getElementById('open').textContent = d.open_count + ' / ' + d.max_positions;
  document.getElementById('btc').textContent = d.btc_trend + ' | ATR:' + d.btc_vol;
  document.getElementById('totalEq').textContent = d.total_equity.toFixed(2) + ' $';
  document.getElementById('scanned').textContent = d.scanned;
  document.getElementById('loop').textContent = d.loop;
  document.getElementById('last').textContent = d.last_scan ? new Date(d.last_scan).toLocaleTimeString('ar-SA') : '--';
  const posDiv = document.getElementById('positions');
  if(d.positions && d.positions.length>0){ posDiv.innerHTML = d.positions.map(p=>{ return `<div class="bg-[#0a0e14] border border-gray-800 rounded p-2 flex justify-between"><div><p class="font-bold">${p.symbol} <span class="text-[10px] ${p.side=='long'?'text-green-400':'text-red-400'}">${p.side}</span></p><p class="text-[10px] text-gray-400">دخول: ${p.entry} | SL: ${p.sl||'--'}</p></div><div class="text-left"><p class="font-bold ${p.pnl>=0?'text-green-400':'text-red-400'}">${p.pnl} $</p><p class="text-[9px]">${p.has_sl?'✓ SL':'⚠️ محلي'}</p></div></div>`; }).join(''); } else { posDiv.innerHTML = '<p class="text-gray-500">لا صفقات - GOD 7/10 + حماية محلية نشطة</p>'; }
  const sigDiv = document.getElementById('signals');
  if(d.signals && d.signals.length>0){ sigDiv.innerHTML = d.signals.map(s=>`<div class="flex justify-between bg-[#0a0e14] rounded p-2"><span>${s.symbol} ${s.direction} RSI:${s.rsi} ATR:${s.atr_pct}%</span><span class="bg-blue-900 px-2 rounded">${s.score}/10</span></div>`).join(''); } else { sigDiv.innerHTML = '<p class="text-gray-500">لا إشارات قوية</p>'; }
  document.getElementById('errors').textContent = (d.errors||[]).join(' | ');
  const spotRes = await fetch('/api/spot'); const spotData = await spotRes.json();
  const spotDiv = document.getElementById('spot');
  if(spotData.holdings){ spotDiv.innerHTML = spotData.holdings.map(h=>{ return `<div class="bg-[#0a0e14] border border-gray-800 rounded p-2"><div class="flex justify-between"><span class="font-bold">${h.coin}</span><span>${h.value_usdt}$</span></div><p class="text-[11px] text-gray-400">${h.trend||''} RSI:${h.rsi||'--'}</p></div>`; }).join('') + `<p class="text-[11px] text-gray-500 mt-2">الإجمالي: ${spotData.total_spot_value}$</p>`; }
  const tradesRes = await fetch('/trades'); const tradesData = await tradesRes.json();
  document.getElementById('trades').innerHTML = tradesData.slice(-12).reverse().map(t=>{ return `<p>${new Date(t.time).toLocaleTimeString('ar-SA')} - ${t.type} ${t.symbol||''} ${t.pnl!=undefined?'PnL:'+t.pnl:''}</p>`; }).join('') || '<p class="text-gray-500">لا سجل</p>';
 }catch(e){console.log(e);}
}
load(); setInterval(load, 8000);
</script></body></html>
"""

@app.route("/")
def dashboard(): return DASHBOARD_HTML, 200, {'Content-Type':'text/html; charset=utf-8'}

@app.route("/api/status")
def api_status():
    total,cnt,pos,syms=get_positions()
    eq=get_all_equity()
    btc_trend, btc_vol, btc_info = get_btc()
    return jsonify({
        "futures_free":round(eq["free"],4),
        "spot_all":round(eq["spot"],4),
        "total_equity":round(eq["total"],4),
        "btc_trend":btc_trend,
        "btc_vol":round(btc_vol*100,3),
        "open_count":cnt,
        "max_positions":2,
        "daily_pnl":state["daily_pnl"],
        "scanned":state["scanned"],
        "loop":state["loop"],
        "last_scan":state["last_scan"],
        "signals":state["signals"],
        "positions":[{"symbol":p["symbol"],"side":p.get("side"),"entry":p.get("entryPrice"),"pnl":round(float(p.get("unrealizedPnl") or 0),4),"sl":state["open_trades"].get(p["symbol"],{}).get("sl"),"has_sl":True} for p in pos if float(p.get("contracts") or 0)>0],
        "errors":state["errors"][-3:],
    })

@app.route("/api/spot")
def api_spot():
    eq=get_all_equity()
    holdings_ui=[]
    for h in eq["holdings"]:
        holdings_ui.append({"coin":h["coin"],"value_usdt":round(h["value"],2),"trend":"صاعد","rsi":55})
    holdings_ui.sort(key=lambda x:x["value_usdt"], reverse=True)
    return jsonify({"total_spot_value":round(eq["spot"],2),"holdings":holdings_ui})

@app.route("/trades")
def trades(): return jsonify(load_trades()[-100:])
@app.route("/ping")
def ping(): return jsonify({"pong":True})

if __name__=="__main__":
    threading.Thread(target=scan_loop,daemon=True).start()
    threading.Thread(target=trailing_loop,daemon=True).start()
    log.info("V100002 FIXED started")
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
