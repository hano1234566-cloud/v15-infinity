import os, re, time, json, logging, threading
from datetime import datetime, timezone
import ccxt
from flask import Flask, jsonify

# === قراءة المفاتيح بكل الطرق الممكنة + تنظيف المسافات ===
def clean(s):
    if not s: return ""
    # يشيل كل المسافات والأسطر والعلامات الخفية
    return re.sub(r'\s+', '', str(s).strip())

def get_keys():
    # يجرب كل الأسماء المحتملة
    k = clean(os.getenv("OKX_API_KEY") or os.getenv("OKX_KEY") or os.getenv("OKX_APIKEY") or "")
    s = clean(os.getenv("OKX_API_SECRET") or os.getenv("OKX_SECRET") or os.getenv("OKX_SECRET_KEY") or os.getenv("OKX_APISECRET") or "")
    p = (os.getenv("OKX_API_PASSWORD") or os.getenv("OKX_PASSPHRASE") or os.getenv("OKX_API_PASSPHRASE") or os.getenv("OKX_PASSWORD") or "").strip()
    # الباسورد ما نشيل المسافات الداخلية بس نشيل اللي برا
    return k,s,p.strip()

API_KEY, API_SECRET, API_PASS = get_keys()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log = logging.getLogger("FIX")
app = Flask(__name__)

def make_ex():
    k,s,p = get_keys()
    return ccxt.okx({"apiKey":k,"secret":s,"password":p,"enableRateLimit":True,"options":{"defaultType":"swap"}})

exchange = make_ex()
state = {"signals":[],"loop":0,"scanned":0,"last_scan":None,"btc_trend":"neutral","btc_vol":0,"errors":[],"last_raw_balance":""}

# === الرصيد الحقيقي - يجرب 4 طرق ===
def get_equity():
    global API_KEY, API_SECRET, API_PASS
    API_KEY, API_SECRET, API_PASS = get_keys()
    free=0; spot=0; holdings=[]
    try:
        if not API_SECRET or len(API_SECRET) < 15:
            state["errors"] = [f"السيكرت ناقص - طوله {len(API_SECRET)} - المفروض > 40 حرف"]
            return {"free":0,"spot":0,"total":0,"holdings":[],"key_len":len(API_SECRET),"has_key":bool(API_KEY)}
        
        # طريقة 1: swap
        try:
            bal = exchange.fetch_balance({"type":"swap"})
            state["last_raw_balance"] = str(bal.get("info",{}).get("data",[]))[:200]
            data = bal.get("info",{}).get("data",[])
            for d in data:
                if d.get("ccy")=="USDT":
                    for field in ["availBal","availEq","eq","bal","frozenBal"]:
                        v = d.get(field)
                        if v and float(v) > 0:
                            if field=="availBal": free=float(v); break
                    if free==0:
                        for field in ["availBal","availEq","eq"]:
                            v = d.get(field)
                            if v: free=float(v); break
        except Exception as e:
            state["errors"].append(f"swap bal: {str(e)[:60]}")

        # طريقة 2: unified
        if free==0:
            try:
                bal2 = exchange.fetch_balance()
                free = float(bal2.get("USDT",{}).get("free",0) or bal2.get("free",{}).get("USDT",0) or 0)
            except: pass

        # طريقة 3: حساب USDT total
        if free==0:
            try:
                bal3 = exchange.fetch_balance({"type":"funding"})
                free = float(bal3.get("total",{}).get("USDT",0) or 0)
            except: pass

        # سبوت
        try:
            bal_all = exchange.fetch_balance()
            for coin,amt in bal_all.get("total",{}).items():
                if coin=="USDT": continue
                a=float(amt or 0)
                if a>0:
                    try:
                        pr=float(exchange.fetch_ticker(f"{coin}/USDT")["last"])
                        val=a*pr
                        if val>=0.3:
                            holdings.append({"coin":coin,"amount":a,"value":val})
                            spot+=val
                    except: pass
        except: pass
        state["errors"]=[]
    except Exception as e:
        state["errors"].append(str(e)[-120:])
    holdings.sort(key=lambda x:x["value"],reverse=True)
    return {"free":free,"spot":spot,"total":free+spot,"holdings":holdings,"key_len":len(API_SECRET),"has_key":bool(API_KEY)}

def get_positions():
    try:
        API_KEY, API_SECRET, API_PASS = get_keys()
        if not API_SECRET or len(API_SECRET)<15: return 0,[]
        exchange.load_markets()
        pos = exchange.fetch_positions()
        lst=[]
        for p in pos:
            c=float(p.get("contracts") or 0)
            if c>0:
                entry=float(p.get("entryPrice") or 0)
                mark=float(p.get("markPrice") or entry)
                if mark==0 or entry==0:
                    try: mark=float(exchange.fetch_ticker(p["symbol"])["last"])
                    except: pass
                side=p.get("side"); pnl=float(p.get("unrealizedPnl") or 0)
                lev=float(p.get("leverage") or 3)
                pct=0
                if entry>0:
                    if side=="long": pct=(mark-entry)/entry*100*lev
                    else: pct=(entry-mark)/entry*100*lev
                lst.append({"symbol":p["symbol"],"side":side,"entry":entry,"mark":mark,"contracts":c,"leverage":lev,"pnl":round(pnl,4),"pnl_pct":round(pct,2),"is_profit":pnl>=0,"margin":float(p.get("initialMargin") or 0)})
        return len(lst),lst
    except Exception as e:
        state["errors"].append(f"pos {str(e)[:70]}")
        return 0,[]

# scan بسيط
def fetch_df(sym):
    try:
        c=exchange.fetch_ohlcv(sym,timeframe="15m",limit=200)
        import pandas as pd
        df=pd.DataFrame(c,columns=["t","o","h","l","cl","v"])
        df=df.iloc[:-1].copy()
        df["ema9"]=df["cl"].ewm(span=9).mean(); df["ema21"]=df["cl"].ewm(span=21).mean(); df["ema200"]=df["cl"].ewm(span=200).mean()
        d=df["cl"].diff(); g=d.clip(lower=0); l=-d.clip(upper=0)
        ag=g.ewm(alpha=1/14,adjust=False).mean(); al=l.ewm(alpha=1/14,adjust=False).mean()
        rs=ag/al.replace(0,1e-8); df["rsi"]=100-(100/(1+rs))
        return df.dropna()
    except: return None

def scan_loop():
    while True:
        try:
            df_btc=fetch_df("BTC/USDT")
            if df_btc is not None:
                cur=df_btc.iloc[-1]
                state["btc_trend"]="bull" if cur["cl"]>cur["ema200"] and cur["ema9"]>cur["ema21"] else "bear" if cur["cl"]<cur["ema200"] else "neutral"
                state["btc_vol"]=round(float((df_btc["h"].iloc[-1]-df_btc["l"].iloc[-1])/cur["cl"]*100),2)
            TOP=["BTC/USDT","ETH/USDT","SOL/USDT"]
            sigs=[]
            for s in TOP:
                df=fetch_df(s)
                if df is None: continue
                cur=df.iloc[-1]; prev=df.iloc[-2]
                if cur["ema9"]>cur["ema21"] and cur["cl"]>cur["ema200"] and prev["ema9"]<=prev["ema21"] and 48<cur["rsi"]<70:
                    sigs.append({"symbol":s,"direction":"long","score":8,"price":float(cur["cl"]),"rsi":round(float(cur["rsi"]),1)})
                elif cur["ema9"]<cur["ema21"] and cur["cl"]<cur["ema200"] and prev["ema9"]>=prev["ema21"] and 28<cur["rsi"]<50:
                    sigs.append({"symbol":s,"direction":"short","score":8,"price":float(cur["cl"]),"rsi":round(float(cur["rsi"]),1)})
            state["signals"]=sigs; state["loop"]+=1; state["last_scan"]=datetime.now(timezone.utc).isoformat()
        except: pass
        time.sleep(20)

DASHBOARD="""
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>V15 FIXED</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{background:#0a0e14;color:#e5e7eb}.card{background:#111827;border:1px solid #1f2937;border-radius:14px}.live{width:8px;height:8px;background:#22c55e;border-radius:50%;display:inline-block;animation:pulse 1s infinite}@keyframes pulse{0%{opacity:1}50%{opacity:0.2}100%{opacity:1}}.num{transition:all 0.3s}</style>
</head><body class="p-3"><div class="max-w-6xl mx-auto">
<div class="flex justify-between mb-4"><h1 class="text-xl font-bold">V15 FIXED <span class="text-green-400">REAL</span> <span class="live"></span></h1><p class="text-[10px] text-gray-400" id="last">--</p></div>
<div id="err" class="hidden bg-red-900/40 border border-red-600 rounded-xl p-3 mb-4 text-xs"></div>
<div id="info" class="bg-blue-900/30 border border-blue-600 rounded-xl p-2 mb-4 text-[10px]"></div>
<div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
<div class="card p-3"><p class="text-[10px] text-gray-400">فيوتشر حر</p><p id="free" class="font-bold text-lg num">--</p><p class="text-[9px] text-gray-500">availBal حقيقي</p></div>
<div class="card p-3"><p class="text-[10px] text-gray-400">ربح الآن</p><p id="tpnl" class="font-bold text-lg num">--</p></div>
<div class="card p-3"><p class="text-[10px] text-gray-400">صفقات</p><p id="cnt" class="font-bold text-lg num">--</p></div>
<div class="card p-3"><p class="text-[10px] text-gray-400">الثروة</p><p id="total" class="font-bold text-lg num">--</p><p id="spotSum" class="text-[9px] text-gray-500"></p></div>
</div>
<div class="card p-4 mb-4"><h3 class="font-bold text-sm mb-3">📊 صفقاتي - ربح / خسارة مباشر <span class="live"></span></h3><div id="pos" class="space-y-3"></div></div>
<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
<div class="card p-4"><h3 class="font-bold text-sm mb-2">🎯 إشارات GOD 7/10</h3><div id="sigs" class="text-xs"></div></div>
<div class="card p-4"><h3 class="font-bold text-sm mb-2">💰 كل السبوت</h3><div id="spot" class="text-xs"></div></div>
</div>
</div>
<script>
async function load(){
 try{
  const r=await fetch('/api/full'); const d=await r.json();
  document.getElementById('free').textContent=d.free.toFixed(2)+' USDT';
  document.getElementById('total').textContent=d.total.toFixed(2)+' $';
  document.getElementById('spotSum').textContent='سبوت: '+d.spot.toFixed(2)+'$ | مفتاح: '+(d.has_key?'✅':'❌')+' طول السيكرت: '+d.key_len;
  document.getElementById('cnt').textContent=d.count+' / 2';
  document.getElementById('last').textContent=d.last_scan?new Date(d.last_scan).toLocaleTimeString('ar-SA'):'--';
  document.getElementById('info').textContent='KEY: '+(d.has_key?'موجود ✅':'ناقص ❌')+' | SECRET len: '+d.key_len+' | PASS: '+(d.has_pass?'✅':'❌')+' | raw: '+(d.raw_balance||'').substring(0,80);
  const errDiv=document.getElementById('err');
  if(d.errors && d.errors.length){errDiv.classList.remove('hidden'); errDiv.textContent=d.errors.join(' | ');} else {errDiv.classList.add('hidden');}
  const tpnl=document.getElementById('tpnl');
  tpnl.textContent=(d.total_pnl>=0?'+':'')+d.total_pnl.toFixed(4)+' $';
  tpnl.className='font-bold text-lg num '+(d.total_pnl>=0?'text-green-400':'text-red-400');
  const posDiv=document.getElementById('pos');
  if(d.positions.length==0){posDiv.innerHTML='<p class="text-gray-500 text-sm">لا صفقات مفتوحة في OKX حاليا</p>';}
  else{
    posDiv.innerHTML=d.positions.map(p=>{
      const up=p.is_profit; const bg=up?'bg-green-500/10 border-green-500/50':'bg-red-500/10 border-red-500/50'; const col=up?'text-green-400':'text-red-400';
      return `<div class="border ${bg} rounded-xl p-3 flex justify-between"><div><p class="font-bold">${p.symbol.replace(':USDT','')} <span class="text-[10px] px-2 py-0.5 rounded ${p.side=='long'?'bg-green-600':'bg-red-600'}">${p.side} x${p.leverage}</span></p><p class="text-[11px] text-gray-400">دخول ${p.entry.toFixed(2)} | حالي <span class="text-white font-bold num">${p.mark.toFixed(2)}</span></p></div><div class="text-left"><p class="font-black text-lg num ${col}">${p.pnl>=0?'+':''}${p.pnl.toFixed(4)}$</p><p class="text-sm num ${col}">${p.pnl_pct>=0?'+':''}${p.pnl_pct.toFixed(2)}% ${up?'🟢 ربحانة':'🔴 خسرانة'}</p></div></div>`;
    }).join('');
  }
  document.getElementById('sigs').innerHTML=d.signals.length?d.signals.map(s=>`<div class="bg-[#0a0e14] rounded p-2 mb-1">${s.symbol} ${s.direction} ${s.score}/10</div>`).join(''):'لا إشارات';
  document.getElementById('spot').innerHTML=d.holdings.length?d.holdings.map(h=>`<div class="flex justify-between bg-[#0a0e14] rounded p-2 mb-1"><span>${h.coin}</span><span>${h.value.toFixed(2)}$</span></div>`).join(''):'لا سبوت';
 }catch(e){}
}
load(); setInterval(load,2000);
</script></body></html>
"""

@app.route("/")
def home(): return DASHBOARD,200,{'Content-Type':'text/html; charset=utf-8'}

@app.route("/api/full")
def api_full():
    eq=get_equity()
    cnt,positions=get_positions()
    total=sum([p["pnl"] for p in positions])
    k,s,p = get_keys()
    return jsonify({
        "free":eq["free"],"spot":eq["spot"],"total":eq["total"],"holdings":eq["holdings"],
        "count":cnt,"positions":positions,"total_pnl":round(total,4),
        "btc_trend":state["btc_trend"],"btc_vol":state["btc_vol"],
        "signals":state["signals"],"loop":state["loop"],"last_scan":state["last_scan"],
        "errors":state["errors"][-2:],"has_key":bool(k),"has_pass":bool(p),"key_len":len(s),"raw_balance":state["last_raw_balance"]
    })

@app.route("/ping")
def ping():
    k,s,p = get_keys()
    return jsonify({"key":bool(k),"key_len":len(k),"secret_len":len(s),"pass":bool(p),"pass_len":len(p)})

if __name__=="__main__":
    threading.Thread(target=scan_loop,daemon=True).start()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
