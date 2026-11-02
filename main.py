import os, time, json, logging, threading
from datetime import datetime, timezone
import ccxt, pandas as pd
from flask import Flask, jsonify

API_KEY=(os.getenv("OKX_API_KEY") or os.getenv("OKX_KEY") or "").strip()
API_SECRET=(os.getenv("OKX_API_SECRET") or os.getenv("OKX_SECRET") or "").strip()
API_PASS=(os.getenv("OKX_API_PASSWORD") or os.getenv("OKX_PASSPHRASE") or "").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log=logging.getLogger("FULL")
app=Flask(__name__)

def make_ex(): return ccxt.okx({"apiKey":API_KEY,"secret":API_SECRET,"password":API_PASS,"enableRateLimit":True,"options":{"defaultType":"swap"}})
exchange=make_ex()

state={"signals":[],"loop":0,"scanned":0,"last_scan":None,"btc_trend":"neutral","btc_vol":0,"errors":[],"trades_log":[]}

def load_trades():
    try:
        with open("trades_log.json","r") as f: return json.load(f)
    except: return []

# REAL BALANCE - availBal
def get_equity():
    free=0; spot=0; holdings=[]
    try:
        if not API_SECRET or len(API_SECRET)<20:
            state["errors"]=["المفاتيح ناقصة - حط OKX_API_KEY/SECRET/PASSWORD في Render"]
            return {"free":0,"spot":0,"total":0,"holdings":[]}
        bal_swap=exchange.fetch_balance({"type":"swap"})
        data=bal_swap.get("info",{}).get("data",[])
        for d in data:
            if d.get("ccy")=="USDT":
                free=float(d.get("availBal") or d.get("eq") or 0)
                break
        # spot
        bal=exchange.fetch_balance()
        for coin,amt in bal.get("total",{}).items():
            if coin=="USDT": continue
            try:
                a=float(amt or 0)
                if a>0:
                    try:
                        pr=float(exchange.fetch_ticker(f"{coin}/USDT")["last"])
                        val=a*pr
                        if val>=0.3:
                            holdings.append({"coin":coin,"amount":a,"value":val})
                            spot+=val
                    except: pass
            except: pass
    except Exception as e:
        state["errors"].append(str(e)[-100:])
    holdings.sort(key=lambda x:x["value"],reverse=True)
    return {"free":free,"spot":spot,"total":free+spot,"holdings":holdings}

# REAL POSITIONS - LIVE PnL
def get_positions():
    try:
        if not API_SECRET or len(API_SECRET)<20: return 0,[],[]
        exchange.load_markets()
        pos=exchange.fetch_positions()
        lst=[]
        for p in pos:
            c=float(p.get("contracts") or 0)
            if c>0:
                entry=float(p.get("entryPrice") or 0)
                mark=float(p.get("markPrice") or entry)
                if mark==0 or abs(mark-entry)/entry>0.2:
                    try: mark=float(exchange.fetch_ticker(p["symbol"])["last"])
                    except: pass
                side=p.get("side")
                pnl=float(p.get("unrealizedPnl") or 0)
                lev=float(p.get("leverage") or 3)
                pct=0
                if entry>0:
                    if side=="long": pct=(mark-entry)/entry*100*lev
                    else: pct=(entry-mark)/entry*100*lev
                lst.append({"symbol":p["symbol"],"side":side,"entry":entry,"mark":mark,"contracts":c,"leverage":lev,"pnl":round(pnl,4),"pnl_pct":round(pct,2),"is_profit":pnl>=0,"margin":float(p.get("initialMargin") or 0)})
        return len(lst),lst,[p["symbol"] for p in lst]
    except Exception as e:
        state["errors"].append(f"pos {str(e)[:80]}")
        return 0,[],[]

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

def scan_loop():
    while True:
        try:
            # BTC filter
            df_btc=fetch_df("BTC/USDT","15m")
            if df_btc is not None:
                cur=df_btc.iloc[-1]
                state["btc_trend"]="bull" if cur["cl"]>cur["ema200"] and cur["ema9"]>cur["ema21"] else "bear" if cur["cl"]<cur["ema200"] else "neutral"
                state["btc_vol"]=round(float((df_btc["h"].iloc[-1]-df_btc["l"].iloc[-1])/cur["cl"]*100),2)
            TOP=["BTC/USDT","ETH/USDT","SOL/USDT","AVAX/USDT","LINK/USDT","ARB/USDT","FET/USDT","TAO/USDT","RENDER/USDT","SUI/USDT","ENA/USDT"]
            sigs=[]; scanned=0
            _,_,open_syms=get_positions()
            for s in TOP:
                if any(s.split("/")[0] in sym for sym in open_syms): continue
                df=fetch_df(s,"15m")
                if df is None: continue
                cur=df.iloc[-1]; prev=df.iloc[-2]
                if cur["v"]<cur["vol_avg"]*1.2: continue
                if cur["ema9"]>cur["ema21"]>cur["ema50"] and cur["cl"]>cur["ema200"] and 48<cur["rsi"]<70:
                    if prev["ema9"]<=prev["ema21"]:
                        sigs.append({"symbol":s,"direction":"long","score":8,"price":float(cur["cl"]),"rsi":round(float(cur["rsi"]),1)})
                elif cur["ema9"]<cur["ema21"]<cur["ema50"] and cur["cl"]<cur["ema200"] and 28<cur["rsi"]<50:
                    if prev["ema9"]>=prev["ema21"]:
                        sigs.append({"symbol":s,"direction":"short","score":8,"price":float(cur["cl"]),"rsi":round(float(cur["rsi"]),1)})
                scanned+=1; time.sleep(0.1)
            sigs.sort(key=lambda x:x["score"],reverse=True)
            state["signals"]=sigs[:5]; state["scanned"]=scanned; state["last_scan"]=datetime.now(timezone.utc).isoformat(); state["loop"]+=1
        except Exception as e:
            state["errors"].append(str(e)[-80:])
        time.sleep(20)

DASHBOARD="""
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>V15 FULL REAL</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{background:#0a0e14;color:#e5e7eb;font-family:system-ui}.card{background:#111827;border:1px solid #1f2937;border-radius:14px}.live{width:8px;height:8px;background:#22c55e;border-radius:50%;display:inline-block;animation:pulse 1s infinite}@keyframes pulse{0%{opacity:1}50%{opacity:0.2}100%{opacity:1}}.num{transition:all 0.3s ease}</style>
</head><body class="p-3 md:p-6"><div class="max-w-7xl mx-auto">
<div class="flex justify-between items-center mb-4">
<div><h1 class="text-xl font-extrabold">V15 FULL <span class="text-green-400">REAL</span> <span class="live"></span></h1><p class="text-[11px] text-yellow-400">كل شي قدامك - حقيقي من OKX - تحديث كل 2 ثانية</p></div>
<p class="text-[10px] text-gray-400" id="last">--</p>
</div>

<div id="err" class="hidden bg-red-900/30 border border-red-600 rounded-xl p-3 mb-4 text-xs"></div>

<div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
<div class="card p-3"><p class="text-[10px] text-gray-400">فيوتشر حر</p><p id="free" class="font-bold text-lg num">--</p><p class="text-[9px] text-gray-500">availBal</p></div>
<div class="card p-3"><p class="text-[10px] text-gray-400">ربح الصفقات الآن</p><p id="tpnl" class="font-bold text-lg num">--</p><p class="text-[9px] text-gray-500">LIVE من OKX</p></div>
<div class="card p-3"><p class="text-[10px] text-gray-400">صفقات</p><p id="cnt" class="font-bold text-lg num">-- / 2</p></div>
<div class="card p-3"><p class="text-[10px] text-gray-400">BTC فلتر</p><p id="btc" class="font-bold text-sm">--</p></div>
<div class="card p-3"><p class="text-[10px] text-gray-400">الثروة الكلية</p><p id="total" class="font-bold text-lg num">--</p><p id="spotSum" class="text-[9px] text-gray-500">سبوت: --</p></div>
</div>

<div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
<div class="lg:col-span-2 space-y-4">
<div class="card p-4"><h3 class="font-bold text-sm mb-3">📊 صفقاتي الحالية - ربح / خسارة مباشر <span class="live"></span></h3><div id="pos" class="space-y-3"></div></div>
<div class="card p-4"><h3 class="font-bold text-sm mb-2">🎯 إشارات GOD 7/10</h3><div id="sigs" class="space-y-2 text-xs"></div></div>
<div class="card p-4"><h3 class="font-bold text-sm mb-2">📜 سجل</h3><div id="trades" class="space-y-1 text-[11px] max-h-32 overflow-y-auto"></div></div>
</div>
<div class="space-y-4">
<div class="card p-4"><h3 class="font-bold text-sm mb-2">💰 كل السبوت</h3><div id="spot" class="space-y-2 text-xs"></div></div>
<div class="card p-4 text-[11px] text-gray-400"><p>فحص: <span id="scanned">--</span> | لفة: <span id="loop">--</span></p><div id="errs" class="mt-2 text-[10px] text-red-400"></div></div>
</div>
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
  document.getElementById('btc').textContent=d.btc_trend+' | '+d.btc_vol+'%';
  document.getElementById('scanned').textContent=d.scanned;
  document.getElementById('loop').textContent=d.loop;
  document.getElementById('last').textContent=d.last_scan?new Date(d.last_scan).toLocaleTimeString('ar-SA')+' تحديث كل 2 ثانية':'--';
  
  const errDiv=document.getElementById('err');
  if(d.main_error){errDiv.classList.remove('hidden'); errDiv.textContent='⚠️ '+d.main_error;}
  else{errDiv.classList.add('hidden');}
  
  const tpnl=document.getElementById('tpnl');
  tpnl.textContent=(d.total_pnl>=0?'+':'')+d.total_pnl.toFixed(4)+' $';
  tpnl.className='font-bold text-lg num '+(d.total_pnl>=0?'text-green-400':'text-red-400');
  
  const posDiv=document.getElementById('pos');
  if(d.positions.length==0){
    posDiv.innerHTML='<p class="text-gray-500 text-sm">لا صفقات مفتوحة في OKX - ينتظر إشارة 7/10</p>';
  } else {
    posDiv.innerHTML=d.positions.map(p=>{
      const up=p.is_profit;
      const bg=up?'bg-green-500/10 border-green-500/50':'bg-red-500/10 border-red-500/50';
      const col=up?'text-green-400':'text-red-400';
      return `<div class="border ${bg} rounded-xl p-3">
        <div class="flex justify-between">
          <div>
            <p class="font-bold">${p.symbol.replace(':USDT','')} <span class="text-[10px] px-2 py-0.5 rounded ${p.side=='long'?'bg-green-600':'bg-red-600'}">${p.side=='long'?'LONG ↑':'SHORT ↓'} x${p.leverage}</span></p>
            <p class="text-[11px] text-gray-400 mt-1">دخول: <span class="text-white">${p.entry.toFixed(4)}</span> | حالي: <span class="text-white font-bold num">${p.mark.toFixed(4)}</span></p>
            <p class="text-[10px] text-gray-500">عقود: ${p.contracts} | مارجن: ${p.margin.toFixed(2)}$</p>
          </div>
          <div class="text-left">
            <p class="font-black text-lg num ${col}">${p.pnl>=0?'+':''}${p.pnl.toFixed(4)} $</p>
            <p class="font-bold text-sm num ${col}">${p.pnl_pct>=0?'+':''}${p.pnl_pct.toFixed(2)}% ${p.pnl_pct>=0?'▲':'▼'}</p>
            <p class="text-[11px] ${col}">${up?'🟢 ربحانة':'🔴 خسرانة'}</p>
          </div>
        </div>
        <div class="mt-2 h-1.5 bg-gray-800 rounded-full overflow-hidden"><div class="h-full ${up?'bg-green-500':'bg-red-500'}" style="width:${Math.min(Math.abs(p.pnl_pct)*6,100)}%"></div></div>
      </div>`;
    }).join('');
  }
  
  document.getElementById('sigs').innerHTML=d.signals.length?d.signals.map(s=>`<div class="flex justify-between bg-[#0a0e14] rounded p-2"><span>${s.symbol} ${s.direction} RSI:${s.rsi}</span><span class="bg-blue-900 px-2 rounded">${s.score}/10</span></div>`).join(''):'<p class="text-gray-500">لا إشارات قوية</p>';
  
  document.getElementById('spot').innerHTML=d.holdings.length?d.holdings.map(h=>`<div class="flex justify-between bg-[#0a0e14] rounded p-2"><span>${h.coin}</span><span>${h.value.toFixed(2)}$</span></div>`).join('')+`<p class="text-[10px] text-gray-500 mt-2">الإجمالي: ${d.spot.toFixed(2)}$</p>`:'<p class="text-gray-500">لا سبوت</p>';
  
  document.getElementById('trades').innerHTML=d.trades_log.length?d.trades_log.slice(-10).reverse().map(t=>`<p>${t.time?new Date(t.time).toLocaleTimeString('ar-SA'):''} ${t.type||''} ${t.symbol||''}</p>`).join(''):'<p class="text-gray-500">لا سجل</p>';
  
  document.getElementById('errs').textContent=(d.errors||[]).slice(-2).join(' | ');
 }catch(e){console.log(e)}
}
load(); setInterval(load,2000);
</script></body></html>
"""

@app.route("/")
def home(): return DASHBOARD,200,{'Content-Type':'text/html; charset=utf-8'}

@app.route("/api/full")
def api_full():
    eq=get_equity()
    cnt,positions,_=get_positions()
    total_pnl=sum([p["pnl"] for p in positions])
    return jsonify({
        "free":eq["free"],"spot":eq["spot"],"total":eq["total"],"holdings":eq["holdings"],
        "count":cnt,"positions":positions,"total_pnl":round(total_pnl,4),
        "btc_trend":state["btc_trend"],"btc_vol":state["btc_vol"],
        "signals":state["signals"],"scanned":state["scanned"],"loop":state["loop"],"last_scan":state["last_scan"],
        "errors":state["errors"][-3:],"main_error":state["errors"][-1] if state["errors"] else "",
        "trades_log":load_trades()[-20:]
    })

@app.route("/ping")
def ping(): return jsonify({"pong":True})

if __name__=="__main__":
    threading.Thread(target=scan_loop,daemon=True).start()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
