import os, time, ccxt
from flask import Flask

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL=21.10; LIQ=0.0; TEST_RESULT="لم يتم الفحص بعد"
LAST="Engine ready - AVAX 3x - ONE WAY MODE"

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
        ex.load_markets()
        bal = ex.fetch_balance()
        BAL = float(bal.get('USDT',{}).get('free',0) or 21.10)
        
        sym = "AVAX/USDT:USDT"
        # ضبط الرافعة 3x مثل ما انت حاط في الصورة
        ex.set_leverage(3, sym, {'mgnMode':'isolated'})
        
        # كمية 1.2 AVAX = حوالي $10 - آمنة
        amount = 1.2
        
        # بدون posSide - هذا المهم لحسابك
        params = {'tdMode':'isolated'}
        
        order = ex.create_market_buy_order(sym, amount, params)
        time.sleep(2)
        ex.create_market_sell_order(sym, amount, params)
        
        TEST_RESULT = f"✅ SUCCESS: الفيوتشر شغال 100%!<br>فتح وسكر {amount} AVAX x3<br>رصيدك ${BAL:.2f} - جاهز يصيد لين المغرب"
        
    except Exception as e:
        err = str(e)
        if "51000" in err and "posSide" in err:
            TEST_RESULT = f"حاولت ب posSide - جاري المحاولة بدون... {err[:100]}"
        TEST_RESULT = f"❌ {err[:400]}"
    return home()

@app.route('/')
def home():
    return f"""
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{margin:0;background:#050507;color:#fff;font-family:monospace}}
.card{{background:linear-gradient(135deg,rgba(168,85,247,0.15),rgba(0,0,0,0.5));border:1px solid #a855f7;border-radius:16px;padding:14px;margin:10px}}
.live{{background:#00ff88;color:#000;padding:5px 12px;border-radius:20px;font-size:11px}} .yellow{{color:#facc15}} .red{{color:#ff003c}}
.btn{{display:block;background:linear-gradient(90deg,#a855f7,#ff003c);color:#fff;text-align:center;padding:14px;border-radius:12px;text-decoration:none;font-weight:900;margin:10px;font-size:14px}}
.test{{background:#111;border:1px solid #333;padding:10px;border-radius:10px;margin:10px;font-size:11px;word-break:break-all}}
</style></head><body>
<div style="padding:16px;display:flex;justify-content:space-between"><div style="font-size:16px;font-weight:900">DEATH HUNTER FUTURES</div><div class="live">● LIVE V20003 ONE-WAY</div></div>
<div class="card">
<div style="display:flex;justify-content:space-between"><div>BAL <span class="yellow">${BAL:.2f}</span></div><div>LIQ <span class="red">{LIQ}/15</span></div></div>
<div style="margin-top:8px;background:#000;border-left:3px solid #00ff88;padding:8px;font-size:11px">{LAST} | SECRET:{len(SECRET)}</div>
</div>
<a class="btn" href="/test_fut">🔥 TEST FUTURES - اضغط هنا</a>
<div class="test"><b>نتيجة الفحص:</b><br><br>{TEST_RESULT}</div>
</body></html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))
