import os, time, threading
from flask import Flask
import ccxt

app=Flask(__name__)
API=os.getenv("OKX_API_KEY","").strip()
SEC=os.getenv("OKX_SECRET_KEY","").strip()
PAS=os.getenv("OKX_PASSPHRASE","").strip()
LOG=[]

def bot():
    while True:
        try:
            ex=ccxt.okx({'apiKey':API,'secret':SEC,'password':PAS,'enableRateLimit':True})
            b=ex.fetch_balance()
            usdt=b.get('USDT',{}).get('free',0)
            t=ex.fetch_ticker('BTC/USDT')
            LOG.append(f"✅ LIVE USDT:{usdt} BTC:{t['last']}")
        except Exception as e:
            LOG.append(f"❌ {str(e)[:300]}")
        time.sleep(15)

threading.Thread(target=bot,daemon=True).start()

@app.route("/")
def home():
    return f"<h1>✅ V31 LIVE</h1>API {API[:8]}..<br>Balance<br>{'<br>'.join(LOG[-10:])}"

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)
