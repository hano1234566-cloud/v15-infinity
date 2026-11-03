import os, time, threading, ccxt, json
from flask import Flask, jsonify

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

STATE_FILE = "state.json"
FEE = 0.04
MARGIN = 2.0
LEV = 10
STOP = -0.50
TARGET = 1.0

# === حمل البيانات القديمة ===
def load_state():
    default = {"open":{}, "daily":0, "daily_gross":0, "fees":0, "wins":0, "losses":0, "trades":0, "bal":0, "total":0, "last":"V20026 - يكمل من القديم"}
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE,'r') as f:
                data=json.load(f)
                default.update(data)
                # open قديم من الملف نحتفظ بأسمائه فقط
                print(f"Loaded old state: {default['trades']} trades, daily ${default['daily']}")
                return default
    except Exception as e:
        print(f"load err {e}")
    return default

def save_state():
    try:
        with open(STATE_FILE,'w') as f:
            json.dump(STATE, f)
    except: pass

STATE = load_state()

app = Flask(__name__)
def get_ex():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'options':{'defaultType':'swap'},'enableRateLimit':True})

def get_bal():
    try:
        r=get_ex().private_get_account_balance()
        for d in r['data'][0]['details']:
            if d['ccy']=='USDT':
                STATE["bal"]=float(d['availBal'] or 0)
                STATE["total"]=float(d['eq'] or 0)
                save_state()
                return STATE["bal"]
    except: pass
    return STATE["bal"]

def sync_from_okx():
    """يشبك من البيانات القديمة في OKX ويكمل"""
    try:
        ex=get_ex()
        positions=ex.fetch_positions()
        found=[]
        for p in positions:
            amt=float(p.get('contracts',0) or 0)
            if amt>0:
                sym=p['symbol']
                entry=float(p.get('entryPrice',0) or 0)
                gross=float(p.get('unrealizedPnl',0) or 0)
                found.append(sym)
                if sym not in STATE["open"]:
                    # صفقة قديمة من OKX - نكمل منها
                    side=p.get('side','long')
                    name=sym.replace('/USDT:USDT','').replace(':USDT','')
                    STATE["open"][sym]={
                        "name":name,
                        "dir":'long' if side=='long' else 'short',
                        "entry":entry,
                        "best":gross,
                        "best_net":gross-FEE,
                        "from":"OKX_OLD"
                    }
                    print(f"🔄 كمل من القديم: {name} دخول {entry} ربح {gross}")
                else:
                    # حدث البيانات
                    STATE["open"][sym]["entry"]=entry
                    if gross>STATE["open"][sym].get("best",-999):
                        STATE["open"][sym]["best"]=gross
                        STATE["open"][sym]["best_net"]=gross-FEE
        # نظف اللي انقفلت في OKX
        for s in list(STATE["open"].keys()):
            if s not in found:
                # انقفلت - احسبها
                d=STATE["open"].pop(s,None)
                if d:
                    net=d.get("best_net",0)
                    STATE["daily"]+=net
                    STATE["trades"]+=1
                    if net>0: STATE["wins"]+=1
                    else: STATE["losses"]+=1
                    STATE["fees"]+=FEE
        save_state()
        return found
    except Exception as e:
        print(f"sync err {e}")
        return []

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
    # أول شي شبك من القديم
    sync_from_okx()
    get_bal()
    while True:
        try:
            get_bal()
            if int(time.time())%10==0:
                sync_from_okx()

            # حماية - يقفل الخسارة
            try:
                ex=get_ex()
                for p in ex.fetch_positions():
                    if float(p.get('contracts',0) or 0)>0:
                        gross=float(p.get('unrealizedPnl',0) or 0)
                        net=gross-FEE
                        sym=p['symbol']
                        if net<=STOP or net>=1.20:
                            if close_any(sym):
                                STATE["open"].pop(sym,None)
                                STATE["daily"]+=net
                                STATE["trades"]+=1
                                if net>0: STATE["wins"]+=1
                                else: STATE["losses"]+=1
                                STATE["fees"]+=FEE
                                STATE["last"]=f"{'✅' if net>0 else '🔴'} قفل {sym.replace('/USDT:USDT','')} صافي ${net:.2f} - كمل من القديم"
                                save_state()
            except: pass

            save_state()
            time.sleep(2)
        except Exception as e:
            STATE["last"]=f"خطأ {str(e)[:60]}"
            time.sleep(3)

@app.route("/")
def index(): return HTML
@app.route("/api/pnl")
def pnl():
    sync_from_okx()
    live=[]
    try:
        ex=get_ex()
        for p in ex.fetch_positions():
            if float(p.get('contracts',0) or 0)>0:
                entry=float(p.get('entryPrice',0) or 0); last=float(p.get('markPrice',0) or entry)
                gross=float(p.get('unrealizedPnl',0) or 0); roe=float(p.get('percentage',0) or 0)
                mgn=float(p.get('imr',0) or p.get('margin',0) or 53); amt=float(p.get('contracts',0) or 0)
                lev=int(float(p.get('leverage',0) or 3)); liq=float(p.get('liquidationPrice',0) or 0)
                sym=p['symbol']; name=sym.replace('/USDT:USDT','').replace(':USDT','')
                live.append({"sym":name,"full":sym,"side":p.get('side','long'),"gross":gross,"net":gross-FEE,"entry":entry,"last":last,"amt":amt,"mgn":mgn,"lev":lev,"roe":roe,"liq":liq,"from":"OKX"})
    except: pass
    return jsonify({"bal":get_bal(),"total":STATE["total"],"daily":STATE["daily"],"trades":STATE["trades"],"wins":STATE["wins"],"losses":STATE["losses"],"fees":STATE["fees"],"last":STATE["last"],"live":live,"open_count":len(STATE["open"])})

@app.route("/api/close/<sym>")
def close_api(sym):
    try:
        for p in get_ex().fetch_positions():
            if sym in p['symbol'] and float(p.get('contracts',0) or 0)>0:
                close_any(p['symbol']); sync_from_okx()
                return jsonify({"ok":True})
        return jsonify({"ok":False})
    except Exception as e:
        return jsonify({"ok":False,"err":str(e)})

HTML = """
<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>يكمل من القديم</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{background:#000;color:#fff}.card{background:#111214;border-radius:16px}</style></head>
<body class="max-w-[420px] mx-auto p-3">
<div class="bg-[#111214] rounded-[20px] p-4">
<div class="flex justify-between text-[11px] text-gray-400"><span>يكمل من البيانات القديمة - OKX</span><span class="text-green-400">● LIVE</span></div>
<div class="flex gap-2 items-baseline mt-2"><div id="bal" class="text-[28px] font-black">$0 متاح</div><div id="total" class="text-[11px] text-gray-500"></div></div>
<div id="last" class="text-[12px] font-bold mt-2 text-yellow-300"></div>
<div class="flex gap-2 mt-3 flex-wrap"><span id="cnt" class="bg-white/10 px-2.5 py-1 rounded-full text-[10px]"></span><span id="daily" class="bg-white/10 px-2.5 py-1 rounded-full text-[10px]"></span><span id="tr" class="bg-white/10 px-2.5 py-1 rounded-full text-[10px]"></span></div>
</div>
<div id="box" class="mt-3"></div>
<script>
async function load(){
 const d=await fetch('/api/pnl').then(r=>r.json());
 document.getElementById('bal').textContent=`$${d.bal.toFixed(2)} متاح`;
 document.getElementById('total').textContent=`/ $${d.total.toFixed(2)} كلي`;
 document.getElementById('last').textContent=d.last;
 document.getElementById('cnt').textContent=d.open_count+'/2 مفتوح';
 document.getElementById('daily').textContent=`اليوم صافي $${d.daily.toFixed(2)}`;
 document.getElementById('tr').textContent=`${d.trades} صفقة | ✅${d.wins} ❌${d.losses} | رسوم $${d.fees.toFixed(2)}`;
 document.getElementById('box').innerHTML=d.live.map(x=>{
  const neg=x.gross<0; return `<div class="card p-4 mt-3 border ${neg?'border-red-500/50':'border-green-500/30'}">
   <div class="flex justify-between text-[11px]"><span>العقود الدائمة ${x.sym}USDT</span><span class="px-2 py-0.5 rounded bg-red-500/20 text-red-400 text-[10px]">${x.side==='short'?'بيع':'شراء'} ${x.lev}x منفصل • من القديم</span></div>
   <div class="mt-3"><div class="text-[11px] text-gray-500">الأرباح والخسائر (USDT)</div><div class="text-[24px] font-bold ${neg?'text-red-500':'text-green-400'}">${x.gross>=0?'+':''}${x.gross.toFixed(2)} (${x.roe>=0?'+':''}${x.roe.toFixed(2)}%)</div><div class="text-[11px] text-gray-500">صافي بعد رسوم $${x.net.toFixed(3)} • LIVE من OKX</div></div>
   <div class="grid grid-cols-3 gap-3 mt-4 text-[11px]"><div><div class="text-gray-500">الحجم (${x.sym})</div><div class="font-bold">${x.amt.toFixed(0)}</div></div><div><div class="text-gray-500">الهامش</div><div class="font-bold">+ $${x.mgn.toFixed(0)}</div></div><div><div class="text-gray-500">ضمان الصيانة</div><div class="font-bold text-green-400">4,636%</div></div></div>
   <div class="grid grid-cols-3 gap-3 mt-3 text-[11px]"><div><div class="text-gray-500">سعر الدخول</div><div class="font-bold">${x.entry.toFixed(5)}</div></div><div><div class="text-gray-500">المرجعي</div><div class="font-bold">${x.last.toFixed(5)}</div></div><div><div class="text-gray-500">التصفية</div><div class="font-bold">${x.liq?x.liq.toFixed(5):'0.22396'}</div></div></div>
   <div class="flex gap-2 mt-4"><button onclick="fetch('/api/close/${x.sym}').then(()=>location.reload())" class="flex-1 bg-white text-black rounded-full py-2.5 text-[12px] font-bold">إغلاق</button><button class="flex-1 bg-[#1e1e20] rounded-full py-2.5 text-[12px]">TP/SL</button></div>
  </div>`
 }).join('') || `<div class="text-center py-16 text-gray-500">يبحث... يكمل من القديم</div>`;
}
setInterval(load,1500); load();
</script></body></html>
"""

threading.Thread(target=hunter,daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))