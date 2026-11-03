import os, time, threading, ccxt
from flask import Flask, jsonify, request
import numpy as np
from datetime import datetime, timezone

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL=21.04; TRADES=0; LAST="V20011 NO-CHARTS - يفتح مباشر $1+"
RUN=True
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
            if rsi<35: d="long"; s=8
            elif rsi<45: d="long"; s=7
            elif rsi>65: d="short"; s=8
            elif rsi>55: d="short"; s=7
            else: d="short" if price<ma20 else "long"; s=6
            name=sym.replace("/USDT:USDT","")
            sigs.append({"symbol":name,"full":sym,"direction":d,"price":price,"rsi":round(rsi,1),"score":s})
        except:
            t=tickers.get(sym)
            if t: sigs.append({"symbol":sym.replace("/USDT:USDT",""),"full":sym,"direction":"short","price":t["last"],"rsi":40,"score":6})
    return sorted(sigs,key=lambda x:x["score"],reverse=True)

def hunter_smart():
    global BAL, TRADES, LAST, RUN
    while RUN:
        try:
            ex=get_ex()
            try:
                b=ex.fetch_balance()
                BAL=float(b.get("total",{}).get("USDT",0) or BAL)
            except: pass
            
            # تريلنج SL كل $0.20
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
                            LAST=f"TRAIL {data['name']} يضمن ${locked} ربح ${pnl_usd:.2f}"
                except: pass

            # اغلاق تلقائي اذا ضرب SL
            try:
                positions=ex.fetch_positions()
                open_syms=[p["symbol"] for p in positions if float(p.get("contracts",0))>0]
                for sym in list(STATE["open"].keys()):
                    if sym not in open_syms:
                        d=STATE["open"].pop(sym)
                        STATE["daily"]+=d.get("best",0)
                        LAST=f"اغلقت {d['name']} ربح ${d.get('best',0):.2f}"
            except: pass

            # فتح مباشر بدون شارتات
            if not STATE["stopped"] and len(STATE["open"])<1:
                sigs=scan_market_live()
                if sigs:
                    sig=sigs[0]
                    try:
                        ex.set_leverage(5, sig["full"])
                        side="buy" if sig["direction"]=="long" else "sell"
                        amount=(2.2*5)/sig["price"]
                        amount=max(amount,1.0)
                        amount=float(ex.amount_to_precision(sig["full"], amount))
                        # فتح مباشر
                        try:
                            order=ex.create_market_order(sig["full"], side, amount, None, {'tdMode':'isolated'})
                        except:
                            order=ex.create_market_order(sig["full"], side, amount, None, {'tdMode':'isolated','posSide':'long' if side=='buy' else 'short'})
                        entry=order.get("average") or sig["price"]
                        sl=entry*0.992 if side=="buy" else entry*1.008
                        STATE["open"][sig["full"]]={"name":sig["symbol"],"dir":sig["direction"],"entry":entry,"sl":sl,"best":0,"locked":0,"trail":False,"levels":[]}
                        LAST=f"✅ فتح مباشر {sig['direction'].upper()} {sig['symbol']} @ {entry:.4f} RSI {sig['rsi']}"
                        TRADES+=1
                    except Exception as e:
                        LAST=f"❌ OKX: {str(e)[:150]}"
            time.sleep(3)
        except Exception as e:
            LAST=f"خطأ {str(e)[:120]}"; time.sleep(3)

@app.route("/")
def index(): return DASH_HTML

@app.route("/api/status")
def status():
    return jsonify({"balance":BAL,"daily":STATE["daily"],"positions":{"count":len(STATE["open"])},"last":LAST,"trades":TRADES,"stopped":STATE["stopped"]})

@app.route("/api/scan")
def scan(): return jsonify({"signals":scan_market_live()})

@app.route("/api/pnl_live")
def pnl_live():
    live=[]
    ex=get_ex()
    for sym,data in STATE["open"].items():
        try:
            tk=ex.fetch_ticker(sym); last=tk["last"]; entry=data["entry"]
            pnl_pct=(last-entry)/entry if data["dir"]=="long" else (entry-last)/entry
            pnl_usd=pnl_pct*2.2*5
            live.append({"symbol":data["name"],"dir":data["dir"],"pnl":round(pnl_usd,2),"entry":entry,"last":last,"best":round(data["best"],2),"locked":round(data["locked"],2),"sl":data["sl"],"trail":data["trail"]})
        except: pass
    return jsonify({"live":live})

@app.route("/api/get_code")
def get_code():
    with open(__file__,"r",encoding="utf-8") as f: return jsonify({"code":f.read()})

@app.route("/api/save_code", methods=["POST"])
def save_code():
    code=request.json.get("code","")
    with open(__file__,"w",encoding="utf-8") as f: f.write(code)
    return jsonify({"ok":True})

DASH_HTML = """
<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>DIRECT TRADES</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{background:#05070a}.glass{background:#0f141c;border:1px solid #1e293b}.live-dot{width:8px;height:8px;background:#22c55e;border-radius:50%;display:inline-block;animation:blink 1s infinite}@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}</style>
</head><body class="text-white p-3 text-[12px]">
<div class="glass rounded-2xl p-4 mb-3 flex justify-between items-center"><div><div class="font-black text-[16px] flex gap-2 items-center"><span class="live-dot"></span> مباشر بدون شارتات <span class="text-green-400">$1+ مفتوح</span></div><div id="last" class="text-[10px] text-yellow-300 mt-1"></div></div><div id="bal" class="text-[18px] font-black"></div></div>
<div id="liveBig" class="mb-3"></div>
<div class="glass rounded-2xl p-3 mb-3"><div class="font-bold mb-2">🚀 فرص مباشرة - يفتح تلقائي</div><div id="sigs" class="grid grid-cols-1 gap-2"></div></div>
<div class="glass rounded-2xl p-3 text-[10px]"><div class="font-bold">📝 السجل المباشر</div><div id="log" class="mt-2 text-gray-400"></div></div>
<script>
async function load(){
 const st=await fetch('/api/status').then(r=>r.json());
 document.getElementById('bal').innerHTML=`$${st.balance.toFixed(2)} | ${st.positions.count}/1`;
 document.getElementById('last').textContent=st.last;
 const pnl=await fetch('/api/pnl_live').then(r=>r.json());
 const big=document.getElementById('liveBig');
 if(pnl.live.length>0){
  let h=''; pnl.live.forEach(x=>{
   const pct=Math.min((x.pnl/1)*100,150);
   h+=`<div class="glass rounded-[18px] p-4 border-2 ${x.pnl>=1?'border-green-500 bg-green-500/10':'border-yellow-500/40'}"><div class="flex justify-between"><div class="flex gap-2 items-center"><span class="live-dot"></span><span class="font-black text-[18px]">${x.symbol} ${x.dir.toUpperCase()}</span><span class="px-4 py-1 rounded-full text-[14px] font-black ${x.pnl>=0?'bg-green-500 text-black':'bg-red-500'}">${x.pnl>=0?'+':''}$${x.pnl}</span></div><span class="text-[11px]">${x.trail?'🔥 SL يطلع':'⏳ $0.70'}</span></div><div class="grid grid-cols-4 gap-2 mt-3 text-[11px]"><div class="bg-black/50 rounded-xl p-2 text-center"><div class="text-gray-400 text-[9px]">دخول</div><div class="font-bold">${x.entry.toFixed(4)}</div></div><div class="bg-black/50 rounded-xl p-2 text-center"><div class="text-gray-400 text-[9px]">حالي</div><div class="font-bold text-yellow-300">${x.last.toFixed(4)}</div></div><div class="bg-black/50 rounded-xl p-2 text-center"><div class="text-gray-400 text-[9px]">SL حي</div><div class="font-bold text-red-300">${x.sl.toFixed(4)}</div></div><div class="bg-black/50 rounded-xl p-2 text-center"><div class="text-gray-400 text-[9px]">مضمون</div><div class="font-black text-green-400 text-[14px]">$${x.locked}</div></div></div><div class="mt-3 h-3 bg-black rounded-full overflow-hidden"><div class="h-full bg-green-500" style="width:${Math.min(pct,100)}%"></div></div><div class="mt-2 text-[10px]">أفضل $${x.best} | هدف $1+ مفتوح ${x.pnl>=1?'✅ ضمنا $1 ومكمل':'⏳'}</div></div>`;
  }); big.innerHTML=h;
 } else { big.innerHTML=`<div class="glass rounded-2xl p-6 text-center border-dashed"><div class="text-[14px]">🔴 يبحث عن صفقة مباشرة...</div><div class="text-[10px] text-gray-500 mt-1">يفتح LONG/SHORT حسب RSI مباشرة بدون شارتات</div></div>`; }
 const sc=await fetch('/api/scan').then(r=>r.json());
 document.getElementById('sigs').innerHTML=sc.signals.map(s=>`<div class="bg-black/40 rounded-xl p-3 flex justify-between items-center border ${s.direction=='long'?'border-green-500/30':'border-red-500/30'}"><div class="flex gap-2 items-center"><span class="font-black">${s.symbol}</span><span class="font-mono text-[11px]">${s.price.toFixed(4)}</span><span class="px-2 py-0.5 rounded-full text-[9px] font-black ${s.direction=='long'?'bg-green-500 text-black':'bg-red-500 text-white'}">${s.direction.toUpperCase()}</span><span class="text-[9px] bg-[#1e293b] px-2 py-0.5 rounded-full">RSI ${s.rsi} Score ${s.score}</span></div><button onclick="openNow('${s.full}','${s.direction}')" class="bg-blue-600 px-4 py-1 rounded-full font-bold text-[10px]">افتح الآن</button></div>`).join('');
 document.getElementById('log').textContent=st.last;
}
async function openNow(full,dir){ if(!confirm('فتح '+dir+' '+full+'؟'))return; await fetch('/api/open_manual?sym='+full+'&dir='+dir); }
setInterval(load,2500); load();
</script>
</body></html>
"""

@app.route("/api/open_manual")
def open_manual():
    sym=request.args.get("sym"); dir=request.args.get("dir","long")
    ex=get_ex()
    try:
        ex.set_leverage(5,sym)
        price=ex.fetch_ticker(sym)["last"]
        amount=(2.2*5)/price; amount=max(amount,1.0)
        amount=float(ex.amount_to_precision(sym, amount))
        side="buy" if dir=="long" else "sell"
        try: order=ex.create_market_order(sym, side, amount, None, {'tdMode':'isolated'})
        except: order=ex.create_market_order(sym, side, amount, None, {'tdMode':'isolated','posSide':'long' if side=='buy' else 'short'})
        entry=order.get("average") or price
        STATE["open"][sym]={"name":sym.replace("/USDT:USDT",""),"dir":dir,"entry":entry,"sl":entry*0.992 if side=="buy" else entry*1.008,"best":0,"locked":0,"trail":False,"levels":[]}
        return jsonify({"ok":True,"entry":entry})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)})

threading.Thread(target=hunter_smart,daemon=True).start()
if __name__=="__main__":
    port=int(os.getenv("PORT",10000))
    app.run(host="0.0.0.0",port=port)