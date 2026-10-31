import os, time, threading
from flask import Flask
import ccxt

app=Flask(__name__)
API_KEY=os.getenv("OKX_API_KEY","").strip()
SECRET=os.getenv("OKX_SECRET_KEY","").strip()
PASSPHRASE=os.getenv("OKX_PASSPHRASE","").strip()

LOG=[]

def bot_loop():
    while True:
        try:
            ex = ccxt.okx({
                'apiKey': API_KEY,
                'secret': SECRET,
                'password': PASSPHRASE,
                'enableRateLimit': True,
            })
            bal = ex.fetch_balance()
            usdt = bal.get('USDT',{}).get('free',0)
            LOG.append(f"✅ Balance OK USDT {usdt}")
            ticker = ex.fetch_ticker('BTC/USDT')
            LOG.append(f"BTC {ticker['last']}")
        except Exception as e:
            LOG.append(f"Error {str(e)[:200]}")
        time.sleep(20)

threading.Thread(target=bot_loop, daemon=True).start()

@app.route("/")
def home():
    logs="<br>".join(LOG[-15:])
    return f"<h1>✅ V31 SPOT - CCXT</h1><p>API: {API_KEY[:8]}..</p><p>{logs}</p>"

if __name__=="__main__":
    app.run(host="0.0.0.0", port=10000)
