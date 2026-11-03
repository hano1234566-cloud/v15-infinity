import os, time, threading, ccxt, json
from flask import Flask, jsonify
import numpy as np

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL = 0.0
LAST = "V20029 - نفس المفتاح + شارتات + $1"
FEE = 0.04
MARGIN = 2.0
LEV = 10
STOP = -0.50
TARGET = 1.0
SECOND_NET = 0.50

STATE = {"open":{}, "daily":0, "avail":0, "total":0, "wins":0, "losses":0, "fees":0, "trades":0}
FILE = "/tmp/state_old.json"
try:
    if os.path.exists(FILE):
        with open(FILE,'r') as f:
            d=json.load(f)
            for k in ["daily","wins","losses","trades","fees"]:
                STATE[k]=d.get(k,0)
except: pass

def save():
    try:
        with open(FILE,'w') as f:
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
                    STATE["open"][sym]={"name":name,"dir":'long' if side=='long' else 'short',"entry":entry,"best":float(p.get('unrealizedPnl',0) or 0)}
    except: pass

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

def scan_live():
    sigs=[]
    for sym in ["ENA/USDT:USDT","FET/USDT:USDT","TAO/USDT:USDT","RENDER/USDT:USDT","SUI/USDT:USDT","ARB/USDT:USDT","WLD/USDT:USDT","OP/USDT:USDT","APT/USDT:USDT"]:
        try:
            ex=get_ex(); ohlcv=ex.fetch_ohlcv(sym,'1h',100)
            closes=[c[4] for c in ohlcv]; price=closes[-1]; rsi=calc_rsi(closes)
            if rsi<32: sigs.append({"symbol":sym.replace("/USDT:USDT",""),"full":sym,"direction":"long","price":price,"rsi":round(rsi,1),"score":9})
            elif rsi>68: sigs.append({"symbol":sym.replace("/USDT:USDT",""),"full":sym,"direction":"short","price":price,"rsi":round(rsi,1),"score":9})
            elif rsi<40: sigs.append({"symbol":sym.replace("/USDT:USDT",""),"full":sym,"direction":"long","price":price,"rsi":round(rsi,1),"score":7})
            elif rsi>60: sigs.append({"symbol":sym.replace("/USDT:USDT",""),"full":sym,"direction":"short","price":price,"rsi":round(rsi,1),"score":7})
        except: pass
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
    global LAST
    sync_real()
    get_real_balance()
    while True:
        try:
            get_real_balance()
            if int(time.time())%8==0: sync_real()

            # حماية وهدف
            try:
                ex=get_ex()
                for p in ex.fetch_positions():
                    if float(p.get('contracts',0) or 0)>0:
                        gross=float(p.get('unrealizedPnl',0) or 0)
                        net=gross-FEE
                        sym=p['symbol']
                        if net<=STOP or net>=1.20:
                            if close_any(sym):
                                LAST=f"{'✅' if net>0 else '🔴'} قفل {sym.replace('/USDT:USDT','')} صافي ${net:.2f} - ENA كانت ${56.67} الآن"
                                STATE["open"].pop(sym,None)
                                STATE["daily"]+=net
                                STATE["trades"]+=1
                                if net>0: STATE["wins"]+=1
                                else: STATE["losses"]+=1
                                STATE["fees"]+=FEE
                                save()
            except: pass

            # حساب صافي المفتوح
            nets=[]
            try:
                for p in get_ex().fetch_positions():
                    if float(p.get('contracts',0) or 0)>0:
                        nets.append(float(p.get('unrealizedPnl',0) or 0)-FEE)
            except: pass
            if not nets and STATE["open"]:
                for s,d in STATE["open"].items():
                    try:
                        last=get_ex().fetch_ticker(s)["last"]
                        entry=d["entry"]
                        g=(last-entry)/entry*MARGIN*LEV if d["dir"]=="long" else (entry-last)/entry*MARGIN*LEV
                        nets.append(g-FEE)
                    except:
                        nets.append(d.get("best",0)-FEE)

            total=sum(nets) if nets else 0
            can=False
            if len(STATE["open"])==0:
                can=True; LAST="🔍 يبحث - ENA انقفلت - يفتح $1 جديد"
            elif len(STATE["open"])==1:
                if nets and nets[0]>=SECOND_NET:
                    can=True; LAST=f"🟢 الأولى صافي ${nets[0]:.2f} - يفتح الثانية"
                else:
                    LAST=f"⏳ الأولى صافي ${nets[0]:.2f} - ينتظر ${SECOND_NET}"
            else:
                LAST=f"✅ صفقتين صافي ${total:.2f}"

            # فتح صفقات جديدة مستمر
            if can and get_real_balance()>=MARGIN and len(STATE["open"])<2:
                sigs=scan_live()
                exist=[v["name"] for v in STATE["open"].values()]
                sig=next((s for s in sigs if s["symbol"] not in exist),None)
                if sig:
                    try:
                        ex=get_ex(); ex.set_leverage(LEV,sig["full"])
                        side="buy" if sig["direction"]=="long" else "sell"
                        amt=(MARGIN*LEV)/sig["price"]; amt=float(ex.amount_to_precision(sig["full"],max(amt,1)))
                        order=None
                        for mode in [{'tdMode':'isolated'},{'tdMode':'cross'}]:
                            try: order=ex.create_market_order(sig["full"],side,amt,None,mode); break
                            except: continue
                        if order:
                            entry=order.get("average") or sig["price"]
                            STATE["open"][sig["full"]]={"name":sig["symbol"],"dir":sig["direction"],"entry":entry,"best":0}
                            LAST=f"✅ فتح {sig['symbol']} ${MARGIN}×{LEV} هدف $1 - بعد ENA"
                            save()
                    except Exception as e:
                        LAST=f"❌ {str(e)[:70]}"
            time.sleep(2)
        except Exception as e:
            LAST=f"خطأ {str(e)[:70]}"; time.sleep(3)

@app.route("/")
def index(): return HTML
@app.route("/api/status")
def status(): return jsonify({"bal":get_real_balance(),"avail":STATE["avail"],"total":STATE["total"],"count":len(STATE["open"]),"last":LAST,"daily":STATE["daily"],"wins":STATE["wins"],"losses":STATE["losses"],"trades":STATE["trades"],"fees":STATE["fees"]})
@app.route("/api/pnl")
def pnl():
    live=[]
    try:
        ex=get_ex()
        for p in ex.fetch_positions():
            if float(p.get('contracts',0) or 0)>0:
                entry=float(p.get('entryPrice',0) or 0); last=float(p.get('markPrice',0) or entry)
                gross=float(p.get('unrealizedPnl',0) or 0); roe=float(p.get('percentage',0) or 0)
                mgn=float(p.get('imr',0) or p.get('margin',0) or MARGIN); amt=float(p.get('contracts',0) or 0)
                lev=int(float(p.get('leverage',0) or LEV)); liq=float(p.get('liquidationPrice',0) or 0)
                sym=p['symbol']; name=sym.replace('/USDT:USDT','').replace(':USDT','')
                live.append({"sym":name,"full":sym,"side":p.get('side','long'),"gross":gross,"net":gross-FEE,"entry":entry,"last":last,"amt":amt,"mgn":mgn,"lev":lev,"roe":roe,"liq":liq})
    except: pass
    return jsonify({"bal":get_real_balance(),"total":STATE["total"],"live":live})

@app.route("/api/scan")
def scan(): return jsonify({"signals":scan_live()})
@app.route("/api/close/<sym>")
def close_api(sym):
    try:
        for p in get_ex().fetch_positions():
            if sym in p['symbol'] and float(p.get('contracts',0) or 0)>0:
                close_any(p['symbol']); return jsonify({"ok":True})
        return jsonify({"ok":False})
    except Exception as e:
        return jsonify({"ok":False,"err":str(e)})

HTML = """
<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>شارتات + صفقات</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{background:#000;color:#fff}.card{background:#111214;border-radius:16px}.glass{background:#111c2f;border:1px solid #1e355a}</style></head>
<body class="max-w-[480px] mx-auto p-3">
<div class="bg-[#111214] rounded-[22px] p-4">
<div class="flex justify-between text-[11px] text-gray-400"><span>OKX - V20015 الأصلي + شارتات - يكمل من القديم</span><span class="text-green-400">LIVE ●</span></div>
<div class="flex gap-2 items-baseline mt-2"><div id="bal" class="text-[28px] font-black">$0 متاح</div><div id="total" class="text-[11px] text-gray-500"></div></div>
<div id="last" class="text-[12px] font-bold mt-2 text-yellow-300"></div>
<div class="flex gap-2 mt-3 flex-wrap"><span id="cnt" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="daily" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="tr" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span></div>
</div>

<div id="liveBig" class="my-3"></div>

<div class="glass rounded-2xl p-3 mt-3"><div class="font-black text-[12px] mb-2">📊 الشارتات - فرص LIVE $1</div><div id="sigs" class="space-y-2"></div></div>

<div class="mt-3 bg-[#111214] rounded-xl p-3 text-[10px] text-gray-400">
📍 <b>وش صار على ENA؟</b> انقفلت على -$1 تقريبا - كان هامشها $53 - الآن $56.67 حر<br>
✅ الآن يفتح $2×10 = $20 حجم - هدف $1 صافي - حركة 5% فقط<br>
♾️ مستمر بلا توقف - يكمل من القديم
</div>

<script>
async function load(){
 const s=await fetch('/api/status').then(r=>r.json());
 document.getElementById('bal').textContent=`$${s.bal.toFixed(2)} متاح`;
 document.getElementById('total').textContent=`/ $${s.total.toFixed(2)} كلي`;
 document.getElementById('last').textContent=s.last;
 document.getElementById('cnt').textContent=s.count+'/2 مفتوح | '+s.trades+' صفقة';
 document.getElementById('daily').textContent=`صافي اليوم $${s.daily.toFixed(2)}`;
 document.getElementById('tr').textContent=`✅${s.wins} ❌${s.losses} رسوم $${s.fees.toFixed(2)}`;
 const d=await fetch('/api/pnl').then(r=>r.json());
 document.getElementById('liveBig').innerHTML=d.live.length? d.live.map(x=>{
  const neg=x.gross<0; return `<div class="card p-4 border-2 ${neg?'border-red-500/60 bg-red-500/10':'border-green-500/50 bg-green-500/10'}">
   <div class="flex justify-between text-[11px]"><span>العقود الدائمة ${x.sym}USDT</span><span class="px-2 py-0.5 rounded bg-${x.side==='short'?'red':'green'}-500/20 text-${x.side==='short'?'red':'green'}-400 text-[10px]">${x.side==='short'?'بيع':'شراء'} ${x.lev}x</span></div>
   <div class="mt-3"><div class="text-[11px] text-gray-500">الأرباح والخسائر (USDT)</div><div class="text-[24px] font-bold ${neg?'text-red-500':'text-green-400'}">${x.gross>=0?'+':''}${x.gross.toFixed(2)} (${x.roe>=0?'+':''}${x.roe.toFixed(2)}%)</div><div class="text-[11px] text-gray-500">صافي $${x.net.toFixed(3)} - هدف $1</div></div>
   <div class="grid grid-cols-3 gap-3 mt-4 text-[11px]"><div><div class="text-gray-500">الحجم</div><div class="font-bold">${x.amt.toFixed(0)}</div></div><div><div class="text-gray-500">الهامش</div><div class="font-bold">+ $${x.mgn.toFixed(0)}</div></div><div><div class="text-gray-500">التصفية</div><div class="font-bold">${x.liq?x.liq.toFixed(5):'--'}</div></div></div>
   <div class="grid grid-cols-2 gap-3 mt-3 text-[11px]"><div><div class="text-gray-500">دخول</div><div class="font-bold">${x.entry.toFixed(5)}</div></div><div><div class="text-gray-500">حالي LIVE</div><div class="font-bold">${x.last.toFixed(5)}</div></div></div>
   <div class="mt-3 h-2 bg-black/60 rounded-full overflow-hidden"><div class="h-full ${neg?'bg-red-500':'bg-green-500'} transition-all" style="width:${Math.min(100,Math.abs(x.net*100))}%"></div></div>
   <button onclick="fetch('/api/close/${x.sym}').then(()=>location.reload())" class="w-full mt-3 bg-white text-black rounded-full py-2 text-[12px] font-bold">إغلاق</button>
  </div>`
 }).join('') : `<div class="glass rounded-[20px] p-8 text-center"><div class="text-[30px]">📊</div><div class="font-bold text-[13px] mt-2">ENA انقفلت - $56.67 حر</div><div class="text-[11px] text-gray-400 mt-1">يبحث عن صفقة $1 صافي - الشارتات تحت</div></div>`;
 const sc=await fetch('/api/scan').then(r=>r.json());
 document.getElementById('sigs').innerHTML=sc.signals.length? sc.signals.map(s=>`<div class="bg-black/40 rounded-xl p-2.5 flex justify-between"><span class="text-[12px] font-bold">${s.symbol} <span class="px-1.5 py-0.5 rounded-full text-[9px] ${s.direction=='long'?'bg-green-500 text-black':'bg-red-500'}">${s.direction.toUpperCase()}</span> RSI ${s.rsi}</span><span class="text-[11px]">${s.price.toFixed(4)}</span></div>`).join('') : `<div class="text-[11px] text-gray-500 text-center py-2">ينتظر فرصة $1</div>`;
}
setInterval(load,1500); load();
</script></body></html>
"""

threading.Thread(target=hunter,daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))