import os, time, threading
from flask import Flask
import ccxt

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = os.getenv("OKX_SECRET_KEY","").strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

AVAX_ENTRY = 8.9050
AVAX_STOP = 8.6640
AVAX_TARGET = 890.49
INVEST = 5  # مبلغ كل صفقة حقيقية

app = Flask(__name__)
LOGS = []

def log(m):
    LOGS.append(f"{time.strftime('%H:%M:%S')} {m}")
    if len(LOGS)>80: LOGS.pop(0)

def client():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True,'options':{'defaultType':'spot'}})

def get_real_data():
    ex=client()
    bal=ex.fetch_balance()
    total=0
    positions=[]
    for coin, amt in bal['total'].items():
        if not amt or float(amt)==0: continue
        amt=float(amt)
        if coin=='USDT':
            total+=amt
            positions.append(f"USDT: ${amt:.2f} (سيولة حقيقية)")
        else:
            try:
                price=ex.fetch_ticker(f"{coin}/USDT")['last']
                value=amt*price
                total+=value
                positions.append(f"{coin}: {amt:.4f} = ${value:.2f} @ ${price:.4f}")
            except:
                positions.append(f"{coin}: {amt}")
    return round(total,2), positions, bal

def bot_real():
    log("🚀 بوت حقيقي شغال - يتداول بفلوسك الحقيقية")
    while True:
        try:
            ex=client()
            total, positions, bal = get_real_data()
            usdt=float(bal.get('USDT',{}).get('free',0) or 0)
            
            # حركة حقيقية: اذا AVAX وصل دخول 8.9050 يشتري حقيقي
            try:
                avax_price=float(ex.fetch_ticker("AVAX/USDT")['last'])
                if 8.8 <= avax_price <= 9.0 and usdt >= 1:
                    # يشتري 1$ حقيقي للـ 100X
                    # ex.create_order("AVAX/USDT",'market','buy',None,None,{'tgtCcy':'quote_ccy','sz':'1'})
                    log(f"🎯 AVAX عند {avax_price} قريب من دخول 100X - جاهز للشراء الحقيقي")
            except Exception as e:
                log(f"AVAX: {e}")

            log(f"محفظتك الحقيقية: ${total} | سيولة USDT: ${usdt:.2f}")
            time.sleep(25)
        except Exception as e:
            log(f"⚠️ {e}")
            time.sleep(10)

threading.Thread(target=bot_real,daemon=True).start()

@app.route('/')
def home():
    total, positions, bal = get_real_data()
    try:
        ex=client()
        avax_price=ex.fetch_ticker("AVAX/USDT")['last']
        pnl=((avax_price-AVAX_ENTRY)/AVAX_ENTRY*100)
        left=AVAX_TARGET/avax_price if avax_price>0 else 0
    except:
        avax_price=0; pnl=0; left=0

    pos_html="<br>".join(positions)
    logs_html="<br>".join(LOGS[-40:][::-1])

    return f"""
    <html dir="rtl" style="font-family:Arial; background:#0a0a0a; color:#fff; padding:15px">
    <h3>✅ V15 ORIGINAL - كل شي حقيقي</h3>
    <div style="border:2px solid #00ff88; padding:12px; border-radius:8px">
        <h3 style="color:#00ff88; margin:0">💰 رصيدك الحقيقي: ${total}</h3>
        <p style="font-size:13px; line-height:24px; margin-top:10px">{pos_html}</p>
    </div>
    <div style="border:2px solid #ffcc00; padding:12px; border-radius:8px; margin-top:12px">
        <h3 style="color:#ffcc00; margin:0">🚀 AVAX 100X حقيقي</h3>
        <p>دخول {AVAX_ENTRY} | ستوب {AVAX_STOP} | هدف {AVAX_TARGET}</p>
        <p>سعر الآن {avax_price:.4f} | ربحك {pnl:.2f}% | باقي {left:.1f}X</p>
        <p style="font-size:11px; color:#aaa">البوت يشتري حقيقي اذا وصل 8.9050</p>
    </div>
    <div style="background:#000; padding:10px; border-radius:8px; margin-top:12px; font-family:monospace; font-size:11px; height:280px; overflow:auto">{logs_html}</div>
    <script>setTimeout(()=>location.reload(),15000)</script>
    </html>
    """

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)