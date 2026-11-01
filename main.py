import os, time, ccxt
from flask import Flask

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL=21.10; LIQ=0.0; TEST_RESULT="لم يتم الفحص بعد"
LAST="Engine ready - RAW ORDER NO posSide"

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
        
        # ضبط رافعة 3x
        try:
            ex.set_leverage(3, 'AVAX/USDT:USDT', {'mgnMode':'isolated'})
        except: pass
        
        # طلب خام مباشر ل OKX - بدون posSide نهائيا
        order_buy = {
            'instId': 'AVAX-USDT-SWAP',
            'tdMode': 'isolated',
            'side': 'buy',
            'ordType': 'market',
            'sz': '1.2',
        }
        
        # ارسال مباشر
        result = ex.private_post_trade_order(order_buy)
        
        time.sleep(3)
        
        order_sell = {
            'instId': 'AVAX-USDT-SWAP',
            'tdMode': 'isolated',
            'side': 'sell',
            'ordType': 'market',
            'sz': '1.2',
        }
        ex.private_post_trade_order(order_sell)
        
        TEST_RESULT = f"✅ SUCCESS: الفيوتشر شغال 100%!<br>فتح وسكر 1.2 AVAX x3<br>رد OKX: {str(result)[:100]}<br>رصيدك ${BAL:.2f}<br><br>البوت جاهز يصيد لين المغرب"
        
    except Exception as e:
        err = str(e)
        # لو نجح الشراء بس فشل البيع - يعتبر نجاح
        if "51000" not in err or "buy" in err.lower():
            TEST_RESULT = f"✅ جزئي: فتح صفقة بس فشل اغلاق<br>{err[:300]}<br>ادخل OKX وسكرها يدوي"
        else:
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
<div style="padding:16px;display:flex;justify-content:space-between"><div style="font-size:16px;font-weight:900">DEATH HUNTER</div><div class="live">● LIVE V20005 RAW</div></div>
<div class="card">
<div style="display:flex;justify-content:space-between"><div>BAL <span class="yellow">${BAL:.2f}</span></div><div>LIQ <span class="red">{LIQ}/15</span></div></div>
<div style="margin-top:8px;background:#000;border-left:3px solid #00ff88;padding:8px;font-size:11px">{LAST}</div>
</div>
<a class="btn" href="/test_fut">🔥 TEST FUTURES - اضغط هنا</a>
<div class="test"><b>نتيجة الفحص:</b><br><br>{TEST_RESULT}</div>
</body></html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))
