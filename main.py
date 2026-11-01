# DEATH HUNTER V20001 + TEST FUTURES BUTTON
import os, time, ccxt, threading
from flask import Flask
from datetime import datetime

API_KEY = os.getenv("OKX_API_KEY")
SECRET = os.getenv("OKX_SECRET")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")

SPOT_BUY = 10.0
FUT_SIZE = 5.0
LEV = 10
HUNTS=0; KILLS=0; BAL=40.08; LIQ=0.0; PNL=0.0; TEST_RESULT="لم يتم الفحص بعد"
LAST="Engine ready - press TEST FUTURES"
HOLD="OKX: $40.08 USDT Ready"
COINS = ["BTC","ETH","SOL","DOGE","XRP","PEPE","SHIB","BONK","WIF","FLOKI"]

app = Flask(__name__)
ex = ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True})

def get_free():
    try: return float(ex.fetch_balance().get('USDT',{}).get('free',0) or BAL)
    except: return BAL

@app.route('/test_fut')
def test_fut():
    global TEST_RESULT, LIQ, BAL
    try:
        BAL = get_free()
        if BAL < 6:
            TEST_RESULT = f"❌ FAIL: رصيدك Trading ${BAL:.2f} - حول $15 من Funding"
            return home()
        # جرب افتح $1 فقط
        sym = "BTC/USDT:USDT"
        ex.set_leverage(LEV, sym)
        ticker = ex.fetch_ticker("BTC/USDT:USDT")
        amount = (1.0*LEV)/ticker['last']  # $1 margin
        order = ex.create_order(sym,'market','buy',amount,None,{'tdMode':'isolated','posSide':'long'})
        # سكرها فورا
        time.sleep(1)
        ex.create_order(sym,'market','sell',amount,None,{'tdMode':'isolated','posSide':'long'})
        TEST_RESULT = f"✅ SUCCESS: الفيوتشر شغال! فتح وسكر $1 x{LEV} BTC"
        LIQ = 0
    except Exception as e:
        err = str(e)[:200]
        if "balance" in err.lower() or "insufficient" in err.lower():
            TEST_RESULT = f"❌ FAIL: حول فلوس لـ Trading Account - {err[:80]}"
        elif "leverage" in err.lower() or "permission" in err.lower() or "not supported" in err.lower():
            TEST_RESULT = f"❌ FAIL: فعل الفيوتشر في OKX - ادخل OKX وفعل Futures Trading"
        else:
            TEST_RESULT = f"❌ FAIL: {err}"
    return home()

@app.route('/')
def home():
    return f"""
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="15">
<style>
body{{margin:0;background:#050507;color:#fff;font-family:monospace}}
.card{{background:linear-gradient(135deg,rgba(168,85,247,0.15),rgba(0,0,0,0.5));border:1px solid #a855f7;border-radius:16px;padding:14px;margin:10px}}
.live{{background:#ff003c;padding:5px 12px;border-radius:20px;font-size:11px}} .green{{color:#00ff88}} .red{{color:#ff003c}} .yellow{{color:#facc15}}
.btn{{display:block;background:linear-gradient(90deg,#a855f7,#ff003c);color:#fff;text-align:center;padding:14px;border-radius:12px;text-decoration:none;font-weight:900;margin:10px;font-size:14px}}
.test{{background:#111;border:1px solid #333;padding:10px;border-radius:10px;margin:10px;font-size:11px}}
</style></head><body>
<div style="padding:16px;display:flex;justify-content:space-between"><div style="font-size:18px;font-weight:900">DEATH HUNTER FUTURES</div><div class="live">● LIVE V20001</div></div>
<div class="card">
<div style="display:flex;justify-content:space-between"><div>BAL <span class="yellow">${BAL:.2f}</span></div><div>LIQ <span class="red">{LIQ}/15</span></div></div>
<div style="margin-top:8px;background:#000;border-left:3px solid #ff003c;padding:8px;font-size:11px">{LAST}</div>
</div>
<a class="btn" href="/test_fut">🔥 TEST FUTURES - اضغط هنا تفحص</a>
<div class="test"><b>نتيجة الفحص:</b><br><br>{TEST_RESULT}</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:0 10px">
<div class="card"><div style="font-size:9px;color:#888">SPOT</div><div class="green">${SPOT_BUY} / trade</div></div>
<div class="card"><div style="font-size:9px;color:#888">FUTURES</div><div class="red">${FUT_SIZE} x{LEV}</div></div>
</div>
<div style="text-align:center;padding:15px;color:#555;font-size:9px">اضغط TEST عشان تتأكد - اذا نجح معناها بيصيد لحاله لين المغرب</div>
</body></html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))
