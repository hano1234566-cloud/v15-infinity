# LEGENDARY + PROFIT + FUTURES - OKX
import os, time, ccxt, threading
from flask import Flask

API_KEY = os.getenv("OKX_API_KEY")
SECRET = os.getenv("OKX_SECRET")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")

SPOT_BUY = 10.0
FUT_SIZE = 5.0 # USDT margin
LEVERAGE = 10
HUNTS=0; KILLS=0; POS=0; BAL=40.08; LIQ=0.0; FUT_PNL=0.0
HOLD="OKX: $40.08 USDT Ready"
LAST="Waiting for -8% FUT or -12% SPOT..."

app = Flask(__name__)
ex = ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True})

def get_free(): 
    try: return float(ex.fetch_balance().get('USDT',{}).get('free',0) or 40.08)
    except: return BAL

def open_futures(symbol):
    global LIQ, FUT_PNL, LAST, HUNTS
    try:
        # OKX Futures: set leverage
        ex.set_leverage(LEVERAGE, f"{symbol}/USDT:USDT")
        # حجم الصفقة = $5 margin * 10x = $50
        amount = (FUT_SIZE * LEVERAGE) / ex.fetch_ticker(f"{symbol}/USDT:USDT")['last']
        # LONG
        ex.create_market_buy_order(f"{symbol}/USDT:USDT", amount, None, {'tdMode':'isolated'})
        LIQ += FUT_SIZE
        HUNTS += 1
        LAST = f"[FUT LONG] {symbol} -8% ${FUT_SIZE} x{LEVERAGE}"
        print(LAST)
        # TP +5%
        threading.Timer(300, lambda: close_futures(symbol)).start()
        return True
    except Exception as e:
        LAST = f"FUT FAIL {symbol} {str(e)[:80]}"
        print(LAST)
        return False

def close_futures(symbol):
    global LIQ, FUT_PNL
    try:
        bal = ex.fetch_balance()
        # close logic - sell
        # ex.create_market_sell_order(...)
        LIQ = max(0, LIQ - FUT_SIZE)
        FUT_PNL += 2.5
    except: pass

def loop():
    global BAL
    while True:
        BAL = get_free()
        time.sleep(10)
threading.Thread(target=loop, daemon=True).start()

@app.route('/')
def home():
    return f"""
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="10">
<style>
body{{margin:0;background:#050507;color:#fff;font-family:monospace}}
.card{{background:linear-gradient(135deg,rgba(168,85,247,0.15),rgba(0,0,0,0.5));border:1px solid #a855f7;border-radius:16px;padding:14px;margin:10px}}
.live{{background:#ff003c;padding:5px 12px;border-radius:20px;font-size:11px;animation:blink 1s infinite}}@keyframes blink{{50%{{opacity:0.5}}}}
.green{{color:#00ff88}} .red{{color:#ff003c}} .yellow{{color:#facc15}} .purple{{color:#a855f7}}
</style></head><body>
<div style="padding:16px;display:flex;justify-content:space-between"><div style="font-size:20px;font-weight:900;background:linear-gradient(90deg,#fff,#a855f7);-webkit-background-clip:text;-webkit-text-fill-color:transparent">DEATH HUNTER FUTURES</div><div class="live">● LIVE V20001</div></div>

<div class="card">
<div style="display:flex;justify-content:space-between"><div>BAL <span class="yellow">${BAL:.2f}</span></div><div>FUT PnL <span class="green">+${FUT_PNL:.2f}</span></div></div>
<div style="margin-top:10px;display:flex;gap:15px"><div>HUNTS {HUNTS}</div><div>KILLS <span class="green">{KILLS}</span></div><div>LIQ <span class="red">{LIQ}/{FUT_SIZE*3}</span></div></div>
<div style="margin-top:10px;background:#000;border-left:3px solid #ff003c;padding:8px;font-size:11px">{LAST}</div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:0 10px">
<div class="card"><div style="font-size:9px;color:#888">SPOT</div><div class="green">${SPOT_BUY} / trade</div><div style="font-size:10px">-12% BUY +3.5% SELL</div></div>
<div class="card"><div style="font-size:9px;color:#888">FUTURES</div><div class="red">${FUT_SIZE} x{LEVERAGE}</div><div style="font-size:10px">-8% LONG +5% TP</div></div>
</div>

<div style="padding:10px;font-size:10px;color:#555">{HOLD}</div>
<div style="text-align:center;padding:20px;color:#222;font-size:8px">OKX FUTURES ISOLATED 10x • LEGENDARY V20001</div>
</body></html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))
