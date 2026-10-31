import os, time, threading
from flask import Flask
import okx.Account as Account
import okx.Trade as Trade
import okx.MarketData as Market

app=Flask(__name__)
API_KEY=os.getenv("OKX_API_KEY")
SECRET=os.getenv("OKX_SECRET_KEY")
PASSPHRASE=os.getenv("OKX_PASSPHRASE")
flag="0"  # Live

acct=Account.AccountAPI(API_KEY, SECRET, PASSPHRASE, False, flag)
trade=Trade.TradeAPI(API_KEY, SECRET, PASSPHRASE, False, flag)
market=Market.MarketAPI(flag=flag)

SPOT=["PEPE-USDT","SHIB-USDT","DOGE-USDT"]
LOG=[]; PROFIT=0.0

def price(inst):
    try:
        r=market.get_ticker(instId=inst)
        return float(r['data'][0]['last'])
    except:
        return 0

def bot_loop():
    global PROFIT
    while True:
        try:
            bal=acct.get_account_balance()
            LOG.append(f"Balance OK {bal['code']}")
            # هنا تداول سبوت فقط - بدون فيوتشر
            for inst in SPOT:
                p=price(inst)
                LOG.append(f"SPOT {inst} {p}")
        except Exception as e:
            LOG.append(f"Error {e}")
        time.sleep(30)

threading.Thread(target=bot_loop, daemon=True).start()

@app.route("/")
def home():
    logs="<br>".join(LOG[-20:])
    return f"<h1>✅ V31 SPOT ONLY شغال</h1><p>API: {API_KEY[:8]}..</p><p>{logs}</p>"

if __name__=="__main__":
    app.run(host="0.0.0.0", port=10000)
