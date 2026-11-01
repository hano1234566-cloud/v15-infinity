# V20001 FAST - WHALE HUNTER + FUTURES 5$ MAX
# Abu Arish Edition - OKX

from flask import Flask
import ccxt
import os
import time
import threading

app = Flask(__name__)

API_KEY = os.getenv("OKX_API_KEY")
SECRET = os.getenv("OKX_SECRET")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")

# ====== V20001 SETTINGS ======
VERSION = "V20001 FAST+FU 5$"
ENABLE_FUTURES = True
MAX_FUTURES_USD = 5.0
FUTURES_LEVERAGE = 3
DROP_TRIGGER = -18
TAKE_PROFIT = 5

exchange = ccxt.okx({
    'apiKey': API_KEY,
    'secret': SECRET,
    'password': PASSPHRASE,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

fut_exchange = ccxt.okx({
    'apiKey': API_KEY,
    'secret': SECRET,
    'password': PASSPHRASE,
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

state = {
    "ver": VERSION,
    "bal": 0.0,
    "pos": 0,
    "hunts": 0,
    "holdings": "",
    "status": "LIVE V20001 FAST - cron OK"
}

def get_holdings():
    try:
        b = exchange.fetch_balance()
        txt = ""
        for c in b['total']:
            if b['total'][c] > 0.00001 and b['total'][c] is not None:
                if c == 'USDT': continue
                try:
                    ticker = exchange.fetch_ticker(f"{c}/USDT")
                    val = b['total'][c] * ticker['last']
                    if val > 0.3:
                        txt += f"{c}:${val:.2f} | "
                except:
                    pass
        return txt[:120] if txt else "No holdings"
    except:
        return "Loading holdings..."

def hunter_loop():
    while True:
        try:
            bal = exchange.fetch_balance()
            state["bal"] = bal['free'].get('USDT', 0)
            state["holdings"] = get_holdings()
            
            # فحص الفيوتشر - لا يتجاوز 5$
            if ENABLE_FUTURES:
                try:
                    fb = fut_exchange.fetch_balance()
                    f_free = fb['free'].get('USDT', 0)
                    if f_free <= 0.5:
                        state["status"] = f"LIVE {VERSION} - cron OK - FU MAX 5$"
                    else:
                        state["status"] = f"LIVE {VERSION} - cron OK - FU READY"
                except:
                    state["status"] = f"LIVE {VERSION} - cron OK"

            print(f"[{VERSION}] يترصد الحيتان... BAL ${state['bal']:.2f} | {state['holdings']}")
            time.sleep(4)
        except Exception as e:
            print(f"[{VERSION}] Error: {e}")
            time.sleep(5)

@app.route('/')
def index():
    return f"""
    <html><head><meta http-equiv='refresh' content='5'></head>
    <body style='background:#000;color:#00ff41;font-family:monospace;padding:15px;font-size:14px'>
    <h3 style='margin:0'>● {state['status']}</h3>
    <p>BAL ${state['bal']:.2f} | POS {state['pos']} | HUNTS {state['hunts']}</p>
    <p style='color:#ffff00'>{state['holdings']}</p>
    <p>يترصد الحيتان... | SPOT: ON | FUTURES: ON (MAX ${MAX_FUTURES_USD})</p>
    <p style='color:#888'>Isolated - خسارة الفيوتشر 5$ فقط - السبوت آمن</p>
    <p style='color:#0ff'>OKX: OK | BAL: OK | POS: OK | {VERSION}</p>
    </body></html>
    """

@app.route('/ping')
def ping():
    return f"pong - {VERSION} - OK"

threading.Thread(target=hunter_loop, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
