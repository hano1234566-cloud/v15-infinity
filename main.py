import os, time, threading, ccxt, json
from flask import Flask, jsonify
import numpy as np
from datetime import datetime, timedelta

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL = 0.0
LAST = "V30004 - حماية 100%"
SCAN_LOG = "بانتظار..."
SCAN_CURRENT = "-"
SCAN_COUNT = 0
FEE = 0.04
BASE_MARGIN = 2.0
COMP_MARGIN = 3.0
LEV = 10
MAX_LOSS = -1.00
FILE = "/tmp/state_v30004.json"
# حماية جديدة
DAILY_PROFIT_STOP = 3.0
DAILY_LOSS_STOP = -3.0
MAX_DAILY_LOSSES = 3
LIQ_BUFFER = 0.15  # 15% قبل التصفية

STATE = {
    "open":{}, "closed":[], "blacklist":{},
    "daily":0, "avail":0, "total":0, "wins":0, "losses":0, "fees":0, "trades":0,
    "consec_losses":0, "next_margin":BASE_MARGIN, "daily_losses":0, "daily_profit_lock": False
}
try:
    if os.path.exists(FILE):
        with open(FILE,'r') as f:
            d=json.load(f)
            for k in ["daily","wins","losses","fees","trades","consec_losses","next_margin","daily_losses"]:
                if k in d: STATE[k]=d[k]
            STATE["closed"]=d.get("closed",[])
            STATE["blacklist"]=d.get("blacklist",{})
            now=datetime.now().timestamp()
            STATE["blacklist"]={k:v for k,v in STATE["blacklist"].items() if v>now}
            # تصفير يومي لو يوم جديد
            last_day = d.get("day","")
            today = datetime.now().strftime("%Y-%m-%d")
            if last_day != today:
                STATE["daily"]=0
                STATE["daily_losses"]=0
                STATE["daily_profit_lock"]=False
except: pass

def save():
    try:
        STATE["day"]=datetime.now().strftime("%Y-%m-%d")
        with open(FILE,'w') as f: json.dump(STATE,f)
    except: pass

app = Flask(__name__)
def get_ex():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'options':{'defaultType':'swap'},'enableRateLimit':True})

def get_real_balance():
    global BAL
    try:
        r=get_ex().private_get_account_balance()
        for item in r['data'][0]['details']:
            if item['ccy']=='USDT':
                STATE["avail"]=float(item['availBal'] or 0)
                STATE["total"]=float(item['eq'] or 0)
                BAL=STATE["avail"]
                return BAL
    except: pass
    try:
        b=get_ex().fetch_balance()
        BAL=float(b['total'].get('USDT',0) or 0)
        STATE["total"]=BAL; STATE["avail"]=BAL
        return BAL
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

def scan_all_real():
    global SCAN_LOG, SCAN_COUNT, SCAN_CURRENT, LAST
    strong=[]; medium=[]
    try:
        ex=get_ex()
        tickers=ex.fetch_tickers()
        candidates=[]
        for sym,t in tickers.items():
            if "/USDT:USDT" in sym and t.get('quoteVolume',0):
                vol=float(t.get('quoteVolume',0) or 0)
                if vol>5000000: candidates.append((sym,vol))
        candidates=sorted(candidates,key=lambda x:x[1],reverse=True)[:40]
        SCAN_COUNT=len(candidates)
        for i,(sym,_) in enumerate(candidates):
            name=sym.replace("/USDT:USDT","")
            SCAN_CURRENT=f"{name} {i+1}/{SCAN_COUNT}"
            if name in STATE["blacklist"]: continue
            try:
                ohlcv=ex.fetch_ohlcv(sym,'1h',100)
                closes=[c[4] for c in ohlcv]; price=closes[-1]; rsi=calc_rsi(closes)
                SCAN_LOG=f"🔍 {name} RSI {rsi:.1f} {i+1}/{SCAN_COUNT}"
                if rsi<30: strong.append({"symbol":name,"full":sym,"direction":"long","price":price,"rsi":round(rsi,1),"score":10,"type":"قوية 🔥","vol":_})
                elif rsi>70: strong.append({"symbol":name,"full":sym,"direction":"short","price":price,"rsi":round(rsi,1),"score":10,"type":"قوية 🔥","vol":_})
                elif rsi<45: medium.append({"symbol":name,"full":sym,"direction":"long","price":price,"rsi":round(rsi,1),"score":6,"type":"متوسطة ⚡","vol":_})
                elif rsi>55: medium.append({"symbol":name,"full":sym,"direction":"short","price":price,"rsi":round(rsi,1),"score":6,"type":"متوسطة ⚡","vol":_})
            except: continue
        LAST=f"🔍 فحص {SCAN_COUNT} - قوية {len(strong)} متوسطة {len(medium)}"
        SCAN_LOG=f"✅ قوية:{len(strong)} متوسطة:{len(medium)} {datetime.now().strftime('%H:%M:%S')}"
    except Exception as e:
        SCAN_LOG=f"❌ {str(e)[:60]}"
    return {"strong":sorted(strong,key=lambda x:x["rsi"]), "medium":sorted(medium,key=lambda x: abs(x["rsi"]-50), reverse=True), "all": sorted(strong+medium, key=lambda x:x["score"], reverse=True)}

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
    get_real_balance()
    while True:
        try:
            get_real_balance()
            # حماية يومية محسنة
            if STATE["daily_losses"]>=MAX_DAILY_LOSSES:
                LAST=f"🛡️ وقف - 3 خسائر اليوم - صافي {STATE['daily']:.2f}$"; time.sleep(60); continue
            if STATE["daily"]<=DAILY_LOSS_STOP:
                LAST=f"🛡️ وقف - خسارة يومية {STATE['daily']:.2f}$ - الحد -3$"; time.sleep(60); continue
            if STATE["daily"]>=DAILY_PROFIT_STOP:
                LAST=f"🛡️ وقف - ربح يومي {STATE['daily']:.2f}$ - هدف +3$ تحقق ✅"; time.sleep(60); continue

            # حماية صفقات مفتوحة
            try:
                ex=get_ex()
                positions = ex.fetch_positions()
                for p in positions:
                    if float(p.get('contracts',0) or 0)>0:
                        sym=p['symbol']; name=sym.replace('/USDT:USDT','')
                        gross=float(p.get('unrealizedPnl',0) or 0); net=gross-FEE
                        entry=float(p.get('entryPrice',0) or 0); mark=float(p.get('markPrice',0) or entry)
                        liq=float(p.get('liquidationPrice',0) or 0)
                        side=p.get('side','long')
                        if sym not in STATE["open"]:
                            STATE["open"][sym]={"name":name,"dir":side,"entry":entry,"best":net,"best_net":net}
                        best=STATE["open"][sym].get("best_net",net)
                        if net>best: STATE["open"][sym]["best_net"]=net; best=net
                        should=False; reason=""
                        # 1- ستوب -$1
                        if net<=MAX_LOSS: should=True; reason=f"ستوب -1$ حقيقي {net:.2f}"
                        # 2- حماية تصفية 15%
                        if not should and liq>0 and entry>0:
                            if side=='long':
                                dist = (mark - liq) / (entry - liq) if (entry-liq)!=0 else 1
                                if mark <= liq + (entry-liq)*LIQ_BUFFER: should=True; reason=f"حماية تصفية Long قرب {((mark-liq)/(entry-liq)*100):.0f}%"
                            else:
                                dist = (liq - mark) / (liq - entry) if (liq-entry)!=0 else 1
                                if mark >= liq - (liq-entry)*LIQ_BUFFER: should=True; reason=f"حماية تصفية Short قرب {((liq-mark)/(liq-entry)*100):.0f}%"
                        # 3- تتبع ربح
                        if not should:
                            if best>=0.5 and net<=best-0.7: should=True; reason=f"حماية ربح نزل {best:.2f}->{net:.2f}"
                            elif best>=1.0 and net<=0.50: should=True; reason=f"تأمين +0.50 من قمة {best:.2f}"
                            elif best>=2.0 and net<=1.20: should=True; reason=f"تأمين +1.20 من قمة {best:.2f}"
                        if should and close_any(sym):
                            closed={"pair":name,"side":side,"pnl":net,"gross":gross,"time":datetime.now().strftime("%H:%M"),"reason":reason}
                            STATE["closed"].insert(0,closed); STATE["closed"]=STATE["closed"][:20]
                            STATE["open"].pop(sym,None)
                            STATE["daily"]+=net; STATE["trades"]+=1; STATE["fees"]+=FEE
                            if net>0: STATE["wins"]+=1; STATE["consec_losses"]=0; STATE["next_margin"]=BASE_MARGIN; LAST=f"✅ ربح ${net:.2f} {name} - {reason}"
                            else: 
                                STATE["losses"]+=1; STATE["consec_losses"]+=1; STATE["daily_losses"]+=1; STATE["next_margin"]=COMP_MARGIN
                                cnt=sum(1 for c in STATE["closed"][:5] if c["pair"]==name and c["pnl"]<0)
                                if cnt>=2:
                                    STATE["blacklist"][name]=(datetime.now()+timedelta(hours=24)).timestamp()
                                    LAST=f"🔴 خسارة ${net:.2f} {name} حظر 24س - {reason}"
                                else: LAST=f"🔴 خسارة ${net:.2f} {name} تعويض $3 - {reason}"
                            save()
            except Exception as e: LAST=f"حماية err {str(e)[:50]}"

            try: live_count=len([p for p in get_ex().fetch_positions() if float(p.get('contracts',0) or 0)>0])
            except: live_count=len(STATE["open"])
            open_names=[v["name"] for v in STATE["open"].values()]
            has_strong = any(v.get("score",0)>=10 for v in STATE["open"].values())

            bal = get_real_balance()
            # حماية رصيد
            if bal < 2.5:
                LAST=f"🛡️ رصيد قليل ${bal:.2f} - يوقف فتح"
                time.sleep(30); continue

            if live_count<2 and bal>=STATE["next_margin"] and STATE["daily_losses"]<MAX_DAILY_LOSSES and STATE["daily"]<DAILY_PROFIT_STOP:
                res=scan_all_real()
                sig_strong = next((s for s in res["strong"] if s["symbol"] not in open_names and s["symbol"] not in STATE["blacklist"]), None)
                sig_medium = next((s for s in res["medium"] if s["symbol"] not in open_names and s["symbol"] not in STATE["blacklist"]), None)
                to_open = []
                if live_count==0:
                    if sig_strong: to_open.append(sig_strong)
                    elif sig_medium: to_open.append(sig_medium)
                elif live_count==1:
                    if has_strong and sig_medium: to_open.append(sig_medium)
                    elif not has_strong and sig_strong: to_open.append(sig_strong)
                    elif sig_medium: to_open.append(sig_medium)
                    elif sig_strong: to_open.append(sig_strong)

                for sig in to_open[:1]:
                    try:
                        ex=get_ex(); ex.set_leverage(LEV,sig["full"])
                        side="buy" if sig["direction"]=="long" else "sell"; margin=STATE["next_margin"]
                        # حماية رصيد - لو رصيد قليل لا يفتح تعويض
                        if bal < 4 and margin==COMP_MARGIN: margin=BASE_MARGIN
                        amt=(margin*LEV)/sig["price"]; amt=float(ex.amount_to_precision(sig["full"],max(amt,1)))
                        order=None
                        for mode in [{'tdMode':'isolated'},{'tdMode':'cross'}]:
                            try: order=ex.create_market_order(sig["full"],side,amt,None,mode); break
                            except: continue
                        if order:
                            entry=order.get("average") or sig["price"]
                            STATE["open"][sig["full"]]={"name":sig["symbol"],"dir":sig["direction"],"entry":entry,"best":0,"best_net":0,"type":sig["type"],"score":sig["score"],"rsi":sig["rsi"]}
                            LAST=f"✅ فتح {sig['type']} {sig['symbol']} {sig['direction']} RSI {sig['rsi']} ${margin}×{LEV}"
                            save()
                    except Exception as e: LAST=f"❌ فتح فشل {sig['symbol']} {str(e)[:60]}"
            time.sleep(3)
        except Exception as e: LAST=f"خطأ {str(e)[:70]}"; time.sleep(5)

@app.route("/")
def index(): return HTML
@app.route("/health")
def health(): return "OK", 200
@app.route("/api/status")
def status(): return jsonify({"bal":get_real_balance(),"avail":STATE["avail"],"total":STATE["total"],"count":len(STATE["open"]),"last":LAST,"scan_log":SCAN_LOG,"scan_current":SCAN_CURRENT,"scan_count":SCAN_COUNT,"daily":STATE["daily"],"wins":STATE["wins"],"losses":STATE["losses"],"trades":STATE["trades"],"fees":STATE["fees"],"next_margin":STATE["next_margin"],"daily_losses":STATE["daily_losses"],"blacklist":list(STATE["blacklist"].keys())})
@app.route("/api/pnl")
def pnl():
    live=[]
    try:
        ex=get_ex()
        for p in ex.fetch_positions():
            if float(p.get('contracts',0) or 0)>0:
                entry=float(p.get('entryPrice',0) or 0); last=float(p.get('markPrice',0) or entry)
                gross=float(p.get('unrealizedPnl',0) or 0); roe=float(p.get('percentage',0) or 0)
                mgn=float(p.get('imr',0) or p.get('margin',0) or BASE_MARGIN); amt=float(p.get('contracts',0) or 0)
                lev=int(float(p.get('leverage',0) or LEV)); liq=float(p.get('liquidationPrice',0) or 0)
                sym=p['symbol']; name=sym.replace('/USDT:USDT','').replace(':USDT','')
                info=STATE["open"].get(sym,{}); best=info.get("best_net",gross-FEE)
                live.append({"sym":name,"full":sym,"side":p.get('side','long'),"gross":gross,"net":gross-FEE,"entry":entry,"last":last,"amt":amt,"mgn":mgn,"lev":lev,"roe":roe,"liq":liq,"best":best,"type":info.get("type","-"),"rsi":info.get("rsi",0)})
    except: pass
    return jsonify({"bal":get_real_balance(),"total":STATE["total"],"live":live,"closed":STATE["closed"],"next_margin":STATE["next_margin"]})
@app.route("/api/scan")
def scan():
    r=scan_all_real()
    return jsonify({"strong":r["strong"],"medium":r["medium"],"all":r["all"],"log":SCAN_LOG,"current":SCAN_CURRENT})
@app.route("/api/close/<sym>")
def close_api(sym):
    try:
        for p in get_ex().fetch_positions():
            if sym in p['symbol'] and float(p.get('contracts',0) or 0)>0:
                close_any(p['symbol']); return jsonify({"ok":True})
        return jsonify({"ok":False})
    except Exception as e: return jsonify({"ok":False,"err":str(e)})

HTML = """
<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>V30004 حماية 100%</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{background:#000;color:#fff}.card{background:#111214;border-radius:18px}.glass{background:#111c2f;border:1px solid #1e355a}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}} .live-dot{animation:pulse 1s infinite}
</style></head>
<body class="max-w-[480px] mx-auto p-3">
<div class="bg-[#111214] rounded-[22px] p-4 border border-green-500/30">
<div class="flex justify-between text-[11px] text-gray-400"><span class="flex gap-1 items-center"><span class="w-2 h-2 bg-green-500 rounded-full live-dot"></span>V30004 حماية 100%</span><span>قوية+متوسطة</span></div>
<div class="flex gap-2 items-baseline mt-2"><div id="bal" class="text-[30px] font-black">$0</div><div id="total" class="text-[11px] text-gray-500"></div><div id="next" class="text-[10px] bg-yellow-500 text-black px-2 py-0.5 rounded-full font-bold"></div></div>
<div id="last" class="text-[12px] font-bold mt-2 text-yellow-300"></div>
<div class="mt-2 bg-black/60 rounded-xl p-2 border border-green-500/30">
<div class="flex justify-between text-[10px]"><span class="text-green-400 font-bold">🔍 فحص LIVE</span><span id="scanCurrent" class="text-yellow-300 font-mono">-</span></div>
<div id="scanLog" class="text-[11px] text-white mt-1 font-mono">بانتظار...</div>
<div id="scanBar" class="mt-2 h-1.5 bg-white/10 rounded-full overflow-hidden"><div id="scanProgress" class="h-full bg-green-500 transition-all" style="width:0%"></div></div>
</div>
<div class="flex gap-2 mt-3 flex-wrap"><span id="cnt" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="daily" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="tr" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="bl" class="bg-red-500/20 px-3 py-1 rounded-full text-[10px]"></span></div>
<div class="mt-2 grid grid-cols-3 gap-2 text-[9px]">
<div class="bg-green-500/10 border border-green-500/20 rounded-lg p-1.5 text-center"><div class="text-gray-400">ستوب</div><div class="font-bold text-green-400">-$1</div></div>
<div class="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-1.5 text-center"><div class="text-gray-400">تصفية</div><div class="font-bold text-yellow-400">15%</div></div>
<div class="bg-blue-500/10 border border-blue-500/20 rounded-lg p-1.5 text-center"><div class="text-gray-400">يومي</div><div class="font-bold text-blue-400">+3$ / -3$</div></div>
</div>
</div>
<div id="liveBig" class="my-3"></div>
<div class="glass rounded-2xl p-3"><div class="flex justify-between text-[11px] font-black"><span>🔥 قوية RSI&lt;30 &gt;70</span><span id="strongCount" class="bg-red-500 text-white px-2 py-0.5 rounded-full text-[9px]">0</span></div><div id="strong" class="space-y-2 mt-2"></div></div>
<div class="glass rounded-2xl p-3 mt-3"><div class="flex justify-between text-[11px] font-black"><span>⚡ متوسطة RSI&lt;45 &gt;55</span><span id="mediumCount" class="bg-yellow-500 text-black px-2 py-0.5 rounded-full text-[9px]">0</span></div><div id="medium" class="space-y-2 mt-2"></div></div>
<div class="mt-3 bg-[#111214] rounded-xl p-3"><div class="font-black text-[12px] mb-2">📜 مقفلة حقيقية</div><div id="closed" class="space-y-1"></div></div>
<script>
async function load(){
 const s=await fetch('/api/status').then(r=>r.json());
 document.getElementById('bal').textContent=`$${s.bal.toFixed(2)} متاح`;
 document.getElementById('total').textContent=`/ $${s.total.toFixed(2)} كلي`;
 document.getElementById('next').textContent=s.next_margin>2?`الجاية $${s.next_margin} تعويض`:`الجاية $${s.next_margin}`;
 document.getElementById('last').textContent=s.last;
 document.getElementById('scanLog').textContent=s.scan_log;
 document.getElementById('scanCurrent').textContent=s.scan_current;
 document.getElementById('cnt').textContent=s.count+'/2 مفتوح';
 document.getElementById('daily').textContent=`صافي $${s.daily.toFixed(2)} خسائر ${s.daily_losses}/3`;
 document.getElementById('tr').textContent=`✅${s.wins} ❌${s.losses} ${s.trades} صفقات $${s.fees.toFixed(2)}`;
 document.getElementById('bl').textContent=s.blacklist.length?`محظور ${s.blacklist.join(',')}`:'لا حظر';
 const prog=s.scan_count>0? (parseInt(s.scan_current.split('/')[0].replace(/[^0-9]/g,''))||0)/s.scan_count*100 : 0;
 document.getElementById('scanProgress').style.width=prog+'%';
 const d=await fetch('/api/pnl').then(r=>r.json());
 document.getElementById('liveBig').innerHTML=d.live.length? d.live.map(x=>{
  const neg=x.gross<0; 
  const liqRisk = x.liq>0 ? Math.abs((x.last-x.liq)/(x.entry-x.liq)*100).toFixed(0) : 100;
  return `<div class="card p-4 border-2 ${neg?'border-red-500/60':'border-green-500/50'}">
   <div class="flex justify-between text-[11px]"><span>${x.type} ${x.sym}</span><span class="px-2 py-0.5 rounded bg-${x.side==='short'?'red':'green'}-500/20 text-[10px]">${x.side.toUpperCase()} ${x.lev}x RSI ${x.rsi}</span></div>
   <div class="mt-3"><div class="text-[26px] font-black ${neg?'text-red-500':'text-green-400'}">${x.gross>=0?'+':''}${x.gross.toFixed(2)} (${x.roe>=0?'+':''}${x.roe.toFixed(2)}%)</div><div class="text-[11px] text-gray-400">صافي $${x.net.toFixed(3)} | قمة $${x.best.toFixed(2)} | أمان تصفية ${liqRisk}%</div></div>
   <button onclick="fetch('/api/close/${x.sym}').then(()=>location.reload())" class="w-full mt-3 bg-white text-black rounded-full py-2.5 text-[12px] font-bold">إغلاق</button>
  </div>`
 }).join('') : `<div class="glass rounded-[20px] p-8 text-center"><div class="text-[32px]">🛡️</div><div class="font-bold text-[13px] mt-2">$${d.total?d.total.toFixed(2):'56'} حر - حماية 100%</div><div class="text-[11px] text-gray-400 mt-1">قوية + متوسطة | ستوب -1$ | تصفية 15% | يومي +3$/-3$</div></div>`;
 document.getElementById('closed').innerHTML=d.closed.length? d.closed.map(c=>`<div class="bg-black/40 rounded-lg p-2 flex justify-between text-[11px]"><span class="font-bold">${c.pair} <span class="${c.pnl>=0?'text-green-400':'text-red-400'}">${c.pnl>=0?'+':''}${c.pnl.toFixed(2)}$</span></span><span class="text-gray-500">${c.time} ${c.reason}</span></div>`).join('') : `<div class="text-[11px] text-gray-500 text-center py-3">ينتظر مقفلة</div>`;
 const sc=await fetch('/api/scan').then(r=>r.json()).catch(()=>({strong:[],medium:[]}));
 document.getElementById('strongCount').textContent=sc.strong.length;
 document.getElementById('mediumCount').textContent=sc.medium.length;
 document.getElementById('strong').innerHTML=sc.strong.slice(0,5).map(s=>`<div class="bg-black/40 rounded-xl p-2.5 flex justify-between items-center border border-red-500/30"><div><div class="text-[12px] font-bold">${s.symbol} <span class="px-1.5 py-0.5 rounded-full text-[9px] ${s.direction=='long'?'bg-green-500 text-black':'bg-red-500'}">${s.direction.toUpperCase()}</span> <span class="text-[8px] bg-red-500 text-white px-1 rounded">${s.type}</span></div><div class="text-[10px] text-gray-500">RSI ${s.rsi}</div></div><div class="text-[11px] font-bold">${s.price.toFixed(4)}</div></div>`).join('') || `<div class="text-[10px] text-gray-500 text-center py-2">لا يوجد قوية - السوق عرضي</div>`;
 document.getElementById('medium').innerHTML=sc.medium.slice(0,5).map(s=>`<div class="bg-black/40 rounded-xl p-2.5 flex justify-between items-center border border-yellow-500/30"><div><div class="text-[12px] font-bold">${s.symbol} <span class="px-1.5 py-0.5 rounded-full text-[9px] ${s.direction=='long'?'bg-green-500 text-black':'bg-red-500'}">${s.direction.toUpperCase()}</span> <span class="text-[8px] bg-yellow-500 text-black px-1 rounded">${s.type}</span></div><div class="text-[10px] text-gray-500">RSI ${s.rsi}</div></div><div class="text-[11px] font-bold">${s.price.toFixed(4)}</div></div>`).join('') || `<div class="text-[10px] text-gray-500 text-center py-2">لا يوجد متوسطة</div>`;
}
setInterval(load,1000); load();
</script></body></html>
"""

threading.Thread(target=hunter,daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))