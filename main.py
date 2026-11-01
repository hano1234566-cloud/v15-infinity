import os, time, threading
from flask import Flask
import ccxt

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = os.getenv("OKX_SECRET_KEY","").strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "AVAX/USDT", "DOGE/USDT", "WIF/USDT"]
INVEST = 5
DROP = 2.5
PROFIT = 2.8

# حركة 100X
AVAX_ENTRY = 8.9050
AVAX_STOP = 8.6640
AVAX_TARGET = AVAX_ENTRY * 100  # 890.5

app = Flask(__name__)
LOGS = []
STATE = {s: {"last": 0, "trades": 0} for s in SYMBOLS}
AVAX_100X = {"current": 0, "pnl": 0, "left_x": 0}

def log(m):
    LOGS.append(f"{time.strftime('%H:%M:%S')} {m}")
    if len(LOGS)>80: LOGS.pop(0)

def client():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True,'options':{'defaultType':'spot'}})

def get_total():
    try:
        ex=client(); bal=ex.fetch_balance(); total=0
        for coin, amt in bal['total'].items():
            if not amt: continue
            if coin=='USDT': total+=float(amt)
            else:
                try:
                    p=ex.fetch_ticker(f"{coin}/USDT")['last']
                    total+=float(amt)*p
                except: pass
        return round(total,2), bal
    except:
        return 0, {}

def bot():
    log(f"🚀 V15 كامل - يومي + 100X")
    while True:
        try:
            ex=client()
            total, bal = get_total()
            usdt=float(bal.get('USDT',{}).get('free',0))

            # تحديث AVAX 100X
            try:
                avax_price=float(ex.fetch_ticker("AVAX/USDT")['last'])
                AVAX_100X["current"]=avax_price
                AVAX_100X["pnl"]=((avax_price-AVAX_ENTRY)/AVAX_ENTRY*100)
                AVAX_100X["left_x"]=AVAX_TARGET/avax_price if avax_price>0 else 0
            except: pass

            for sym in SYMBOLS:
                try:
                    coin=sym.split('/')[0]
                    coin_free=float(bal.get(coin,{}).get('free',0))
                    price=float(ex.fetch_ticker(sym)['last'])
                    if STATE[sym]["last"]==0: STATE[sym]["last"]=price
                    drop=((STATE[sym]["last"]-price)/STATE[sym]["last"]*100) if STATE[sym]["last"]>0 else 0

                    if drop>=DROP and usdt>=INVEST:
                        ex.create_order(sym,'market','buy',None,None,{'tgtCcy':'quote_ccy','sz':str(INVEST)})
                        STATE[sym]["last"]=price; STATE[sym]["trades"]+=1; usdt-=INVEST
                        log(f"✅ شراء {sym} {price}")
                        time.sleep(2)
                    elif coin_free*price>=5:
                        profit=((price-STATE[sym]["last"])/STATE[sym]["last"]*100) if STATE[sym]["last"]>0 else 0
                        if profit>=PROFIT:
                            ex.create_market_sell_order(sym, coin_free*0.85)
                            log(f"💸 بيع {sym} ربح {profit:.2f}%")
                            time.sleep(2)
                except Exception as e:
                    log(f"⚠️ {sym}: {str(e)[:80]}")
            time.sleep(20)
        except Exception as e:
            log(f"⚠️ {e}"); time.sleep(10)

threading.Thread(target=bot,daemon=True).start()

@app.route('/')
def home():
    total,_ = get_total()
    trades=sum([v["trades"] for v in STATE.values()])
    logs="<br>".join(LOGS[-30:][::-1])
    state_html="<br>".join([f"{k}: آخر {v['last']:.4f} | صفقات {v['trades']}" for k,v in STATE.items()])
    
    return f"""
    <html dir="rtl" style="font-family:Arial; background:#0a0a0a; color:#fff; padding:15px">
    <h2>✅ V15 ORIGINAL - كل شي يبان</h2>
    
    <div style="background:#111; border:2px solid #00ff88; padding:12px; border-radius:8px">
        <h3 style="margin:0; color:#00ff88">💰 رصيدك الإجمالي: ${total}</h3>
        <p>إجمالي صفقات اليوم: {trades}</p>
        <p style="font-size:12px">{state_html}</p>
    </div>

    <div style="background:#111; border:2px solid #ffcc00; padding:12px; border-radius:8px; margin-top:15px">
        <h3 style="margin:0; color:#ffcc00">🚀 حركة 100X - AVAX</h3>
        <p>دخول: {AVAX_ENTRY} | ستوب: {AVAX_STOP} | هدف 100X: {AVAX_TARGET}</p>
        <p style="font-size:18px">سعر الآن: <b>{AVAX_100X['current']}</b> | ربح/خسارة: <b>{AVAX_100X['pnl']:.2f}%</b></p>
        <p>باقي للهدف: <b>{AVAX_100X['left_x']:.1f}X</b></p>
        <p style="color:#aaa; font-size:11px">سكور 94 - إذا وصل 8.9050 يشتري 1$ ويتركها للـ100X</p>
    </div>

    <div style="margin-top:15px; font-family:monospace; font-size:11px; background:#000; padding:10px; border-radius:8px">{logs}</div>
    <script>setTimeout(()=>location.reload(),15000)</script>
    </html>
    """

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)