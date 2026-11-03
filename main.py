import os, time, threading, ccxt, json
from flask import Flask, jsonify
import numpy as np

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL = 0.0
LAST = "V20028 - نفس مفاتيح V20015 + يكمل من القديم"
FEE = 0.04
MARGIN = 2.0
LEV = 10
STOP = -0.50
STATE = {"open":{}, "daily":0, "daily_gross":0, "avail":0, "total":0, "wins":0, "losses":0, "fees":0, "trades":0}

STATE_FILE = "/tmp/state_old.json"
try:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE,'r') as f:
            d=json.load(f)
            STATE["daily"]=d.get("daily",0)
            STATE["wins"]=d.get("wins",0)
            STATE["losses"]=d.get("losses",0)
            STATE["trades"]=d.get("trades",0)
            STATE["fees"]=d.get("fees",0)
except: pass

def save():
    try:
        with open(STATE_FILE,'w') as f:
            json.dump(STATE,f)
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
    except:
        return BAL

def sync_real():
    try:
        for p in get_ex().fetch_positions():
            if float(p.get('contracts',0) or 0)>0:
                sym=p['symbol']
                if sym not in STATE["open"]:
                    entry=float(p.get('entryPrice',0) or 0)
                    side=p.get('side','long')
                    name=sym.replace('/USDT:USDT','').replace(':USDT','')
                    STATE["open"][sym]={"name":name,"dir":'long' if side=='long' else 'short',"entry":entry,"best":float(p.get('unrealizedPnl',0) or 0),"best_net":float(p.get('unrealizedPnl',0) or 0)-FEE,"from":"OLD"}
    except: pass

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
    sync_real()
    get_real_balance()
    while True:
        try:
            get_real_balance()
            if int(time.time())%8==0:
                sync_real()
            # يقفل خسارة -0.50 صافي
            try:
                ex=get_ex()
                for p in ex.fetch_positions():
                    if float(p.get('contracts',0) or 0)>0:
                        gross=float(p.get('unrealizedPnl',0) or 0)
                        net=gross-FEE
                        sym=p['symbol']
                        if net<=STOP or net>=1.20:
                            if close_any(sym):
                                LAST=f"{'✅' if net>0 else '🔴'} قفل {sym.replace('/USDT:USDT','')} صافي ${net:.2f} - كمل من القديم"
                                STATE["open"].pop(sym,None)
                                STATE["daily"]+=net
                                STATE["trades"]+=1
                                if net>0: STATE["wins"]+=1
                                else: STATE["losses"]+=1
                                STATE["fees"]+=FEE
                                save()
            except: pass
            save()
            time.sleep(2)
        except Exception as e:
            LAST=f"خطأ {str(e)[:70]}"
            time.sleep(3)

@app.route("/")
def index(): return HTML
@app.route("/api/status")
def status():
    return jsonify({"bal":get_real_balance(),"avail":STATE["avail"],"total":STATE["total"],"count":len(STATE["open"]),"last":LAST,"daily":STATE["daily"],"wins":STATE["wins"],"losses":STATE["losses"],"trades":STATE["trades"],"fees":STATE["fees"]})

@app.route("/api/pnl")
def pnl():
    live=[]
    try:
        ex=get_ex()
        for p in ex.fetch_positions():
            if float(p.get('contracts',0) or 0)>0:
                entry=float(p.get('entryPrice',0) or 0)
                last=float(p.get('markPrice',0) or entry)
                gross=float(p.get('unrealizedPnl',0) or 0)
                roe=float(p.get('percentage',0) or 0)
                mgn=float(p.get('imr',0) or p.get('margin',0) or 53)
                amt=float(p.get('contracts',0) or 0)
                lev=int(float(p.get('leverage',0) or 3))
                liq=float(p.get('liquidationPrice',0) or 0)
                sym=p['symbol']
                name=sym.replace('/USDT:USDT','').replace(':USDT','')
                live.append({"sym":name,"full":sym,"side":p.get('side','long'),"gross":gross,"net":gross-FEE,"entry":entry,"last":last,"amt":amt,"mgn":mgn,"lev":lev,"roe":roe,"liq":liq})
    except Exception as e:
        LAST=f"pnl err {str(e)[:60]}"
    return jsonify({"bal":get_real_balance(),"total":STATE["total"],"live":live})

@app.route("/api/close/<sym>")
def close_api(sym):
    try:
        for p in get_ex().fetch_positions():
            if sym in p['symbol'] and float(p.get('contracts',0) or 0)>0:
                close_any(p['symbol'])
                sync_real()
                return jsonify({"ok":True})
        return jsonify({"ok":False})
    except Exception as e:
        return jsonify({"ok":False,"err":str(e)})

HTML = """
<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>مفاتيح صحيحة</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{background:#000;color:#fff}.card{background:#111214;border-radius:16px}</style></head>
<body class="max-w-[420px] mx-auto p-3">
<div class="bg-[#111214] rounded-[22px] p-4">
<div class="flex justify-between text-[11px] text-gray-400"><span>OKX - مفاتيح V20015 الأصلية - يكمل من القديم</span><span class="text-green-400">LIVE ●</span></div>
<div class="flex gap-2 items-baseline mt-2"><div id="bal" class="text-[28px] font-black">$0 متاح</div><div id="total" class="text-[11px] text-gray-500"></div></div>
<div id="last" class="text-[12px] font-bold mt-2 text-yellow-300"></div>
<div class="flex gap-2 mt-2"><span id="cnt" class="bg-white/10 px-2.5 py-1 rounded-full text-[10px]"></span><span id="daily" class="bg-white/10 px-2.5 py-1 rounded-full text-[10px]"></span></div>
</div>
<div id="box" class="mt-3"></div>
<script>
async function load(){
 const s=await fetch('/api/status').then(r=>r.json());
 document.getElementById('bal').textContent=`$${s.bal.toFixed(2)} متاح`;
 document.getElementById('total').textContent=`/ $${s.total.toFixed(2)} كلي`;
 document.getElementById('last').textContent=s.last;
 document.getElementById('cnt').textContent=s.count+'/2 مفتوح | '+s.trades+' صفقة';
 document.getElementById('daily').textContent=`صافي $${s.daily.toFixed(2)} | ✅${s.wins} ❌${s.losses}`;
 const d=await fetch('/api/pnl').then(r=>r.json());
 document.getElementById('box').innerHTML=d.live.map(x=>{
  const neg=x.gross<0; return `<div class="card p-4 mt-3 border ${neg?'border-red-500/60':'border-green-500/40'}">
   <div class="flex justify-between text-[11px]"><span>العقود الدائمة ${x.sym}USDT</span><span class="px-2 py-0.5 rounded bg-red-500/20 text-red-400 text-[10px]">${x.side==='short'?'بيع':'شراء'} ${x.lev}x منفصل • قديم</span></div>
   <div class="mt-3"><div class="text-[11px] text-gray-500">الأرباح والخسائر (USDT)</div><div class="text-[24px] font-bold ${neg?'text-red-500':'text-green-400'}">${x.gross>=0?'+':''}${x.gross.toFixed(2)} (${x.roe>=0?'+':''}${x.roe.toFixed(2)}%)</div><div class="text-[11px] text-gray-500">صافي $${x.net.toFixed(3)} • LIVE</div></div>
   <div class="grid grid-cols-3 gap-3 mt-4 text-[11px]"><div><div class="text-gray-500">الحجم</div><div class="font-bold">${x.amt.toFixed(2)}</div></div><div><div class="text-gray-500">الهامش</div><div class="font-bold">+ $${x.mgn.toFixed(2)}</div></div><div><div class="text-gray-500">التصفية</div><div class="font-bold">${x.liq?x.liq.toFixed(5):'0.22396'}</div></div></div>
   <div class="grid grid-cols-2 gap-3 mt-3 text-[11px]"><div><div class="text-gray-500">دخول</div><div class="font-bold">${x.entry.toFixed(5)}</div></div><div><div class="text-gray-500">حالي</div><div class="font-bold">${x.last.toFixed(5)}</div></div></div>
   <button onclick="fetch('/api/close/${x.sym}').then(()=>location.reload())" class="w-full mt-4 bg-white text-black rounded-full py-2.5 text-[12px] font-bold">إغلاق</button>
  </div>`
 }).join('') || `<div class="text-center py-16 text-gray-500">يبحث... البيانات القديمة محفوظة</div>`;
}
setInterval(load,1500); load();
</script></body></html>
"""

threading.Thread(target=hunter,daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))