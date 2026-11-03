import os, time, threading, ccxt, json
from flask import Flask, jsonify
import numpy as np
from datetime import datetime, timedelta

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL = 0.0
LAST = "V30007 - أول 60 عملة LIVE"
SCAN_LOG = "🚀 يبدأ فحص 60 عملة..."
SCAN_CURRENT = "BTC 1/60"
SCAN_COUNT = 60
FEE = 0.04
BASE_MARGIN = 2.0
COMP_MARGIN = 3.0
LEV = 10
FILE = "/tmp/state_v30007.json"

COINS_60 = [
"BTC","ETH","SOL","XRP","BNB","DOGE","ADA","AVAX","DOT","LINK",
"TRX","LTC","BCH","UNI","PEPE","NEAR","ETC","APT","FIL","STX",
"MATIC","OP","ARB","HBAR","IMX","MNT","RNDR","TAO","INJ","AR",
"FET","GRT","LDO","MKR","AAVE","SUI","SEI","WIF","BONK","JUP",
"ENA","WLD","FLOKI","TIA","PYTH","STRK","JTO","ORDI","SATS","RUNE",
"FLOW","KAS","BEAM","ARKM","AGIX","XLM","XMR","CRO","VET","ALGO"
]

STATE = {"open":{},"closed":[],"blacklist":{},"daily":0,"avail":0,"total":0,"wins":0,"losses":0,"fees":0,"trades":0,"consec_losses":0,"next_margin":BASE_MARGIN,"daily_losses":0}
try:
    if os.path.exists(FILE):
        with open(FILE,'r') as f:
            d=json.load(f)
            for k in STATE:
                if k in d and k not in ["open"]: STATE[k]=d[k]
            STATE["closed"]=d.get("closed",[])
            STATE["blacklist"]=d.get("blacklist",{})
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
def get_ex():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'options':{'defaultType':'swap'},'enableRateLimit':True})

def get_bal():
    global BAL
    try:
        r=get_ex().private_get_account_balance()
        for item in r['data'][0]['details']:
            if item['ccy']=='USDT':
                STATE["avail"]=float(item['availBal'] or 0)
                STATE["total"]=float(item['eq'] or 0)
                BAL=STATE["avail"]; return BAL
    except: pass
    try:
        b=get_ex().fetch_balance()
        BAL=float(b['total'].get('USDT',0) or 0); STATE["total"]=BAL; STATE["avail"]=BAL; return BAL
    except: return BAL

def calc_rsi(prices,p=14):
    try:
        prices=np.array(prices,float); d=np.diff(prices); up=np.where(d>0,d,0); down=np.where(d<0,-d,0)
        mu=np.mean(up[:p]); md=np.mean(down[:p])
        rsi=100-(100/(1+mu/md)) if md!=0 else 70
        for i in range(p,len(d)):
            mu=(mu*(p-1)+up[i])/p; md=(md*(p-1)+down[i])/p
            rsi=100-(100/(1+mu/md)) if md!=0 else 70
        return float(rsi)
    except: return 50

def scan_60():
    global SCAN_LOG, SCAN_CURRENT, LAST
    strong=[]; medium=[]
    ex=get_ex()
    for i,name in enumerate(COINS_60):
        SCAN_CURRENT=f"{name} {i+1}/60"
        if name in STATE["blacklist"]: continue
        try:
            sym=f"{name}/USDT:USDT"
            ohlcv=ex.fetch_ohlcv(sym,'1h',100)
            closes=[c[4] for c in ohlcv]; price=closes[-1]; rsi=calc_rsi(closes)
            SCAN_LOG=f"🔍 {name} RSI {rsi:.1f} {i+1}/60"
            if rsi<30: strong.append({"symbol":name,"full":sym,"direction":"long","price":price,"rsi":round(rsi,1),"score":10,"type":"قوية 🔥"})
            elif rsi>70: strong.append({"symbol":name,"full":sym,"direction":"short","price":price,"rsi":round(rsi,1),"score":10,"type":"قوية 🔥"})
            elif rsi<45: medium.append({"symbol":name,"full":sym,"direction":"long","price":price,"rsi":round(rsi,1),"score":6,"type":"متوسطة ⚡"})
            elif rsi>55: medium.append({"symbol":name,"full":sym,"direction":"short","price":price,"rsi":round(rsi,1),"score":6,"type":"متوسطة ⚡"})
        except Exception as e:
            SCAN_LOG=f"{name} {str(e)[:30]}"; continue
    LAST=f"🔍 فحص 60 - قوية {len(strong)} متوسطة {len(medium)} {datetime.now().strftime('%H:%M:%S')}"
    SCAN_LOG=f"✅ قوية:{len(strong)} متوسطة:{len(medium)} {datetime.now().strftime('%H:%M:%S')}"
    return {"strong":sorted(strong,key=lambda x:x["rsi"]), "medium":sorted(medium,key=lambda x: abs(x["rsi"]-50),reverse=True), "all": sorted(strong+medium,key=lambda x:x["score"],reverse=True)}

def close_any(sym):
    ex=get_ex()
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
                LAST=f"🛡️ وقف يومي {STATE['daily']:.2f}$"; time.sleep(60); continue
            try:
                ex=get_ex()
                for p in ex.fetch_positions():
                    if float(p.get('contracts',0) or 0)>0:
                        sym=p['symbol']; name=sym.replace('/USDT:USDT','')
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
                        elif best>=0.5 and net<=best-0.7: should=True; reason="حماية ربح"
                        elif best>=1.0 and net<=0.50: should=True; reason="تأمين +0.50"
                        elif best>=2.0 and net<=1.20: should=True; reason="تأمين +1.20"
                        if should and close_any(sym):
                            closed={"pair":name,"side":side,"pnl":net,"gross":gross,"time":datetime.now().strftime("%H:%M"),"reason":reason}
                            STATE["closed"].insert(0,closed); STATE["closed"]=STATE["closed"][:20]
                            STATE["open"].pop(sym,None); STATE["daily"]+=net; STATE["trades"]+=1; STATE["fees"]+=FEE
                            if net>0: STATE["wins"]+=1; STATE["consec_losses"]=0; STATE["next_margin"]=BASE_MARGIN
                            else: STATE["losses"]+=1; STATE["consec_losses"]+=1; STATE["daily_losses"]+=1; STATE["next_margin"]=COMP_MARGIN
                            if sum(1 for c in STATE["closed"][:5] if c["pair"]==name and c["pnl"]<0)>=2: STATE["blacklist"][name]=(datetime.now()+timedelta(hours=24)).timestamp()
                            save(); LAST=f"{'✅' if net>0 else '🔴'} {name} ${net:.2f}"
            except: pass
            try: live=len([p for p in get_ex().fetch_positions() if float(p.get('contracts',0) or 0)>0])
            except: live=len(STATE["open"])
            open_names=[v["name"] for v in STATE["open"].values()]
            has_strong=any(v.get("score",0)>=10 for v in STATE["open"].values())
            if live<2 and get_bal()>=STATE["next_margin"]:
                res=scan_60()
                s_strong=next((s for s in res["strong"] if s["symbol"] not in open_names and s["symbol"] not in STATE["blacklist"]),None)
                s_medium=next((s for s in res["medium"] if s["symbol"] not in open_names and s["symbol"] not in STATE["blacklist"]),None)
                to_open=[]
                if live==0:
                    if s_strong: to_open.append(s_strong)
                    elif s_medium: to_open.append(s_medium)
                else:
                    if has_strong and s_medium: to_open.append(s_medium)
                    elif not has_strong and s_strong: to_open.append(s_strong)
                    elif s_medium: to_open.append(s_medium)
                for sig in to_open[:1]:
                    try:
                        ex=get_ex(); ex.set_leverage(LEV,sig["full"])
                        side="buy" if sig["direction"]=="long" else "sell"; margin=STATE["next_margin"]
                        if get_bal()<4 and margin==COMP_MARGIN: margin=BASE_MARGIN
                        amt=(margin*LEV)/sig["price"]; amt=float(ex.amount_to_precision(sig["full"],max(amt,1)))
                        order=None
                        for mode in [{'tdMode':'isolated'},{'tdMode':'cross'}]:
                            try: order=ex.create_market_order(sig["full"],side,amt,None,mode); break
                            except: continue
                        if order:
                            entry=order.get("average") or sig["price"]
                            STATE["open"][sig["full"]]={"name":sig["symbol"],"dir":sig["direction"],"entry":entry,"best":0,"best_net":0,"type":sig["type"],"score":sig["score"],"rsi":sig["rsi"]}
                            LAST=f"✅ فتح {sig['type']} {sig['symbol']} {sig['direction']} RSI {sig['rsi']}"; save()
                    except Exception as e: LAST=f"❌ {str(e)[:50]}"
            time.sleep(2)
        except Exception as e: LAST=f"خطأ {str(e)[:60]}"; time.sleep(5)

@app.route("/", methods=["GET","POST"])
def index(): return HTML
@app.route("/health", methods=["GET","POST"])
def health(): return "OK", 200
@app.route("/api/status", methods=["GET","POST"])
def status(): return jsonify({"bal":get_bal(),"avail":STATE["avail"],"total":STATE["total"],"count":len(STATE["open"]),"last":LAST,"scan_log":SCAN_LOG,"scan_current":SCAN_CURRENT,"scan_count":60,"daily":STATE["daily"],"wins":STATE["wins"],"losses":STATE["losses"],"trades":STATE["trades"],"fees":STATE["fees"],"next_margin":STATE["next_margin"],"daily_losses":STATE["daily_losses"],"blacklist":list(STATE["blacklist"].keys())})
@app.route("/api/pnl", methods=["GET","POST"])
def pnl():
    live=[]
    try:
        ex=get_ex()
        for p in ex.fetch_positions():
            if float(p.get('contracts',0) or 0)>0:
                entry=float(p.get('entryPrice',0) or 0); last=float(p.get('markPrice',0) or entry)
                gross=float(p.get('unrealizedPnl',0) or 0); roe=float(p.get('percentage',0) or 0)
                mgn=float(p.get('imr',0) or 0); amt=float(p.get('contracts',0) or 0)
                lev=int(float(p.get('leverage',0) or LEV)); liq=float(p.get('liquidationPrice',0) or 0)
                sym=p['symbol']; name=sym.replace('/USDT:USDT','')
                info=STATE["open"].get(sym,{}); best=info.get("best_net",gross-FEE)
                live.append({"sym":name,"full":sym,"side":p.get('side','long'),"gross":gross,"net":gross-FEE,"entry":entry,"last":last,"amt":amt,"mgn":mgn,"lev":lev,"roe":roe,"liq":liq,"best":best,"type":info.get("type","-"),"rsi":info.get("rsi",0)})
    except: pass
    return jsonify({"bal":get_bal(),"total":STATE["total"],"live":live,"closed":STATE["closed"],"next_margin":STATE["next_margin"]})
@app.route("/api/scan", methods=["GET","POST"])
def scan(): r=scan_60(); return jsonify({"strong":r["strong"],"medium":r["medium"],"all":r["all"],"log":SCAN_LOG,"current":SCAN_CURRENT})
@app.route("/api/close/<sym>", methods=["GET","POST"])
def close_api(sym):
    try:
        for p in get_ex().fetch_positions():
            if sym in p['symbol'] and float(p.get('contracts',0) or 0)>0:
                close_any(p['symbol']); return jsonify({"ok":True})
        return jsonify({"ok":False})
    except Exception as e: return jsonify({"ok":False,"err":str(e)})

HTML = """<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>V30007 60 عملة LIVE</title><script src="https://cdn.tailwindcss.com"></script><style>body{background:#000;color:#fff}.card{background:#111214;border-radius:18px}.glass{background:#111c2f;border:1px solid #1e355a}.live-dot{animation:pulse 1s infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}</style></head><body class="max-w-[480px] mx-auto p-3"><div class="bg-[#111214] rounded-[22px] p-4 border border-green-500/30"><div class="flex justify-between text-[11px] text-gray-400"><span class="flex gap-1 items-center"><span class="w-2 h-2 bg-green-500 rounded-full live-dot"></span>V30007 أول 60 LIVE</span><span>حماية 100%</span></div><div class="flex gap-2 items-baseline mt-2"><div id="bal" class="text-[30px] font-black">$0</div><div id="total" class="text-[11px] text-gray-500"></div><div id="next" class="text-[10px] bg-yellow-500 text-black px-2 py-0.5 rounded-full font-bold"></div></div><div id="last" class="text-[12px] font-bold mt-2 text-yellow-300"></div><div class="mt-2 bg-black/60 rounded-xl p-2 border border-green-500/30"><div class="flex justify-between text-[10px]"><span class="text-green-400 font-bold">🔍 فحص LIVE 60 عملة</span><span id="scanCurrent" class="text-yellow-300 font-mono">-</span></div><div id="scanLog" class="text-[11px] text-white mt-1 font-mono">بانتظار...</div><div class="mt-2 h-1.5 bg-white/10 rounded-full overflow-hidden"><div id="scanProgress" class="h-full bg-green-500" style="width:0%"></div></div></div><div class="flex gap-2 mt-3 flex-wrap"><span id="cnt" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="daily" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="tr" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="bl" class="bg-red-500/20 px-3 py-1 rounded-full text-[10px]"></span></div></div><div id="liveBig" class="my-3"></div><div class="glass rounded-2xl p-3"><div class="flex justify-between text-[11px] font-black"><span>🔥 قوية RSI&lt;30 &gt;70</span><span id="strongCount" class="bg-red-500 text-white px-2 py-0.5 rounded-full text-[9px]">0</span></div><div id="strong" class="space-y-2 mt-2"></div></div><div class="glass rounded-2xl p-3 mt-3"><div class="flex justify-between text-[11px] font-black"><span>⚡ متوسطة RSI&lt;45 &gt;55</span><span id="mediumCount" class="bg-yellow-500 text-black px-2 py-0.5 rounded-full text-[9px]">0</span></div><div id="medium" class="space-y-2 mt-2"></div></div><div class="mt-3 bg-[#111214] rounded-xl p-3"><div class="font-black text-[12px] mb-2">📜 مقفلة</div><div id="closed" class="space-y-1"></div></div><script>async function load(){const s=await fetch('/api/status').then(r=>r.json());document.getElementById('bal').textContent=`$${s.bal.toFixed(2)}`;document.getElementById('total').textContent=`/ $${s.total.toFixed(2)} كلي`;document.getElementById('next').textContent=s.next_margin>2?`الجاية $${s.next_margin} تعويض`:`الجاية $${s.next_margin}`;document.getElementById('last').textContent=s.last;document.getElementById('scanLog').textContent=s.scan_log;document.getElementById('scanCurrent').textContent=s.scan_current;document.getElementById('cnt').textContent=s.count+'/2 مفتوح';document.getElementById('daily').textContent=`صافي $${s.daily.toFixed(2)} ${s.daily_losses}/3`;document.getElementById('tr').textContent=`✅${s.wins} ❌${s.losses} ${s.trades}`;document.getElementById('bl').textContent=s.blacklist.length?`محظور ${s.blacklist.join(',')}`:'لا حظر';const prog=s.scan_count>0?(parseInt(s.scan_current.split('/')[0].replace(/[^0-9]/g,''))||0)/s.scan_count*100:0;document.getElementById('scanProgress').style.width=prog+'%';const d=await fetch('/api/pnl').then(r=>r.json());document.getElementById('liveBig').innerHTML=d.live.length?d.live.map(x=>{const neg=x.gross<0;return `<div class="card p-4 border-2 ${neg?'border-red-500/60':'border-green-500/50'}"><div class="flex justify-between text-[11px]"><span>${x.type} ${x.sym}</span><span class="px-2 py-0.5 rounded bg-${x.side==='short'?'red':'green'}-500/20 text-[10px]">${x.side.toUpperCase()} ${x.lev}x RSI ${x.rsi}</span></div><div class="mt-3"><div class="text-[26px] font-black ${neg?'text-red-500':'text-green-400'}">${x.gross>=0?'+':''}${x.gross.toFixed(2)}</div><div class="text-[11px] text-gray-400">صافي $${x.net.toFixed(3)} | قمة $${x.best.toFixed(2)}</div></div><button onclick="fetch('/api/close/${x.sym}',{method:'POST'}).then(()=>location.reload())" class="w-full mt-3 bg-white text-black rounded-full py-2.5 text-[12px] font-bold">إغلاق</button></div>`}).join(''):`<div class="glass rounded-[20px] p-8 text-center"><div class="text-[32px]">🔍</div><div class="font-bold text-[13px] mt-2">$${d.total?d.total.toFixed(2):'56'} حر - 60 عملة LIVE</div><div class="text-[11px] text-gray-400 mt-1">قوية + متوسطة | 60 عملة</div></div>`;document.getElementById('closed').innerHTML=d.closed.length?d.closed.map(c=>`<div class="bg-black/40 rounded-lg p-2 flex justify-between text-[11px]"><span class="font-bold">${c.pair} <span class="${c.pnl>=0?'text-green-400':'text-red-400'}">${c.pnl>=0?'+':''}${c.pnl.toFixed(2)}$</span></span><span class="text-gray-500">${c.time} ${c.reason}</span></div>`).join(''):`<div class="text-[11px] text-gray-500 text-center py-3">ينتظر مقفلة</div>`;const sc=await fetch('/api/scan').then(r=>r.json()).catch(()=>({strong:[],medium:[]}));
document.getElementById('strongCount').textContent=sc.strong.length;document.getElementById('mediumCount').textContent=sc.medium.length;document.getElementById('strong').innerHTML=sc.strong.slice(0,8).map(s=>`<div class="bg-black/40 rounded-xl p-2.5 flex justify-between items-center border border-red-500/30"><div><div class="text-[12px] font-bold">${s.symbol} <span class="px-1.5 py-0.5 rounded-full text-[9px] ${s.direction=='long'?'bg-green-500 text-black':'bg-red-500'}">${s.direction.toUpperCase()}</span></div><div class="text-[10px] text-gray-500">RSI ${s.rsi}</div></div><div class="text-[11px] font-bold">${s.price.toFixed(4)}</div></div>`).join('')||`<div class="text-[10px] text-gray-500 text-center py-2">لا يوجد قوية</div>`;document.getElementById('medium').innerHTML=sc.medium.slice(0,10).map(s=>`<div class="bg-black/40 rounded-xl p-2.5 flex justify-between items-center border border-yellow-500/30"><div><div class="text-[12px] font-bold">${s.symbol} <span class="px-1.5 py-0.5 rounded-full text-[9px] ${s.direction=='long'?'bg-green-500 text-black':'bg-red-500'}">${s.direction.toUpperCase()}</span></div><div class="text-[10px] text-gray-500">RSI ${s.rsi}</div></div><div class="text-[11px] font-bold">${s.price.toFixed(4)}</div></div>`).join('')||`<div class="text-[10px] text-gray-500 text-center py-2">يفحص 60...</div>`;}setInterval(load,1000);load();</script></body></html>
"""

threading.Thread(target=hunter,daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))