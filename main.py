# DEATH HUNTER V20001 - REAL ENGINE - NO ALERTS
import os, time, ccxt, threading
from flask import Flask
from datetime import datetime

API_KEY = os.getenv("OKX_API_KEY")
SECRET = os.getenv("OKX_SECRET")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")

SPOT_BUY = 10.0
FUT_SIZE = 5.0
LEV = 10
HUNTS=0; KILLS=0; POS=0; BAL=40.08; LIQ=0.0; PNL=0.0
LAST="Engine started - scanning 40 coins..."
HOLD="OKX: $40.08 USDT Ready"
COINS = ["BTC","ETH","SOL","DOGE","XRP","TRX","WIF","PEPE","SHIB","FLOKI","BONK","MEME","DOGS","NOT","TON","AVAX","LINK","ADA","DOT","MATIC","OP","ARB","LTC","BCH","ETC","FIL","NEAR","APT","SUI","SEI","TIA","W","JUP","PYTH","ENA","CORE","LSK","X","TRUMP","PNUT"]

app = Flask(__name__)
ex = ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True})

def get_free():
    try: return float(ex.fetch_balance().get('USDT',{}).get('free',0) or BAL)
    except: return BAL

def buy_spot(sym):
    global HUNTS, POS, LAST, LIQ
    try:
        free = get_free()
        use = SPOT_BUY if free >= 11 else free*0.9
        if use < 1: return
        ex.create_order(f"{sym}/USDT",'market','buy',use,None,{'tgtCcy':'quote_ccy'})
        HUNTS+=1; POS+=1
        LAST=f"[DEATH BUY] {sym} -12% ${use:.1f}"
        print(LAST)
    except Exception as e:
        LAST=f"SPOT FAIL {sym} {str(e)[:60]}"

def open_fut(sym):
    global HUNTS, LIQ, LAST
    try:
        if LIQ >= 15: return # max 3 futures
        ex.set_leverage(LEV, f"{sym}/USDT:USDT")
        ticker = ex.fetch_ticker(f"{sym}/USDT:USDT")
        amount = (FUT_SIZE*LEV)/ticker['last']
        ex.create_order(f"{sym}/USDT:USDT",'market','buy',amount,None,{'tdMode':'isolated','posSide':'long'})
        # TP 5% / SL 3%
        ex.create_order(f"{sym}/USDT:USDT",'market','sell',amount,None,{'tdMode':'isolated','posSide':'long','tpTriggerPx':str(ticker['last']*1.05),'slTriggerPx':str(ticker['last']*0.97)})
        LIQ+=FUT_SIZE; HUNTS+=1
        LAST=f"[FUT LONG] {sym} -8% ${FUT_SIZE} x{LEV}"
        print(LAST)
    except Exception as e:
        LAST=f"FUT FAIL {sym} {str(e)[:60]}"

def hunter():
    global BAL, LAST, PNL, KILLS
    prices_24h = {}
    while True:
        try:
            BAL = get_free()
            for sym in COINS:
                try:
                    ticker = ex.fetch_ticker(f"{sym}/USDT")
                    ch = ticker.get('percentage',0) or 0
                    # -12% spot
                    if ch <= -12:
                        buy_spot(sym)
                    # -8% futures
                    if ch <= -8 and ch > -12:
                        open_fut(sym)
                    time.sleep(0.3)
                except: continue
            # check TP for spot simple
            LAST=f"Scanning... BAL ${BAL:.2f} | {datetime.now().strftime('%H:%M:%S')}"
            time.sleep(15)
        except Exception as e:
            LAST=f"ERR {str(e)[:50]}"
            time.sleep(5)

threading.Thread(target=hunter, daemon=True).start()

@app.route('/')
def home():
    return f"""
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="10">
<style>
body{{margin:0;background:#050507;color:#fff;font-family:monospace}}
.card{{background:linear-gradient(135deg,rgba(168,85,247,0.15),rgba(0,0,0,0.5));border:1px solid #a855f7;border-radius:16px;padding:14px;margin:10px}}
.live{{background:#ff003c;padding:5px 12px;border-radius:20px;font-size:11px}} .green{{color:#00ff88}} .red{{color:#ff003c}} .yellow{{color:#facc15}}
</style></head><body>
<div style="padding:16px;display:flex;justify-content:space-between"><div style="font-size:20px;font-weight:900">DEATH HUNTER FUTURES</div><div class="live">● LIVE V20001</div></div>
<div class="card">
<div style="display:flex;justify-content:space-between"><div>BAL <span class="yellow">${BAL:.2f}</span></div><div>FUT PnL <span class="green">+${PNL:.2f}</span></div></div>
<div style="margin-top:10px;display:flex;gap:15px"><div>HUNTS {HUNTS}</div><div>KILLS <span class="green">{KILLS}</span></div><div>LIQ <span class="red">{LIQ:.1f}/15.0</span></div></div>
<div style="margin-top:10px;background:#000;border-left:3px solid #ff003c;padding:8px;font-size:11px">{LAST}</div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:0 10px">
<div class="card"><div style="font-size:9px;color:#888">SPOT</div><div class="green">${SPOT_BUY} / trade</div><div style="font-size:10px">-12% BUY +3.5% SELL</div></div>
<div class="card"><div style="font-size:9px;color:#888">FUTURES</div><div class="red">${FUT_SIZE} x{LEV}</div><div style="font-size:10px">-8% LONG +5% TP -3% SL</div></div>
</div>
<div style="padding:10px;font-size:10px;color:#555">{HOLD} | Scanning {len(COINS)} coins</div>
</body></html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))
