import os, time, json, logging, threading
from datetime import datetime, timezone
import ccxt, pandas as pd
from flask import Flask, jsonify

API_KEY=(os.getenv("OKX_API_KEY") or "").strip()
API_SECRET=(os.getenv("OKX_API_SECRET") or "").strip()
API_PASS=(os.getenv("OKX_API_PASSWORD") or os.getenv("OKX_PASSPHRASE") or "").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log=logging.getLogger("LIVE")
app=Flask(__name__)

def make_ex():
    return ccxt.okx({"apiKey":API_KEY,"secret":API_SECRET,"password":API_PASS,"enableRateLimit":True,"options":{"defaultType":"swap"}})
exchange=make_ex()

state={"signals":[],"loop":0,"positions_cache":[]}

def get_free():
    try:
        if not API_SECRET: return 9.5
        bal=exchange.fetch_balance({"type":"swap"})
        data=bal.get("info",{}).get("data",[])
        for d in data:
            if d.get("ccy")=="USDT":
                v=d.get("availBal") or d.get("eq")
                if v and float(v)>0: return float(v)
        return float(bal.get("USDT",{}).get("free",0) or 0)
    except: return 0.0

def get_live_positions():
    try:
        if not API_SECRET: 
            # DEMO - عشان تشوف الشكل لو مافي مفاتيح
            return [{"symbol":"BTC/USDT:USDT","side":"short","entry":94500.0,"mark":94420.5,"contracts":0.01,"pnl":2.35,"pnl_pct":1.24,"is_profit":True}]
        pos=exchange.fetch_positions()
        lst=[]
        for p in pos:
            c=float(p.get("contracts") or 0)
            if c>0:
                entry=float(p.get("entryPrice") or 0)
                mark=float(p.get("markPrice") or entry)
                side=p.get("side")
                pnl=float(p.get("unrealizedPnl") or 0)
                pct=0
                if entry>0:
                    if side=="long": pct=(mark-entry)/entry*100*3
                    else: pct=(entry-mark)/entry*100*3
                lst.append({"symbol":p["symbol"],"side":side,"entry":entry,"mark":mark,"contracts":c,"pnl":pnl,"pnl_pct":pct,"is_profit":pnl>=0})
        state["positions_cache"]=lst
        return lst
    except Exception as e:
        return state["positions_cache"]

def fetch_df(sym):
    try:
        c=exchange.fetch_ohlcv(sym,timeframe="15m",limit=200)
        df=pd.DataFrame(c,columns=["t","o","h","l","cl","v"])
        df=df.iloc[:-1].copy()
        df["ema9"]=df["cl"].ewm(span=9).mean(); df["ema21"]=df["cl"].ewm(span=21).mean(); df["ema50"]=df["cl"].ewm(span=50).mean()
        df["ema200"]=df["cl"].ewm(span=200).mean()
        d=df["cl"].diff(); g=d.clip(lower=0); l=-d.clip(upper=0)
        ag=g.ewm(alpha=1/14,adjust=False).mean(); al=l.ewm(alpha=1/14,adjust=False).mean()
        rs=ag/al.replace(0,1e-8); df["rsi"]=100-(100/(1+rs))
        return df.dropna()
    except: return None

def scan_loop():
    while True:
        try:
            TOP=["BTC/USDT","ETH/USDT","SOL/USDT","FET/USDT"]
            sigs=[]
            for s in TOP:
                df=fetch_df(s)
                if df is None: continue
                cur=df.iloc[-1]; prev=df.iloc[-2]
                if cur["ema9"]>cur["ema21"]>cur["ema50"] and cur["cl"]>cur["ema200"] and 48<cur["rsi"]<70 and prev["ema9"]<=prev["ema21"]:
                    sigs.append({"symbol":s,"direction":"long","score":8,"price":float(cur["cl"])})
                elif cur["ema9"]<cur["ema21"]<cur["ema50"] and cur["cl"]<cur["ema200"] and 28<cur["rsi"]<50 and prev["ema9"]>=prev["ema21"]:
                    sigs.append({"symbol":s,"direction":"short","score":8,"price":float(cur["cl"])})
            state["signals"]=sigs; state["loop"]+=1
        except: pass
        time.sleep(15)

HTML="""
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LIVE PnL</title><script src="https://cdn.tailwindcss.com"></script>
<style>
body{background:#0a0e14;color:#fff;font-family:system-ui}
.card{background:#151b24;border:1px solid #222a36;border-radius:16px}
.live-dot{width:8px;height:8px;background:#22c55e;border-radius:50%;display:inline-block;animation:pulse 1s infinite}
@keyframes pulse{0%{opacity:1}50%{opacity:0.3}100%{opacity:1}}
.pnl-up{color:#22c55e} .pnl-down{color:#ef4444}
@keyframes countUp{from{transform:scale(0.9)}to{transform:scale(1)}}
.num{transition:all 0.3s ease; display:inline-block}
</style>
</head><body class="p-3"><div class="max-w-5xl mx-auto">
<div class="flex justify-between items-center mb-4">
<h1 class="text-xl font-bold">LIVE <span class="text-green-400">مباشر</span> <span class="live-dot"></span></h1>
<p class="text-[11px] text-gray-400" id="time">--</p>
</div>

<div class="grid grid-cols-3 gap-2 mb-4">
<div class="card p-3 text-center"><p class="text-[10px] text-gray-400">الرصيد</p><p id="bal" class="font-bold text-lg num">--</p></div>
<div class="card p-3 text-center"><p class="text-[10px] text-gray-400">الربح الآن</p><p id="tpnl" class="font-bold text-lg num">--</p></div>
<div class="card p-3 text-center"><p class="text-[10px] text-gray-400">صفقات</p><p id="cnt" class="font-bold text-lg num">--</p></div>
</div>

<div id="pos" class="space-y-3"></div>

<div class="card p-3 mt-4">
<p class="text-xs font-bold mb-2">إشارات</p>
<div id="sigs" class="text-xs"></div>
</div>

</div>
<script>
let lastPnl={};
function fmt(n){return n>=0?'+'+n.toFixed(4):n.toFixed(4)}

async function load(){
 try{
  const r=await fetch('/api/live'); const d=await r.json();
  document.getElementById('bal').textContent=d.free.toFixed(2)+' USDT';
  document.getElementById('cnt').textContent=d.count;
  document.getElementById('time').textContent=new Date().toLocaleTimeString('ar-SA')+' - تحديث كل 2 ثانية';
  
  const tpnlEl=document.getElementById('tpnl');
  tpnlEl.textContent=fmt(d.total_pnl)+' $';
  tpnlEl.className='font-bold text-lg num '+(d.total_pnl>=0?'pnl-up':'pnl-down');
  
  const posDiv=document.getElementById('pos');
  if(d.positions.length==0){
    posDiv.innerHTML='<div class="card p-6 text-center text-gray-500 text-sm">لا صفقات - ينتظر إشارة</div>';
  } else {
    posDiv.innerHTML=d.positions.map(p=>{
      const isUp=p.pnl>=0;
      const bg=isUp?'bg-green-500/10 border-green-500/50':'bg-red-500/10 border-red-500/50';
      const arrow=isUp?'▲':'▼';
      return `<div class="card p-4 border ${bg}">
        <div class="flex justify-between items-start">
          <div>
            <p class="font-bold text-[15px]">${p.symbol.replace(':USDT','')} <span class="text-xs px-2 py-0.5 rounded ${p.side=='long'?'bg-green-600':'bg-red-600'}">${p.side=='long'?'LONG ↑':'SHORT ↓'}</span></p>
            <p class="text-[11px] text-gray-400 mt-1">دخول: <span class="text-white">${p.entry.toFixed(2)}</span> | حالي: <span class="text-white font-bold">${p.mark.toFixed(2)}</span></p>
            <div class="flex gap-2 mt-1 text-[11px]"><span class="bg-gray-800 px-2 py-0.5 rounded">${p.contracts} عقد</span><span class="bg-gray-800 px-2 py-0.5 rounded">${arrow} ${Math.abs(p.pnl_pct).toFixed(2)}%</span></div>
          </div>
          <div class="text-left">
            <p class="font-black text-xl num ${isUp?'pnl-up':'pnl-down'}" style="animation:countUp 0.3s">${fmt(p.pnl)} $</p>
            <p class="font-bold text-sm num ${isUp?'pnl-up':'pnl-down'}">${p.pnl_pct>=0?'+':''}${p.pnl_pct.toFixed(2)}%</p>
            <p class="text-[11px] mt-1 ${isUp?'pnl-up':'pnl-down'}">${isUp?'🟢 ربحانة':'🔴 خسرانة'}</p>
          </div>
        </div>
        <div class="mt-3 h-1 bg-gray-800 rounded-full overflow-hidden"><div class="h-full ${isUp?'bg-green-500':'bg-red-500'}" style="width:${Math.min(Math.abs(p.pnl_pct)*10,100)}%"></div></div>
      </div>`;
    }).join('');
  }
  document.getElementById('sigs').innerHTML=d.signals.length?d.signals.map(s=>`<div>${s.symbol} ${s.direction} ${s.score}/10</div>`).join(''):'لا إشارات';
 }catch(e){}
}
load();
setInterval(load,2000);
</script></body></html>
"""

@app.route("/")
def home(): return HTML,200,{'Content-Type':'text/html; charset=utf-8'}

@app.route("/api/live")
def live():
    free=get_free()
    positions=get_live_positions()
    total=sum([p["pnl"] for p in positions])
    return jsonify({"free":free,"count":len(positions),"total_pnl":round(total,4),"positions":positions,"signals":state["signals"]})

@app.route("/ping")
def ping(): return jsonify({"pong":True})

if __name__=="__main__":
    threading.Thread(target=scan_loop,daemon=True).start()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
