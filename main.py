import os, re, time, json, logging, threading
from datetime import datetime, timezone
import ccxt, pandas as pd
from flask import Flask, jsonify

def clean(s): return re.sub(r'\s+','',str(s).strip()) if s else ""
def get_keys():
    k=clean(os.getenv("OKX_API_KEY") or os.getenv("OKX_KEY") or "")
    s=clean(os.getenv("OKX_API_SECRET") or os.getenv("OKX_SECRET") or "")
    p=(os.getenv("OKX_API_PASSWORD") or os.getenv("OKX_PASSPHRASE") or "").strip()
    return k,s,p

API_KEY,API_SECRET,API_PASS=get_keys()
app=Flask(__name__)
def make_ex():
    k,s,p=get_keys()
    return ccxt.okx({"apiKey":k,"secret":s,"password":p,"enableRateLimit":True,"options":{"defaultType":"swap"}})
exchange=make_ex()
state={"signals":[],"loop":0,"scanned":0,"last_scan":None,"btc_trend":"neutral","btc_vol":0,"errors":[],"trades_log":[],"last_trades":[]}

TRADES_FILE="trades_log.json"
def log_trade(d):
    try:
        arr=[]
        try:
            with open(TRADES_FILE,"r") as f: arr=json.load(f)
        except: arr=[]
        arr.append(d)
        with open(TRADES_FILE,"w") as f: json.dump(arr[-100:],f)
        state["trades_log"]=arr[-20:]
    except: pass

def get_equity():
    k,s,p=get_keys()
    free=0;spot=0;holdings=[]
    try:
        if not s or len(s)<15: return {"free":0,"spot":0,"total":0,"holdings":holdings}
        bal=exchange.fetch_balance({"type":"swap"})
        for d in bal.get("info",{}).get("data",[]):
            if d.get("ccy")=="USDT":
                free=float(d.get("availBal") or d.get("eq") or 0); break
        ball=exchange.fetch_balance()
        for coin,amt in ball.get("total",{}).items():
            if coin=="USDT": continue
            a=float(amt or 0)
            if a>0:
                try:
                    pr=float(exchange.fetch_ticker(f"{coin}/USDT")["last"]); val=a*pr
                    if val>=0.3: holdings.append({"coin":coin,"amount":a,"value":val}); spot+=val
                except: pass
    except Exception as e: state["errors"].append(str(e)[-60:])
    holdings.sort(key=lambda x:x["value"],reverse=True)
    return {"free":free,"spot":spot,"total":free+spot,"holdings":holdings}

def get_positions():
    try:
        k,s,p=get_keys()
        if not s or len(s)<15: return 0,[],[]
        exchange.load_markets()
        pos=exchange.fetch_positions()
        lst=[]
        for pp in pos:
            c=float(pp.get("contracts") or 0)
            if c>0:
                entry=float(pp.get("entryPrice") or 0)
                mark=float(pp.get("markPrice") or entry)
                if mark==0:
                    try: mark=float(exchange.fetch_ticker(pp["symbol"])["last"])
                    except: pass
                side=pp.get("side"); pnl=float(pp.get("unrealizedPnl") or 0)
                lev=float(pp.get("leverage") or 3)
                pct=0
                if entry>0:
                    if side=="long": pct=(mark-entry)/entry*100*lev
                    else: pct=(entry-mark)/entry*100*lev
                lst.append({"symbol":pp["symbol"],"side":side,"entry":entry,"mark":mark,"contracts":c,"leverage":lev,"pnl":round(pnl,4),"pnl_pct":round(pct,2),"is_profit":pnl>=0,"margin":float(pp.get("initialMargin") or 0)})
        return len(lst),lst,[x["symbol"] for x in lst]
    except: return 0,[],[]

def fetch_df(sym,tf="15m"):
    try:
        c=exchange.fetch_ohlcv(sym,timeframe=tf,limit=200)
        df=pd.DataFrame(c,columns=["t","o","h","l","cl","v"])
        df=df.iloc[:-1].copy()
        if df["cl"].iloc[-1]<0.005: return None
        df["ema9"]=df["cl"].ewm(span=9).mean(); df["ema21"]=df["cl"].ewm(span=21).mean(); df["ema50"]=df["cl"].ewm(span=50).mean(); df["ema200"]=df["cl"].ewm(span=200).mean()
        d=df["cl"].diff(); g=d.clip(lower=0); l=-d.clip(upper=0)
        ag=g.ewm(alpha=1/14,adjust=False).mean(); al=l.ewm(alpha=1/14,adjust=False).mean()
        rs=ag/al.replace(0,1e-8); df["rsi"]=100-(100/(1+rs))
        df["vol_avg"]=df["v"].rolling(20).mean()
        return df.dropna()
    except: return None

# فتح صفقة حقيقية
def open_trade(symbol,direction,score,rsi):
    try:
        k,s,p=get_keys()
        if not s: return False
        eq=get_equity()
        free=eq["free"]
        if free < 5:
            state["errors"].append(f"رصيد قليل {free} ما يفتح")
            return False
        cnt,_,_ = get_positions()
        if cnt >= 2:
            return False
        # حجم الصفقة: 15% من الرصيد
        amount_usdt = max(5, min(free*0.15, 20))  # بين 5 و 20 USDT
        exchange.load_markets()
        # ضبط رافعة 3x
        try:
            exchange.set_leverage(3,symbol)
        except: pass
        # سعر السوق
        ticker=exchange.fetch_ticker(symbol)
        price=float(ticker["last"])
        # يحسب العقود
        try:
            # OKX swap contract size
            amount = amount_usdt / price
            # نفتح market
            order = exchange.create_market_order(symbol, "buy" if direction=="long" else "sell", amount)
            log_trade({"time":datetime.now(timezone.utc).isoformat(),"type":"OPEN","symbol":symbol,"direction":direction,"price":price,"score":score,"rsi":rsi,"amount_usdt":amount_usdt,"order":str(order.get("id",""))})
            state["last_trades"].append(f"فتح {symbol} {direction} {score}/10")
            return True
        except Exception as e:
            state["errors"].append(f"open {symbol} {str(e)[:80]}")
            return False
    except Exception as e:
        state["errors"].append(str(e)[-80:])
        return False

def scan_and_trade_loop():
    while True:
        try:
            df_btc=fetch_df("BTC/USDT","15m")
            if df_btc is not None:
                cur=df_btc.iloc[-1]
                state["btc_trend"]="bull" if cur["cl"]>cur["ema200"] and cur["ema9"]>cur["ema21"] else "bear" if cur["cl"]<cur["ema200"] else "neutral"
                state["btc_vol"]=round(float((df_btc["h"].iloc[-1]-df_btc["l"].iloc[-1])/cur["cl"]*100),2)
                # اذا BTC هابط قوي لا يفتح لونج
                btc_bear = state["btc_trend"]=="bear"
            else:
                btc_bear=False

            TOP=["BTC/USDT","ETH/USDT","SOL/USDT","AVAX/USDT","LINK/USDT","ARB/USDT","FET/USDT","TAO/USDT","RENDER/USDT","SUI/USDT","ENA/USDT"]
            sigs=[]
            cnt,_,open_syms=get_positions()
            scanned=0
            for sym in TOP:
                if any(sym.split("/")[0] in s for s in open_syms): continue
                df=fetch_df(sym,"15m")
                if df is None: continue
                cur=df.iloc[-1]; prev=df.iloc[-2]
                if cur["v"] < cur["vol_avg"]*1.2: continue
                # LONG
                if cur["ema9"]>cur["ema21"]>cur["ema50"] and cur["cl"]>cur["ema200"] and 48<cur["rsi"]<70 and prev["ema9"]<=prev["ema21"]:
                    if not btc_bear or sym=="BTC/USDT":
                        sigs.append({"symbol":sym,"direction":"long","score":8,"price":float(cur["cl"]),"rsi":round(float(cur["rsi"]),1)})
                        if cnt < 2:
                            open_trade(sym,"long",8,round(float(cur["rsi"]),1))
                # SHORT
                elif cur["ema9"]<cur["ema21"]<cur["ema50"] and cur["cl"]<cur["ema200"] and 28<cur["rsi"]<50 and prev["ema9"]>=prev["ema21"]:
                    sigs.append({"symbol":sym,"direction":"short","score":8,"price":float(cur["cl"]),"rsi":round(float(cur["rsi"]),1)})
                    if cnt < 2:
                        open_trade(sym,"short",8,round(float(cur["rsi"]),1))
                scanned+=1
                time.sleep(0.2)
            sigs.sort(key=lambda x:x["score"],reverse=True)
            state["signals"]=sigs[:5]; state["scanned"]=scanned; state["loop"]+=1; state["last_scan"]=datetime.now(timezone.utc).isoformat()
        except Exception as e:
            state["errors"].append(str(e)[-80:])
        time.sleep(15)

DASH="""
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>V15 AUTO</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{background:#0a0e14;color:#e5e7eb}.card{background:#111827;border:1px solid #1f2937;border-radius:14px}.live{width:8px;height:8px;background:#22c55e;border-radius:50%;display:inline-block;animation:pulse 1s infinite}@keyframes pulse{0%{opacity:1}50%{opacity:0.2}100%{opacity:1}}.num{transition:all 0.4s}</style>
</head><body class="p-3"><div class="max-w-6xl mx-auto">
<div class="flex justify-between mb-3"><h1 class="text-xl font-black">V15 <span class="text-emerald-400">AUTO يلحق الصفقات</span> <span class="live"></span></h1><p class="text-[10px] text-gray-400" id="last">--</p></div>
<div class="bg-emerald-900/30 border border-emerald-600 rounded-xl p-2 mb-3 text-[11px]">🤖 البوت يشتغل لحاله: يشوف إشارة GOD 7/10 ويفتح الصفقة تلقائيا (15% من الرصيد - رافعة 3x - حد 2 صفقات) - لا تحتاج تفتح يدوي</div>
<div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
<div class="card p-3"><p class="text-[10px] text-gray-400">فيوتشر حر</p><p id="free" class="font-bold text-lg num">--</p></div>
<div class="card p-3"><p class="text-[10px] text-gray-400">ربح الصفقات LIVE</p><p id="tpnl" class="font-bold text-lg num">--</p></div>
<div class="card p-3"><p class="text-[10px] text-gray-400">صفقات مفتوحة</p><p id="cnt" class="font-bold text-lg num">--</p></div>
<div class="card p-3"><p class="text-[10px] text-gray-400">الثروة</p><p id="total" class="font-bold text-lg num">--</p><p id="spotSum" class="text-[9px] text-gray-500"></p></div>
</div>
<div class="card p-4 mb-3 border-2 border-emerald-500/30"><h3 class="font-bold text-base mb-3">📊 صفقاتي الحالية - الربح / الخسارة مباشر <span class="live"></span></h3><div id="pos" class="space-y-3"></div></div>
<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
<div class="card p-4"><h3 class="font-bold text-sm mb-2">🎯 إشارات GOD 7/10 (يفتح تلقائيا)</h3><div id="sigs" class="text-xs space-y-1"></div><div id="lastTrades" class="mt-3 text-[11px] text-emerald-400"></div></div>
<div class="card p-4"><h3 class="font-bold text-sm mb-2">💰 السبوت + السجل</h3><div id="spot" class="text-xs space-y-1"></div><div id="log" class="mt-3 text-[10px] text-gray-400 max-h-32 overflow-y-auto"></div><div id="errs" class="mt-2 text-[10px] text-red-400"></div></div>
</div>
</div>
<script>
async function load(){
 try{
  const r=await fetch('/api/full'); const d=await r.json();
  document.getElementById('free').textContent=d.free.toFixed(2)+' USDT';
  document.getElementById('total').textContent=d.total.toFixed(2)+' $';
  document.getElementById('spotSum').textContent='سبوت: '+d.spot.toFixed(2)+'$';
  document.getElementById('cnt').textContent=d.count+' / 2';
  document.getElementById('last').textContent=d.last_scan?new Date(d.last_scan).toLocaleTimeString('ar-SA')+' - يفحص كل 15 ثانية':'--';
  const tpnl=document.getElementById('tpnl'); tpnl.textContent=(d.total_pnl>=0?'+':'')+d.total_pnl.toFixed(4)+' $'; tpnl.className='font-bold text-lg num '+(d.total_pnl>=0?'text-green-400':'text-red-400');
  const posDiv=document.getElementById('pos');
  if(d.positions.length==0){posDiv.innerHTML='<div class="bg-[#0a0e14] rounded-xl p-6 text-center"><p class="text-gray-400">📭 لا صفقات الآن - البوت يبحث عن إشارة 7/10 ويفتح لحاله</p><p class="text-[11px] text-gray-500 mt-2">رصيدك '+d.free.toFixed(2)+' جاهز - أول ما تطلع إشارة قوية بيفتح (15% رافعة 3x)</p></div>';}
  else{
    posDiv.innerHTML=d.positions.map(p=>{
      const up=p.is_profit; const bg=up?'bg-green-500/10 border-green-500/60':'bg-red-500/10 border-red-500/60'; const col=up?'text-green-400':'text-red-400';
      return `<div class="border-2 ${bg} rounded-xl p-4"><div class="flex justify-between"><div><p class="font-black">${p.symbol.replace(':USDT','')} <span class="text-[11px] px-3 py-1 rounded-full ${p.side=='long'?'bg-green-600':'bg-red-600'} text-white">${p.side} x${p.leverage}</span></p><p class="text-[12px] mt-1">دخول ${p.entry.toFixed(4)} | حالي <span class="text-white font-black num">${p.mark.toFixed(4)}</span></p><p class="text-[10px] text-gray-500">عقود ${p.contracts} | مارجن ${p.margin.toFixed(2)}$</p></div><div class="text-left"><p class="font-black text-xl num ${col}">${p.pnl>=0?'+':''}${p.pnl.toFixed(4)}$</p><p class="text-sm num ${col}">${p.pnl_pct>=0?'+':''}${p.pnl_pct.toFixed(2)}% ${up?'🟢 ربحانة':'🔴 خسرانة'}</p></div></div><div class="mt-3 h-2 bg-gray-800 rounded-full overflow-hidden"><div class="h-full ${up?'bg-green-500':'bg-red-500'}" style="width:${Math.min(Math.abs(p.pnl_pct)*5,100)}%"></div></div></div>`;
    }).join('');
  }
  document.getElementById('sigs').innerHTML=d.signals.length?d.signals.map(s=>`<div class="flex justify-between bg-[#0a0e14] rounded-lg p-2.5"><span class="font-bold">${s.symbol} ${s.direction} RSI:${s.rsi}</span><span class="bg-emerald-900 px-2 rounded">GOD ${s.score}/10</span></div>`).join(''):'<p class="text-gray-500 text-[11px]">لا إشارات قوية الآن</p>';
  document.getElementById('spot').innerHTML=d.holdings.length?d.holdings.map(h=>`<div class="flex justify-between bg-[#0a0e14] rounded p-2"><span>${h.coin}</span><span class="text-green-400">${h.value.toFixed(2)}$</span></div>`).join(''):'لا سبوت';
  document.getElementById('log').innerHTML=(d.trades_log||[]).slice(-8).reverse().map(t=>`<p>${t.time?new Date(t.time).toLocaleTimeString('ar-SA'):''} ${t.type} ${t.symbol} ${t.direction||''} ${t.price||''}</p>`).join('')||'لا سجل';
  document.getElementById('lastTrades').innerHTML=(d.last_trades||[]).slice(-3).join('<br>');
  document.getElementById('errs').textContent=(d.errors||[]).slice(-2).join(' | ');
 }catch(e){}
}
load(); setInterval(load,2000);
</script></body></html>
"""
@app.route("/")
def home(): return DASH,200,{'Content-Type':'text/html; charset=utf-8'}
@app.route("/api/full")
def api_full():
    eq=get_equity(); cnt,positions,_=get_positions(); total=sum([p["pnl"] for p in positions])
    try:
        with open(TRADES_FILE,"r") as f: logs=json.load(f)
    except: logs=[]
    return jsonify({"free":eq["free"],"spot":eq["spot"],"total":eq["total"],"holdings":eq["holdings"],"count":cnt,"positions":positions,"total_pnl":round(total,4),"btc_trend":state["btc_trend"],"btc_vol":state["btc_vol"],"signals":state["signals"],"loop":state["loop"],"last_scan":state["last_scan"],"trades_log":logs[-20:],"last_trades":state["last_trades"][-5:],"errors":state["errors"][-3:]})
@app.route("/ping")
def ping(): return jsonify({"ok":True})
if __name__=="__main__":
    threading.Thread(target=scan_and_trade_loop,daemon=True).start()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
