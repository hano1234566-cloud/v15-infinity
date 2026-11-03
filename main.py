# ===== V100005 FINAL - $1+ INFINITY + SL يطلع مع الربح =====
# الصق هذا كامل

import os, json, time, re, threading
from datetime import datetime, timezone
from flask import Flask, jsonify, request
import ccxt

app = Flask(__name__)

CONFIG = {
    "MAX_POSITIONS":1,
    "MARGIN_PER_TRADE":3.0,
    "LEVERAGE":5,
    "STOP_LOSS":0.008,  # 0.8% SL ابتدائي إجباري
    "DOLLAR_TARGET":1.0, # $1 حد أدنى
    "TRAIL_START":0.70,  # يبدأ يرفع SL بعد $0.70
    "TRAIL_LOCK_PCT":0.60, # يضمن 60% من الربح
    "TRAIL_STEP_USD":0.20, # كل $0.20 ربح جديد يرفع SL
    "MAX_CONSEC_LOSS":1,
}

STATE_FILE="bot_state.json"
state={"open_trades":{},"daily_pnl":0.0,"consecutive_losses":0,"stopped_by_loss":False,"stopped_reason":"","errors":[],"trade_logs":[]}

def load_state():
    global state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE,"r",encoding="utf-8") as f: state.update(json.load(f))
        except: pass
def save_state():
    try:
        with open(STATE_FILE,"w",encoding="utf-8") as f: json.dump(state,f,ensure_ascii=False)
    except: pass
def save_log(e):
    state["trade_logs"].append(e); state["trade_logs"]=state["trade_logs"][-100:]; save_state()
load_state()

exchange=None
try:
    exchange=ccxt.okx({"apiKey":os.getenv("OKX_API_KEY"),"secret":os.getenv("OKX_SECRET"),"password":os.getenv("OKX_PASSWORD"),"enableRateLimit":True,"options":{"defaultType":"swap"}})
except Exception as ex: state["errors"].append(str(ex))

def get_positions():
    try:
        poss=exchange.fetch_positions()
        fil=[p for p in poss if float(p.get("contracts") or 0)>0]
        return len(fil),len(fil),fil,[p["symbol"] for p in fil]
    except: return 0,0,[],[]

def get_amount(sym,margin,price): return (margin*CONFIG["LEVERAGE"])/price if price>0 else 0

def get_targets(entry,direction,margin,lev):
    notional=margin*lev
    tp_pct=max(CONFIG["DOLLAR_TARGET"]/notional,0.012)
    tp_pct=min(tp_pct,0.05)
    if direction=="long": return {"tp":entry*(1+tp_pct),"sl":entry*(1-CONFIG["STOP_LOSS"]),"tp_pct":tp_pct}
    else: return {"tp":entry*(1-tp_pct),"sl":entry*(1+CONFIG["STOP_LOSS"]),"tp_pct":tp_pct}

def place_trade(signal):
    total,cnt,_,open_syms=get_positions()
    if cnt>=CONFIG["MAX_POSITIONS"]: return {"ok":False,"reason":"FULL"}
    if state["stopped_by_loss"]: return {"ok":False,"reason":"STOPPED"}
    base=signal["symbol"].split("/")[0]; swap=base+"/USDT:USDT"
    if any(base in s for s in open_syms): return {"ok":False}
    try:
        margin=CONFIG["MARGIN_PER_TRADE"]; amount=get_amount(swap,margin,signal["price"])
        if amount==0: return {"ok":False}
        try: exchange.set_leverage(CONFIG["LEVERAGE"],swap,{"mgnMode":"isolated"})
        except: pass
        side="buy" if signal["direction"]=="long" else "sell"; posSide="long" if signal["direction"]=="long" else "short"
        order=exchange.create_order(swap,"market",side,amount,None,{"tdMode":"isolated","posSide":posSide,"lever":str(CONFIG["LEVERAGE"])})
        avg=float(order.get("average") or signal["price"]); filled=float(order.get("filled") or amount)
        t=get_targets(avg,signal["direction"],margin,CONFIG["LEVERAGE"])
        for _ in range(3):
            try:
                exchange.create_order(swap,"market","sell" if signal["direction"]=="long" else "buy",filled,None,{"tdMode":"isolated","posSide":posSide,"stopLoss":{"triggerPrice":t["sl"],"orderPrice":"-1"}})
                exchange.create_order(swap,"market","sell" if signal["direction"]=="long" else "buy",filled,None,{"tdMode":"isolated","posSide":posSide,"takeProfit":{"triggerPrice":t["tp"],"orderPrice":"-1"}})
                break
            except: time.sleep(0.5)
        state["open_trades"][swap]={"entry":avg,"direction":signal["direction"],"margin":margin,"amount":filled,"time":datetime.now(timezone.utc).isoformat(),"sl":t["sl"],"tp":t["tp"],"tp_pct":t["tp_pct"],"trail_active":False,"best_pnl":0,"locked_pnl":0,"best_price":avg,"sl_levels":[]}
        save_state()
        save_log({"time":datetime.now(timezone.utc).isoformat(),"type":"ENTRY $1+","symbol":swap,"dir":signal["direction"],"entry":avg,"sl":t["sl"],"tp":t["tp"]})
        return {"ok":True,"symbol":swap}
    except Exception as e: state["errors"].append(str(e)[-200:]); return {"ok":False,"error":str(e)}

def check_closed():
    closed=[]
    for sym,data in list(state["open_trades"].items()):
        try:
            poss=exchange.fetch_positions(); still=any(float(p.get("contracts") or 0)>0 and p["symbol"]==sym for p in poss)
            if not still:
                try:
                    ticker=exchange.fetch_ticker(sym); last=ticker["last"]; entry=data["entry"]
                    pnl_pct=(last-entry)/entry if data["direction"]=="long" else (entry-last)/entry
                    pnl_usd=pnl_pct*data["margin"]*CONFIG["LEVERAGE"]
                except: pnl_usd=data.get("locked_pnl",-0.5)
                state["daily_pnl"]+=pnl_usd
                if pnl_usd<0:
                    state["consecutive_losses"]+=1; state["stopped_by_loss"]=True; state["stopped_reason"]=f"خسارة ${pnl_usd:.2f} في {sym}"
                else: state["consecutive_losses"]=0; state["stopped_by_loss"]=False
                closed.append(sym); del state["open_trades"][sym]
                save_log({"time":datetime.now(timezone.utc).isoformat(),"type":"CLOSE","symbol":sym,"pnl":round(pnl_usd,2)})
                save_state()
        except: pass
    return closed

def can_open(): 
    check_closed()
    _,cnt,_,_=get_positions()
    return cnt==0 and len(state["open_trades"])==0 and not state["stopped_by_loss"]

def trailing_loop():
    while True:
        try:
            for sym,data in list(state["open_trades"].items()):
                try:
                    ticker=exchange.fetch_ticker(sym); last=ticker["last"]; entry=data["entry"]; direction=data["direction"]
                    notional=data["margin"]*CONFIG["LEVERAGE"]
                    pnl_pct=(last-entry)/entry if direction=="long" else (entry-last)/entry
                    pnl_usd=pnl_pct*notional

                    # 1- فعل التريلنج بعد $0.70
                    if pnl_usd>=CONFIG["TRAIL_START"] and not data.get("trail_active"):
                        data["trail_active"]=True
                        data["best_pnl"]=pnl_usd
                        # ارفع SL لربح +$0.30 مضمون
                        lock_pnl=0.30
                        lock_pct=lock_pnl/notional
                        new_sl=entry*(1+lock_pct) if direction=="long" else entry*(1-lock_pct)
                        try:
                            exchange.create_order(sym,"market","sell" if direction=="long" else "buy",data["amount"],None,{"tdMode":"isolated","posSide":direction,"stopLoss":{"triggerPrice":new_sl,"orderPrice":"-1"}})
                            data["sl"]=new_sl; data["locked_pnl"]=lock_pnl; data["sl_levels"].append({"pnl":pnl_usd,"sl":new_sl,"locked":lock_pnl})
                            save_log({"time":datetime.now(timezone.utc).isoformat(),"type":"SL UP $0.70→$0.30","symbol":sym,"pnl":round(pnl_usd,2),"new_sl":new_sl})
                            save_state()
                        except: pass

                    # 2- كل $0.20 زيادة ارفع SL
                    if data.get("trail_active") and pnl_usd > data.get("best_pnl",0)+CONFIG["TRAIL_STEP_USD"]:
                        data["best_pnl"]=pnl_usd
                        # اضمن 60% من الربح
                        lock_pnl=pnl_usd*CONFIG["TRAIL_LOCK_PCT"]
                        lock_pct=lock_pnl/notional
                        new_sl=entry*(1+lock_pct) if direction=="long" else entry*(1-lock_pct)
                        # ارفع فقط إذا أعلى من القديم
                        if (direction=="long" and new_sl>data["sl"]) or (direction=="short" and new_sl<data["sl"]):
                            try:
                                exchange.create_order(sym,"market","sell" if direction=="long" else "buy",data["amount"],None,{"tdMode":"isolated","posSide":direction,"stopLoss":{"triggerPrice":new_sl,"orderPrice":"-1"}})
                                data["sl"]=new_sl; data["locked_pnl"]=lock_pnl; data["sl_levels"].append({"pnl":round(pnl_usd,2),"sl":new_sl,"locked":round(lock_pnl,2)})
                                save_log({"time":datetime.now(timezone.utc).isoformat(),"type":f"SL UP ${pnl_usd:.2f}→${lock_pnl:.2f}","symbol":sym,"best":round(pnl_usd,2),"locked":round(lock_pnl,2)})
                                save_state()
                            except: pass

                    if direction=="long":
                        if last>data.get("best_price",entry): data["best_price"]=last
                    else:
                        if last<data.get("best_price",entry): data["best_price"]=last
                    save_state()
                except: continue
            time.sleep(8)
        except: time.sleep(8)

if not hasattr(app,'trail_started'):
    threading.Thread(target=trailing_loop,daemon=True).start()
    app.trail_started=True

def scan_market():
    sigs=[]
    try:
        tickers=exchange.fetch_tickers()
        watch=["ENA/USDT:USDT","FET/USDT:USDT","TAO/USDT:USDT","RENDER/USDT:USDT","SUI/USDT:USDT"]
        for sym in watch:
            t=tickers.get(sym)
            if t: sigs.append({"symbol":sym.replace(":USDT",""),"direction":"short","price":t["last"],"score":7})
    except: pass
    return sigs

@app.route("/")
def dash(): return DASH_HTML
@app.route("/api/status")
def st():
    try: bal=exchange.fetch_balance(); usdt=float(bal.get("total",{}).get("USDT",58))
    except: usdt=58.33
    total,cnt,_,_=get_positions()
    return jsonify({"balance":usdt,"positions":{"count":cnt,"max":CONFIG["MAX_POSITIONS"]},"losses":state["consecutive_losses"],"daily_pnl":state["daily_pnl"],"stopped":state["stopped_by_loss"],"open":state["open_trades"],"config":CONFIG,"logs":state["trade_logs"][-10:]})
@app.route("/api/scan")
def sc():
    closed=check_closed(); sigs=scan_market(); opened=[]
    if can_open() and sigs:
        best=sorted(sigs,key=lambda x:x["score"],reverse=True)[0]
        r=place_trade(best)
        if r.get("ok"): opened.append(r)
    return jsonify({"closed":closed,"signals":sigs,"opened":opened,"can_open":can_open()})
@app.route("/reset_daily")
def rd(): state["daily_pnl"]=0.0; state["consecutive_losses"]=0; state["stopped_by_loss"]=False; state["stopped_reason"]=""; save_state(); return jsonify({"reset":True})
@app.route("/clear_all")
def ca(): state["open_trades"]={}; state["daily_pnl"]=0.0; state["consecutive_losses"]=0; state["stopped_by_loss"]=False; save_state(); return jsonify({"cleared":True})
@app.route("/resume_after_loss")
def ral(): state["stopped_by_loss"]=False; state["consecutive_losses"]=0; save_state(); return jsonify({"resumed":True})
@app.route("/api/get_code")
def gc(): 
    try:
        with open(__file__,"r",encoding="utf-8") as f: return jsonify({"code":f.read()})
    except Exception as e: return jsonify({"error":str(e)})
@app.route("/api/save_code",methods=["POST"])
def sv():
    try:
        data=request.get_json(); nc=data.get("code","")
        if len(nc)<500: return jsonify({"ok":False,"error":"قصير"})
        with open(__file__+".bak","w",encoding="utf-8") as f: f.write(open(__file__,"r",encoding="utf-8").read())
        with open(__file__,"w",encoding="utf-8") as f: f.write(nc)
        return jsonify({"ok":True,"msg":"تم الحفظ"})
    except Exception as e: return jsonify({"ok":False,"error":str(e)})
@app.route("/api/patch_code",methods=["POST"])
def pc():
    try:
        data=request.get_json(); sn=data.get("snippet","").strip()
        if not sn: return jsonify({"ok":False,"error":"فارغ"})
        with open(__file__,"r",encoding="utf-8") as f: content=f.read()
        content=content.replace('if __name__=="__main__":', sn+'\n\nif __name__=="__main__":')
        with open(__file__+".bak","w",encoding="utf-8") as f: f.write(open(__file__,"r",encoding="utf-8").read())
        with open(__file__,"w",encoding="utf-8") as f: f.write(content)
        return jsonify({"ok":True,"msg":"✅ ترقيع تلقائي"})
    except Exception as e: return jsonify({"ok":False,"error":str(e)})
@app.route("/api/pnl_live")
def pnl():
    live=[]
    for sym,data in state["open_trades"].items():
        try:
            ticker=exchange.fetch_ticker(sym); last=ticker["last"]; entry=data["entry"]
            pnl_pct=(last-entry)/entry if data["direction"]=="long" else (entry-last)/entry
            pnl_usd=pnl_pct*data["margin"]*CONFIG["LEVERAGE"]
            live.append({"symbol":sym,"pnl":round(pnl_usd,2),"best":round(data.get("best_pnl",0),2),"locked":round(data.get("locked_pnl",0),2),"sl":data.get("sl"),"trail":data.get("trail_active"),"levels":data.get("sl_levels",[])})
        except: live.append({"symbol":sym,"pnl":0})
    return jsonify({"live":live})

DASH_HTML="""
<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>V100005 SL UP</title><script src="https://cdn.tailwindcss.com"></script>
<style>.mono{font-family:monospace}.card{background:#161b22;border:1px solid #30363d}</style>
</head><body class="bg-[#0d1117] text-white p-3 text-sm">
<h1 class="font-bold text-lg mb-2">🚀 V100005 - $1+ مع SL يطلع</h1>
<div class="flex gap-2 mb-3">
<button onclick="showTab('main')" class="bg-blue-700 px-3 py-1 rounded text-xs">📊 رئيسي</button>
<button onclick="showTab('code')" class="bg-gray-800 px-3 py-1 rounded text-xs">💻 محرر</button>
</div>
<div id="tab-main">
<div id="status" class="card rounded p-3 mb-3">...</div>
<div class="flex gap-2 mb-3 flex-wrap">
<button onclick="fetch('/reset_daily').then(()=>load())" class="bg-yellow-700 px-3 py-1 rounded text-xs">إعادة ضبط</button>
<button onclick="fetch('/clear_all').then(()=>load())" class="bg-red-700 px-3 py-1 rounded text-xs">تصفير 0/1</button>
<button onclick="fetch('/resume_after_loss').then(()=>load())" class="bg-green-700 px-3 py-1 rounded text-xs">استئناف بعد خسارة</button>
<button onclick="fetch('/api/scan').then(()=>load())" class="bg-blue-700 px-3 py-1 rounded text-xs">🔍 افتح صفقة $1+</button>
</div>
<div id="live" class="card rounded p-3 mb-3"></div>
<div id="signals" class="card rounded p-3"></div>
</div>
<div id="tab-code" class="hidden">
<div class="card rounded p-4">
<h3 class="font-bold mb-2">💻 محرر كامل</h3>
<textarea id="codeArea" class="w-full h-[250px] bg-[#0a0e14] border border-gray-700 rounded p-2 text-[10px] mono"></textarea>
<div class="flex gap-2 mt-2">
<button onclick="loadCode()" class="bg-blue-800 px-3 py-2 rounded text-xs">📥 تحميل</button>
<button onclick="saveCode()" class="bg-green-600 px-3 py-2 rounded text-xs">💾 حفظ</button>
</div><div id="codeMsg" class="mt-2 text-xs"></div>
</div>
<div class="card rounded p-4 mt-4 border-green-800">
<h3 class="font-bold mb-2 text-green-400">⚡ ترقيع سريع - سطرين بس</h3>
<textarea id="patchArea" class="w-full h-[80px] bg-[#0a0e14] border border-green-700 rounded p-2 text-[10px] mono"></textarea>
<button onclick="patchCode()" class="bg-green-600 px-3 py-2 rounded text-xs mt-2">⚡ رقع</button>
<div id="patchMsg" class="mt-2 text-xs"></div>
</div>
</div>
<script>
function showTab(t){document.getElementById('tab-main').classList.toggle('hidden',t!=='main');document.getElementById('tab-code').classList.toggle('hidden',t!=='code');}
async function load(){
 const r=await fetch('/api/status'); const d=await r.json();
 document.getElementById('status').innerHTML=`رصيد $${d.balance.toFixed(2)} | صفقات ${d.positions.count}/${d.positions.max} | خسائر ${d.losses} | ربح يومي ${d.daily_pnl} | ${d.stopped?'⏸️ متوقف':'▶️ شغال'}<br>SL ابتدائي 0.8% إجباري | هدف $1+ مفتوح | يرفع SL كل $0.20`;
 const l=await fetch('/api/pnl_live').then(r=>r.json());
 let html=''; l.live.forEach(x=>{html+=`${x.symbol}: ربح $${x.pnl} | أفضل $${x.best} | مضمون $${x.locked} | SL: ${x.sl?.toFixed(4)} | ${x.trail?'🔥 تريلنج شغال':'⏳ انتظار $0.70'}<br>مستويات SL: ${JSON.stringify(x.levels)}<br><br>`});
 document.getElementById('live').innerHTML=html||'لا صفقات - يفتح واحدة $1+';
 const s=await fetch('/api/scan').then(r=>r.json());
 document.getElementById('signals').innerHTML='إشارات: '+(s.signals.map(x=>x.symbol).join(', ')||'لا يوجد')+'<br>مفتوح: '+JSON.stringify(s.opened)+' | يقدر يفتح؟ '+s.can_open;
}
async function loadCode(){const r=await fetch('/api/get_code');const d=await r.json();if(d.code){document.getElementById('codeArea').value=d.code;document.getElementById('codeMsg').textContent='✅ '+d.code.length}}
async function saveCode(){const code=document.getElementById('codeArea').value;const r=await fetch('/api/save_code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});const d=await r.json();document.getElementById('codeMsg').textContent=d.ok?d.msg:d.error;}
async function patchCode(){const sn=document.getElementById('patchArea').value;const r=await fetch('/api/patch_code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({snippet:sn})});const d=await r.json();document.getElementById('patchMsg').textContent=d.ok?d.msg:d.error;if(d.ok)setTimeout(()=>location.reload(),2000);}
load();setInterval(load,10000);
</script>
</body></html>
"""

if __name__=="__main__":
    port=int(os.getenv("PORT",10000))
    app.run(host="0.0.0.0",port=port)