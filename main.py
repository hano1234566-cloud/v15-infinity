import os, time, threading, ccxt
from flask import Flask, jsonify
import numpy as np

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL = 0.0
LAST = "V20022 - هدف $1 صافي"
FEE_PER_TRADE = 0.04  # $2*10 حجم $20 رسوم 0.1% = $0.02 *2 = $0.04 احتياط
MARGIN_PER_TRADE = 2.0  # $2 للصفقة
LEVERAGE = 10
TARGET_NET = 1.0  # هدف $1 صافي
STOP_NET = -0.50  # وقف -$0.50 صافي
SECOND_OPEN_NET = 0.50  # الثانية تفتح إذا الأولى $0.50 صافي

STATE = {"open":{}, "daily":0, "daily_gross":0, "avail":0, "total":0, "wins":0, "losses":0, "fees":0, "total_trades":0}

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
                    STATE["open"][sym]={"name":name,"dir":'long' if side=='long' else 'short',"entry":entry,"best":0,"best_net":0}
    except: pass

def calc_rsi(prices,p=14):
    try:
        prices=np.array(prices,float); d=np.diff(prices)
        up=np.where(d>0,d,0); down=np.where(d<0,-d,0)
        mu=np.mean(up[:p]); md=np.mean(down[:p])
        if md==0: return 70
        rsi=100-(100/(1+mu/md))
        for i in range(p,len(d)):
            mu=(mu*(p-1)+up[i])/p; md=(md*(p-1)+down[i])/p
            rsi=100-(100/(1+mu/md)) if md!=0 else 70
        return float(rsi)
    except: return 50

def scan_live():
    sigs=[]
    for sym in ["ENA/USDT:USDT","FET/USDT:USDT","TAO/USDT:USDT","RENDER/USDT:USDT","SUI/USDT:USDT","ARB/USDT:USDT","WLD/USDT:USDT","OP/USDT:USDT","APT/USDT:USDT","SEI/USDT:USDT"]:
        try:
            ex=get_ex(); ohlcv=ex.fetch_ohlcv(sym,'1h',100)
            closes=[c[4] for c in ohlcv]; price=closes[-1]; rsi=calc_rsi(closes)
            if rsi<30: sigs.append({"symbol":sym.replace("/USDT:USDT",""),"full":sym,"direction":"long","price":price,"rsi":round(rsi,1),"score":9})
            elif rsi>70: sigs.append({"symbol":sym.replace("/USDT:USDT",""),"full":sym,"direction":"short","price":price,"rsi":round(rsi,1),"score":9})
            elif rsi<38: sigs.append({"symbol":sym.replace("/USDT:USDT",""),"full":sym,"direction":"long","price":price,"rsi":round(rsi,1),"score":7})
            elif rsi>62: sigs.append({"symbol":sym.replace("/USDT:USDT",""),"full":sym,"direction":"short","price":price,"rsi":round(rsi,1),"score":7})
        except: pass
    return sorted(sigs,key=lambda x:x["score"],reverse=True)

def hunter():
    global BAL, LAST
    sync_real()
    while True:
        try:
            BAL=get_real_balance()
            if int(time.time())%8==0: sync_real()

            if STATE["avail"]<2 and STATE["total"]>=5:
                try:
                    get_ex().private_post_asset_transfer({"ccy":"USDT","amt":"5","from":"6","to":"18","type":"0"})
                    time.sleep(3); get_real_balance()
                except: pass

            # حماية - يقفل على STOP_NET صافي
            try:
                ex=get_ex()
                for p in ex.fetch_positions():
                    if float(p.get('contracts',0) or 0)>0:
                        gross=float(p.get('unrealizedPnl',0) or 0)
                        net=gross - FEE_PER_TRADE
                        sym=p['symbol']
                        # إذا وصل هدف $1 - يثبت؟ لا يتركها تكمل ل $1.5 تريلنج
                        if net >= TARGET_NET + 0.5:
                            # تريلنج بعد $1.5
                            pass
                        if net <= STOP_NET:
                            try:
                                side='sell' if p['side']=='long' else 'buy'
                                ex.create_market_order(sym, side, float(p.get('contracts',0)), None, {'tdMode':'cross'})
                                LAST=f"🔴 قفل حماية صافي ${net:.2f} خام ${gross:.2f}"
                                if sym in STATE["open"]:
                                    STATE["open"].pop(sym,None)
                                    STATE["daily"]+=net
                                    STATE["daily_gross"]+=gross
                                    STATE["fees"]+=FEE_PER_TRADE
                                    STATE["losses"]+=1
                                    STATE["total_trades"]+=1
                            except: pass
                        # هدف - يقفل على $1.20 صافي تلقائي؟
                        elif net >= 1.20:
                            try:
                                side='sell' if p['side']=='long' else 'buy'
                                ex.create_market_order(sym, side, float(p.get('contracts',0)), None, {'tdMode':'cross'})
                                LAST=f"✅ قفل هدف صافي ${net:.2f} خام ${gross:.2f} - $1 دولار"
                                if sym in STATE["open"]:
                                    STATE["open"].pop(sym,None)
                                    STATE["daily"]+=net
                                    STATE["daily_gross"]+=gross
                                    STATE["fees"]+=FEE_PER_TRADE
                                    STATE["wins"]+=1
                                    STATE["total_trades"]+=1
                            except: pass
            except: pass

            try:
                ex=get_ex(); open_syms=[p["symbol"] for p in ex.fetch_positions() if float(p.get('contracts',0))>0]
                for s in list(STATE["open"].keys()):
                    if s not in open_syms:
                        d=STATE["open"].pop(s,None)
                        if d:
                            net=d.get("best_net",0)
                            gross=d.get("best",0)
                            STATE["daily"]+=net
                            STATE["daily_gross"]+=gross
                            STATE["fees"]+=FEE_PER_TRADE
                            STATE["total_trades"]+=1
                            if net>0: STATE["wins"]+=1
                            else: STATE["losses"]+=1
            except: pass

            try:
                ex=get_ex()
                for p in ex.fetch_positions():
                    if float(p.get('contracts',0))>0:
                        sym=p['symbol']
                        if sym in STATE["open"]:
                            gross=float(p.get('unrealizedPnl',0) or 0)
                            net=gross - FEE_PER_TRADE
                            if gross>STATE["open"][sym]["best"]:
                                STATE["open"][sym]["best"]=gross
                                STATE["open"][sym]["best_net"]=net
            except: pass

            open_nets=[]
            open_gross=[]
            try:
                for p in get_ex().fetch_positions():
                    if float(p.get('contracts',0))>0:
                        g=float(p.get('unrealizedPnl',0) or 0)
                        open_gross.append(g)
                        open_nets.append(g - FEE_PER_TRADE)
            except: pass

            total_net=sum(open_nets) if open_nets else 0
            can=False

            if len(STATE["open"])==0:
                can=True
                LAST=f"🔍 يبحث - هدف ${TARGET_NET} صافي لكل صفقة"

            elif len(STATE["open"])==1:
                if open_nets and open_nets[0] < -0.10:
                    LAST=f"🔴 الوحيدة صافي ${open_nets[0]:.3f} - ينتظر ربح"
                    can=False
                elif open_nets and open_nets[0] >= SECOND_OPEN_NET:
                    can=True
                    LAST=f"🟢 الأولى صافي ${open_nets[0]:.3f} - يفتح الثانية لهدف ${TARGET_NET}"
                else:
                    LAST=f"⏳ الأولى صافي ${open_nets[0]:.3f} - ينتظر ${SECOND_OPEN_NET} للثانية"
                    can=False

            elif len(STATE["open"])>=2:
                if total_net < -0.20:
                    LAST=f"⛔ الصفقتين صافي ${total_net:.3f} - ما يفتح ثالثة"
                else:
                    LAST=f"✅ صفقتين صافي ${total_net:.3f} - هدف ${TARGET_NET*2}"
                can=False

            if can and BAL>=MARGIN_PER_TRADE and len(STATE["open"])<2:
                sigs=scan_live()
                existing=[v["name"] for v in STATE["open"].values()]
                sig=next((s for s in sigs if s["symbol"] not in existing),None)
                if sig:
                    try:
                        ex=get_ex(); ex.set_leverage(LEVERAGE,sig["full"])
                        side="buy" if sig["direction"]=="long" else "sell"
                        # $2 *10 = $20 حجم
                        amt=(MARGIN_PER_TRADE*LEVERAGE)/sig["price"]
                        amt=max(amt,1.0)
                        amt=float(ex.amount_to_precision(sig["full"],amt))
                        order=None
                        for mode in [{'tdMode':'cross'},{'tdMode':'isolated'}]:
                            try: order=ex.create_market_order(sig["full"],side,amt,None,mode); break
                            except: continue
                        if order:
                            entry=order.get("average") or sig["price"]
                            STATE["open"][sig["full"]]={"name":sig["symbol"],"dir":sig["direction"],"entry":entry,"best":0,"best_net":-FEE_PER_TRADE}
                            LAST=f"✅ فتح ${MARGIN_PER_TRADE}×{LEVERAGE} {sig['symbol']} هدف ${TARGET_NET} صافي"
                    except Exception as e:
                        LAST=f"❌ {str(e)[:80]}"
            time.sleep(2)
        except Exception as e:
            LAST=f"خطأ {str(e)[:80]}"; time.sleep(3)

@app.route("/")
def index(): return DASH_HTML
@app.route("/api/status")
def status(): return jsonify({"balance":get_real_balance(),"avail":STATE["avail"],"total":STATE["total"],"count":len(STATE["open"]),"last":LAST,"daily":STATE["daily"],"daily_gross":STATE["daily_gross"],"fees":STATE["fees"],"wins":STATE["wins"],"losses":STATE["losses"],"total_trades":STATE["total_trades"],"fee":FEE_PER_TRADE,"target":TARGET_NET,"margin":MARGIN_PER_TRADE,"lev":LEVERAGE})
@app.route("/api/pnl_live")
def pnl_live():
    live=[]
    try:
        ex=get_ex()
        for p in ex.fetch_positions():
            if float(p.get('contracts',0) or 0)>0:
                entry=float(p.get('entryPrice',0) or 0); last=float(p.get('markPrice',0) or entry)
                gross=float(p.get('unrealizedPnl',0) or 0); net=gross - FEE_PER_TRADE
                sym=p['symbol']; name=sym.replace('/USDT:USDT','').replace(':USDT',''); side=p.get('side','long')
                best=STATE["open"].get(sym,{}).get("best",gross); best_net=STATE["open"].get(sym,{}).get("best_net",net)
                # نسبة للهدف
                pct_target=(net/TARGET_NET*100) if TARGET_NET!=0 else 0
                live.append({"symbol":name,"full":sym,"dir":side,"pnl_gross":gross,"pnl":net,"entry":entry,"last":last,"best":best,"best_net":max(best_net,net),"pct":pct_target})
        if not live:
            for sym,data in STATE["open"].items():
                try:
                    last=get_ex().fetch_ticker(sym)["last"]; entry=data["entry"]
                    gross=(last-entry)/entry*MARGIN_PER_TRADE*LEVERAGE if data["dir"]=="long" else (entry-last)/entry*MARGIN_PER_TRADE*LEVERAGE
                    net=gross - FEE_PER_TRADE
                    live.append({"symbol":data["name"],"full":sym,"dir":data["dir"],"pnl_gross":gross,"pnl":net,"entry":entry,"last":last,"best":data.get("best",gross),"best_net":data.get("best_net",net),"pct":net/TARGET_NET*100})
                except: pass
    except: pass
    return jsonify({"live":live,"fee":FEE_PER_TRADE,"target":TARGET_NET})
@app.route("/api/scan")
def scan(): return jsonify({"signals":scan_live()})

DASH_HTML = """
<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>هدف $1 صافي</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{background:#050a14;color:#fff}.glass{background:#111c2f;border:1px solid #1e355a}.dot{animation:p 1s infinite}@keyframes p{0%{opacity:1}50%{opacity:.3}100%{opacity:1}}</style></head>
<body class="p-3 max-w-[480px] mx-auto">
<div class="glass rounded-[22px] p-5">
<div class="flex justify-between text-[11px] text-gray-400"><span>هدف $1 صافي بعد الرسوم - $2×10</span><span class="flex gap-1 items-center"><span class="w-2 h-2 bg-green-500 rounded-full dot"></span>LIVE $1</span></div>
<div class="flex gap-2 items-baseline mt-1"><div id="bal" class="text-[30px] font-black">$0</div><div id="total" class="text-[11px] text-gray-400"></div></div>
<div id="last" class="text-[12px] font-bold mt-2 text-yellow-300"></div>
<div class="flex gap-2 mt-3 flex-wrap"><span id="cnt" class="bg-white/10 px-3 py-1 rounded-full text-[11px]"></span><span id="daily" class="px-3 py-1 rounded-full text-[11px]"></span><span id="fees" class="bg-orange-500/20 text-orange-300 px-3 py-1 rounded-full text-[11px]"></span></div>
<div id="wl" class="mt-2 text-[11px] text-gray-400"></div>
</div>
<div id="liveBig" class="space-y-3 my-3"></div>
<div class="glass rounded-2xl p-3"><div class="font-black text-[12px] mb-2">🎯 فرص $1 - يفتح مستمر</div><div id="sigs" class="space-y-2"></div></div>
<div class="mt-3 glass rounded-xl p-3 text-[11px] text-gray-300 leading-6">
💰 <b>هدف $1 صافي:</b> $2 راس مال ×10 رافعة = $20 حجم<br>
📈 حركة 5% = $1 ربح صافي (بعد $0.04 رسوم)<br>
✅ يفتح الثانية إذا الأولى $0.50 صافي<br>
🔴 يقفل خسارة على -$0.50 صافي - حماية<br>
🟢 يقفل ربح تلقائي على $1.20 صافي<br>
♾️ مستمر 24 ساعة - كل قفل يفتح غيره
</div>
<script>
async function load(){
 const st=await fetch('/api/status').then(r=>r.json());
 document.getElementById('bal').textContent='$'+st.balance.toFixed(2)+' متاح';
 document.getElementById('total').textContent='/ $'+st.total.toFixed(2)+' كلي';
 document.getElementById('last').textContent=st.last;
 document.getElementById('cnt').textContent=st.count+'/2 مفتوح | '+st.total_trades+' كلي | $'+st.margin+'×'+st.lev+' هدف $'+st.target;
 const d=document.getElementById('daily'); d.textContent='صافي اليوم $'+st.daily.toFixed(2)+' خام $'+st.daily_gross.toFixed(2); d.className='px-3 py-1 rounded-full text-[11px] '+(st.daily>=0?'bg-green-500/20 text-green-400':'bg-red-500/20 text-red-400');
 document.getElementById('fees').textContent='رسوم $'+st.fees.toFixed(3);
 document.getElementById('wl').textContent=`✅ ${st.wins} ربح $1 | ❌ ${st.losses} خسارة | رسوم $${st.fee}`;
 const pnl=await fetch('/api/pnl_live').then(r=>r.json());
 document.getElementById('liveBig').innerHTML=pnl.live.length? pnl.live.map(x=>{
  const prof=x.pnl>=0; const pct=Math.min(100,Math.max(0,x.pct)); return `<div class="glass rounded-[22px] p-4 border-2 ${prof?'border-green-500 bg-green-500/10':'border-red-500 bg-red-500/10'}">
   <div class="flex justify-between"><div><div class="font-black text-[17px]">${x.symbol} <span class="px-2 py-0.5 rounded-full text-[9px] ${x.dir=='long'?'bg-green-500 text-black':'bg-red-500 text-white'}">${x.dir.toUpperCase()} ${st.lev}x</span></div><div class="text-[11px] text-gray-400 mt-1">${prof?'🟢 صافي ربح':'🔴 صافي خسارة'} - هدف $1</div><div class="text-[10px] text-gray-500">خام $${x.pnl_gross.toFixed(3)} - رسوم = صافي $${x.pnl.toFixed(3)}</div></div><div class="text-left"><div class="px-4 py-2 rounded-full font-black text-[19px] ${prof?'bg-green-500 text-black':'bg-red-500 text-white'}">$${x.pnl.toFixed(3)}</div><div class="text-[11px] text-center mt-1">${x.pct.toFixed(0)}% من $1</div></div></div>
   <div class="mt-3"><div class="flex justify-between text-[10px] text-gray-400 mb-1"><span>$0</span><span>هدف $1 صافي</span><span>$1.20 قفل</span></div><div class="h-2.5 bg-black/60 rounded-full overflow-hidden"><div class="h-full ${prof?'bg-green-500':'bg-red-500'} transition-all duration-500" style="width:${pct}%"></div></div></div>
   <div class="grid grid-cols-3 gap-2 mt-3 text-[11px]"><div class="bg-black/60 rounded-xl p-2 text-center"><div class="text-gray-400">دخول</div><div class="font-bold mt-1">${x.entry.toFixed(5)}</div></div><div class="bg-black/60 rounded-xl p-2 text-center"><div class="text-gray-400">حالي</div><div class="font-bold mt-1">${x.last.toFixed(5)}</div></div><div class="bg-black/60 rounded-xl p-2 text-center"><div class="text-gray-400">أفضل صافي</div><div class="font-bold text-green-400 mt-1">$${x.best_net.toFixed(3)}</div></div></div>
  </div>`
 }).join('') : `<div class="glass rounded-[20px] p-8 text-center"><div class="text-[30px]">💵</div><div class="font-bold text-[13px] mt-2">يبحث عن $1 صافي</div><div class="text-[11px] text-gray-400 mt-1">$2×10 = $20 حجم - حركة 5% = $1</div></div>`;
 const sc=await fetch('/api/scan').then(r=>r.json());
 document.getElementById('sigs').innerHTML=sc.signals.length? sc.signals.map(s=>`<div class="bg-black/40 rounded-xl p-2.5 flex justify-between"><span class="text-[12px] font-bold">${s.symbol} <span class="px-1.5 py-0.5 rounded-full text-[9px] ${s.direction=='long'?'bg-green-500 text-black':'bg-red-500'}">${s.direction.toUpperCase()}</span> RSI ${s.rsi}</span><span class="text-[11px]">${s.price.toFixed(4)}</span></div>`).join('') : `<div class="text-[11px] text-gray-500 text-center py-2">ينتظر فرصة</div>`;
}
setInterval(load,1500); load();
</script></body></html>
"""

threading.Thread(target=hunter,daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))