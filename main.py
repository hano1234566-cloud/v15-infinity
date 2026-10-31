import os, time, threading
from flask import Flask
import okx.Account as Account
import okx.MarketData as Market

app=Flask(__name__)
API_KEY=os.getenv("OKX_API_KEY","").strip()
SECRET=os.getenv("OKX_SECRET_KEY","").strip()
PASSPHRASE=os.getenv("OKX_PASSPHRASE","").strip()
flag="0"

acct=Account.AccountAPI(API_KEY, SECRET, PASSPHRASE, False, flag)
market=Market.MarketAPI(flag=flag)

LOG=[]

def bot_loop():
    while True:
        try:
            bal=acct.get_account_balance()
            if bal['code']=='0':
                LOG.append(f"✅ Balance OK {bal['data'][0]['totalEq']}")
            else:
                LOG.append(f"❌ {bal}")
            r=market.get_ticker(instId="BTC-USDT")
            LOG.append(f"BTC Price {r['data'][0]['last']}")
        except Exception as e:
            LOG.append(f"Error {e}")
        time.sleep(20)

threading.Thread(target=bot_loop, daemon=True).start()

@app.route("/")
def home():
    logs="<br>".join(LOG[-15:])
    return f"<h1>✅ V31 SPOT شغال</h1><p>API: {API_KEY[:8]}..</p><p>{logs}</p>"

if __name__=="__main__":
    app.run(host="0.0.0.0", port=10000)
