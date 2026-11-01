import os, time, ccxt
from flask import Flask

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

SPOT_BUY = 10.0
FUT_SIZE = 10.0  # زدنا لـ $10 عشان يعدي الحد الادنى
LEV = 3  # مثل ما انت مسوي يدوي 3x
BAL=21.10; LIQ=0.0; TEST_RESULT="لم يتم الفحص بعد"
LAST="Engine ready - press TEST FUTURES"

app = Flask(__name__)

def get_ex():
    return ccxt.okx({
        'apiKey': API_KEY,
        'secret': SECRET,
        'password': PASSPHRASE,
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'},
    })

@app.route('/test_fut')
def test_fut():
    global TEST_RESULT, BAL
    try:
        ex = get_ex()
        bal = ex.fetch_balance()
        free = float(bal.get('USDT',{}).get('free',0) or 0)
        BAL = free
        
        # نستخدم AVAX مثل ما انت تتداول يدوي
        sym = "AVAX/USDT:USDT"
        ex.load_markets()
        ex.set_leverage(LEV, sym, {'mgnMode':'isolated'})
        
        ticker = ex.fetch_ticker(sym)
        price = ticker['last']
        
        # كمية آمنة - 1.5 AVAX = حوالي $13
        amount = 1.5
        
        # فتح
        order = ex.create_market_buy_order(sym, amount, {'tdMode':'isolated','posSide':'long'})
        time.sleep(2)
        # اغلاق فورا
        ex.create_market_sell_order(sym, amount, {'tdMode':'isolated','posSide':'long'})
        
        TEST_RESULT = f"✅ SUCCESS: الفيوتشر شغال 100%!<br>فتح وسكر {amount} AVAX x{LEV}<br>السعر ${price:.2f}<br>رصيدك ${free:.2f}"
        
    except Exception as e:
        err = str(e)
        # لو فشل بسبب الهيدج مود
        if "posSide" in err.lower() or "position" in err.lower():
            try:
                ex = get_ex()
                sym = "AVAX/USDT:USDT"
                amount = 1.5
                # جرب بدون posSide
                ex.create_market_buy_order(sym, amount, {'tdMode':'isolated'})
                time.sleep(2)
                ex.create_market_sell_order(sym, amount, {'tdMode':'isolated'})
                TEST_RESULT = f"✅ SUCCESS (بدون posSide): شغال!<br>رصيدك ${BAL:.2f}"
                return home()
            except Exception as e2:
                err = str(e2)
        TEST_RESULT = f"❌ {err[:300]}"
    return home()

@app.route('/')
def home():
    return f"""
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30">
<style>
body{{margin:0;background:#050507;color:#fff;font-family:monospace}}
.card{{background:linear-gradient(135deg,rgba(168,85,247,0.15),rgba(0,0,0,0.5));border:1px solid #a855f7;border-radius:16px;padding:14px;margin:10px}}
.live{{background:#ff003c;padding:5px 12px;border-radius:20px;font-size:11px}} .green{{color:#00ff88}} .red{{color:#ff003c}} .yellow{{color:#facc15}}
.btn{{display:block;background:linear-gradient(90deg,#a855f7,#ff003c);color:#fff;text-align:center;padding:14px;border-radius:12px;text-decoration:none;font-weight:900;margin:10px;font-size:14px}}
.test{{background:#111;border:1px solid #333;padding:10px;border-radius:10px;margin:10px;font-size:11px;word-break:break-all}}
</style></head><body>
<div style="padding:16px;display:flex;justify-content:space-between"><div style="font-size:18px;font-weight:900">DEATH HUNTER FUTURES</div><div class="live">● LIVE V20002 FIXED AVAX</div></div>
<div class="card">
<div style="display:flex;justify-content:space-between"><div>BAL <span class="yellow">${BAL:.2f}</span></div><div>LIQ <span class="red">{LIQ}/15</span></div></div>
<div style="margin-top:8px;background:#000;border-left:3px solid #ff003c;padding:8px;font-size:11px">{LAST} | SECRET:{len(SECRET)} chars | AVAX 3x</div>
</div>
<a class="btn" href="/test_fut">🔥 TEST FUTURES - اضغط هنا تفحص</a>
<div class="test"><b>نتيجة الفحص:</b><br><br>{TEST_RESULT}</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:0 10px">
<div class="card"><div style="font-size:9px;color:#888">SPOT</div><div class="green">${SPOT_BUY} / trade</div></div>
<div class="card"><div style="font-size:9px;color:#888">FUTURES</div><div class="red">${FUT_SIZE} x{LEV} AVAX</div></div>
</div>
</body></html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))
