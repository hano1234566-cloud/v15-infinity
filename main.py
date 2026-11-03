import os, time, threading, ccxt, json, requests
from flask import Flask, jsonify
import numpy as np
from datetime import datetime

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL = 0.0
LAST = "V30022 - 6 قوية بوقف حديد"
SCAN_LOG = "🚀 يبدأ"
SCAN_CURRENT = "BTC 1/60"
ALL_RSI = []
SCAN_IDX = 0
FEE = 0.04
BASE_MARGIN = 7.0   # ⭐ مارجن صغير عشان 6 صفقات = 42$ بس
COMP_MARGIN = 9.0
LEV = 10
FILE = "/tmp/state_v30022.json"

COINS_60 = ["BTC","ETH","SOL","XRP","BNB","DOGE","ADA","AVAX","DOT","LINK","TRX","LTC","BCH","UNI","PEPE","NEAR","ETC","APT","FIL","STX","MATIC","OP","ARB","HBAR","IMX","MNT","RNDR","TAO","INJ","AR","FET","GRT","LDO","MKR","AAVE","SUI","SEI","WIF","BONK","JUP","ENA","WLD","FLOKI","TIA","PYTH","STRK","JTO","ORDI","SATS","RUNE","FLOW","KAS","BEAM","ARKM","AGIX","XLM","XMR","CRO","VET","ALGO"]

CONTRACT_SIZE = {
    "BTC":0.01, "ETH":0.1, "SOL":1, "XRP":100, "BNB":0.1, "DOGE":1000,
    "ADA":100, "AVAX":1, "DOT":10, "LINK":10, "TRX":1000, "LTC":0.1,
    "BCH":0.1, "UNI":10, "PEPE":10000000, "NEAR":10, "ETC":1, "APT":10,
    "FIL":1, "STX":100, "MATIC":100, "OP":10, "ARB":10, "HBAR":1000,
    "IMX":10, "MNT":10, "RNDR":10, "TAO":0.1, "INJ":1, "AR":1, "FET":100,
    "GRT":1000, "LDO":10, "MKR":0.01, "AAVE":0.1, "SUI":10, "SEI":100,
    "WIF":10, "BONK":10000000, "JUP":10, "ENA":100, "WLD":10, "FLOKI":10000000,
    "TIA":10, "PYTH":100, "STRK":10, "JTO":10, "ORDI":1, "SATS":10000000,
    "RUNE":10, "FLOW":10, "KAS":1000, "BEAM":1000, "ARKM":10, "AGIX":100,
    "XLM":1000, "XMR":0.1, "CRO":1000, "VET":10000, "ALGO":100
}

STATE = {"open":{},"closed":[],"blacklist":{},"daily":0,"avail":0,"total":0,"wins":0,"losses":0,"fees":0,"trades":0,"consec_losses":0,"next_margin":BASE_MARGIN,"daily_losses":0,"daily_loss_amount":0.0}
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
                STATE["daily"]=0; STATE["daily_losses"]=0; STATE["daily_loss_amount"]=0.0
except: pass

def save():
    try:
        STATE["day"]=datetime.now().strftime("%Y-%m-%d")
        with open(FILE,'w') as f: json.dump(STATE,f)
    except: pass

app = Flask(__name__)
EX_CACHE = None
def get_ex_auth():
    global EX_CACHE
    if EX_CACHE is None:
        EX_CACHE = ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'options':{'defaultType':'swap'},'enableRateLimit':True})
        try: EX_CACHE.load_markets()
        except: pass
    return EX_CACHE

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

def fetch_direct(name):
    try:
        inst=f"{name}-USDT-SWAP"
        url=f"https://www.okx.com/api/v5/market/candles?instId={inst}&bar=1H&limit=100"
        r=requests.get(url, timeout=5)
        data=r.json()
        if data.get("code")=="0" and data.get("data"):
            closes=[float(x[4]) for x in data["data"] if len(x)>=5]
            closes=closes[::-1]
            if len(closes)>=20:
                return closes, f"{name}/USDT:USDT"
    except: pass
    return None, None

def scan_chunk():
    global SCAN_LOG, SCAN_CURRENT, ALL_RSI, SCAN_IDX, LAST
    start=SCAN_IDX
    end=min(start+5, 60)
    new_results=[]
    for i in range(start, end):
        name=COINS_60[i]
        SCAN_CURRENT=f"{name} {i+1}/60"
        if name in STATE["blacklist"]: continue
        closes, sym=fetch_direct(name)
        if not closes:
            SCAN_LOG=f"❌ {name} فشل"
            continue
        price=closes[-1]
        rsi=calc_rsi_safe(closes)
        new_results.append({"symbol":name,"full":sym,"price":price,"rsi":round(rsi,1)})
        SCAN_LOG=f"✅ {name} RSI {rsi:.1f} {i+1}/60"
        time.sleep(0.3)
    existing={x["symbol"]:x for x in ALL_RSI}
    for x in new_results: existing[x["symbol"]]=x
    ALL_RSI=list(existing.values())
    SCAN_IDX=end
    if SCAN_IDX>=60:
        SCAN_IDX=0
        LAST=f"✅ اكتمل 60"

def close_any(sym):
    ex=get_ex_auth()
    for mode in [{'tdMode':'isolated','posSide':'long'},{'tdMode':'isolated','posSide':'short'},{'tdMode':'cross','posSide':'long'},{'tdMode':'cross','posSide':'short'}]:
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
    try: get_ex_auth().load_markets()
    except: pass
    while True:
        try:
            scan_chunk()
            get_bal()
            
            # ⭐ وقف جحفلة يومي - لا نفتح إذا خسرنا أكثر من $5 اليوم
            if STATE["daily_loss_amount"]<=-5.0:
                LAST=f"🛡️ وقف جحفلة يومي خسرنا ${STATE['daily_loss_amount']:.1f} اليوم - بكرا نكمل"
                time.sleep(120)
                continue
            if STATE["daily_losses"]>=5:
                LAST="🛡️ وقف 5 خسائر يومي"
                time.sleep(120)
                continue
            
            # ⭐ مراقبة وإغلاق بوقف حديد
            total_gross=0
            try:
                ex=get_ex_auth()
                positions=ex.fetch_positions()
                for p in positions:
                    if float(p.get('contracts',0) or 0)>0:
                        sym=p['symbol']; name=sym.replace('/USDT:USDT','')
                        gross=float(p.get('unrealizedPnl',0) or 0); net=gross-FEE
                        total_gross+=gross
                        entry=float(p.get('entryPrice',0) or 0); mark=float(p.get('markPrice',0) or entry)
                        liq=float(p.get('liquidationPrice',0) or 0); side=p.get('side','long')
                        if sym not in STATE["open"]: STATE["open"][sym]={"name":name,"dir":side,"entry":entry,"best":net,"best_net":net}
                        best=STATE["open"][sym].get("best_net",net)
                        if net>best: STATE["open"][sym]["best_net"]=net; best=net
                        
                        should=False; reason=""
                        # ⭐ وقف خسارة حديد -1$ لكل صفقة
                        if net<=-1.0:
                            should=True; reason=f"ستوب -1$ ({net:.2f})"
                        # ⭐ وقف جحفلة تصفية - إذا قرب من التصفية 15% نسكر فوراً
                        elif liq>0 and entry>0:
                            if side=='long':
                                dist=(mark-liq)/entry*100  # كم % بعيد عن التصفية
                                if dist<8:  # أقل من 8% بعيد = خطر جحفلة
                                    should=True; reason=f"تصفية {dist:.1f}% قريب"
                                elif mark <= liq + (entry-liq)*0.2:
                                    should=True; reason="تصفية قريب"
                            else:
                                dist=(liq-mark)/entry*100
                                if dist<8:
                                    should=True; reason=f"تصفية {dist:.1f}% قريب"
                                elif mark >= liq - (liq-entry)*0.2:
                                    should=True; reason="تصفية قريب"
                        # ⭐ حماية ربح
                        elif best>=0.6 and net<=best-0.8:
                            should=True; reason=f"حماية {best:.2f}->{net:.2f}"
                        # ⭐ هدف ربح $1.5 للقوية
                        elif net>=1.5:
                            should=True; reason=f"هدف +${net:.2f}"
                        
                        if should and close_any(sym):
                            closed={"pair":name,"side":side,"pnl":net,"gross":gross,"time":datetime.now().strftime("%H:%M"),"reason":reason}
                            STATE["closed"].insert(0,closed); STATE["closed"]=STATE["closed"][:20]
                            STATE["open"].pop(sym,None); STATE["daily"]+=net; STATE["trades"]+=1; STATE["fees"]+=FEE
                            STATE["daily_loss_amount"]+=net if net<0 else 0
                            if net>0: STATE["wins"]+=1; STATE["consec_losses"]=0; STATE["next_margin"]=BASE_MARGIN
                            else: STATE["losses"]+=1; STATE["consec_losses"]+=1; STATE["daily_losses"]+=1; STATE["next_margin"]=COMP_MARGIN
                            save()
                
                # ⭐ وقف جحفلة إجمالي - إذا كل الصفقات خاسرة -3$ نسكر الكل
                if total_gross<=-3.0 and len([p for p in positions if float(p.get('contracts',0) or 0)>0])>=3:
                    LAST=f"🛡️ وقف جحفلة إجمالي {total_gross:.1f}$ - نسكر الكل"
                    for p in positions:
                        if float(p.get('contracts',0) or 0)>0:
                            close_any(p['symbol'])
                            time.sleep(0.5)
                    time.sleep(2)
                    continue
                    
            except Exception as e:
                LAST=f"مراقبة {str(e)[:30]}"

            try: live=len([p for p in get_ex_auth().fetch_positions() if float(p.get('contracts',0) or 0)>0])
            except: live=len(STATE["open"])
            open_names=[v["name"] for v in STATE["open"].values()]

            very_strong_count=len([x for x in ALL_RSI if x["rsi"]<=25 or x["rsi"]>=75])
            strong_count=len([x for x in ALL_RSI if x["rsi"]<=32 or x["rsi"]>=68])
            
            # ⭐ حد ديناميكي بس ما نتجحفل
            total_eq=STATE["total"]
            if total_eq<10: max_positions=1
            elif very_strong_count>=3 and total_eq>=40: max_positions=6
            elif very_strong_count>=1 and total_eq>=30: max_positions=5
            elif strong_count>=3 and total_eq>=25: max_positions=4
            else: max_positions=2
            
            # ⭐ لا نستخدم أكثر من 60% من الرصيد
            max_margin_allowed=total_eq*0.6
            current_margin_used=live*BASE_MARGIN
            remaining_margin=max_margin_allowed - current_margin_used
            
            LAST=f"🔥 {very_strong_count} جداً + {strong_count} قوية | {live}/{max_positions} | رصيد ${total_eq:.1f} مسموح مارجن ${max_margin_allowed:.0f} باقي ${remaining_margin:.0f} | خسارة اليوم ${STATE['daily_loss_amount']:.1f}"

            if live<max_positions and remaining_margin>=5 and get_bal()>=4 and len(ALL_RSI)>=15:
                strong=[]
                medium=[]
                for x in ALL_RSI:
                    if x["symbol"] in open_names or x["symbol"] in STATE["blacklist"]: continue
                    r=x["rsi"]
                    if r<=22: strong.append({**x,"direction":"long","score":25,"type":"قوية جداً جداً 🔥🔥🔥"})
                    elif r>=78: strong.append({**x,"direction":"short","score":25,"type":"قوية جداً جداً 🔥🔥🔥"})
                    elif r<=25: strong.append({**x,"direction":"long","score":20,"type":"قوية جداً 🔥🔥"})
                    elif r>=75: strong.append({**x,"direction":"short","score":20,"type":"قوية جداً 🔥🔥"})
                    elif r<=30: strong.append({**x,"direction":"long","score":15,"type":"قوية 🔥"})
                    elif r>=70: strong.append({**x,"direction":"short","score":15,"type":"قوية 🔥"})
                    elif r<=38: medium.append({**x,"direction":"long","score":8,"type":"متوسطة ⚡"})
                    elif r>=62: medium.append({**x,"direction":"short","score":8,"type":"متوسطة ⚡"})
                
                strong_sorted=sorted(strong, key=lambda x: abs(x["rsi"]-50), reverse=True)
                medium_sorted=sorted(medium, key=lambda x: abs(x["rsi"]-50), reverse=True)
                candidates=strong_sorted + medium_sorted
                
                opened_this_round=0
                for to_open in candidates:
                    if live+opened_this_round>=max_positions: break
                    if remaining_margin<5: break
                    try:
                        ex=get_ex_auth()
                        price=to_open["price"]
                        sym_name=to_open["symbol"]
                        contract_size=CONTRACT_SIZE.get(sym_name, 1)
                        
                        margin=BASE_MARGIN if to_open["score"]>=15 else BASE_MARGIN
                        contracts=(margin*LEV)/(price*contract_size)
                        contracts=max(contracts, 1)
                        if sym_name in ["BTC","MKR"]: contracts=round(contracts,3)
                        elif sym_name in ["ETH","LTC","BCH","XMR","TAO"]: contracts=round(contracts,2)
                        else: contracts=int(contracts) if contracts>=1 else round(contracts,1)
                        if contracts<1: contracts=1
                        
                        real_notional=contracts*contract_size*price
                        real_margin=real_notional/LEV
                        if real_margin>get_bal()+0.5 or real_margin>remaining_margin:
                            continue
                        try: ex.set_leverage(LEV,to_open["full"])
                        except: pass
                        is_long=to_open["direction"]=="long"
                        side="buy" if is_long else "sell"
                        pos_side="long" if is_long else "short"
                        LAST=f"🔄 يفتح {to_open['type']} {sym_name} RSI {to_open['rsi']} {live+opened_this_round+1}/{max_positions} مارجن ${real_margin:.1f} باقي مسموح ${remaining_margin:.0f}"
                        time.sleep(0.6)
                        order=None
                        for mode in [{'tdMode':'isolated','posSide':pos_side},{'tdMode':'cross','posSide':pos_side}]:
                            try:
                                order=ex.create_market_order(to_open["full"],side,contracts,None,mode)
                                break
                            except: continue
                        if order:
                            entry=float(order.get("average") or price)
                            STATE["open"][to_open["full"]]={"name":sym_name,"dir":to_open["direction"],"entry":entry,"best":0,"best_net":0,"type":to_open["type"],"score":to_open["score"],"rsi":to_open["rsi"]}
                            opened_this_round+=1
                            live+=1
                            remaining_margin-=real_margin
                            LAST=f"✅ فتح {to_open['type']} {sym_name} RSI {to_open['rsi']} {live}/{max_positions} باقي ${remaining_margin:.0f}"
                            save()
                            time.sleep(0.5)
                            if to_open["score"]>=20:
                                continue
                            else:
                                break
                    except Exception as e:
                        LAST=f"❌ {to_open['symbol']} {str(e)[:80]}"
                        continue
            time.sleep(2)
        except Exception as e:
            LAST=f"خطأ {str(e)[:90]}"
            time.sleep(5)

@app.route("/", methods=["GET","POST"])
def index(): return HTML
@app.route("/health", methods=["GET","POST"])
def health(): return "OK", 200
@app.route("/api/status", methods=["GET","POST"])
def status(): return jsonify({"bal":get_bal(),"avail":STATE["avail"],"total":STATE["total"],"count":len(STATE["open"]),"last":LAST,"scan_log":SCAN_LOG,"scan_current":SCAN_CURRENT,"scan_count":60,"all_rsi":ALL_RSI,"scan_idx":SCAN_IDX,"daily":STATE["daily"],"wins":STATE["wins"],"losses":STATE["losses"],"trades":STATE["trades"],"fees":STATE["fees"],"next_margin":STATE["next_margin"],"daily_losses":STATE["daily_losses"],"daily_loss_amount":STATE["daily_loss_amount"],"blacklist":list(STATE["blacklist"].keys())})
@app.route("/api/pnl", methods=["GET","POST"])
def pnl():
    live=[]
    try:
        ex=get_ex_auth()
        for p in ex.fetch_positions():
            if float(p.get('contracts',0) or 0)>0:
                entry=float(p.get('entryPrice',0) or 0); last=float(p.get('markPrice',0) or entry)
                gross=float(p.get('unrealizedPnl',0) or 0); sym=p['symbol']; name=sym.replace('/USDT:USDT','')
                liq=float(p.get('liquidationPrice',0) or 0)
                dist=0
                if entry>0 and liq>0:
                    dist=abs(last-liq)/entry*100
                info=STATE["open"].get(sym,{}); best=info.get("best_net",gross-FEE)
                live.append({"sym":name,"full":sym,"side":p.get('side','long'),"gross":gross,"net":gross-FEE,"entry":entry,"last":last,"lev":LEV,"best":best,"type":info.get("type","-"),"rsi":info.get("rsi",0),"liq":liq,"dist":dist})
    except: pass
    return jsonify({"bal":get_bal(),"total":STATE["total"],"live":live,"closed":STATE["closed"]})

HTML = """<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>V30022 ضد الجحفلة</title><script src="https://cdn.tailwindcss.com"></script><style>body{background:#000;color:#fff}.card{background:#111214;border-radius:18px}.glass{background:#111c2f;border:1px solid #1e355a}.live-dot{animation:pulse 1s infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}</style></head><body class="max-w-[480px] mx-auto p-3"><div class="bg-[#111214] rounded-[22px] p-4 border border-green-500/30"><div class="flex justify-between text-[11px] text-gray-400"><span class="flex gap-1 items-center"><span class="w-2 h-2 bg-green-500 rounded-full live-dot"></span>V30022 ضد الجحفلة 🛡️</span><span>60</span></div><div class="flex gap-2 items-baseline mt-2"><div id="bal" class="text-[30px] font-black">$0</div><div id="total" class="text-[11px] text-gray-500"></div><div id="next" class="text-[10px] bg-yellow-500 text-black px-2 py-0.5 rounded-full font-bold"></div></div><div id="last" class="text-[10px] font-bold mt-2 text-yellow-300 break-all leading-5"></div><div class="mt-2 bg-black/60 rounded-xl p-2 border border-yellow-500/30"><div class="flex justify-between text-[10px]"><span class="text-yellow-400 font-bold">🛡️ حماية من الجحفلة</span><span id="riskInfo" class="text-white font-mono">-</span></div><div id="scanLog" class="text-[11px] text-white mt-1 font-mono">بانتظار...</div><div class="mt-2 h-1.5 bg-white/10 rounded-full overflow-hidden"><div id="scanProgress" class="h-full bg-green-500" style="width:0%"></div></div></div><div class="flex gap-2 mt-3 flex-wrap"><span id="cnt" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="allCount" class="bg-blue-500/20 px-3 py-1 rounded-full text-[10px]"></span><span id="strongCount" class="bg-green-500 text-black px-3 py-1 rounded-full text-[10px] font-black"></span><span id="maxPos" class="bg-yellow-400 text-black px-3 py-1 rounded-full text-[10px] font-black"></span></div></div><div id="liveBig" class="my-3"></div><div class="glass rounded-2xl p-3 border-2 border-green-400"><div class="flex justify-between text-[12px] font-black"><span>🔥🔥 القوية جداً (يفتح 6 بوقف)</span><span id="strongTop" class="bg-green-500 text-black px-2 py-0.5 rounded-full text-[9px]"></span></div><div id="strongList" class="space-y-2 mt-2"></div></div><div class="glass rounded-2xl p-3 mt-3 border border-yellow-500/20"><div class="text-[11px] font-black">🛡️ قوانين ضد الجحفلة</div><div class="text-[10px] text-gray-400 mt-1 leading-4">• ستوب -1$ لكل صفقة<br>• تصفية أقل من 8% يسكر فوراً<br>• خسارة إجمالية -3$ يسكر الكل<br>• يومي -5$ يوقف اليوم<br>• مارجن 60% بس من الرصيد</div></div><div class="glass rounded-2xl p-3 mt-3"><div class="flex justify-between text-[11px] font-black"><span>📊 كل العملات</span><span id="idx" class="bg-white/10 px-2 py-0.5 rounded-full text-[9px]">0</span></div><div id="all" class="space-y-2 mt-2 max-h-[300px] overflow-y-auto"></div></div><script>async function load(){const s=await fetch('/api/status').then(r=>r.json());document.getElementById('bal').textContent=`$${s.bal.toFixed(2)}`;document.getElementById('total').textContent=`/ $${s.total.toFixed(2)} كلي`;document.getElementById('next').textContent=s.next_margin>2?`الجاية $${s.next_margin} تعويض`:`الجاية $${s.next_margin}`;document.getElementById('last').textContent=s.last;document.getElementById('scanLog').textContent=s.scan_log;document.getElementById('riskInfo').textContent=`خسارة اليوم ${s.daily_loss_amount.toFixed(1)}$ | ${s.daily_losses} خسائر`;document.getElementById('cnt').textContent=s.count+'/6 مفتوح';document.getElementById('allCount').textContent=(s.all_rsi||[]).length+'/60';const veryStrong=(s.all_rsi||[]).filter(x=>x.rsi<=25||x.rsi>=75);const strong=(s.all_rsi||[]).filter(x=>x.rsi<=32||x.rsi>=68);document.getElementById('strongCount').textContent=`🔥 ${veryStrong.length} جداً + ${strong.length} قوية`;const maxPos=veryStrong.length>=3?6:veryStrong.length>=1?5:strong.length>=3?4:2;document.getElementById('maxPos').textContent=`يفتح حتى ${maxPos}`;document.getElementById('strongTop').textContent=`${veryStrong.length} قوية جداً`;document.getElementById('idx').textContent=s.scan_idx+'/60';const prog=s.scan_count>0?(parseInt(s.scan_current.split('/')[0].replace(/[^0-9]/g,''))||0)/s.scan_count*100:0;document.getElementById('scanProgress').style.width=prog+'%';document.getElementById('strongList').innerHTML=veryStrong.concat(strong.filter(x=>!veryStrong.includes(x))).sort((a,b)=>Math.abs(b.rsi-50)-Math.abs(a.rsi-50)).slice(0,6).map(x=>{const isVery=x.rsi<=25||x.rsi>=75;const isVeryVery=x.rsi<=22||x.rsi>=78;const col=isVeryVery?'border-yellow-400 bg-yellow-500/20':isVery?'border-green-400 bg-green-500/20':'border-green-500/60 bg-green-500/10';const dir=x.rsi<50?'LONG':'SHORT';const type=isVeryVery?'قوية جداً جداً 🔥🔥🔥':isVery?'قوية جداً 🔥🔥':'قوية 🔥';return `<div class="rounded-xl p-3 flex justify-between items-center border-2 ${col}"><div><div class="text-[13px] font-black">${x.symbol} <span class="px-2 py-0.5 rounded-full text-[10px] ${dir=='LONG'?'bg-green-500 text-black':'bg-red-500'}">${dir}</span> <span class="text-[10px]">${type}</span></div><div class="text-[11px] text-white">RSI ${x.rsi} $${x.price.toFixed(4)}</div></div><div class="text-[9px] bg-yellow-400 text-black px-2 py-1 rounded-full font-black">يفتح بوقف -1$</div></div>`}).join('')||`<div class="text-[11px] text-gray-400 text-center py-3">بانتظار فرص قوية جداً...<br>RSI تحت 25 أو فوق 75 = 6 صفقات بوقف</div>`;document.getElementById('all').innerHTML=(s.all_rsi||[]).sort((a,b)=>Math.abs(b.rsi-50)-Math.abs(a.rsi-50)).slice(0,15).map(x=>{const isVery=x.rsi<=25||x.rsi>=75;const isStrong=x.rsi<=32||x.rsi>=68;const col=isVery?'border-yellow-400 border-2':isStrong?'border-green-500/60':'border-white/10';const dir=x.rsi<50?'LONG':'SHORT';return `<div class="bg-black/40 rounded-xl p-2.5 flex justify-between items-center border ${col} ${isStrong?'bg-green-500/5':''}"><div><div class="text-[12px] font-bold">${x.symbol} ${isVery?'🔥🔥':isStrong?'🔥':''} <span class="px-1.5 py-0.5 rounded-full text-[9px] ${dir=='LONG'?'bg-green-500 text-black':'bg-red-500'}">${dir}</span></div><div class="text-[10px] text-gray-400">RSI ${x.rsi}</div></div></div>`}).join('');const d=await fetch('/api/pnl').then(r=>r.json());document.getElementById('liveBig').innerHTML=d.live.length?d.live.map(x=>`<div class="card p-3 border-2 ${x.gross<0?'border-red-500/60':'border-green-500'} mb-2"><div class="flex justify-between text-[11px]"><span>${x.type} ${x.sym}</span><span>${x.side.toUpperCase()} ${x.lev}x RSI ${x.rsi}</span></div><div class="flex justify-between items-end"><div class="text-[22px] font-black ${x.gross<0?'text-red-500':'text-green-400'}">${x.gross>=0?'+':''}${x.gross.toFixed(2)}</div><div class="text-[9px] ${x.dist<10?'text-red-400 font-black':'text-gray-400'}">تصفية ${x.dist.toFixed(1)}% بعيد</div></div><div class="text-[9px] text-gray-500">ستوب -1$ | هدف +1.5$ | حماية 0.6→</div></div>`).join(''):`<div class="glass rounded-[20px] p-4 text-center text-[11px] text-gray-400">يفتح 6 بوقف حديد 🛡️<br>ما نتجحفل</div>`;}setInterval(load,1000);load();</script></body></html>
"""

threading.Thread(target=hunter,daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))