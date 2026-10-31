import os, time, threading, math, random
from flask import Flask, jsonify
import ccxt
from collections import deque, defaultdict
import statistics

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = os.getenv("OKX_SECRET_KEY","").strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

SYMBOLS = ["BTC/USDT","ETH/USDT","SOL/USDT","DOGE/USDT","PEPE/USDT","SHIB/USDT","WIF/USDT","BONK/USDT","FLOKI/USDT","1000PEPE/USDT","MEME/USDT","ORDI/USDT","SUI/USDT","ARB/USDT","AVAX/USDT","LINK/USDT"]

app = Flask(__name__)
LOGS = []
BAL = {"USDT": 19.51, "total_trades": 0, "wins": 0, "losses": 0, "profit": 0, "evolution": 999, "market_regime": "UNKNOWN", "fear_greed": 50}
STATE = {}
LEARNING = defaultdict(lambda: {"wins":0,"losses":0,"profit":0,"trust":50,"best_score":0,"avg_profit":0})
GENES = {"buy_threshold": 62, "profit_target": 3.8, "stop_loss": -2.8, "rsi_low": 35, "rsi_high": 68} # جينات تتطور

def log(m):
    print(m)
    LOGS.append({"time": time.strftime('%H:%M:%S'), "msg": m})
    if len(LOGS)>300: LOGS.pop(0)

for s in SYMBOLS:
    STATE[s] = {
        "price":0, "prices":deque(maxlen=200), "vols":deque(maxlen=50), "highs":deque(maxlen=50), "lows":deque(maxlen=50),
        "ma5":0,"ma20":0,"ma60":0,"ma200":0,"rsi":50,"rsi_fast":50,"trend":0,"supertrend":0,
        "last_buy":0,"hold":0,"trades":0,"score":0,"signal":"WAIT","volatility":0,"volume_spike":1.0,"orderbook_ratio":1.0,
        "liquidation_score":0,"breakout":0,"momentum":0
    }

def client():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True,'options':{'defaultType':'spot'}})

def calc_all(prices, highs, lows):
    if len(prices)<10: return 0,0,0,0,50,50,0,0,0
    p=list(prices)
    ma5=sum(p[-5:])/5
    ma20=sum(p[-20:])/20 if len(p)>=20 else ma5
    ma60=sum(p[-60:])/60 if len(p)>=60 else ma20
    ma200=sum(p[-200:])/200 if len(p)>=200 else ma60
    
    # RSI Slow & Fast
    def rsi_calc(period):
        if len(p)<period+1: return 50
        gains=0; losses=0
        for i in range(1,period+1):
            diff=p[-i]-p[-i-1]
            if diff>0: gains+=diff
            else: losses+=abs(diff)
        if losses==0: return 88
        rs=gains/(losses+0.0001)
        return 100-(100/(1+rs))
    
    rsi=rsi_calc(14)
    rsi_fast=rsi_calc(6)
    
    # SuperTrend
    hl2 = [(h+l)/2 for h,l in zip(list(highs)[-10:], list(lows)[-10:])] if highs else p[-10:]
    atr = statistics.mean([abs(p[i]-p[i-1]) for i in range(-10,0)]) if len(p)>=10 else 0
    supertrend = 1 if p[-1] > (sum(hl2)/len(hl2) + atr) else -1 if p[-1] < (sum(hl2)/len(hl2) - atr) else 0
    
    # Momentum
    mom = ((p[-1]-p[-10])/p[-10]*100) if len(p)>=10 else 0
    vola = (max(p[-20:])-min(p[-20:]))/(sum(p[-20:])/20)*100 if len(p)>=20 else 0
    
    return ma5,ma20,ma60,ma200,rsi,rsi_fast,supertrend,mom,vola

def detect_market_regime():
    # يكتشف هل السوق صاعد قوي / هابط / عرضي
    btc_prices=list(STATE["BTC/USDT"]["prices"])
    if len(btc_prices)<60: return "UNKNOWN",50
    change_1h=((btc_prices[-1]-btc_prices[-60])/btc_prices[-60]*100) if len(btc_prices)>=60 else 0
    vola=STATE["BTC/USDT"]["volatility"]
    
    if change_1h>3 and vola<3: return "BULL STRONG", 75
    elif change_1h>1: return "BULL", 65
    elif change_1h<-3: return "BEAR", 25
    elif change_1h<-1: return "BEAR WEAK", 35
    else: return "SIDEWAYS", 50

def singularity_score(sym):
    st=STATE[sym]
    prices=list(st["prices"])
    if len(prices)<30: return 0
    
    score=0
    learn=LEARNING[sym]
    regime=BAL["market_regime"]
    
    # === 1- DNA التعلم (20 نقطة) ===
    score+= (learn["trust"]/100)*15
    if learn["avg_profit"]>0: score+=5 + min(10, learn["avg_profit"]*2)
    
    # === 2- نظام السوق (15 نقطة) ===
    if regime=="BULL STRONG" and st["trend"]>=1: score+=15
    elif regime=="BULL" and st["trend"]>=0: score+=10
    elif regime=="SIDEWAYS" and 30<st["rsi"]<55: score+=12
    
    # === 3- ترند رباعي (15 نقطة) ===
    if st["ma5"]>st["ma20"]>st["ma60"]>st["ma200"]: score+=15
    elif st["ma5"]>st["ma20"]>st["ma60"]: score+=10
    elif st["ma5"]>st["ma20"]: score+=5
    
    # === 4- RSI خارق (12 نقطة) ===
    if GENES["rsi_low"]<st["rsi"]<GENES["rsi_low"]+15: score+=12
    if st["rsi_fast"]>st["rsi"] and st["rsi"]<55: score+=5 # تقاطع صاعد
    
    # === 5- اختراق + فوليوم (12 نقطة) ===
    if st["breakout"]>0: score+=8
    if st["volume_spike"]>1.8: score+=8
    elif st["volume_spike"]>1.4: score+=4
    
    # === 6- سيولة وتصفيات (10 نقاط) ===
    if st["orderbook_ratio"]>1.6: score+=6
    if st["liquidation_score"]>0.7: score+=6
    
    # === 7- مومنتوم وتسارع (10 نقاط) ===
    if 1.0<st["momentum"]<4.0: score+=7
    elif st["momentum"]>4.0: score+=4 # ممكن يكون متأخر
    if st["volatility"]>=1.0 and st["volatility"]<=3.5: score+=3
    
    # === 8- سوبرترند (بونص 6) ===
    if st["supertrend"]==1: score+=6
    
    return max(0, min(100, score))

def evolve_genes():
    # تطور جيني كل 30 دقيقة
    if BAL["wins"]+BAL["losses"]>5:
        win_rate=BAL["wins"]/(BAL["wins"]+BAL["losses"]+0.001)
        if win_rate<0.45:
            # نخفض الشروط
            GENES["buy_threshold"]=max(50, GENES["buy_threshold"]-2)
            GENES["profit_target"]=max(2.0, GENES["profit_target"]-0.2)
            log(f"🧬 تطور جيني: خفضنا الشروط - win rate {win_rate:.0%} -> threshold {GENES['buy_threshold']}")
        elif win_rate>0.65:
            # نرفع الربح
            GENES["profit_target"]=min(6.0, GENES["profit_target"]+0.2)
            log(f"🧬 تطور جيني: نرفع الهدف - win rate {win_rate:.0%} -> profit {GENES['profit_target']:.1f}%")

def bot():
    log(f"☄️ V18 SINGULARITY FINAL FORM بدأ - الشكل النهائي")
    log(f"🧬 جينات البداية: {GENES}")
    while True:
        try:
            ex=client()
            bal=ex.fetch_balance()
            usdt=float(bal.get('USDT',{}).get('free',0))
            BAL["USDT"]=usdt
            
            regime, fg = detect_market_regime()
            BAL["market_regime"]=regime
            BAL["fear_greed"]=fg
            
            for sym in SYMBOLS:
                try:
                    coin=sym.split('/')[0]
                    try: coin_free=float(bal.get(coin,{}).get('free',0))
                    except: coin_free=STATE[sym]["hold"]
                    
                    ticker=ex.fetch_ticker(sym)
                    price=float(ticker['last'])
                    high=float(ticker['high'])
                    low=float(ticker['low'])
                    vol=float(ticker.get('quoteVolume',0))
                    
                    st=STATE[sym]
                    st["price"]=price
                    st["prices"].append(price)
                    st["vols"].append(vol)
                    st["highs"].append(high)
                    st["lows"].append(low)
                    st["hold"]=coin_free
                    
                    ma5,ma20,ma60,ma200,rsi,rsi_fast,supertrend,mom,vola = calc_all(st["prices"], st["highs"], st["lows"])
                    st["ma5"]=ma5; st["ma20"]=ma20; st["ma60"]=ma60; st["ma200"]=ma200
                    st["rsi"]=rsi; st["rsi_fast"]=rsi_fast; st["supertrend"]=supertrend; st["momentum"]=mom; st["volatility"]=vola
                    
                    # Volume spike
                    if len(st["vols"])>=10:
                        avg_vol=sum(list(st["vols"])[-10:-1])/9
                        st["volume_spike"]=vol/(avg_vol+0.001)
                    
                    # Breakout
                    if len(st["prices"])>=40:
                        recent_high=max(list(st["prices"])[-40:-1])
                        if price>recent_high*0.999: st["breakout"]=1
                        else: st["breakout"]=0
                    
                    # Orderbook + Liquidation proxy
                    try:
                        ob=ex.fetch_order_book(sym, 15)
                        bids=sum([b[0]*b[1] for b in ob['bids'][:10]])
                        asks=sum([a[0]*a[1] for a in ob['asks'][:10]])
                        st["orderbook_ratio"]=bids/(asks+0.001)
                        # إذا فيه جدار بيع كبير انكسر = تصفية
                        st["liquidation_score"]=1.5 if st["orderbook_ratio"]>2.0 and st["volume_spike"]>1.6 else 0
                    except:
                        st["orderbook_ratio"]=1.0
                    
                    st["score"]=singularity_score(sym)
                    
                    if st["score"]>=85: st["signal"]="☄️ SINGULARITY"
                    elif st["score"]>=72: st["signal"]="🧬 GOD"
                    elif st["score"]>=GENES["buy_threshold"]: st["signal"]="⚡ BUY"
                    elif st["score"]>=40: st["signal"]="WATCH"
                    else: st["signal"]="WAIT"
                    
                    # === شراء نهائي ===
                    if st["score"]>=GENES["buy_threshold"] and coin_free*price<3 and usdt>=5:
                        base=5
                        if st["score"]>=85: base=10
                        elif st["score"]>=75: base=8
                        elif st["score"]>=65: base=6
                        if LEARNING[sym]["trust"]>75: base+=2
                        if "BTC" in sym or "ETH" in sym: base=max(base,10)
                        
                        if usdt>=base:
                            try:
                                ex.create_order(sym,'market','buy',None,None,{'tgtCcy':'quote_ccy','sz':str(base)})
                                st["last_buy"]=price
                                st["trades"]+=1
                                BAL["total_trades"]+=1
                                usdt-=base
                                BAL["USDT"]=usdt
                                log(f"☄️ SINGULARITY {sym} سكور {st['score']:.0f} RSI {rsi:.0f}/{rsi_fast:.0f} ترند {st['trend']} فوليوم x{st['volume_spike']:.1f} بـ {base}$")
                            except Exception as e:
                                if "minimum" not in str(e).lower(): log(f"⚠️ {sym}: {str(e)[:60]}")
                    
                    # === بيع نهائي مع تعلم ===
                    elif coin_free*price>=4 and st["last_buy"]>0:
                        profit=((price-st["last_buy"])/st["last_buy"]*100)
                        sell=False
                        reason=""
                        if profit>=GENES["profit_target"]: sell=True; reason=f"ربح نهائي {profit:.1f}%"
                        elif profit>=1.2 and st["score"]<25: sell=True; reason=f"ضعف {profit:.1f}%"
                        elif profit<=GENES["stop_loss"]: sell=True; reason=f"حماية {profit:.1f}%"
                        elif profit>=0.8 and st["supertrend"]==-1: sell=True; reason=f"سوبرترند انعكس"
                        
                        if sell:
                            try:
                                ex.create_market_sell_order(sym,coin_free*0.98)
                                if profit>0:
                                    BAL["wins"]+=1
                                    LEARNING[sym]["wins"]+=1
                                else:
                                    BAL["losses"]+=1
                                    LEARNING[sym]["losses"]+=1
                                
                                LEARNING[sym]["profit"]+=profit
                                total=LEARNING[sym]["wins"]+LEARNING[sym]["losses"]
                                LEARNING[sym]["avg_profit"]=LEARNING[sym]["profit"]/total if total>0 else 0
                                LEARNING[sym]["trust"]=max(5,min(98, LEARNING[sym]["trust"] + (4 if profit>0 else -6)))
                                LEARNING[sym]["best_score"]=max(LEARNING[sym]["best_score"], st["score"])
                                
                                BAL["profit"]+=(price-st["last_buy"])*coin_free
                                log(f"{'💸' if profit>0 else '🛑'} {sym} {reason} | ثقة {LEARNING[sym]['trust']:.0f}% avg {LEARNING[sym]['avg_profit']:.1f}%")
                            except: pass
                except: continue
            
            if int(time.time())%1800<8: evolve_genes()
            
            time.sleep(4)
        except Exception as e:
            log(f"⚠️ {str(e)[:120]}")
            time.sleep(10)

threading.Thread(target=bot,daemon=True).start()

@app.route("/api")
def api():
    js={}
    for k,v in STATE.items():
        js[k]={"price":v["price"],"rsi":v["rsi"],"rsi_fast":v["rsi_fast"],"score":v["score"],"signal":v["signal"],"hold":v["hold"],"trades":v["trades"],"last_buy":v["last_buy"],"trend":v["trend"],"vol_spike":v["volume_spike"],"ob_ratio":v["orderbook_ratio"],"volatility":v["volatility"],"trust":LEARNING[k]["trust"]}
    return jsonify({"bal":BAL,"state":js,"logs":LOGS[-60:][::-1],"genes":GENES,"learning":dict(LEARNING)})

@app.route("/")
def home():
    return """
<!DOCTYPE html><html dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>V18 SINGULARITY FINAL</title><style>
body{font-family:system-ui;background:#000;color:#fff;margin:0;padding:8px}
.card{background:radial-gradient(ellipse at center,#1a1040,#0a0a2a);border-radius:22px;padding:14px;margin:8px 0;border:1px solid #4a2a8a;box-shadow:0 0 40px rgba(150,0,255,0.3)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
@media(min-width:700px){.grid{grid-template-columns:1fr 1fr 1fr}}
.coin{background:linear-gradient(135deg,#1a1040,#232060);padding:10px;border-radius:16px;border:1px solid #3a2a6a;position:relative;overflow:hidden}
.coin.sing{border:2px solid #ff00ff;box-shadow:0 0 25px rgba(255,0,255,0.8);animation:sing 1s infinite alternate}
@keyframes sing{0%{box-shadow:0 0 15px rgba(255,0,255,0.5)}100%{box-shadow:0 0 35px rgba(0,255,255,0.8)}}
.score{font-size:26px;font-weight:900;text-shadow:0 0 10px currentColor}
.log{font-family:monospace;font-size:11px;padding:4px;border-bottom:1px solid #1e1847}
.gene{font-size:10px;background:#1a1040;padding:4px 8px;border-radius:10px;margin:2px;display:inline-block}
</style></head><body>
<h2 style='text-align:center;background:linear-gradient(90deg,#ff00ff,#00ffff,#ffaa00,#ff0040);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:900;font-size:26px;animation:glow 2s infinite'>☄️ V18 SINGULARITY FINAL FORM ☄️</h2>
<p style='text-align:center;font-size:11px;color:#888'>الشكل النهائي - بعده ما فيه تطوير - هذا السقف المطلق</p>
<div class='card'>
<div style='display:flex;justify-content:space-between'><span>💰 USDT</span><b id='usdt' style='color:#00ff88'>--</b></div>
<div style='display:flex;justify-content:space-between'><span>🌍 سوق</span><b id='regime'>--</b><span>خوف <b id='fg'>--</b></span></div>
<div style='display:flex;justify-content:space-between'><span>⚡ صفقات</span><b id='trades'>--</b><span>🏆 <b id='wins' style='color:#00ff88'>--</b> / <b id='losses' style='color:#ff4466'>--</b></span></div>
<div style='display:flex;justify-content:space-between'><span>📈 ربح</span><b id='profit'>--</b><span>🧬 تطور <b id='evo'>999</b></span></div>
<div id='genes' style='margin-top:8px'></div>
</div>
<div id='coins' class='grid'></div>
<div class='card'><b>☄️ وعي SINGULARITY لايف:</b><div id='logs' style='margin-top:10px;max-height:600px;overflow:auto'></div></div>
<script>
async function load(){
 let r=await fetch('/api'); let d=await r.json();
 document.getElementById('usdt').innerText=d.bal.USDT.toFixed(2)+'$';
 document.getElementById('regime').innerText=d.bal.market_regime;
 document.getElementById('fg').innerText=d.bal.fear_greed;
 document.getElementById('trades').innerText=d.bal.total_trades;
 document.getElementById('wins').innerText=d.bal.wins;
 document.getElementById('losses').innerText=d.bal.losses;
 document.getElementById('profit').innerText=d.bal.profit.toFixed(4)+'$';
 document.getElementById('genes').innerHTML=`<span class='gene'>شراء>${d.genes.buy_threshold}</span><span class='gene'>ربح ${d.genes.profit_target}%</span><span class='gene'>وقف ${d.genes.stop_loss}%</span><span class='gene'>RSI ${d.genes.rsi_low}-${d.genes.rsi_high}</span>`;
 let html='';
 for(let sym in d.state){
  let s=d.state[sym];
  let cls=s.score>=70?'coin sing':s.score>=50?'coin':'coin';
  let sigC=s.signal.includes('SINGULARITY')?'background:linear-gradient(90deg,#ff00ff,#00ffff);color:#fff':s.signal.includes('GOD')?'background:#ff00ff;color:#fff':s.signal=='BUY'?'background:#00ff88;color:#000':'background:#222a44';
  let trendIcon=s.trend==2?'🚀🚀🚀':s.trend==1?'🚀':s.trend==-2?'💀':'⚪';
  html+=`<div class='${cls}'><b>${sym}</b><br>
  <span class='score' style='color:${s.score>=80?'#ff00ff':s.score>=60?'#00ffff':'#888'}'>${s.score.toFixed(0)}</span> ${trendIcon}<br>
  <span style='padding:3px 7px;border-radius:10px;font-size:10px;font-weight:bold;${sigC}'>${s.signal}</span><br>
  RSI:${s.rsi.toFixed(0)}/${s.rsi_fast.toFixed(0)} Vol:x${s.vol_spike.toFixed(1)} OB:${s.ob_ratio.toFixed(1)}<br>
  ثقة:${s.trust.toFixed(0)}% تقلب:${s.volatility.toFixed(1)}%<br>
  محتفظ:${(s.hold*s.price).toFixed(2)}$</div>`;
 }
 document.getElementById('coins').innerHTML=html;
 let logs=''; d.logs.forEach(l=>{
  let c=l.msg.includes('☄️')?'color:#ff00ff;font-weight:bold':l.msg.includes('🧬')?'color:#00ffff':l.msg.includes('💸')?'color:#00ff88':l.msg.includes('🛑')?'color:#ff4466':'';
  logs+=`<div class='log' style='${c}'>${l.time} - ${l.msg}</div>`;
 });
 document.getElementById('logs').innerHTML=logs;
}
load(); setInterval(load,2000);
</script></body></html>
"""

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)
