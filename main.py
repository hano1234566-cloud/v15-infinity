import os, time, threading, ccxt, json, requests
from flask import Flask, jsonify
import numpy as np
from datetime import datetime

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL = 0.0
LAST = "V30024 - أقصى ربح تريلينق ذكي"
SCAN_LOG = "🚀 يبدأ"
SCAN_CURRENT = "BTC 1/60"
ALL_RSI = []
SCAN_IDX = 0
FEE = 0.04
BASE_MARGIN = 5.0
COMP_MARGIN = 6.0
LEV = 10
FILE = "/tmp/state_v30024.json"

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
        if len(prices)<30: return 50
        arr=np.array(prices,float); d=np.diff(arr)
        if len(d)<14: return 50
        up=np.where(d>0,d,0); down=np.where(d<0,-d,0)
        mu=np.mean(up[:14]); md=np.mean(down[:14])
        if md==0: return 70
        rsi=100-(100/(1+mu/md))
        for i in range(14,len(d)):
            mu=(mu*13+up[i])/14; md=(md*13+down[i])/14
            rsi=100-(100/(1+mu/md)) if md!=0 else 70
        if rsi<=0 or rsi>=100: return 50
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
            if len(closes)>=30:
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
        if rsi<=1 or rsi>=99: continue
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
            if STATE["daily_loss_amount"]<=-6.0:
                LAST=f"🛡️ وقف يومي ${STATE['daily_loss_amount']:.1f}"; time.sleep(120); continue
            if STATE["daily_losses"]>=6:
                LAST="🛡️ وقف 6 خسائر"; time.sleep(120); continue
            
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
                        info=STATE["open"].get(sym,{})
                        if info.get("rsi",50)==0:
                            close_any(sym); STATE["open"].pop(sym,None); continue
                        
                        # ⭐ تريلينق ذكي لأقصى ربح
                        if sym not in STATE["open"]:
                            STATE["open"][sym]={"name":name,"dir":side,"entry":entry,"best":net,"best_net":net,"rsi":50,"start_time":datetime.now().timestamp()}
                        best=STATE["open"][sym].get("best_net",net)
                        if net>best:
                            STATE["open"][sym]["best_net"]=net
                            best=net
                        score=STATE["open"][sym].get("score",10)
                        rsi_entry=STATE["open"][sym].get("rsi",50)
                        
                        # هدف حسب قوة RSI
                        if score>=20: target=3.0  # قوية جداً هدف 3$
                        elif score>=15: target=2.0  # قوية هدف 2$
                        else: target=1.2  # متوسطة هدف 1.2$
                        
                        should=False; reason=""
                        # 1- ستوب ثابت ضد الجحفلة
                        if net<=-0.9:
                            should=True; reason=f"ستوب -0.9$ 🛡️"
                        # 2- تصفية
                        elif liq>0 and entry>0:
                            dist=(mark-liq)/entry*100 if side=='long' else (liq-mark)/entry*100
                            if dist<9: should=True; reason=f"تصفية {dist:.1f}% 🛡️"
                        # 3- جني أرباح ذكي - تريلينق
                        else:
                            # إذا وصلنا هدف قوي جداً خلاص
                            if net>=target:
                                # لكن لا نسكر فوراً - نعطيه فرصة يطير أكثر
                                # إذا نزل من القمة نصف دولار نسكر
                                if best>=target and net<=best-0.5:
                                    should=True; reason=f"جني ذكي قمة ${best:.2f} → ${net:.2f} هدف ${target}"
                                elif best>=target+1.0 and net<=best-0.8:
                                    # إذا طار فوق الهدف بدولار - نسمح بتراجع 0.8
                                    should=True; reason=f"جني طيران ${best:.2f}→${net:.2f}"
                                # إذا ما نزل - خليه يطير لأقصى ربح
                            
                            # حماية رأس مال - إذا ربح +0.4$ انقل ستوب على الدخول
                            if best>=0.4 and net<=0.05:
                                should=True; reason=f"حماية رأس مال +${best:.2f}→${net:.2f}"
                            # تريلينق متدرج
                            elif best>=0.6 and net<=best-0.5:
                                should=True; reason=f"تريلينق +${best:.2f}→${net:.2f}"
                            elif best>=1.5 and net<=best-0.7:
                                should=True; reason=f"تريلينق ربح عالي ${best:.2f}→${net:.2f}"
                            elif best>=2.5 and net<=best-1.0:
                                should=True; reason=f"تريلينق طيران ${best:.2f}→${net:.2f}"
                        
                        if should and close_any(sym):
                            closed={"pair":name,"side":side,"pnl":net,"gross":gross,"time":datetime.now().strftime("%H:%M"),"reason":reason,"best":best}
                            STATE["closed"].insert(0,closed); STATE["closed"]=STATE["closed"][:20]
                            STATE["open"].pop(sym,None); STATE["daily"]+=net; STATE["trades"]+=1; STATE["fees"]+=FEE
                            if net<0: STATE["daily_loss_amount"]+=net
                            if net>0: STATE["wins"]+=1; STATE["consec_losses"]=0; STATE["next_margin"]=BASE_MARGIN
                            else: STATE["losses"]+=1; STATE["consec_losses"]+=1; STATE["daily_losses"]+=1; STATE["next_margin"]=COMP_MARGIN
                            save()
                
                if total_gross<=-3.0 and len([p for p in positions if float(p.get('contracts',0) or 0)>0])>=3:
                    LAST=f"🛡️ وقف إجمالي {total_gross:.1f}$"
                    for p in positions:
                        if float(p.get('contracts',0) or 0)>0:
                            close_any(p['symbol']); time.sleep(0.3)
                    time.sleep(1); continue
                    
            except Exception as e:
                LAST=f"مراقبة {str(e)[:30]}"

            try: live=len([p for p in get_ex_auth().fetch_positions() if float(p.get('contracts',0) or 0)>0])
            except: live=len(STATE["open"])
            open_names=[v["name"] for v in STATE["open"].values()]

            very_strong_count=len([x for x in ALL_RSI if (x["rsi"]<=25 or x["rsi"]>=75) and x["rsi"]>1])
            strong_count=len([x for x in ALL_RSI if (x["rsi"]<=32 or x["rsi"]>=68) and x["rsi"]>1])
            
            total_eq=STATE["total"]
            if total_eq<10: max_positions=1
            elif very_strong_count>=3 and total_eq>=30: max_positions=6
            elif very_strong_count>=1 and total_eq>=20: max_positions=5
            elif strong_count>=3 and total_eq>=15: max_positions=4
            else: max_positions=2
            
            max_margin_allowed=total_eq*0.55
            current_margin_used=live*BASE_MARGIN
            remaining_margin=max_margin_allowed - current_margin_used
            
            LAST=f"💰 أقصى ربح | {very_strong_count} جداً + {strong_count} قوية | {live}/{max_positions} | كلي ${total_eq:.1f} | خسارة اليوم ${STATE['daily_loss_amount']:.1f}"

            if live<max_positions and remaining_margin>=4 and get_bal()>=3 and len(ALL_RSI)>=10:
                strong=[]; medium=[]
                for x in ALL_RSI:
                    if x["symbol"] in open_names or x["symbol"] in STATE["blacklist"]: continue
                    r=x["rsi"]
                    if r<=1 or r>=99: continue
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
                    if remaining_margin<4: break
                    try:
                        ex=get_ex_auth()
                        price=to_open["price"]; sym_name=to_open["symbol"]
                        contract_size=CONTRACT_SIZE.get(sym_name, 1)
                        margin=BASE_MARGIN
                        contracts=(margin*LEV)/(price*contract_size)
                        contracts=max(contracts, 1)
                        if sym_name in ["BTC","MKR"]: contracts=round(contracts,3)
                        elif sym_name in ["ETH","LTC","BCH","XMR","TAO"]: contracts=round(contracts,2)
                        else: contracts=int(contracts) if contracts>=1 else round(contracts,1)
                        if contracts<1: contracts=1
                        real_notional=contracts*contract_size*price
                        real_margin=real_notional/LEV
                        if real_margin>get_bal()+0.5 or real_margin>remaining_margin: continue
                        try: ex.set_leverage(LEV,to_open["full"])
                        except: pass
                        is_long=to_open["direction"]=="long"
                        side="buy" if is_long else "sell"
                        pos_side="long" if is_long else "short"
                        LAST=f"🔄 يفتح {to_open['type']} {sym_name} RSI {to_open['rsi']} {live+opened_this_round+1}/{max_positions} هدف ${3.0 if to_open['score']>=20 else 2.0 if to_open['score']>=15 else 1.2}"
                        time.sleep(0.6)
                        order=None
                        for mode in [{'tdMode':'isolated','posSide':pos_side},{'tdMode':'cross','posSide':pos_side}]:
                            try:
                                order=ex.create_market_order(to_open["full"],side,contracts,None,mode)
                                break
                            except: continue
                        if order:
                            entry=float(order.get("average") or price)
                            STATE["open"][to_open["full"]]={"name":sym_name,"dir":to_open["direction"],"entry":entry,"best":0,"best_net":0,"type":to_open["type"],"score":to_open["score"],"rsi":to_open["rsi"],"start_time":datetime.now().timestamp()}
                            opened_this_round+=1; live+=1; remaining_margin-=real_margin
                            LAST=f"✅ فتح {to_open['type']} {sym_name} RSI {to_open['rsi']} هدف ${3.0 if to_open['score']>=20 else 2.0 if to_open['score']>=15 else 1.2} {live}/{max_positions}"; save()
                            time.sleep(0.5)
                            if to_open["score"]>=20: continue
                            else: break
                    except Exception as e:
                        LAST=f"❌ {to_open['symbol']} {str(e)[:80]}"; continue
            time.sleep(2)
        except Exception as e:
            LAST=f"خطأ {str(e)[:90]}"; time.sleep(5)

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
                dist=abs(last-liq)/entry*100 if entry>0 and liq>0 else 100
                info=STATE["open"].get(sym,{}); best=info.get("best_net",gross-FEE)
                score=info.get("score",10)
                target=3.0 if score>=20 else 2.0 if score>=15 else 1.2
                live.append({"sym":name,"full":sym,"side":p.get('side','long'),"gross":gross,"net":gross-FEE,"entry":entry,"last":last,"lev":LEV,"best":best,"type":info.get("type","-"),"rsi":info.get("rsi",0),"liq":liq,"dist":dist,"target":target})
    except: pass
    return jsonify({"bal":get_bal(),"total":STATE["total"],"live":live,"closed":STATE["closed"]})

HTML = """<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>V30024 أقصى ربح</title><script src="https://cdn.tailwindcss.com"></script><style>body{background:#000;color:#fff}.card{background:#111214;border-radius:18px}.glass{background:#111c2f;border:1px solid #1e355a}.live-dot{animation:pulse 1s infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}</style></head><body class="max-w-[480px] mx-auto p-3"><div class="bg-[#111214] rounded-[22px] p-4 border border-green-500/30"><div class="flex justify-between text-[11px] text-gray-400"><span class="flex gap-1 items-center"><span class="w-2 h-2 bg-green-500 rounded-full live-dot"></span>V30024 أقصى ربح 💰</span><span>60</span></div><div class="flex gap-2 items-baseline mt-2"><div id="bal" class="text-[30px] font-black">$0</div><div id="total" class="text-[11px] text-gray-500"></div><div id="next" class="text-[10px] bg-yellow-500 text-black px-2 py-0.5 rounded-full font-bold"></div></div><div id="last" class="text-[10px] font-bold mt-2 text-yellow-300 break-all leading-5"></div><div class="mt-2 bg-black/60 rounded-xl p-2 border border-green-500/30"><div class="flex justify-between text-[10px]"><span class="text-green-400 font-bold">💰 أقصى ربح تريلينق</span><span id="riskInfo" class="text-white font-mono">-</span></div><div id="scanLog" class="text-[11px] text-white mt-1 font-mono">بانتظار...</div><div class="mt-2 h-1.5 bg-white/10 rounded-full overflow-hidden"><div id="scanProgress" class="h-full bg-green-500" style="width:0%"></div></div></div><div class="flex gap-2 mt-3 flex-wrap"><span id="cnt" class="bg-white/10 px-3 py-1 rounded-full text-[10px]"></span><span id="allCount" class="bg-blue-500/20 px-3 py-1 rounded-full text-[10px]"></span><span id="strongCount" class="bg-green-500 text-black px-3 py-1 rounded-full text-[10px] font-black"></span><span id="maxPos" class="bg-yellow-400 text-black px-3 py-1 rounded-full text-[10px] font-black"></span></div></div><div id="liveBig" class="my-3"></div><div class="glass rounded-2xl p-3 border-2 border-green-400"><div class="flex justify-between text-[12px] font-black"><span>💰 أهداف قصوى</span><span id="strongTop" class="bg-green-500 text-black px-2 py-0.5 rounded-full text-[9px]"></span></div><div id="strongList" class="space-y-2 mt-2"></div></div><div class="glass rounded-2xl p-3 mt-3 border border-yellow-500/20"><div class="text-[11px] font-black">💰 جني أرباح لأقصى ربح</div><div class="text-[10px] text-gray-400 mt-1 leading-4">• قوية جداً 🔥🔥 هدف $3 + تريلينق<br>• قوية 🔥 هدف $2 + تريلينق<br>• متوسطة هدف $1.2<br>• تريلينق: +0.4 → ستوب دخول<br>• +0.6 → يحمي -0.5<br>• +1.5 → يحمي -0.7<br>• +2.5 → يحمي -1.0 يطير<br>• ستوب ثابت -0.9$ ضد الجحفلة</div></div><script>async function load(){const s=await fetch('/api/status').then(r=>r.json());document.getElementById('bal').textContent=`$${s.bal.toFixed(2)}`;document.getElementById('total').textContent=`/ $${s.total.toFixed(2)} كلي`;document.getElementById('next').textContent=s.next_margin>2?`الجاية $${s.next_margin} تعويض`:`الجاية $${s.next_margin}`;document.getElementById('last').textContent=s.last;document.getElementById('scanLog').textContent=s.scan_log;document.getElementById('riskInfo').textContent=`خسارة اليوم ${s.daily_loss_amount.toFixed(1)}$ | ${s.daily_losses} خسائر`;document.getElementById('cnt').textContent=s.count+'/6 مفتوح';document.getElementById('allCount').textContent=(s.all_rsi||[]).length+'/60';const veryStrong=(s.all_rsi||[]).filter(x=>x.rsi>1&& (x.rsi<=25||x.rsi>=75));const strong=(s.all_rsi||[]).filter(x=>x.rsi>1&& (x.rsi<=32||x.rsi>=68));document.getElementById('strongCount').textContent=`🔥 ${veryStrong.length} جداً + ${strong.length} قوية`;const maxPos=veryStrong.length>=3?6:veryStrong.length>=1?5:strong.length>=3?4:2;document.getElementById('maxPos').textContent=`يفتح حتى ${maxPos}`;document.getElementById('strongTop').textContent=`${veryStrong.length} قوية جداً`;const prog=s.scan_count>0?(parseInt(s.scan_current.split('/')[0].replace(/[^0-9]/g,''))||0)/s.scan_count*100:0;document.getElementById('scanProgress').style.width=prog+'%';document.getElementById('strongList').innerHTML=veryStrong.concat(strong.filter(x=>!veryStrong.some(v=>v.symbol===x.symbol))).sort((a,b)=>Math.abs(b.rsi-50)-Math.abs(a.rsi-50)).slice(0,6).map(x=>{const isVery=x.rsi<=25||x.rsi>=75;const target=isVery&& (x.rsi<=22||x.rsi>=78)?3.0:isVery?3.0:x.rsi<=30||x.rsi>=70?2.0:1.2;const col=isVery?'border-yellow-400 bg-yellow-500/20':'border-green-500/60 bg-green-500/10';const dir=x.rsi<50?'LONG':'SHORT';const type=x.rsi<=22||x.rsi>=78?'قوية جداً جداً 🔥🔥🔥':isVery?'قوية جداً 🔥🔥':'قوية 🔥';return `<div class="rounded-xl p-3 flex justify-between items-center border-2 ${col}"><div><div class="text-[13px] font-black">${x.symbol} <span class="px-2 py-0.5 rounded-full text-[10px] ${dir=='LONG'?'bg-green-500 text-black':'bg-red-500'}">${dir}</span> <span class="text-[10px]">${type}</span></div><div class="text-[11px] text-white">RSI ${x.rsi} هدف $${target}</div></div><div class="text-[9px] bg-green-500 text-black px-2 py-1 rounded-full font-black">تريلينق لأقصى ربح</div></div>`}).join('')||`<div class="text-[11px] text-gray-400 text-center py-3">بانتظار فرص...<br>هدف $3 للقوية جداً</div>`;const d=await fetch('/api/pnl').then(r=>r.json());document.getElementById('liveBig').innerHTML=d.live.length?d.live.map(x=>{const pct=x.target>0?(x.net/x.target*100).toFixed(0):0;return `<div class="card p-3 border-2 ${x.gross<0?'border-red-500/60':x.net>=x.target?'border-yellow-400':'border-green-500'} mb-2"><div class="flex justify-between text-[11px]"><span>${x.type} ${x.sym} RSI ${x.rsi}</span><span>${x.side.toUpperCase()} ${x.lev}x هدف $${x.target}</span></div><div class="flex justify-between items-end mt-1"><div class="text-[20px] font-black ${x.gross<0?'text-red-500':x.best>=x.target?'text-yellow-400':'text-green-400'}">${x.gross>=0?'+':''}${x.gross.toFixed(2)} <span class="text-[10px]">/ قمة $${x.best.toFixed(2)}</span></div><div class="text-[10px] bg-white/10 px-2 py-0.5 rounded-full">${pct}% من الهدف</div></div><div class="mt-1 h-1.5 bg-white/10 rounded-full overflow-hidden"><div class="h-full ${x.net<0?'bg-red-500':x.net>=x.target?'bg-yellow-400':'bg-green-500'}" style="width:${Math.min(100,Math.max(0,(x.net/x.target*100)))}%"></div></div><div class="text-[9px] text-gray-500 mt-1">تصفية ${x.dist.toFixed(1)}% | تريلينق ${x.best>=2.5?'1.0':x.best>=1.5?'0.7':x.best>=0.6?'0.5':'0.4'} → ستوب -0.9$</div></div>`}).join(''):`<div class="glass rounded-[20px] p-4 text-center text-[11px] text-gray-400">جني أرباح ذكي لأقصى ربح 💰<br>قوية جداً هدف $3 تريلينق</div>`;}setInterval(load,1000);load();</script></body></html>
"""

threading.Thread(target=hunter,daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))