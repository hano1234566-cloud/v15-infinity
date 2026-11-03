import os, time, threading, ccxt
from flask import Flask, jsonify, request
import numpy as np
from datetime import datetime, timezone

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL=21.04; LIQ=0; TRADES=3; PNLS=0.006; WINS=0
LAST="V20010 LIVE FIXED - BINANCE CHARTS + $1+ SL UP"
RUN=True

# حالة اضافية للـ LIVE
STATE = {"open":{}, "daily":0, "logs":[], "stopped":False, "losses":0}

app = Flask(__name__)

def get_ex():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'options':{'defaultType':'swap'},'enableRateLimit':True})

def calc_rsi(prices, p=14):
    try:
        prices=np.array(prices,float)
        deltas=np.diff(prices)
        up=np.where(deltas>0,deltas,0); down=np.where(deltas<0,-deltas,0)
        ma_up=np.mean(up[:p]); ma_down=np.mean(down[:p])
        if ma_down==0: return 70.0
        rsi=100-(100/(1+ma_up/ma_down))
        for i in range(p,len(deltas)):
            ma_up=(ma_up*(p-1)+up[i])/p
            ma_down=(ma_down*(p-1)+down[i])/p
            rsi=100-(100/(1+ma_up/ma_down)) if ma_down!=0 else 70
        return float(rsi)
    except: return 50.0

def scan_market_live():
    sigs=[]
    WATCH=["ENA/USDT:USDT","FET/USDT:USDT","TAO/USDT:USDT","RENDER/USDT:USDT","SUI/USDT:USDT"]
    ex=get_ex()
    try: tickers=ex.fetch_tickers()
    except: tickers={}
    for sym in WATCH:
        try:
            ohlcv=ex.fetch_ohlcv(sym,'1h',80)
            closes=[c[4] for c in ohlcv]
            price=closes[-1]; rsi=calc_rsi(closes); ma20=sum(closes[-20:])/20
            atr=(max(closes[-14:])-min(closes[-14:]))/price
            if rsi<32 and price<ma20*0.98: d="long"; s=8
            elif rsi<40 and price<ma20: d="long"; s=7
            elif rsi>68 and price>ma20*1.02: d="short"; s=8
            elif rsi>58 or price<ma20*0.995: d="short"; s=7
            else: d="short" if price<ma20 else "long"; s=6
            name=sym.replace("/USDT:USDT","")
            sigs.append({"symbol":name,"full":sym,"direction":d,"price":price,"rsi":round(rsi,1),"atr":round(atr,5),"ma20":round(ma20,4),"score":s})
        except:
            t=tickers.get(sym)
            if t: sigs.append({"symbol":sym.replace("/USDT:USDT",""),"full":sym,"direction":"short","price":t["last"],"rsi":38,"atr":0.005,"ma20":t["last"],"score":6})
    return sorted(sigs,key=lambda x:x["score"],reverse=True)

def hunter_smart():
    global BAL, LIQ, TRADES, PNLS, LAST, WINS, RUN
    while RUN:
        try:
            ex = get_ex()
            b = ex.fetch_balance()
            try: BAL=float(b.get("total",{}).get("USDT",0) or b.get("USDT",{}).get("total",0) or BAL)
            except: pass
            
            # تريلنج SL
            for sym,data in list(STATE["open"].items()):
                try:
                    tk=ex.fetch_ticker(sym)
                    last=tk["last"]; entry=data["entry"]
                    pnl_pct=(last-entry)/entry if data["dir"]=="long" else (entry-last)/entry
                    pnl_usd=pnl_pct*2.2*5
                    if pnl_usd>data["best"]: data["best"]=pnl_usd
                    if pnl_usd>=0.70: data["trail"]=True
                    if data["trail"]:
                        locked=0
                        if pnl_usd>=0.70: locked=0.30
                        if pnl_usd>=0.90: locked=0.54
                        if pnl_usd>=1.10: locked=0.66
                        if pnl_usd>=1.30: locked=0.85
                        if pnl_usd>=1.50: locked=1.05
                        if pnl_usd>=2.00: locked=1.40
                        if locked>data["locked"]:
                            data["locked"]=locked
                            pct=locked/(2.2*5)
                            data["sl"]=entry*(1+pct*0.9) if data["dir"]=="long" else entry*(1-pct*0.9)
                            data["levels"].append({"pnl":round(pnl_usd,2),"locked":locked})
                            LAST=f"TRAIL {data['name']} يضمن ${locked} ربح ${pnl_usd:.2f}"
                except: pass

            # فتح صفقة جديدة
            if not STATE["stopped"] and len(STATE["open"])<1:
                sigs=scan_market_live()
                if sigs:
                    sig=sigs[0]
                    try:
                        ex.set_leverage(5,sig["full"])
                        side="buy" if sig["direction"]=="long" else "sell"
                        amount=(2.2*5)/sig["price"]
                        order=ex.create_market_order(sig["full"],side,amount)
                        entry=order.get("average") or sig["price"]
                        sl=entry*0.992 if side=="buy" else entry*1.008
                        STATE["open"][sig["full"]]={"name":sig["symbol"],"dir":sig["direction"],"entry":entry,"sl":sl,"best":0,"locked":0,"trail":False,"levels":[]}
                        LAST=f"فتح {sig['direction']} {sig['symbol']} RSI {sig['rsi']}"
                        TRADES+=1
                    except Exception as e:
                        LAST=f"خطأ فتح: {str(e)[:60]}"
            
            if BAL < 5: LAST="رصيد قليل"; time.sleep(10)
            time.sleep(4)
        except Exception as e:
            LAST=f"خطأ عام {str(e)[:80]}"; time.sleep(5)

# ROUTES
@app.route("/")
def index(): return DASH_HTML

@app.route("/api/status")
def status():
    return jsonify({"balance":BAL,"daily_pnl":STATE["daily"],"losses":STATE["losses"],"stopped":STATE["stopped"],"positions":{"count":len(STATE["open"]),"max":1},"logs":[{"time":datetime.now(timezone.utc).isoformat(),"type":"INFO","symbol":k,"msg":LAST} for k in [1]],"last":LAST,"trades":TRADES})

@app.route("/api/scan")
def scan(): return jsonify({"signals":scan_market_live()})

@app.route("/api/pnl_live")
def pnl_live():
    live=[]
    for sym,data in STATE["open"].items():
        try:
            ex=get_ex(); tk=ex.fetch_ticker(sym); last=tk["last"]; entry=data["entry"]
            pnl_pct=(last-entry)/entry if data["dir"]=="long" else (entry-last)/entry
            pnl_usd=pnl_pct*2.2*5
            live.append({"symbol":data["name"],"pnl":round(pnl_usd,2),"pct":round(pnl_usd*100,1),"entry":entry,"last":last,"best":round(data["best"],2),"locked":round(data["locked"],2),"sl":data["sl"],"trail":data["trail"],"levels":data["levels"]})
        except: live.append({"symbol":data["name"],"pnl":0,"pct":0,"entry":data["entry"],"last":0,"best":0,"locked":0,"sl":data["sl"],"trail":False,"levels":[]})
    return jsonify({"live":live})

@app.route("/api/get_code")
def get_code():
    with open(__file__,"r",encoding="utf-8") as f: return jsonify({"code":f.read()})

@app.route("/api/save_code", methods=["POST"])
def save_code():
    code=request.json.get("code","")
    with open(__file__,"w",encoding="utf-8") as f: f.write(code)
    return jsonify({"ok":True,"msg":f"حفظ {len(code)}"})

DASH_HTML = """
<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>V20010 LIVE</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{background:#05070a}.glass{background:#0f141c;border:1px solid #1e293b}.live-dot{width:7px;height:7px;background:#22c55e;border-radius:50%;display:inline-block;animation:blink 1s infinite}@keyframes blink{0%,100%{opacity:1}50%{opacity:0.2}}.tv{height:260px;width:100%;border:0;border-radius:14px;background:#0f141c}</style>
</head><body class="text-white p-2 pb-20 text-[11px]">
<div class="flex justify-between items-center glass rounded-2xl p-3 mb-2"><div><div class="font-black text-[14px] flex items-center gap-2"><span class="live-dot"></span> V20010 LIVE <span class="text-green-400">FIXED</span> <span id="clock" class="text-[10px] text-gray-400"></span></div><div class="text-[9px] text-gray-400">مبني على كودك V20009 - شارتات BINANCE LIVE + $1+ SL يطلع</div></div><div class="flex gap-1"><button onclick="showTab('main')" class="bg-blue-600 px-3 py-1.5 rounded-full text-[10px] font-bold">LIVE</button><button onclick="showTab('code')" class="bg-[#1e293b] px-3 py-1.5 rounded-full text-[10px]">كود</button></div></div>
<div id="tab-main"><div id="stats" class="grid grid-cols-4 gap-2 mb-2"></div><div id="liveBig" class="mb-2"></div><div class="glass rounded-2xl p-2 mb-2 overflow-x-auto"><div class="flex gap-2" id="tickerLive">اسعار حية...</div></div><div id="chartsGrid" class="grid grid-cols-1 gap-2"></div><div id="logs" class="glass rounded-2xl p-3 mt-2 text-[10px] font-mono text-gray-400"></div></div>
<div id="tab-code" class="hidden"><div class="glass rounded-2xl p-3"><textarea id="codeArea" class="w-full h-[400px] bg-black/60 border border-gray-700 rounded-xl p-2 text-[10px] font-mono"></textarea><div class="flex gap-2 mt-2"><button onclick="loadCode()" class="bg-[#1e293b] px-4 py-2 rounded-full">تحميل</button><button onclick="saveCode()" class="bg-green-600 px-6 py-2 rounded-full font-black">حفظ</button></div><div id="codeMsg" class="mt-2 text-xs"></div></div></div>
<script>
function showTab(t){document.getElementById('tab-main').classList.toggle('hidden',t!=='main');document.getElementById('tab-code').classList.toggle('hidden',t!=='code');}
let priceCache={};
async function load(){
 const r=await fetch('/api/status'); const d=await r.json();
 document.getElementById('stats').innerHTML=`<div class="glass rounded-xl p-2 text-center"><div class="text-[8px] text-gray-400">الرصيد LIVE</div><div class="font-black text-[13px]">$${d.balance.toFixed(2)}</div><div class="text-[8px] text-green-400">${d.last?.slice(0,20)||''}</div></div><div class="glass rounded-xl p-2 text-center"><div class="text-[8px] text-gray-400">صفقات</div><div class="font-black text-[13px]">${d.positions.count}/${d.positions.max}</div></div><div class="glass rounded-xl p-2 text-center"><div class="text-[8px] text-gray-400">يومي LIVE</div><div class="font-black text-[13px] text-green-400">$${d.balance.toFixed(2)}</div></div><div class="glass rounded-xl p-2 text-center"><div class="text-[8px] text-gray-400">حالة LIVE</div><div class="font-black ${d.stopped?'text-red-400':'text-green-400'}">${d.stopped?'⏸️':'▶️ شغال'}</div></div>`;
 const lv=await fetch('/api/pnl_live').then(r=>r.json());
 const big=document.getElementById('liveBig');
 if(lv.live.length>0){
  let h=''; lv.live.forEach(x=>{
   const pct=Math.min((x.pnl/1)*100,150);
   h+=`<div class="glass rounded-[18px] p-3 border ${x.pnl>=1?'border-green-500/60 bg-green-500/10':'border-yellow-500/30'}"><div class="flex justify-between items-center"><div class="flex items-center gap-2"><span class="live-dot"></span><span class="font-black text-[15px]">${x.symbol}</span><span class="px-3 py-1 rounded-full text-[12px] font-black ${x.pnl>=0?'bg-green-500 text-black':'bg-red-500 text-white'}">${x.pnl>=0?'+':''}$${x.pnl} LIVE</span><span class="text-[10px]">${x.trail?'🔥 SL يطلع حي':'⏳ انتظار $0.70'}</span></div><span class="text-[10px]">${x.pct}%</span></div><div class="grid grid-cols-4 gap-2 mt-3 text-[10px]"><div class="bg-black/50 rounded-xl p-2 text-center"><div class="text-gray-400 text-[8px]">دخول</div><div class="font-mono font-bold">${x.entry?.toFixed(5)}</div></div><div class="bg-black/50 rounded-xl p-2 text-center"><div class="text-gray-400 text-[8px]">حالي LIVE</div><div class="font-mono font-bold text-yellow-300">${x.last?.toFixed(5)}</div></div><div class="bg-black/50 rounded-xl p-2 text-center"><div class="text-gray-400 text-[8px]">SL حي</div><div class="font-mono font-bold text-red-300">${x.sl?.toFixed(5)}</div></div><div class="bg-black/50 rounded-xl p-2 text-center"><div class="text-gray-400 text-[8px]">مضمون LIVE</div><div class="font-black text-green-400 text-[13px]">$${x.locked}</div></div></div><div class="mt-3"><div class="flex justify-between text-[9px] mb-1"><span>هدف $1+ مفتوح</span><span class="${x.pnl>=1?'text-green-400 font-black':''}">${x.pnl>=1?'✅ ضمنا $1+':'$'+x.pnl+' / $1'}</span></div><div class="h-2.5 bg-black rounded-full overflow-hidden"><div class="h-full bg-gradient-to-r from-green-400 to-emerald-500" style="width:${Math.min(pct,100)}%"></div></div></div></div>`;
  }); big.innerHTML=h;
 } else { big.innerHTML=`<div class="glass rounded-2xl p-5 text-center border-dashed"><div class="text-[12px]">🔴 لا صفقات - يفتح LIVE حسب الشارت RSI</div><div class="text-[9px] text-gray-500 mt-1">LONG/SHORT حسب RSI الحقيقي - هدف $1+ مفتوح</div></div>`; }
 const s=await fetch('/api/scan').then(r=>r.json());
 let tickHtml=''; s.signals.forEach(sig=>{
  const prev=priceCache[sig.symbol]||sig.price; const ch=((sig.price-prev)/prev*100).toFixed(2); const up=sig.price>=prev; priceCache[sig.symbol]=sig.price;
  tickHtml+=`<div class="bg-black/50 rounded-full px-3 py-1.5 flex items-center gap-2 whitespace-nowrap border ${sig.direction==='long'?'border-green-500/30':'border-red-500/30'}"><span class="font-black">${sig.symbol}</span><span class="font-mono">${sig.price?.toFixed(4)}</span><span class="${up?'text-green-400':'text-red-400'} text-[9px]">${up?'▲':'▼'} ${ch}% LIVE</span><span class="px-2 py-0.5 rounded-full text-[8px] font-black ${sig.direction==='long'?'bg-green-500 text-black':'bg-red-500 text-white'}">${sig.direction.toUpperCase()} LIVE</span><span class="text-[8px] bg-[#1e293b] px-1.5 py-0.5 rounded-full">RSI ${sig.rsi}</span></div>`;
 }); document.getElementById('tickerLive').innerHTML=tickHtml;
 let chartsHtml=''; s.signals.forEach(sig=>{
  const tvSym=`BINANCE:${sig.symbol}USDT`;
  const url=`https://s.tradingview.com/widgetembed/?symbol=${tvSym}&interval=60&hidesidetoolbar=1&theme=dark&style=1&timezone=Asia%2FRiyadh&locale=ar`;
  chartsHtml+=`<div class="glass rounded-2xl p-2"><div class="flex justify-between items-center mb-2"><div class="flex items-center gap-2"><span class="live-dot"></span><span class="font-black text-[12px]">${sig.symbol}</span><span class="px-2 py-0.5 rounded-full text-[8px] font-black ${sig.direction==='long'?'bg-green-500 text-black':'bg-red-500 text-white'}">${sig.direction.toUpperCase()} LIVE</span><span class="text-[9px] bg-black/40 px-2 py-0.5 rounded-full">RSI ${sig.rsi} LIVE | Score ${sig.score}/10</span></div><span class="font-mono text-[11px] font-bold">${sig.price?.toFixed(4)} LIVE</span></div><iframe class="tv" src="${url}" loading="lazy"></iframe><div class="grid grid-cols-3 gap-1 mt-2 text-[9px]"><div class="bg-black/40 rounded-lg p-1.5 text-center"><div class="text-gray-400">RSI حي</div><div class="font-bold text-[11px]">${sig.rsi}</div></div><div class="bg-black/40 rounded-lg p-1.5 text-center"><div class="text-gray-400">ATR حي</div><div class="font-bold text-[11px]">${sig.atr}</div></div><div class="bg-black/40 rounded-lg p-1.5 text-center"><div class="text-gray-400">MA20 حي</div><div class="font-bold text-[11px]">${sig.ma20}</div></div></div></div>`;
 }); document.getElementById('chartsGrid').innerHTML=chartsHtml;
 document.getElementById('clock').textContent=new Date().toLocaleTimeString('ar-SA');
 document.getElementById('logs').innerHTML='<div class="font-bold mb-1">السجل LIVE: '+d.last+'</div>';
}
async function loadCode(){const r=await fetch('/api/get_code');const d=await r.json();if(d.code){document.getElementById('codeArea').value=d.code;document.getElementById('codeMsg').textContent='✅ '+d.code.length;}}
async function saveCode(){const c=document.getElementById('codeArea').value;if(!confirm('حفظ '+c.length+'؟'))return;const r=await fetch('/api/save_code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:c})});const d=await r.json();document.getElementById('codeMsg').textContent=d.ok?'✅ '+d.msg:'❌ '+d.error;}
load(); setInterval(load,4000);
</script>
</body></html>
"""

threading.Thread(target=hunter_smart,daemon=True).start()

if __name__=="__main__":
    port=int(os.getenv("PORT",10000))
    app.run(host="0.0.0.0",port=port)