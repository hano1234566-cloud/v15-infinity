import ccxt, time, threading
from flask import Flask
from datetime import datetime

API_KEY = ""
API_SECRET = ""

app = Flask(__name__)
@app.route('/')
def home():
    return "V15 INFINITY RUNNING"

class V15Auto:
    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        self.portfolios = [
            {"id":1,"balance":4,"symbol":"BTC/USDT"},
            {"id":2,"balance":4,"symbol":"ETH/USDT"},
            {"id":3,"balance":4,"symbol":"SOL/USDT"},
            {"id":4,"balance":4,"symbol":"BNB/USDT"},
            {"id":5,"balance":4,"symbol":"AVAX/USDT"}
        ]

    def get_balance(self):
        try:
            bal = self.exchange.fetch_balance()
            return float(bal['USDT']['free'])
        except:
            return 20.0

    def run(self):
        while True:
            balance = self.get_balance()
            print(f"[{datetime.now()}] Balance: {balance}$ | Portfolios: {len(self.portfolios)} | Mode: INFINITY")
            time.sleep(60)

def run_web():
    app.run(host='0.0.0.0', port=10000)

def run_bot():
    bot = V15Auto()
    bot.run()

threading.Thread(target=run_web).start()
run_bot()
