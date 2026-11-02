import os, time, json, logging, threading
from datetime import datetime, timezone
import ccxt
from flask import Flask, jsonify

API_KEY = (os.getenv("OKX_API_KEY") or os.getenv("OKX_KEY") or "").strip()
API_SECRET = (os.getenv("OKX_API_SECRET") or os.getenv("OKX_SECRET") or os.getenv("OKX_SECRET_KEY") or "").strip()
API_PASS = (os.getenv("OKX_API_PASSWORD") or os.getenv("OKX_PASSPHRASE") or os.getenv("OKX_API_PASSPHRASE") or "").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log = logging.getLogger("REAL")
app = Flask(__name__)

def make_ex():
    return ccxt.okx({
        "apiKey": API_KEY,
        "secret": API_SECRET,
        "password": API_PASS,
        "enableRateLimit": True,
        "options": {"defaultType": "swap"}
    })

exchange = make_ex()
state = {"loop":0, "last_error":""}

def get_real_free():
    try:
        if not API_SECRET or len(API_SECRET) < 20:
            state["last_error"] = "المفاتيح ناقصة في Render"
            return 0.0
        bal = exchange.fetch_balance({"type":"swap"})
        # OKX يرجع availBal مو free
        data = bal.get("info",{}).get("data",[])
        for d in data:
            if d.get("ccy") == "USDT":
                v = d.get("availBal") or d.get("availEq") or d.get("eq")
                if v:
                    return float(v)
        # fallback
        return float(bal.get("USDT",{}).get("free",0) or bal.get("total",{}).get("USDT",0) or 0)
    except Exception as e:
        state["last_error"] = f"balance error: {str(e)[:100]}"
        log.error(state["last_error"])
        return 0.0

def get_real_positions():
    try:
        if not API_SECRET or len(API_SECRET) < 20:
            return []
        exchange.load_markets()
        pos = exchange.fetch_positions()
        real = []
        for p in pos:
            contracts = float(p.get("contracts") or 0)
            if contracts > 0:
                entry = float(p.get("entryPrice") or 0)
                mark = float(p.get("markPrice") or p.get("lastPrice") or entry)
                if mark == 0: 
                    try:
                        ticker = exchange.fetch_ticker(p["symbol"])
                        mark = float(ticker["last"])
                    except: mark = entry
                side = p.get("side")
                pnl = float(p.get("unrealizedPnl") or 0)
                # احسب النسبة الحقيقية
                pct = 0
                if entry > 0:
                    if side == "long": pct = (mark-entry)/entry*100*float(p.get("leverage") or 3)
                    else: pct = (entry-mark)/entry*100*float(p.get("leverage") or 3)
                real.append({
                    "symbol": p["symbol"],
                    "side": side,
                    "entry": entry,
                    "mark": mark,
                    "contracts": contracts,
                    "leverage": float(p.get("leverage") or 3),
                    "pnl": round(pnl,4),
                    "pnl_pct": round(pct,2),
                    "is_profit": pnl >= 0,
                    "margin": float(p.get("initialMargin") or p.get("collateral") or 0)
                })
        state["last_error"] = ""
        return real
    except Exception as e:
        state["last_error"] = f"pos error: {str(e)[:150]}"
        log.error(state["last_error"])
        return []

HTML = """
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>REAL LIVE PnL</title><script src="https://cdn.tailwindcss.com"></script>
<style>
body{background:#070a12;color:#fff;font-family:system-ui}
.card{background:#131a29;border:1px solid #1e293b;border-radius:16px}
.live-dot{width:8px;height:8px;background:#22c55e;border-radius:50%;display:inline-block;animation:pulse 1s infinite}
@keyframes pulse{0%{opacity:1}50%{opacity:0.2}100%{opacity:1}}
.num{transition:all 0.2s ease}
</style>
</head><body class="p-3"><div class="max-w-5xl mx-auto">
<div class="flex justify-between items-center mb-4">
<h1 class="text-xl font-bold">حقيقي REAL <span class="live-dot"></span> <span class="text-[11px] text-yellow-400 border border-yellow-600 px-2 py-0.5 rounded">OKX LIVE</span></h1>
<p class="text-[10px] text-gray-400" id="time">--</p>
</div>

<div id="err" class="hidden bg-red-900/30 border border-red-600 rounded-xl p-3 mb-4 text-[12px]"></div>

<div class="grid grid-cols-3 gap-2 mb-4">
<div class="card p-3 text-center"><p class="text-[10px] text-gray-400">الرصيد الحر</p><p id="bal" class="font-bold text-lg num">--</p><p class="text-[9px] text-gray-500">availBal</p></div>
<div class="card p-3 text-center"><p class="text-[10px] text-gray-400">الربح الآن</p><p id="tpnl" class="font-bold text-lg num">--</p><p class="text-[9px] text-gray-500">من OKX</p></div>
<div class="card p-3 text-center"><p class="text-[10px] text-gray-400">صفقات</p><p id="cnt" class="font-bold text-lg num">--</p></div>
</div>

<div id="pos" class="space-y-3"></div>

</div>
<script>
async function load(){
 try{
  const r=await fetch('/api/real'); 
  const d=await r.json();
  
  document.getElementById('time').textContent=new Date().toLocaleTimeString('ar-SA')+' | لوب '+d.loop;
  document.getElementById('bal').textContent=d.free.toFixed(2)+' USDT';
  document.getElementById('cnt').textContent=d.count;
  
  const errDiv=document.getElementById('err');
  if(d.error){errDiv.classList.remove('hidden'); errDiv.textContent='⚠️ '+d.error+' - تأكد من OKX_API_KEY / SECRET / PASSWORD في Render Environment';}
  else{errDiv.classList.add('hidden');}
  
  const tpnlEl=document.getElementById('tpnl');
  tpnlEl.textContent=(d.total_pnl>=0?'+':'')+d.total_pnl.toFixed(4)+' $';
  tpnlEl.className='font-bold text-lg num '+(d.total_pnl>=0?'text-green-400':'text-red-400');
  
  const posDiv=document.getElementById('pos');
  if(d.positions.length==0){
    posDiv.innerHTML='<div class="card p-8 text-center"><p class="text-gray-400 text-sm">لا يوجد صفقات مفتوحة الآن في OKX</p><p class="text-[11px] text-gray-500 mt-2">اذا عندك صفقة في OKX وما طلعت، تأكد من المفاتيح</p><p class="text-[11px] text-gray-600 mt-1">API Key: '+(d.has_keys?'✅ موجود':'❌ ناقص')+'</p></div>';
  } else {
    posDiv.innerHTML=d.positions.map(p=>{
      const isUp=p.pnl>=0;
      const bg=isUp?'bg-green-500/10 border-green-500/50':'bg-red-500/10 border-red-500/50';
      return `<div class="card p-4 border ${bg}">
        <div class="flex justify-between">
          <div>
            <p class="font-bold text-[15px]">${p.symbol.replace(':USDT','').replace('/USDT','')} <span class="text-[10px] px-2 py-0.5 rounded ${p.side=='long'?'bg-green-600':'bg-red-600'}">${p.side=='long'?'LONG ↑':'SHORT ↓'} x${p.leverage}</span></p>
            <p class="text-[11px] text-gray-400 mt-1">دخول: <span class="text-white">${p.entry.toFixed(2)}</span> | حالي: <span class="text-white font-bold num">${p.mark.toFixed(2)}</span></p>
            <p class="text-[10px] text-gray-500">عقود: ${p.contracts} | مارجن: ${p.margin.toFixed(2)}$</p>
          </div>
          <div class="text-left">
            <p class="font-black text-xl num ${isUp?'text-green-400':'text-red-400'}">${p.pnl>=0?'+':''}${p.pnl.toFixed(4)}</p>
            <p class="font-bold text-sm num ${isUp?'text-green-400':'text-red-400'}">${p.pnl_pct>=0?'+':''}${p.pnl_pct.toFixed(2)}%</p>
            <p class="text-[11px] mt-1 ${isUp?'text-green-400':'text-red-400'}">${isUp?'🟢 ربحانة':'🔴 خسرانة'}</p>
          </div>
        </div>
        <div class="mt-3 h-1.5 bg-gray-800 rounded-full overflow-hidden"><div class="h-full ${isUp?'bg-green-500':'bg-red-500'}" style="width:${Math.min(Math.abs(p.pnl_pct)*8,100)}%"></div></div>
      </div>`;
    }).join('');
  }
 }catch(e){console.log(e)}
}
load(); setInterval(load,2000);
</script></body></html>
"""

@app.route("/")
def home(): return HTML,200,{'Content-Type':'text/html; charset=utf-8'}

@app.route("/api/real")
def api_real():
    free = get_real_free()
    positions = get_real_positions()
    total = sum([p["pnl"] for p in positions])
    state["loop"]+=1
    return jsonify({
        "free": free,
        "count": len(positions),
        "total_pnl": round(total,4),
        "positions": positions,
        "loop": state["loop"],
        "error": state["last_error"],
        "has_keys": len(API_SECRET) > 20
    })

@app.route("/ping")
def ping(): return jsonify({"pong":True,"has_keys":len(API_SECRET)>20})

if __name__=="__main__":
    log.info(f"REAL mode started - key len {len(API_KEY)} secret len {len(API_SECRET)}")
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
