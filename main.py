import os, time, threading, ccxt
from flask import Flask, jsonify, request
import numpy as np

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL = 0.0
LAST = "V20015 - صفقتين بشرط الربح"
STATE = {"open":{}, "daily":0, "stopped":False, "avail":0, "total":0, "last_pnl":None}

app = Flask(__name__)

def get_ex():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'options':{'defaultType':'swap'},'enableRateLimit':True})

def get_real_balance():
    global BAL
    try:
        ex = get_ex()
        resp = ex.private_get_account_balance()
        data = resp.get('data', [])[0]
        for item in data.get('details', []):
            if item.get('ccy') == 'USDT':
                avail = float(item.get('availBal',0) or 0)
                total = float(item.get('eq',0) or 0)
                STATE["avail"] = avail
                STATE["total"] = total
                BAL = avail
                return avail
    except: pass
    try:
        bal = get_ex().fetch_balance()
        BAL = float(bal.get('total',{}).get('USDT',0) or 0)
        return BAL
    except:
        return BAL

def calc_rsi(prices, p=14):
    try:
        prices=np.array(prices,float)
        deltas=np.diff(prices)
        up=np.where(deltas>0,deltas,0); down=np.where(deltas<0,-deltas,0)
        ma_up=np.mean(up[:p]); ma_down=np.mean(down[:p])
        if ma_down==0: return 70
        rsi=100-(100/(1+ma_up/ma_down))
        for i in range(p,len(deltas)):
            ma_up=(ma_up*(p-1)+up[i])/p; ma_down=(ma_down*(p-1)+down[i])/p
            rsi=100-(100/(1+ma_up/ma_down)) if ma_down!=0 else 70
        return float(rsi)
    except: return 50.0

def scan_live():
    sigs=[]
    for sym in ["ENA/USDT:USDT","FET/USDT:USDT","TAO/USDT:USDT","RENDER/USDT:USDT","SUI/USDT:USDT","ARB/USDT:USDT"]:
        try:
            ex=get_ex()
            ohlcv=ex.fetch_ohlcv(sym,'1h',80)
            closes=[c[4] for c in ohlcv]
            price=closes[-1]; rsi=calc_rsi(closes)
            d="long" if rsi<45 else "short" if rsi>55 else "long"
            sigs.append({"symbol":sym.replace("/USDT:USDT",""),"full":sym,"direction":d,"price":price,"rsi":round(rsi,1),"score":8 if rsi<35 or rsi>65 else 6})
        except: pass
    return sorted(sigs,key=lambda x:x["score"],reverse=True)

def hunter():
    global BAL, LAST
    while True:
        try:
            BAL = get_real_balance()
            avail = STATE.get("avail",0)
            total = STATE.get("total",0)

            if avail < 1 and total >= 5:
                LAST = f"أنقل $5 من Funding للتداول... الكلي ${total:.2f} المتاح ${avail:.2f}"
                try:
                    ex=get_ex()
                    ex.private_post_asset_transfer({"ccy":"USDT","amt":"5","from":"6","to":"18","type":"0"})
                    time.sleep(3)
                    BAL = get_real_balance()
                    LAST = f"✅ نقلت $5 - المتاح ${BAL:.2f}"
                except Exception as e:
                    LAST = f"انقل يدوي Assets>Transfer Funding->Trading $5"
                    time.sleep(10)
                    continue

            # تنظيف المقفلة
            try:
                ex=get_ex()
                positions=ex.fetch_positions()
                open_syms=[p["symbol"] for p in positions if float(p.get("contracts",0))>0]
                for sym in list(STATE["open"].keys()):
                    if sym not in open_syms:
                        d=STATE["open"].pop(sym)
                        pnl = d.get("best",0)
                        STATE["last_pnl"] = pnl
                        STATE["daily"]+=pnl
                        if pnl>0:
                            LAST=f"✅ قفلت {d['name']} ربح ${pnl:.2f}"
                        else:
                            LAST=f"❌ قفلت {d['name']} خسارة ${pnl:.2f} - يوقف"
            except: pass

            # تريلنج
            for sym,data in list(STATE["open"].items()):
                try:
                    ex=get_ex()
                    tk=ex.fetch_ticker(sym)
                    last=tk["last"]; entry=data["entry"]
                    pnl_pct=(last-entry)/entry if data["dir"]=="long" else (entry-last)/entry
                    pnl_usd=pnl_pct*1.0*5
                    if pnl_usd>data["best"]: data["best"]=pnl_usd
                    if pnl_usd>=0.70: data["trail"]=True
                except: pass

            # حساب خسائر المفتوح
            open_pnls = []
            try:
                ex=get_ex()
                for sym,data in list(STATE["open"].items()):
                    tk=ex.fetch_ticker(sym)
                    last=tk["last"]; entry=data["entry"]
                    pct=(last-entry)/entry if data["dir"]=="long" else (entry-last)/entry
                    usd=pct*1.0*5
                    open_pnls.append(usd)
            except: pass

            total_open_pnl = sum(open_pnls) if open_pnls else 0
            can_open = False

            if len(STATE["open"])==0:
                if STATE.get("last_pnl") is not None and STATE["last_pnl"] < 0:
                    LAST = f"آخر صفقة خسرانة ${STATE.get('last_pnl',0):.2f} - موقف"
                    can_open = False
                else:
                    can_open = True
            elif len(STATE["open"])==1:
                if open_pnls and open_pnls[0] < 0:
                    LAST = f"الصفقة خسرانة ${open_pnls[0]:.2f} - ما يفتح الثانية"
                    can_open = False
                elif open_pnls and open_pnls[0] >= 0.30:
                    can_open = True
                    LAST = f"الأولى ربحانة ${open_pnls[0]:.2f} - يسمح الثانية"
                else:
                    LAST = f"الأولى ${open_pnls[0]:.2f} - ينتظر $0.30"
            elif len(STATE["open"])>=2:
                if total_open_pnl < 0:
                    LAST = f"الصفقتين خسرانة ${total_open_pnl:.2f} - موقف"
                can_open = False

            if can_open and BAL>=0.5 and len(STATE["open"])<2:
                sigs=scan_live()
                if sigs:
                    existing = [v["name"] for v in STATE["open"].values()]
                    sig = None
                    for s in sigs:
                        if s["symbol"] not in existing:
                            sig = s
                            break
                    if not sig:
                        time.sleep(3)
                        continue
                    try:
                        ex=get_ex()
                        ex.set_leverage(5, sig["full"])
                        side="buy" if sig["direction"]=="long" else "sell"
                        amount=(1.0*5)/sig["price"]
                        amount=max(amount,1.0)
                        amount=float(ex.amount_to_precision(sig["full"], amount))
                        order=None
                        for mode in [{'tdMode':'cross'}, {'tdMode':'isolated'}, {'tdMode':'isolated','posSide':'long' if side=='buy' else 'short'}]:
                            try:
                                order=ex.create_market_order(sig["full"], side, amount, None, mode)
                                break
                            except: continue
                        if order:
                            entry=order.get("average") or sig["price"]
                            STATE["open"][sig["full"]]={"name":sig["symbol"],"dir":sig["direction"],"entry":entry,"sl":entry*0.992 if side=="buy" else entry*1.008,"best":0,"locked":0,"trail":False}
                            LAST=f"✅ فتح {len(STATE['open'])}/2 {sig['direction'].upper()} {sig['symbol']}"
                        else:
                            LAST=f"❌ فشل فتح {sig['symbol']}"
                    except Exception as e:
                        LAST=f"❌ {str(e)[:120]} رصيد ${BAL:.2f}"
            time.sleep(3)
        except Exception as e:
            LAST=f"خطأ {str(e)[:100]}"; time.sleep(3)

@app.route("/")
def index(): return DASH_HTML
@app.route("/api/status")
def status(): return jsonify({"balance":get_real_balance(),"avail":STATE.get("avail",0),"total":STATE.get("total",0),"count":len(STATE["open"]),"last":LAST,"daily":STATE.get("daily",0),"last_pnl":STATE.get("last_pnl")})
@app.route("/api/scan")
def scan(): return jsonify({"signals":scan_live()})
@app.route("/api/pnl_live")
def pnl_live():
    live=[]; ex=get_ex()
    for sym,data in STATE["open"].items():
        try:
            tk=ex.fetch_ticker(sym); last=tk["last"]; entry=data["entry"]
            pct=(last-entry)/entry if data["dir"]=="long" else (entry-last)/entry
            usd=pct*1.0*5
            live.append({"symbol":data["name"],"dir":data["dir"],"pnl":round(usd,2),"entry":entry,"last":last,"sl":data["sl"],"best":round(data["best"],2)})
        except: pass
    return jsonify({"live":live})

DASH_HTML = """
<!DOCTYPE html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>V20015 2 صفقات</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{background:#0a0e14}.glass{background:#121a26;border:1px solid #1e2d42}</style></head>
<body class="text-white p-3">
<div class="glass rounded-[20px] p-5 mb-4">
<div class="text-[11px] text-gray-400">المتاح / الكلي - مباشر من OKX</div>
<div class="flex gap-3 items-end"><div id="bal" class="text-[28px] font-black">$0</div><div id="total" class="text-[13px] text-gray-400 mb-1"></div></div>
<div id="last" class="text-[12px] text-yellow-300 mt-2"></div>
<div class="flex gap-4 mt-2 text-[11px]"><div id="cnt"></div><div id="daily" class="text-green-400"></div><div id="lastpnl"></div></div>
</div>
<div id="liveBig" class="mb-4 space-y-3"></div>
<div class="glass rounded-2xl p-4"><div class="font-black mb-2 text-[13px]">🚀 السوق - صفقتين بشرط الربح</div><div id="sigs" class="space-y-2"></div></div>
<script>
async function load(){
 const st=await fetch('/api/status').then(r=>r.json());
 document.getElementById('bal').textContent='$'+st.balance.toFixed(2)+' متاح';
 document.getElementById('total').textContent='/ $'+st.total.toFixed(2)+' كلي';
 document.getElementById('last').textContent=st.last;
 document.getElementById('cnt').textContent=st.count+'/2 صفقات';
 document.getElementById('daily').textContent='اليوم $'+st.daily.toFixed(2);
 document.getElementById('lastpnl').textContent=st.last_pnl!=null?'آخر $'+st.last_pnl.toFixed(2):'';
 const pnl=await fetch('/api/pnl_live').then(r=>r.json());
 document.getElementById('liveBig').innerHTML=pnl.live.length? pnl.live.map(x=>`<div class="glass rounded-[20px] p-4 border ${x.pnl>=0?'border-green-500/50':'border-red-500/50'}"><div class="flex justify-between"><span class="font-black">${x.symbol} ${x.dir.toUpperCase()}</span><span class="px-3 py-1 rounded-full font-black text-[13px] ${x.pnl>=0?'bg-green-500 text-black':'bg-red-500'}">${x.pnl>=0?'+':''}$${x.pnl}</span></div><div class="grid grid-cols-3 gap-2 mt-2 text-[11px]"><div class="bg-black/40 rounded-lg p-2 text-center">دخول<br>${x.entry.toFixed(4)}</div><div class="bg-black/40 rounded-lg p-2 text-center">حالي<br>${x.last.toFixed(4)}</div><div class="bg-black/40 rounded-lg p-2 text-center">أفضل<br>$${x.best}</div></div></div>`).join('') : `<div class="glass rounded-2xl p-5 text-center border-dashed text-[12px]">🔴 يبحث - يفتح الأولى دايم، الثانية فقط إذا الأولى +$0.30 ربح<br>إذا خسرانة ما يفتح</div>`;
 const sc=await fetch('/api/scan').then(r=>r.json());
 document.getElementById('sigs').innerHTML=sc.signals.map(s=>`<div class="bg-black/30 rounded-xl p-2.5 flex justify-between text-[12px]"><span>${s.symbol} ${s.price.toFixed(4)} <span class="px-2 py-0.5 rounded-full text-[10px] ${s.direction=='long'?'bg-green-500 text-black':'bg-red-500'}">${s.direction.toUpperCase()}</span> RSI ${s.rsi}</span><span class="text-gray-400">Score ${s.score}</span></div>`).join('');
}
setInterval(load,2500); load();
</script></body></html>
"""

threading.Thread(target=hunter,daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))