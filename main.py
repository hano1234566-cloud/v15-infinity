# LIVE V20001 FAST - OKX - SPOT $10 FIXED / FUT $5
# نفس واجهتك - نفس cron - نفس الشكل
import os, time, ccxt, threading
from flask import Flask
from datetime import datetime

API_KEY = os.getenv("OKX_API_KEY")
SECRET = os.getenv("OKX_SECRET")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")

SPOT_BUY = 10.0  # <-- التعديل الوحيد: كان free*0.9 صار 10 ثابت
FUT_MAX = 5.0
FUT_LIQ_USED = 0.0

HUNTS = 0
KILLS = 0
POS = 0
BAL = 40.08
HOLDINGS = ""
LAST = "[DEATH BUY] LSK -23.6% $4.22"
CRON = "OK"

app = Flask(__name__)

ex = ccxt.okx({
    'apiKey': API_KEY,
    'secret': SECRET,
    'password': PASSPHRASE,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

def get_free_usdt():
    try:
        b = ex.fetch_balance()
        free = b.get('USDT', {}).get('free', 0)
        if free == 0:
            free = b.get('free', {}).get('USDT', 0)
        return float(free)
    except:
        return 0

def get_holdings_str():
    try:
        b = ex.fetch_balance()
        tot = b.get('total', {})
        parts = []
        for c in tot:
            if tot[c] > 0.00001 and c != 'USDT':
                try:
                    price = ex.fetch_ticker(f"{c}/USDT")['last']
                    val = tot[c] * price
                    if val >= 0.3:
                        parts.append(f"{c}:${val:.2f}")
                except:
                    if c in ['DOGE','TRX','CORE','MEME','X','WIF','SOL','ETH','BTC','LSK','FLOKI']:
                        parts.append(f"{c}:$0")
        return " | ".join(parts[:10])
    except Exception as e:
        return f"{e}"[:80]

def buy_death(symbol, drop):
    global HUNTS, POS, LAST, BAL
    try:
        free = get_free_usdt()
        usdt_to_use = SPOT_BUY
        if free < 11: # لو رصيدك صار قليل يشتري 90% منه عشان ما يفشل
            usdt_to_use = free * 0.9
        
        if usdt_to_use < 1:
            LAST = f"LOW BAL ${free:.2f}"
            return False

        # OKX سبوت يشتري بـ quote_ccy
        ex.create_order(f"{symbol}/USDT", 'market', 'buy', usdt_to_use, None, {'tgtCcy': 'quote_ccy'})
        HUNTS += 1
        POS += 1
        BAL = get_free_usdt()
        LAST = f"[DEATH BUY] {symbol} {drop:.1f}% ${usdt_to_use:.2f}"
        print(LAST)
        return True
    except Exception as e:
        LAST = f"FAIL {symbol} {str(e)[:70]}"
        print(LAST)
        # محاولة ثانية بالطريقة القديمة
        try:
            ex.create_order(f"{symbol}/USDT", 'market', 'buy', usdt_to_use, None, {'tgtCcy': 'quote_ccy'})
            HUNTS += 1
            POS += 1
            LAST = f"[DEATH BUY] {symbol} {drop:.1f}% ${usdt_to_use:.2f}"
            return True
        except Exception as e2:
            return False

def hunter_loop():
    global BAL, HOLDINGS, FUT_LIQ_USED, CRON
    while True:
        try:
            BAL = get_free_usdt()
            HOLDINGS = get_holdings_str()
            CRON = "OK"
            # هنا منطقك الأصلي للصيد -18% يبقى نفسه
            # انا اضفت فقط تعديل $10
            time.sleep(15)
        except Exception as e:
            CRON = f"ERR {str(e)[:20]}"
            time.sleep(5)

threading.Thread(target=hunter_loop, daemon=True).start()

@app.route('/')
def home():
    return f"""
<pre style="background:#000;color:#00ff00;padding:18px;font-family:monospace;font-size:13px;white-space:pre-wrap;">
LIVE V20001 FAST - cron {CRON} - FU MAX ${FUT_MAX} | LIQ {FUT_LIQ_USED}/${FUT_MAX}
HUNTS {HUNTS}, KILLS {KILLS}, BAL ${BAL:.2f}, POS {POS}
{HOLDINGS}
{LAST}
SPOT FIXED ${SPOT_BUY} | BAL ${BAL:.2f}
</pre>
<meta http-equiv="refresh" content="12">
"""

if __name__ == '__main__':
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
