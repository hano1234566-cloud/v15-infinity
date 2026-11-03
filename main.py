import os, time, threading, ccxt, json
from flask import Flask, jsonify
import numpy as np
from datetime import datetime, timedelta

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL = 0.0
LAST = "V30002 - فحص LIVE"
SCAN_LOG = "بانتظار الفحص..."
SCAN_COUNT = 0
SCAN_CURRENT = "-"
FEE = 0.04
BASE_MARGIN = 2.0
COMP_MARGIN = 3.0
LEV = 10
MAX_LOSS = -1.00
FILE = "/tmp/state_v30002.json"

STATE = {
    "open":{}, "closed":[], "blacklist":{},
    "daily":0, "avail":0, "total":0, "wins":0, "losses":0, "fees":0, "trades":0,
    "consec_losses":0, "next_margin":BASE_MARGIN, "daily_losses":0
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
except: pass

def save():
    try:
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
        STATE["total"]=BAL
        STATE["avail"]=BAL
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
    sigs=[]
    try:
        ex=get_ex()
        SCAN_LOG="🔍 يجلب كل العملات من OKX..."
        tickers=ex.fetch_tickers()
        candidates=[]
        for sym,t in tickers.items():
            if "/USDT:USDT" in sym and t.get('quoteVolume',0):
                vol=float(t.get('quoteVolume',0) or 0)
                if vol>5000000: candidates.append((sym,vol))
        candidates=sorted(candidates,key=lambda x:x[1],reverse=True)[:40]
        SCAN_COUNT=len(candidates)
        SCAN_LOG=f"🔍 وجد {SCAN_COUNT} عملة >$5M - يفحص RSI الآن..."
        for i,(sym,_) in enumerate(candidates):
            name=sym.replace("/USDT:USDT","")
            SCAN_CURRENT=f"{name} {i+1}/{SCAN_COUNT}"
            if name in STATE["blacklist"]: continue
            try:
                ohlcv=ex.fetch_ohlcv(sym,'1h',100)
                closes=[c[4] for c in ohlcv]; price=closes[-1]; rsi=calc_rsi(closes)
                SCAN_LOG=f"🔍 يفحص: {name} RSI {rsi:.1f} - {i+1}/{SCAN_COUNT}"
                if rsi<30: sigs.append({"symbol":name,"full":sym,"direction":"long","price":price,"rsi":round(rsi,1),"score":10,"vol":_})
                elif rsi>70: sigs.append({"symbol":name,"full":sym,"direction":"short","price":price,"rsi":round(rsi,1),"score":10,"vol":_})
                elif rsi<38: sigs.append({"symbol":name,"full":sym,"direction":"long","price":price,"rsi":round(rsi,1),"score":8,"vol":_})
                elif rsi>62: sigs.append({"symbol":name,"full":sym,"direction":"short","price":price,"rsi":round(rsi,1),"score":8,"vol":_})
            except: continue
        LAST=f"🔍 فحص {SCAN_COUNT} عملة - وجد {len(sigs)} فرصة - {datetime.now().strftime('%H:%M:%S')}"
        SCAN_LOG=f"✅ انتهى فحص {SCAN_COUNT} عملة - {len(sigs)} فرصة - {datetime.now().strftime('%H:%M:%S')}"
    except Exception as e:
        SCAN_LOG=f"❌ خطأ فحص {str(e)[:60]}"
        LAST=SCAN_LOG
    return sorted(sigs,key=lambda x:x["score"],reverse=True)

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
    global LAST, SCAN_LOG
    get_real_balance()
    try:
        for p in get_ex().fetch_positions():
            if float(p.get('contracts',0) or 0)>0:
                sym=p['symbol']
                if sym not in STATE["open"]:
                    STATE["open"][sym]={"name":sym.replace('/USDT:USDT','').replace(':USDT',''),"dir":p.get('side','long'),"entry":float(p.get('entryPrice',0) or 0),"best":float(p.get('unrealizedPnl',0) or 0)-FEE,"best_net":float(p.get('unrealizedPnl',0) or 0)-FEE}
    except: pass
    while True:
        try:
            get_real_balance()
            if STATE["daily_losses"]>=3 or STATE["daily"]<=-3:
                LAST=f"🛡️ حماية - وقف اليوم - خسارة {STATE['daily']:.2f} - 3 خسائر"; SCAN_LOG="🛡️ متوقف حماية"
                time.sleep(60); continue
            try:
                ex=get_ex()
                for p in ex.fetch_positions():
                    if float(p.get('contracts',0) or 0)>0:
                        sym=p['symbol']; name=sym.replace('/USDT:USDT','')
                        gross=float(p.get('unrealizedPnl',0) or 0); net=gross-FEE
                        if sym not in STATE["open"]:
                            STATE["open"][sym]={"name":name,"dir":p.get('side','long'),"entry":float(p.get('entryPrice',0) or 0),"best":net,"best_net":net}
                        best=STATE["open"][sym].get("best_net",net)
                        if net>best: STATE["open"][sym]["best_net"]=net; best=net
                        should=False; reason=""
                        if net<=MAX_LOSS: should=True; reason=f"ستوب -$1 حقيقي {net:.2f}"
                        elif best>=0.5 and net<=best-0.7: should=True; reason=f"حماية ربح نزل من {best:.2f} لـ {net:.2f}"
                        elif best>=1.0 and net<=0.50: should=True; reason=f"تأمين +0.50 من قمة {best:.2f}"
                        elif best>=2.0 and net<=1.20: should=True; reason=f"تأمين +1.20 من قمة {best:.2f}"
                        if should and close_any(sym):
                            closed={"pair":name,"side":p.get('side',''),"pnl":net,"gross":gross,"time":datetime.now().strftime("%H:%M"),"reason":reason}
                            STATE["closed"].insert(0,closed); STATE["closed"]=STATE["closed"][:20]
                            STATE["open"].pop(sym,None)
                            STATE["daily"]+=net; STATE["trades"]+=1; STATE["fees"]+=FEE
                            if net>0: STATE["wins"]+=1; STATE["consec_losses"]=0; STATE["next_margin"]=BASE_MARGIN; LAST=f"✅ ربح حقيقي ${net:.2f} {name} - {reason}"
                            else: 
                                STATE["losses"]+=1; STATE["consec_losses"]+=1; STATE["daily_losses"]+=1; STATE["next_margin"]=COMP_MARGIN
                                cnt=sum(1 for c in STATE["closed"][:5] if c["pair"]==name and c["pnl"]<0)
                                if cnt>=2:
                                    STATE["blacklist"][name]=(datetime.now()+timedelta(hours=24)).timestamp()
                                    LAST=f"🔴 خسارة حقيقية ${net:.2f} {name} - حظر 24س - {reason}"
                                else: LAST=f"🔴 خسارة حقيقية ${net:.2f} {name} - تعويض الجاية $3 - {reason}"
                            save()
            except Exception as e: LAST=f"حماية err {str(e)[:60]}"
            try: live_count=len([p for p in get_ex().fetch_positions() if float(p.get('contracts',0) or 0)>0])
            except: live_count=len(STATE["open"])
            if live_count<2 and get_real_balance()>=STATE["next_margin"] and STATE["daily_losses"]<3:
                sigs=scan_all_real()
                exist=[v["name"] for v in STATE["open"].values()]
                sig=next((s for s in sigs if s["symbol"] not in exist and s["symbol"] not in STATE["blacklist"]),None)
                if sig:
                    try:
                        ex=get_ex(); ex.set_leverage(LEV,sig["full"])
                        side="buy" if sig["direction"]=="long" else "sell"; margin=STATE["next_margin"]
                        amt=(margin*LEV)/sig["price"]; amt=float(ex.amount_to_precision(sig["full"],max(amt,1)))
                        order=None
                        for mode in [{'tdMode':'isolated'},{'tdMode':'cross'}]:
                            try: order=ex.create_market_order(sig["full"],side,amt,None,mode); break
                            except: continue
                        if order:
                            entry=order.get("average") or sig["price"]
                            STATE["open"][sig["full"]]={"name":sig["symbol"],"dir":sig["direction"],"entry":entry,"best":0,"best_net":0}
                            LAST=f"✅ فتح حقيقي {sig['symbol']} {sig['direction']} ${margin}×{LEV} RSI {sig['rsi']} - تعويض" if margin>BASE_MARGIN else f"✅ فتح حقيقي {sig['symbol']} {sig['direction']} ${margin}×{LEV} RSI {sig['rsi']}"
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
                best=STATE["open"].get(sym,{}).get("best_net",gross-FEE)
                live.append({"sym":name,"full":sym,"side":p.get('side','long'),"gross":gross,"net":gross-FEE,"entry":entry,"last":last,"amt":amt,"mgn":mgn,"lev":lev,"roe":roe,"liq":liq,"best":best})
    except: pass
    return jsonify({"bal":get_real_balance(),"total":STATE["total"],"live":live,"closed":STATE["closed"],"next_margin":STATE["next_margin"]})
@app.route("/api/scan")
def scan(): return jsonify({"signals":scan_all_real(),"log":SCAN_LOG,"current":SCAN_CURRENT})
@app.route("/api/close/<sym>")
def close_api(sym):
    try:
        for p in get_ex().fetch_positions():
            if sym in p['symbol'] and float(p.get('contracts',0) or 0)>0:
                close_any(p['symbol']); return jsonify({"ok":True})
        return jsonify({"ok":False})
    except Exception as e: return jsonify({"ok":False,"err":str(e)})

HTML = """
<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>V30002 LIVE SCAN</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{background:#000;color:#fff}.card{background:#111214;border-radius:18px}.glass{background:#111c2f;border:1px solid #1e355a}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}} .live-dot{animation:pulse 1s infinite}
</style></head>
<body class="max-w-[480px] mx-auto p-3">
<div class="bg-[#111214] rounded-[22px] p-4 border border-yellow-500/20">
<div class="flex justify-between text-[11px] text-gray-400"><span class="flex gap-1 items-center"><span class="w-2 h-2 bg-green-500 rounded-full live-dot"></span>LIVE REAL - يفحص</span><span>V30002 - LIVE SCAN</span></div>
<div class="flex gap-2 items-baseline mt-2"><div id="bal" class="text-[30px] font-black">$0</div><div id="total" class="text-[11px] text-gray-500"></div><div id="next" class="text-[10px] bg-yellow-500 text-black px-2 py-0.5 rounded-full font-bold"></div></div>
<div id="last" class="text-[12px] font-bold mt-2 text-yellow-300"></div>
<div class="mt-2 bg-black/60 rounded-xl p-2 border border-green-500/20">
<div class="flex justify-between text-[10px]"><span class="text-green-400 font-bold">🔍 الفحص المباشر</span><span id="scanCurrent" class="text-yellow-300 font-mono">-</span></div>
<div id="scanLog" class="text-[11px] text-white mt-1 font-mono">بانتظار...</div>
<div id="scanBar" class="mt-2 h-1.5 bg-white/10 rounded-full overflow-hidden"><div id="scanProgress" class="h-full bg-green-500 transition-all" style="width:0%"></div></div>
</div>
<div class="flex gap-2 mt-3 flex-wrap"><span id="cnt" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="daily" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="tr" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="bl" class="bg-red-500/20 px-3 py-1 rounded-full text-[10px]"></span></div>
</div>
<div id="liveBig" class="my-3"></div>
<div class="glass rounded-2xl p-3"><div class="flex justify-between"><div class="font-black text-[12px]">📊 فرص حقيقية LIVE</div><div id="scanCount" class="text-[10px] text-gray-400"></div></div><div id="sigs" class="space-y-2 mt-2"></div></div>
<div class="mt-3 bg-[#111214] rounded-xl p-3"><div class="font-black text-[12px] mb-2">📜 مقفلة حقيقية OKX</div><div id="closed" class="space-y-1"></div></div>
<div class="mt-3 bg-[#111214] rounded-xl p-3 text-[10px] text-gray-300 leading-5">
<b class="text-white">✅ V30002 - فحص LIVE:</b><br>
- تشوفه يفحص كل عملة باسمها و RSI مباشر<br>
- /health لـ cron-job.org ما يفشل 503<br>
- ستوب -$1 تتبع ربح تعويض $3 بلاك ليست
</div>
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
 document.getElementById('daily').textContent=`صافي $${s.daily.toFixed(2)} خسائر اليوم ${s.daily_losses}/3`;
 document.getElementById('tr').textContent=`✅${s.wins} ❌${s.losses} ${s.trades} صفقات $${s.fees.toFixed(2)} رسوم`;
 document.getElementById('bl').textContent=s.blacklist.length?`محظور ${s.blacklist.join(',')}`:'لا حظر';
 const prog=s.scan_count>0? (parseInt(s.scan_current.split('/')[0].replace(/[^0-9]/g,''))||0)/s.scan_count*100 : 0;
 document.getElementById('scanProgress').style.width=prog+'%';
 document.getElementById('scanCount').textContent=s.scan_count+' عملة';
 const d=await fetch('/api/pnl').then(r=>r.json());
 document.getElementById('liveBig').innerHTML=d.live.length? d.live.map(x=>{
  const neg=x.gross<0; return `<div class="card p-4 border-2 ${neg?'border-red-500/60':'border-green-500/50'}">
   <div class="flex justify-between text-[11px]"><span>OKX ${x.sym}USDT永续</span><span class="px-2 py-0.5 rounded bg-${x.side==='short'?'red':'green'}-500/20 text-[10px]">${x.side.toUpperCase()} ${x.lev}x منفصل</span></div>
   <div class="mt-3"><div class="text-[11px] text-gray-500">الأرباح والخسائر (USDT) - حقيقي LIVE</div><div class="text-[26px] font-black ${neg?'text-red-500':'text-green-400'}">${x.gross>=0?'+':''}${x.gross.toFixed(2)} (${x.roe>=0?'+':''}${x.roe.toFixed(2)}%)</div><div class="text-[11px] text-gray-400">صافي $${x.net.toFixed(3)} | قمة $${x.best.toFixed(2)}</div></div>
   <div class="grid grid-cols-3 gap-3 mt-4 text-[11px]"><div><div class="text-gray-500">الحجم</div><div class="font-bold">${x.amt.toFixed(0)}</div></div><div><div class="text-gray-500">الهامش حقيقي</div><div class="font-bold">$${x.mgn.toFixed(2)}</div></div><div><div class="text-gray-500">التصفية</div><div class="font-bold">${x.liq?x.liq.toFixed(5):'--'}</div></div></div>
   <div class="grid grid-cols-2 gap-3 mt-3 text-[11px]"><div><div class="text-gray-500">دخول حقيقي</div><div class="font-bold">${x.entry.toFixed(5)}</div></div><div><div class="text-gray-500">حالي حقيقي</div><div class="font-bold">${x.last.toFixed(5)}</div></div></div>
   <button onclick="fetch('/api/close/${x.sym}').then(()=>location.reload())" class="w-full mt-3 bg-white text-black rounded-full py-2.5 text-[12px] font-bold">إغلاق حقيقي</button>
  </div>`
 }).join('') : `<div class="glass rounded-[20px] p-8 text-center"><div class="text-[32px]">🔍</div><div class="font-bold text-[13px] mt-2">$${d.total?d.total.toFixed(2):'56.67'} حر - يفحص كل العملات حقيقي LIVE</div><div class="text-[11px] text-gray-400 mt-1">ستوب -$1 حقيقي | تتبع ربح لأعلى قمة | تعويض $3</div></div>`;
 document.getElementById('closed').innerHTML=d.closed.length? d.closed.map(c=>`<div class="bg-black/40 rounded-lg p-2 flex justify-between text-[11px]"><span class="font-bold">${c.pair} ${c.side} <span class="${c.pnl>=0?'text-green-400':'text-red-400'}">${c.pnl>=0?'+':''}${c.pnl.toFixed(2)}$</span></span><span class="text-gray-500">${c.time} ${c.reason}</span></div>`).join('') : `<div class="text-[11px] text-gray-500 text-center py-3">السجل حقيقي - ينتظر أول صفقة مقفلة</div>`;
 const sc=await fetch('/api/scan').then(r=>r.json()).catch(()=>({signals:[]}));
 document.getElementById('sigs').innerHTML=sc.signals.slice(0,8).map(s=>`<div class="bg-black/40 rounded-xl p-2.5 flex justify-between items-center"><div><div class="text-[12px] font-bold">${s.symbol} <span class="px-1.5 py-0.5 rounded-full text-[9px] ${s.direction=='long'?'bg-green-500 text-black':'bg-red-500'}">${s.direction.toUpperCase()}</span> <span class="text-[10px] text-gray-400">$${(s.vol/1000000).toFixed(1)}M</span></div><div class="text-[10px] text-gray-500">RSI ${s.rsi} - حقيقي</div></div><div class="text-[11px] font-bold">${s.price.toFixed(4)}</div></div>`).join('') || `<div class="text-[11px] text-gray-500 text-center py-2">يفحص ${s.scan_count||40} عملة >$5M - LIVE</div>`;
}
setInterval(load,1000); load();
</script></body></html>
"""

threading.Thread(target=hunter,daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))