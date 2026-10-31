import ccxt, time, threading, os, json, random
from flask import Flask
from datetime import datetime

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")
app = Flask(__name__)

BRAIN_FILE = "singularity.json"
TRADES = []

if os.path.exists(BRAIN_FILE):
    with open(BRAIN_FILE, 'r') as f: BRAIN = json.load(f)
else:
    BRAIN = {"generation":0,"iq":100,"stage":"V23 LIVE"}

@app.route('/')
def home():
    trades_html = ""
    for t in TRADES[-5:]:
        trades_html += f"<div>{t}</div>"
    return f"""
    <h1>V23 INFINITY LIVE - FREE 24/7</h1>
    <p>IQ: {BRAIN.get('iq')} | Gen: {BRAIN.get('generation')}</p>
    <p>FREE MODE - No Card Needed</p>
    <hr>{trades_html}
    """

def trading_loop():
    print("=== V23 REAL LIVE FREE | STARTED ===", flush=True)
    exchange = ccxt.binance({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'enableRateLimit': True,
    })
    while True:
        try:
            balance = exchange.fetch_balance()
            free_usdt = balance['USDT']['free'] if 'USDT' in balance else 0
            print(f"FREE USDT: {free_usdt} | IQ: {BRAIN.get('iq')}", flush=True)
            time.sleep(60)
        except Exception as e:
            print(f"Bot Error: {e}", flush=True)
            time.sleep(30)

threading.Thread(target=trading_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
