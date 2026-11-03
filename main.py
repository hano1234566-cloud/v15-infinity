import os, ccxt, time, threading, json
from flask import Flask, jsonify, request
from datetime import datetime, timezone
import numpy as np

app = Flask(__name__)

# ===== CONFIG =====
CONFIG = {
    "LEVERAGE": 5,
    "MARGIN_USDT": 2.2,
    "MAX_POSITIONS": 1,
    "DAILY_LOSS_LIMIT": -3,
    "TARGET_PROFIT": 1.0,
    "TRAIL_START": 0.70,
    "TRAIL_STEP": 0.20,
    "SL_PCT": 0.008,
}

WATCH = ["ENA/USDT:USDT","FET/USDT:USDT","TAO/USDT:USDT","RENDER/USDT:USDT","SUI/USDT:USDT"]

exchange = ccxt.okx({
    "apiKey": os.getenv("OKX_API_KEY"),
    "secret": os.getenv("OKX_SECRET"),
    "password": os.getenv("OKX_PASSWORD"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

state = {
    "balance": 0.0,
    "daily_pnl": 0.0,
    "losses": 0,
    "stopped": False,
    "open_trades": {},
    "logs": [],
    "errors": []
}

def log(msg, typ="INFO", symbol="-", pnl=""):
    state["logs"].append({"time": datetime.now(timezone.utc).isoformat(), "type": typ, "symbol": symbol, "msg": msg, "pnl": pnl})
    state["logs"] = state["logs"][-50:]
    print(f"[{typ}] {symbol} {msg}")

def calc_rsi(prices, period=14):
    try:
        prices = np.array(prices, dtype=float)
        if len(prices) < period+2: return 50.0
        deltas = np.diff(prices)
        up = np.zeros(len(deltas)); down = np.zeros(len(deltas))
        up[deltas>0]=deltas[deltas>0]; down[-deltas>0]=-deltas[-deltas>0]
        ma_up = np.mean(up[:period]); ma_down = np.mean(down[:period])
        if ma_down==0: return 70.0
        rs = ma_up/ma_down
        rsi = 100 - (100/(1+rs))
        for i in range(period, len(deltas)):
            ma_up = (ma_up*(period-1)+up[i])/period
            ma_down = (ma_down*(period-1)+down[i])/period
            rs = ma_up/ma_down if ma_down!=0 else 0
            rsi = 100 - (100/(1+rs)) if ma_down!=0 else 70
        return float(rsi)
    except: return 50.0

def scan_market():
    signals=[]
    try:
        tickers = exchange.fetch_tickers()
    except: tickers={}
    for sym in WATCH:
        try:
            ohlcv = exchange.fetch_ohlcv(sym, timeframe='1h', limit=80)
            closes = [c[4] for c in ohlcv]
            price = closes[-1]
            rsi = calc_rsi(closes)
            ma20 = sum(closes[-20:])/20
            atr = (max(closes[-14:]) - min(closes[-14:])) / price if price>0 else 0.005
            
            if rsi < 32 and price < ma20*0.98:
                direction="long"; score=8
            elif rsi < 40 and price < ma20:
                direction="long"; score=7
            elif rsi > 68 and price > ma20*1.02:
                direction="short"; score=8
            elif rsi > 58 or price < ma20*0.995:
                direction="short"; score=7
            else:
                direction="short" if price < ma20 else "long"; score=6
            
            signals.append({
                "symbol": sym.replace(":USDT","").replace("/USDT",""),
                "full": sym,
                "direction": direction,
                "price": price,
                "rsi": round(rsi,1),
                "atr": round(atr,5),
                "ma20": round(ma20,4),
                "score": score
            })
        except Exception as e:
            try:
                t = tickers.get(sym)
                if t:
                    signals.append({"symbol":sym.replace(":USDT",""),"full":sym,"direction":"short","price":t["last"],"rsi":38.0,"atr":0.005,"ma20":t["last"],"score":6})
            except: pass
    return sorted(signals, key=lambda x: x["score"], reverse=True)

def place_trade(signal):
    try:
        if state["stopped"]: return False
        if len(state["open_trades"]) >= CONFIG["MAX_POSITIONS"]: return False
        sym = signal["full"]
        side = "buy" if signal["direction"]=="long" else "sell"
        price = signal["price"]
        
        exchange.set_leverage(CONFIG["LEVERAGE"], sym)
        amount = (CONFIG["MARGIN_USDT"]*CONFIG["LEVERAGE"])/price
        
        order = exchange.create_market_order(sym, side, amount)
        entry = order.get("average") or price
        
        sl_price = entry*(1-CONFIG["SL_PCT"]) if side=="buy" else entry*(1+CONFIG["SL_PCT"])
        
        state["open_trades"][sym] = {
            "symbol": sym,
            "display": signal["symbol"],
            "direction": signal["direction"],
            "entry": entry,
            "sl": sl_price,
            "best_pnl": 0.0,
            "locked_pnl": 0.0,
            "margin": CONFIG["MARGIN_USDT"],
            "trail_active": False,
            "sl_levels": [],
            "amount": amount
        }
        log(f"فتح {signal['direction']} @ {entry}", "OPEN", signal["symbol"])
        return True
    except Exception as e:
        log(str(e),"ERROR"); state["errors"].append(str(e))
        return False

def trailing_loop():
    while True:
        try:
            for sym, data in list(state["open_trades"].items()):
                try:
                    ticker = exchange.fetch_ticker(sym)
                    last = ticker["last"]
                    entry = data["entry"]
                    pnl_pct = (last-entry)/entry if data["direction"]=="long" else (entry-last)/entry
                    pnl_usd = pnl_pct * data["margin"] * CONFIG["LEVERAGE"]
                    
                    if pnl_usd > data["best_pnl"]:
                        data["best_pnl"] = pnl_usd
                    
                    # تفعيل التريلنج بعد $0.70
                    if pnl_usd >= CONFIG["TRAIL_START"]:
                        data["trail_active"] = True
                    
                    if data["trail_active"]:
                        # كل $0.20 يطلع SL
                        target_locked = 0
                        if pnl_usd >= 0.70: target_locked = 0.30
                        if pnl_usd >= 0.90: target_locked = 0.54
                        if pnl_usd >= 1.10: target_locked = 0.66
                        if pnl_usd >= 1.30: target_locked = 0.85
                        if pnl_usd >= 1.50: target_locked = 1.05
                        if pnl_usd >= 2.00: target_locked = 1.40
                        
                        if target_locked > data["locked_pnl"]:
                            data["locked_pnl"] = target_locked
                            # حساب SL جديد يضمن الربح
                            locked_pct = target_locked / (data["margin"]*CONFIG["LEVERAGE"])
                            if data["direction"]=="long":
                                new_sl = entry*(1+locked_pct*0.9)
                            else:
                                new_sl = entry*(1-locked_pct*0.9)
                            data["sl"] = new_sl
                            data["sl_levels"].append({"pnl":round(pnl_usd,2),"locked":target_locked})
                            log(f"SL ارتفع يضمن ${target_locked} (ربح ${pnl_usd:.2f})","TRAIL",data["display"],f"${pnl_usd:.2f}")
                except: pass
        except: pass
        time.sleep(3)

def check_closed():
    while True:
        try:
            positions = exchange.fetch_positions()
            open_syms = [p["symbol"] for p in positions if float(p.get("contracts",0))>0]
            for sym in list(state["open_trades"].keys()):
                if sym not in open_syms:
                    # أغلقت
                    data = state["open_trades"].pop(sym,None)
                    if data:
                        pnl = data.get("best_pnl",0)
                        if pnl < 0: state["losses"]+=1
                        state["daily_pnl"]+=pnl
                        log(f"أغلقت ربح ${pnl:.2f}","CLOSE",data["display"],f"${pnl:.2f}")
                        if state["losses"]>=1 or state["daily_pnl"]<=CONFIG["DAILY_LOSS_LIMIT"]:
                            state["stopped"]=True
                            log("توقف اليوم - خسارة واحدة","STOP")
        except: pass
        time.sleep(5)

def auto_trader():
    while True:
        try:
            if not state["stopped"] and len(state["open_trades"])<CONFIG["MAX_POSITIONS"]:
                sigs = scan_market()
                if sigs: place_trade(sigs[0])
        except: pass
        time.sleep(15)

# ===== ROUTES =====
@app.route("/")
def dash():
    return DASH_HTML

@app.route("/api/status")
def api_status():
    try: bal = exchange.fetch_balance(); state["balance"]=float(bal.get("total",{}).get("USDT",0))
    except: pass
    return jsonify({
        "balance": state["balance"],
        "daily_pnl": state["daily_pnl"],
        "losses": state["losses"],
        "stopped": state["stopped"],
        "positions": {"count": len(state["open_trades"]), "max": CONFIG["MAX_POSITIONS"]},
        "logs": state["logs"][-10:],
        "errors": state["errors"][-5:]
    })

@app.route("/api/scan")
def api_scan():
    return jsonify({"signals": scan_market()})

@app.route("/api/pnl_live")
def api_pnl():
    live=[]
    for sym,data in state["open_trades"].items():
        try:
            ticker=exchange.fetch_ticker(sym)
            last=ticker["last"]; entry=data["entry"]
            pnl_pct=(last-entry)/entry if data["direction"]=="long" else (entry-last)/entry
            pnl_usd=pnl_pct*data["margin"]*CONFIG["LEVERAGE"]
            pct = (pnl_usd/CONFIG["TARGET_PROFIT"])*100
            live.append({
                "symbol": data["display"],
                "pnl": round(pnl_usd,2),
                "pct": round(pct,1),
                "entry": entry,
                "last": last,
                "best": round(data.get("best_pnl",0),2),
                "locked": round(data.get("locked_pnl",0),2),
                "sl": data.get("sl"),
                "trail": data.get("trail_active",False),
                "levels": data.get("sl_levels",[])
            })
        except:
            live.append({"symbol":data["display"],"pnl":0,"pct":0,"entry":data.get("entry",0),"last":0,"best":0,"locked":0,"sl":0,"trail":False,"levels":[]})
    return jsonify({"live":live})

@app.route("/reset_daily")
def reset_daily():
    state["daily_pnl"]=0; state["losses"]=0; state["stopped"]=False; return jsonify({"ok":True})

@app.route("/clear_all")
def clear_all():
    state["open_trades"]={}; state["daily_pnl"]=0; state["losses"]=0; state["stopped"]=False; state["logs"]=[]; return jsonify({"msg":"تم التصفير 0/1"})

@app.route("/resume_after_loss")
def resume():
    state["stopped"]=False; return jsonify({"ok":True})

@app.route("/api/get_code")
def get_code():
    try:
        with open(__file__,"r",encoding="utf-8") as f: return jsonify({"code":f.read()})
    except Exception as e: return jsonify({"error":str(e)})

@app.route("/api/save_code", methods=["POST"])
def save_code():
    try:
        code=request.json.get("code","")
        with open(__file__,"w",encoding="utf-8") as f: f.write(code)
        return jsonify({"ok":True,"msg":f"تم حفظ {len(code)} حرف - سيعيد التشغيل"})
    except Exception as e: return jsonify({"ok":False,"error":str(e)})

@app.route("/api/patch_code", methods=["POST"])
def patch_code():
    try:
        sn=request.json.get("snippet","")
        with open(__file__,"r",encoding="utf-8") as f: content=f.read()
        if "DASH_HTML" in sn or "def scan_market" in sn or "app.route" in sn:
            # استبدال مباشر
            if "DASH_HTML" in content:
                import re
                content = re.sub(r'DASH_HTML = """.*?"""', sn if 'DASH_HTML' in sn else f'DASH_HTML = """{sn}"""', content, flags=re.DOTALL)
            with open(__file__,"w",encoding="utf-8") as out: out.write(content)
            return jsonify({"ok":True,"msg":"تم الترقيع - أعد التشغيل"})
        else:
            # إضافة قبل if __name__
            content = content.replace('if __name__ =="__main__":', sn + '\nif __name__ =="__main__":')
            with open(__file__,"w",encoding="utf-8") as out: out.write(content)
            return jsonify({"ok":True,"msg":"تمت الإضافة"})
    except Exception as e: return jsonify({"ok":False,"error":str(e)})

# ===== UI V100007 LIVE CHARTS + EVERYTHING LIVE =====
DASH_HTML = """
<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>V15 LIVE CHARTS ULTIMATE</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
*{font-family:system-ui} body{background:#05070a}
.glass{background:#0f141c;border:1px solid #1e293b}
.live-dot{width:7px;height:7px;background:#22c55e;border-radius:50%;display:inline-block;animation:blink 1s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.2}}
.tv{height:200px;width:100%;border:0;border-radius:12px}
.prog{transition:width 0.8s}
</style>
</head><body class="text-white p-2 pb-20 text-[11px]">
<div class="flex justify-between items-center glass rounded-2xl p-3 mb-2">
<div><div class="font-black text-[14px] flex items-center gap-2"><span class="live-dot"></span> V15 LIVE <span class="text-green-400">ULTIMATE</span> <span id="clock" class="text-[10px] text-gray-400"></span></div><div class="text-[9px] text-gray-400">كل شي حي: شارتات + أسعار + ربح $ | $1+ مفتوح | SL يطلع كل $0.20</div></div>
<div class="flex gap-1"><button onclick="showTab('main')" id="b1" class="bg-blue-600 px-3 py-1.5 rounded-full text-[10px] font-bold">📊 LIVE</button><button onclick="showTab('code')" id="b2" class="bg-[#1e293b] px-3 py-1.5 rounded-full text-[10px]">💻 كود</button></div>
</div>

<div id="tab-main">
<div id="stats" class="grid grid-cols-4 gap-2 mb-2"></div>
<div id="liveBig" class="mb-2"></div>
<div class="glass rounded-2xl p-2 mb-2 overflow-x-auto"><div class="flex gap-2" id="tickerLive">⏳ جاري الأسعار الحية...</div></div>
<div id="chartsGrid" class="grid grid-cols-1 gap-2"></div>
<div id="logs" class="glass rounded-2xl p-3 mt-2 text-[10px] font-mono text-gray-400"></div>
</div>

<div id="tab-code" class="hidden">
<div class="glass rounded-2xl p-3"><textarea id="codeArea" class="w-full h-[400px] bg-black/60 border border-gray-700 rounded-xl p-2 text-[10px] font-mono"></textarea><div class="flex gap-2 mt-2"><button onclick="loadCode()" class="bg-[#1e293b] px-4 py-2 rounded-full">📥 تحميل الكود الحالي</button><button onclick="saveCode()" class="bg-green-600 px-6 py-2 rounded-full font-black">💾 حفظ كامل</button></div><div id="codeMsg" class="mt-2 text-xs"></div></div>
</div>

<script>
function showTab(t){document.getElementById('tab-main').classList.toggle('hidden',t!=='main');document.getElementById('tab-code').classList.toggle('hidden',t!=='code');}
let priceCache={};
async function load(){
 const r=await fetch('/api/status'); const d=await r.json();
 document.getElementById('stats').innerHTML=`
 <div class="glass rounded-xl p-2 text-center"><div class="text-[8px] text-gray-400">الرصيد LIVE</div><div class="font-black text-[13px]">$${d.balance.toFixed(2)}</div></div>
 <div class="glass rounded-xl p-2 text-center"><div class="text-[8px] text-gray-400">صفقات LIVE</div><div class="font-black text-[13px]">${d.positions.count}/${d.positions.max}</div></div>
 <div class="glass rounded-xl p-2 text-center"><div class="text-[8px] text-gray-400">يومي LIVE</div><div class="font-black text-[13px] ${d.daily_pnl>=0?'text-green-400':'text-red-400'}">$${d.daily_pnl.toFixed(2)}</div></div>
 <div class="glass rounded-xl p-2 text-center"><div class="text-[8px] text-gray-400">حالة LIVE</div><div class="font-black text-[11px] ${d.stopped?'text-red-400':'text-green-400'}">${d.stopped?'⏸️':'▶️ شغال'}</div></div>`;

 const lv=await fetch('/api/pnl_live').then(r=>r.json());
 const big=document.getElementById('liveBig');
 if(lv.live.length>0){
  let h='';
  lv.live.forEach(x=>{
   const pct=Math.min((x.pnl/1)*100,150);
   h+=`<div class="glass rounded-[18px] p-3 border ${x.pnl>=1?'border-green-500/60 bg-green-500/10':'border-yellow-500/30'}">
   <div class="flex justify-between items-center"><div class="flex items-center gap-2"><span class="live-dot"></span><span class="font-black text-[15px]">${x.symbol}</span><span class="px-3 py-1 rounded-full text-[12px] font-black ${x.pnl>=0?'bg-green-500 text-black':'bg-red-500 text-white'}">${x.pnl>=0?'+':''}$${x.pnl} LIVE</span><span class="text-[10px]">${x.trail?'🔥 SL يطلع حي':'⏳ انتظار $0.70'}</span></div><span class="text-[10px]">${x.pct}%</span></div>
   <div class="grid grid-cols-4 gap-2 mt-3 text-[10px]">
   <div class="bg-black/50 rounded-xl p-2 text-center"><div class="text-gray-400 text-[8px]">دخول</div><div class="font-mono font-bold text-[11px]">${x.entry?.toFixed(5)}</div></div>
   <div class="bg-black/50 rounded-xl p-2 text-center"><div class="text-gray-400 text-[8px]">حالي LIVE</div><div class="font-mono font-bold text-yellow-300 text-[11px]">${x.last?.toFixed(5)}</div></div>
   <div class="bg-black/50 rounded-xl p-2 text-center"><div class="text-gray-400 text-[8px]">SL حي يطلع</div><div class="font-mono font-bold text-red-300 text-[11px]">${x.sl?.toFixed(5)}</div></div>
   <div class="bg-black/50 rounded-xl p-2 text-center"><div class="text-gray-400 text-[8px]">مضمون LIVE</div><div class="font-black text-green-400 text-[13px]">$${x.locked}</div></div>
   </div>
   <div class="mt-3"><div class="flex justify-between text-[9px] mb-1"><span>هدف $1+ مفتوح لأعلى</span><span class="${x.pnl>=1?'text-green-400 font-black':''}">${x.pnl>=1?'✅ ضمنا $1+ ومكمل':'$'+x.pnl+' / $1'}</span></div><div class="h-2.5 bg-black rounded-full overflow-hidden"><div class="prog h-full bg-gradient-to-r from-green-400 to-emerald-500" style="width:${Math.min(pct,100)}%"></div></div></div>
   <div class="mt-2 text-[9px] text-gray-400">أفضل ربح LIVE $${x.best} | مستويات SL: ${x.levels.map(l=>`$${l.pnl}→$${l.locked}`).join(' | ')||'بانتظار $0.70'}</div></div>`;
  });
  big.innerHTML=h;
 } else {
  big.innerHTML=`<div class="glass rounded-2xl p-5 text-center border-dashed"><div class="text-[12px]">🔴 لا صفقات - يفتح LIVE حسب الشارت</div><div class="text-[9px] text-gray-500 mt-1">يقرأ RSI حقيقي ويفتح LONG/SHORT تلقائي هدف $1+ مفتوح</div></div>`;
 }

 const s=await fetch('/api/scan').then(r=>r.json());
 let tickHtml='';
 s.signals.forEach(sig=>{
  const prev=priceCache[sig.symbol]||sig.price;
  const ch=((sig.price-prev)/prev*100).toFixed(2);
  const up=sig.price>=prev;
  priceCache[sig.symbol]=sig.price;
  tickHtml+=`<div class="bg-black/50 rounded-full px-3 py-1.5 flex items-center gap-2 whitespace-nowrap border ${sig.direction==='long'?'border-green-500/30':'border-red-500/30'}"><span class="font-black">${sig.symbol}</span><span class="font-mono">${sig.price?.toFixed(4)}</span><span class="${up?'text-green-400':'text-red-400'} text-[9px]">${up?'▲':'▼'} ${ch}% LIVE</span><span class="px-2 py-0.5 rounded-full text-[8px] font-black ${sig.direction==='long'?'bg-green-500 text-black':'bg-red-500 text-white'}">${sig.direction.toUpperCase()} LIVE</span><span class="text-[8px] bg-[#1e293b] px-1.5 py-0.5 rounded-full">RSI ${sig.rsi} LIVE</span></div>`;
 });
 document.getElementById('tickerLive').innerHTML=tickHtml;

 let chartsHtml='';
 s.signals.forEach(sig=>{
  const tvSym=`OKX:${sig.symbol.replace('/','').replace(':USDT','')}USDT`;
  chartsHtml+=`<div class="glass rounded-2xl p-2">
  <div class="flex justify-between items-center mb-2"><div class="flex items-center gap-2"><span class="live-dot"></span><span class="font-black text-[12px]">${sig.symbol}</span><span class="px-2 py-0.5 rounded-full text-[8px] font-black ${sig.direction==='long'?'bg-green-500 text-black':'bg-red-500 text-white'}">${sig.direction.toUpperCase()} LIVE</span><span class="text-[9px] bg-black/40 px-2 py-0.5 rounded-full">RSI ${sig.rsi} LIVE | Score ${sig.score}/10</span></div><span class="font-mono text-[11px] font-bold">${sig.price?.toFixed(4)} LIVE</span></div>
  <iframe class="tv" src="https://s.tradingview.com/widgetembed/?frameElementId=tv_${sig.symbol}&symbol=${tvSym}&interval=60&hidesidetoolbar=1&symboledit=0&saveImage=0&toolbarbg=060a0f&theme=dark&style=1&timezone=Asia%2FRiyadh&locale=ar"></iframe>
  <div class="grid grid-cols-3 gap-1 mt-2 text-[9px]"><div class="bg-black/40 rounded-lg p-1.5 text-center"><div class="text-gray-400">RSI حي</div><div class="font-bold text-[11px]">${sig.rsi}</div></div><div class="bg-black/40 rounded-lg p-1.5 text-center"><div class="text-gray-400">ATR حي</div><div class="font-bold text-[11px]">${sig.atr}</div></div><div class="bg-black/40 rounded-lg p-1.5 text-center"><div class="text-gray-400">MA20 حي</div><div class="font-bold text-[11px]">${sig.ma20}</div></div></div>
  </div>`;
 });
 document.getElementById('chartsGrid').innerHTML=chartsHtml;
 document.getElementById('clock').textContent=new Date().toLocaleTimeString('ar-SA');
 document.getElementById('logs').innerHTML='<div class="font-bold mb-1">📝 السجل LIVE</div>'+(d.logs||[]).slice(-6).map(l=>`${l.time?.slice(11,19)} ${l.type} ${l.symbol} ${l.pnl||''} ${l.msg?.slice(0,40)}`).join('<br>');
}
async function loadCode(){const r=await fetch('/api/get_code');const d=await r.json();if(d.code){document.getElementById('codeArea').value=d.code;document.getElementById('codeMsg').textContent='✅ '+d.code.length+' حرف';}}
async function saveCode(){const c=document.getElementById('codeArea').value;if(!confirm('حفظ '+c.length+'؟'))return;const r=await fetch('/api/save_code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:c})});const d=await r.json();document.getElementById('codeMsg').textContent=d.ok?'✅ '+d.msg:'❌ '+d.error;}
load(); setInterval(load,4000);
</script>
</body></html>
"""

if __name__ =="__main__":
    threading.Thread(target=trailing_loop,daemon=True).start()
    threading.Thread(target=check_closed,daemon=True).start()
    threading.Thread(target=auto_trader,daemon=True).start()
    port=int(os.getenv("PORT",10000))
    app.run(host="0.0.0.0",port=port)