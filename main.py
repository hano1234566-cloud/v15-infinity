import os, time, threading, ccxt, json
from flask import Flask, jsonify
import numpy as np
from datetime import datetime, timedelta

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL = 0.0
LAST = "V30011 - إصلاح الشموع"
SCAN_LOG = "🚀 يبدأ فحص 60"
SCAN_CURRENT = "BTC 1/60"
ALL_RSI = []
SCAN_IDX = 0
FEE = 0.04
BASE_MARGIN = 2.0
COMP_MARGIN = 3.0
LEV = 10
FILE = "/tmp/state_v30011.json"

COINS_60 = ["BTC","ETH","SOL","XRP","BNB","DOGE","ADA","AVAX","DOT","LINK","TRX","LTC","BCH","UNI","PEPE","NEAR","ETC","APT","FIL","STX","MATIC","OP","ARB","HBAR","IMX","MNT","RNDR","TAO","INJ","AR","FET","GRT","LDO","MKR","AAVE","SUI","SEI","WIF","BONK","JUP","ENA","WLD","FLOKI","TIA","PYTH","STRK","JTO","ORDI","SATS","RUNE","FLOW","KAS","BEAM","ARKM","AGIX","XLM","XMR","CRO","VET","ALGO"]

STATE = {"open":{},"closed":[],"blacklist":{},"daily":0,"avail":0,"total":0,"wins":0,"losses":0,"fees":0,"trades":0,"consec_losses":0,"next_margin":BASE_MARGIN,"daily_losses":0}
try:
    if os.path.exists(FILE):
        with open(FILE,'r') as f:
            d=json.load(f)
            for k in STATE:
                if k in d and k not in ["open"]: STATE[k]=d[k]
            STATE["closed"]=d.get("closed",[]); STATE["blacklist"]=d.get("blacklist",{})
            now=datetime.now().timestamp()
            STATE["blacklist"]={k:v for k,v in STATE["blacklist"].items() if v>now}
            if d.get("day","") != datetime.now().strftime("%Y-%m-%d"):
                STATE["daily"]=0; STATE["daily_losses"]=0
except: pass

def save():
    try:
        STATE["day"]=datetime.now().strftime("%Y-%m-%d")
        with open(FILE,'w') as f: json.dump(STATE,f)
    except: pass

app = Flask(__name__)

def get_ex_auth():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'options':{'defaultType':'swap'},'enableRateLimit':True})

def get_ex_public():
    # بدون مفاتيح للشموع - أسرع وما ينحظر
    return ccxt.okx({'options':{'defaultType':'swap'},'enableRateLimit':True})

def get_bal():
    global BAL
    try:
        r=get_ex_auth().private_get_account_balance()
        for item in r['data'][0]['details']:
            if item['ccy']=='USDT':
                STATE["avail"]=float(item['availBal'] or 0); STATE["total"]=float(item['eq'] or 0); BAL=STATE["avail"]; return BAL
    except: pass
    try:
        b=get_ex_auth().fetch_balance()
        BAL=float(b['total'].get('USDT',0) or 0); STATE["total"]=BAL; STATE["avail"]=BAL; return BAL
    except: return BAL

def calc_rsi_safe(prices):
    try:
        if len(prices)<20: return 50
        arr=np.array(prices,float); d=np.diff(arr)
        if len(d)<14: return 50
        up=np.where(d>0,d,0); down=np.where(d<0,-d,0)
        mu=np.mean(up[:14]); md=np.mean(down[:14])
        if md==0: return 70
        rsi=100-(100/(1+mu/md))
        for i in range(14,len(d)):
            mu=(mu*13+up[i])/14; md=(md*13+down[i])/14
            rsi=100-(100/(1+mu/md)) if md!=0 else 70
        return float(rsi)
    except: return 50

def fetch_candles(name):
    # يجرب 3 طرق
    for sym in [f"{name}/USDT:USDT", f"{name}/USDT", f"{name}-USDT"]:
        for ex_func in [get_ex_public, get_ex_auth]:
            try:
                ex=ex_func()
                ohlcv=ex.fetch_ohlcv(sym,'1h',100)
                if ohlcv and len(ohlcv)>=20:
                    closes=[float(c[4]) for c in ohlcv if c and len(c)>=5 and c[4]]
                    if len(closes)>=20 and closes[-1]>0:
                        return closes, sym
            except: continue
    return None, None

def scan_chunk():
    global SCAN_LOG, SCAN_CURRENT, ALL_RSI, SCAN_IDX, LAST
    ex_count=5  # 5 عملات فقط كل مرة عشان Render ما يعلق
    start=SCAN_IDX
    end=min(start+ex_count, 60)
    new_results=[]
    
    for i in range(start, end):
        name=COINS_60[i]
        SCAN_CURRENT=f"{name} {i+1}/60"
        if name in STATE["blacklist"]:
            SCAN_LOG=f"⏭️ {name} محظور"
            continue
        closes, used_sym=fetch_candles(name)
        if not closes:
            SCAN_LOG=f"❌ {name} فشل جلب - يتخطى {i+1}/60"
            time.sleep(0.3)
            continue
        price=closes[-1]
        rsi=calc_rsi_safe(closes)
        new_results.append({"symbol":name,"full":used_sym or f"{name}/USDT:USDT","price":price,"rsi":round(rsi,1)})
        SCAN_LOG=f"✅ {name} RSI {rsi:.1f} {i+1}/60 OK"
        time.sleep(0.4)

    # ادمج
    existing={x["symbol"]:x for x in ALL_RSI}
    for x in new_results: existing[x["symbol"]]=x
    ALL_RSI=list(existing.values())

    SCAN_IDX=end
    if SCAN_IDX>=60:
        SCAN_IDX=0
        LAST=f"✅ اكتمل 60 - {datetime.now().strftime('%H:%M:%S')} - أفضل {sorted(ALL_RSI,key=lambda x: abs(x['rsi']-50),reverse=True)[0]['symbol'] if ALL_RSI else 'لا يوجد'}"
        SCAN_LOG=f"✅ اكتمل 60 عملة - {len(ALL_RSI)}/60 نجح"
    else:
        LAST=f"🔍 يفحص {SCAN_IDX}/60 ... {len(ALL_RSI)} نجح"

    strong=[]; medium=[]
    for x in ALL_RSI:
        r=x["rsi"]
        if r<30: strong.append({**x,"direction":"long","score":10,"type":"قوية 🔥"})
        elif r>70: strong.append({**x,"direction":"short","score":10,"type":"قوية 🔥"})
        elif r<45: medium.append({**x,"direction":"long","score":6,"type":"متوسطة ⚡"})
        elif r>55: medium.append({**x,"direction":"short","score":6,"type":"متوسطة ⚡"})
    
    if not strong and not medium and ALL_RSI:
        best=sorted(ALL_RSI, key=lambda x: abs(x["rsi"]-50), reverse=True)[0]
        direction="long" if best["rsi"]<50 else "short"
        medium.append({**best,"direction":direction,"score":3,"type":"عرضي - الأفضل ⚡"})

    return {"strong":sorted(strong,key=lambda x:x["rsi"]), "medium":sorted(medium,key=lambda x: abs(x["rsi"]-50),reverse=True), "all":ALL_RSI}

def close_any(sym):
    ex=get_ex_auth()
    for mode in [{'tdMode':'isolated'},{'tdMode':'cross'},{'tdMode':'isolated','posSide':'short'},{'tdMode':'isolated','posSide':'long'},{'tdMode':'cross','posSide':'short'},{'tdMode':'cross','posSide':'long'}]:
        try:
            for p in ex.fetch_positions():
                if p['symbol']==sym and float(p.get('contracts',0) or 0)>0:
                    side='buy' if p['side']=='short' else 'sell'
                    return ex.create_market_order(sym, side, float(p.get('contracts',0)), None, mode)
        except: continue
    return None

def hunter():
    global LAST
    get_bal()
    while True:
        try:
            get_bal()
            if STATE["daily_losses"]>=3 or STATE["daily"]<=-3 or STATE["daily"]>=3:
                LAST=f"🛡️ وقف يومي"; time.sleep(60); continue
            try:
                ex=get_ex_auth()
                for p in ex.fetch_positions():
                    if float(p.get('contracts',0) or 0)>0:
                        sym=p['symbol']; name=sym.replace('/USDT:USDT','').replace('/USDT','').replace('-USDT','')
                        gross=float(p.get('unrealizedPnl',0) or 0); net=gross-FEE
                        entry=float(p.get('entryPrice',0) or 0); mark=float(p.get('markPrice',0) or entry)
                        liq=float(p.get('liquidationPrice',0) or 0); side=p.get('side','long')
                        if sym not in STATE["open"]: STATE["open"][sym]={"name":name,"dir":side,"entry":entry,"best":net,"best_net":net}
                        best=STATE["open"][sym].get("best_net",net)
                        if net>best: STATE["open"][sym]["best_net"]=net; best=net
                        should=False; reason=""
                        if net<=-1.0: should=True; reason="ستوب -1$"
                        elif liq>0 and entry>0:
                            if side=='long' and mark <= liq + (entry-liq)*0.15: should=True; reason="تصفية 15%"
                            elif side=='short' and mark >= liq - (liq-entry)*0.15: should=True; reason="تصفية 15%"
                        elif best>=0.5 and net<=best-0.7: should=True; reason="حماية"
                        if should and close_any(sym):
                            closed={"pair":name,"side":side,"pnl":net,"gross":gross,"time":datetime.now().strftime("%H:%M"),"reason":reason}
                            STATE["closed"].insert(0,closed); STATE["closed"]=STATE["closed"][:20]
                            STATE["open"].pop(sym,None); STATE["daily"]+=net; STATE["trades"]+=1; STATE["fees"]+=FEE
                            if net>0: STATE["wins"]+=1; STATE["consec_losses"]=0; STATE["next_margin"]=BASE_MARGIN
                            else: STATE["losses"]+=1; STATE["consec_losses"]+=1; STATE["daily_losses"]+=1; STATE["next_margin"]=COMP_MARGIN
                            if sum(1 for c in STATE["closed"][:5] if c["pair"]==name and c["pnl"]<0)>=2: STATE["blacklist"][name]=(datetime.now()+timedelta(hours=24)).timestamp()
                            save()
            except: pass
            try: live=len([p for p in get_ex_auth().fetch_positions() if float(p.get('contracts',0) or 0)>0])
            except: live=len(STATE["open"])
            open_names=[v["name"] for v in STATE["open"].values()]
            if live<2 and get_bal()>=STATE["next_margin"]:
                res=scan_chunk()
                s_strong=next((s for s in res["strong"] if s["symbol"] not in open_names and s["symbol"] not in STATE["blacklist"]),None)
                s_medium=next((s for s in res["medium"] if s["symbol"] not in open_names and s["symbol"] not in STATE["blacklist"]),None)
                to_open=s_strong or s_medium
                if to_open:
                    try:
                        ex=get_ex_auth(); ex.set_leverage(LEV,to_open["full"])
                        side="buy" if to_open["direction"]=="long" else "sell"; margin=STATE["next_margin"]
                        if get_bal()<4 and margin==COMP_MARGIN: margin=BASE_MARGIN
                        amt=(margin*LEV)/to_open["price"]; amt=float(ex.amount_to_precision(to_open["full"],max(amt,1)))
                        order=None
                        for mode in [{'tdMode':'isolated'},{'tdMode':'cross'}]:
                            try: order=ex.create_market_order(to_open["full"],side,amt,None,mode); break
                            except: continue
                        if order:
                            entry=order.get("average") or to_open["price"]
                            STATE["open"][to_open["full"]]={"name":to_open["symbol"],"dir":to_open["direction"],"entry":entry,"best":0,"best_net":0,"type":to_open["type"],"score":to_open["score"],"rsi":to_open["rsi"]}
                            LAST=f"✅ فتح {to_open['type']} {to_open['symbol']} RSI {to_open['rsi']}"; save()
                    except Exception as e: LAST=f"❌ فتح {str(e)[:40]}"
            time.sleep(4)
        except Exception as e: LAST=f"خطأ {str(e)[:50]}"; time.sleep(5)

@app.route("/", methods=["GET","POST"])
def index(): return HTML
@app.route("/health", methods=["GET","POST"])
def health(): return "OK", 200
@app.route("/api/status", methods=["GET","POST"])
def status(): return jsonify({"bal":get_bal(),"avail":STATE["avail"],"total":STATE["total"],"count":len(STATE["open"]),"last":LAST,"scan_log":SCAN_LOG,"scan_current":SCAN_CURRENT,"scan_count":60,"all_rsi":ALL_RSI,"scan_idx":SCAN_IDX,"daily":STATE["daily"],"wins":STATE["wins"],"losses":STATE["losses"],"trades":STATE["trades"],"fees":STATE["fees"],"next_margin":STATE["next_margin"],"daily_losses":STATE["daily_losses"],"blacklist":list(STATE["blacklist"].keys())})
@app.route("/api/pnl", methods=["GET","POST"])
def pnl():
    live=[]
    try:
        ex=get_ex_auth()
        for p in ex.fetch_positions():
            if float(p.get('contracts',0) or 0)>0:
                entry=float(p.get('entryPrice',0) or 0); last=float(p.get('markPrice',0) or entry)
                gross=float(p.get('unrealizedPnl',0) or 0); mgn=float(p.get('imr',0) or 0); amt=float(p.get('contracts',0) or 0)
                lev=int(float(p.get('leverage',0) or LEV)); liq=float(p.get('liquidationPrice',0) or 0)
                sym=p['symbol']; name=sym.replace('/USDT:USDT','')
                info=STATE["open"].get(sym,{}); best=info.get("best_net",gross-FEE)
                live.append({"sym":name,"full":sym,"side":p.get('side','long'),"gross":gross,"net":gross-FEE,"entry":entry,"last":last,"amt":amt,"mgn":mgn,"lev":lev,"liq":liq,"best":best,"type":info.get("type","-"),"rsi":info.get("rsi",0)})
    except: pass
    return jsonify({"bal":get_bal(),"total":STATE["total"],"live":live,"closed":STATE["closed"],"next_margin":STATE["next_margin"]})
@app.route("/api/scan", methods=["GET","POST"])
def scan(): return jsonify({"all":ALL_RSI,"log":SCAN_LOG,"current":SCAN_CURRENT,"idx":SCAN_IDX})
@app.route("/api/close/<sym>", methods=["GET","POST"])
def close_api(sym):
    try:
        for p in get_ex_auth().fetch_positions():
            if sym in p['symbol'] and float(p.get('contracts',0) or 0)>0:
                close_any(p['symbol']); return jsonify({"ok":True})
        return jsonify({"ok":False})
    except Exception as e: return jsonify({"ok":False,"err":str(e)})

HTML = """<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>V30011 إصلاح</title><script src="https://cdn.tailwindcss.com"></script><style>body{background:#000;color:#fff}.card{background:#111214;border-radius:18px}.glass{background:#111c2f;border:1px solid #1e355a}.live-dot{animation:pulse 1s infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}</style></head><body class="max-w-[480px] mx-auto p-3"><div class="bg-[#111214] rounded-[22px] p-4 border border-green-500/30"><div class="flex justify-between text-[11px] text-gray-400"><span class="flex gap-1 items-center"><span class="w-2 h-2 bg-green-500 rounded-full live-dot"></span>V30011 إصلاح شموع</span><span>60 عملة</span></div><div class="flex gap-2 items-baseline mt-2"><div id="bal" class="text-[30px] font-black">$0</div><div id="total" class="text-[11px] text-gray-500"></div><div id="next" class="text-[10px] bg-yellow-500 text-black px-2 py-0.5 rounded-full font-bold"></div></div><div id="last" class="text-[12px] font-bold mt-2 text-yellow-300"></div><div class="mt-2 bg-black/60 rounded-xl p-2 border border-green-500/30"><div class="flex justify-between text-[10px]"><span class="text-green-400 font-bold">🔍 فحص LIVE</span><span id="scanCurrent" class="text-yellow-300 font-mono">-</span></div><div id="scanLog" class="text-[11px] text-white mt-1 font-mono">بانتظار...</div><div class="mt-2 h-1.5 bg-white/10 rounded-full overflow-hidden"><div id="scanProgress" class="h-full bg-green-500" style="width:0%"></div></div></div><div class="flex gap-2 mt-3 flex-wrap"><span id="cnt" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="daily" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="allCount" class="bg-blue-500/20 px-3 py-1 rounded-full text-[10px]"></span></div></div><div id="liveBig" class="my-3"></div><div class="glass rounded-2xl p-3"><div class="flex justify-between text-[11px] font-black"><span>📊 كل العملات RSI</span><span id="idx" class="bg-white/10 px-2 py-0.5 rounded-full text-[9px]">0</span></div><div id="all" class="space-y-2 mt-2 max-h-[500px] overflow-y-auto"></div></div><script>async function load(){const s=await fetch('/api/status').then(r=>r.json());document.getElementById('bal').textContent=`$${s.bal.toFixed(2)}`;document.getElementById('total').textContent=`/ $${s.total.toFixed(2)} كلي`;document.getElementById('next').textContent=s.next_margin>2?`الجاية $${s.next_margin} تعويض`:`الجاية $${s.next_margin}`;document.getElementById('last').textContent=s.last;document.getElementById('scanLog').textContent=s.scan_log;document.getElementById('scanCurrent').textContent=s.scan_current;document.getElementById('cnt').textContent=s.count+'/2 مفتوح';document.getElementById('daily').textContent=`صافي $${s.daily.toFixed(2)}`;document.getElementById('allCount').textContent=(s.all_rsi||[]).length+'/60';document.getElementById('idx').textContent=s.scan_idx+'/60';const prog=s.scan_count>0?(parseInt(s.scan_current.split('/')[0].replace(/[^0-9]/g,''))||0)/s.scan_count*100:0;document.getElementById('scanProgress').style.width=prog+'%';document.getElementById('all').innerHTML=(s.all_rsi||[]).sort((a,b)=>Math.abs(b.rsi-50)-Math.abs(a.rsi-50)).map(x=>{const col=x.rsi<30?'border-green-500/60':x.rsi>70?'border-red-500/60':x.rsi<45||x.rsi>55?'border-yellow-500/40':'border-white/10';const dir=x.rsi<50?'LONG':'SHORT';return `<div class="bg-black/40 rounded-xl p-2.5 flex justify-between items-center border ${col}"><div><div class="text-[12px] font-bold">${x.symbol} <span class="px-1.5 py-0.5 rounded-full text-[9px] ${dir=='LONG'?'bg-green-500 text-black':'bg-red-500'}">${dir}</span></div><div class="text-[10px] text-gray-500">RSI ${x.rsi} ${x.rsi<30?'🔥 قوية':x.rsi>70?'🔥 قوية':x.rsi<45||x.rsi>55?'⚡ متوسطة':''}</div></div><div class="text-[11px] font-bold">$${x.price.toFixed(4)}</div></div>`}).join('')||`<div class="text-[10px] text-gray-500 text-center py-4">يفحص... ${s.scan_current}<br>${s.scan_log}</div>`;const d=await fetch('/api/pnl').then(r=>r.json());document.getElementById('liveBig').innerHTML=d.live.length?d.live.map(x=>`<div class="card p-4 border-2 ${x.gross<0?'border-red-500/60':'border-green-500/50'}"><div class="flex justify-between text-[11px]"><span>${x.type} ${x.sym}</span><span class="px-2 py-0.5 rounded bg-${x.side==='short'?'red':'green'}-500/20 text-[10px]">${x.side.toUpperCase()} ${x.lev}x</span></div><div class="mt-3"><div class="text-[26px] font-black ${x.gross<0?'text-red-500':'text-green-400'}">${x.gross>=0?'+':''}${x.gross.toFixed(2)}</div></div></div>`).join(''):`<div class="glass rounded-[20px] p-6 text-center"><div class="text-[11px] text-gray-400">يفحص 5 عملات كل 4 ثواني<br>حتى لو OKX علق يتخطى ويكمل</div></div>`;}setInterval(load,1000);load();</script></body></html>
"""

threading.Thread(target=hunter,daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))