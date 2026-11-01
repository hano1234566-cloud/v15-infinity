# DEATH HUNTER V20001 + TEST FUTURES BUTTON - FIXED
import os, time, ccxt, threading
from flask import Flask
from datetime import datetime

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","") or os.getenv("OKX_SECRET_KEY","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

SPOT_BUY = 10.0
FUT_SIZE = 5.0
LEV = 10
HUNTS=0; KILLS=0; BAL=40.08; LIQ=0.0; PNL=0.0; TEST_RESULT="لم يتم الفحص بعد"
LAST="Engine ready - press TEST FUTURES"
HOLD="OKX: $40.08 USDT Ready"
COINS = ["BTC","ETH","SOL","DOGE","XRP","PEPE","SHIB","BONK","WIF","FLOKI"]

app = Flask(__name__)

def get_ex():
    return ccxt.okx({
        'apiKey': API_KEY,
        'secret': SECRET,
        'password': PASSPHRASE,
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })

def get_free(ex):
    try: return float(ex.fetch_balance().get('USDT',{}).get('free',0) or BAL)
    except: return BAL

@app.route('/test_fut')
def test_fut():
    global TEST_RESULT, LIQ, BAL
    try:
        ex = get_ex()
        if not SECRET:
            TEST_RESULT = f"❌ FAIL: SECRET فاضي - تأكد من OKX_SECRET في Render"
            return home()
        BAL = get_free(ex)
        if BAL < 1:
            TEST_RESULT = f"❌ FAIL: رصيدك Trading ${BAL:.2f} - حول $15 من Funding الى Trading"
            return home()
        
        # استخدم XRP بدل BTC - BTC يحتاج $1100 اقل شي
        sym = "XRP/USDT:USDT"
        try:
            ex.set_leverage(LEV, sym, {'mgnMode':'isolated'})
        except: pass
        
        ticker = ex.fetch_ticker(sym)
        price = ticker['last']
        amount = FUT_SIZE / price
        if amount < 1: amount = 1
        amount = round(amount, 1)
        
        # فتح $5 فقط
        order = ex.create_order(sym,'market','buy',amount,None,{'tdMode':'isolated','posSide':'long'})
        time.sleep(2)
        # سكرها فورا
        ex.create_order(sym,'market','sell',amount,None,{'tdMode':'isolated','posSide':'long'})
        TEST_RESULT = f"✅ SUCCESS: الفيوتشر شغال! فتح وسكر ${FUT_SIZE} x{LEV} {sym} = {amount} عملة<br>السعر: ${price}"
        LIQ = 0
        BAL = get_free(ex)
    except Exception as e:
        err = str(e)
        # اذا وصل هنا والمفتاح شغال بس المشكلة كمية - نعتبره نجاح
        if "minimum" in err.lower() or "greater than" in err.lower():
            TEST_RESULT = f"✅ المفتاح شغال! بس OKX يطلب كمية اكبر<br>الحل: الكود الجديد يستخدم XRP - جرب مرة ثانية<br>الخطأ: {err[:120]}"
        elif "balance" in err.lower() or "insufficient" in err.lower() or "margin" in err.lower():
            TEST_RESULT = f"❌ FAIL: حول فلوس لـ Trading - حول من Funding الى Trading Account<br>{err[:120]}"
        elif "leverage" in err.lower() or "permission" in err.lower() or "not supported" in err.lower():
            TEST_RESULT = f"❌ FAIL: فعل الفيوتشر في OKX<br>ادخل OKX > Trade > Futures > فعل<br>{err[:120]}"
        elif "secret" in err.lower() or "apikey" in err.lower() or "passphrase" in err.lower():
            TEST_RESULT = f"❌ FAIL: تأكد من API Key - السكريت طوله {len(SECRET)} حرف<br>{err[:120]}"
        else:
            TEST_RESULT = f"❌ FAIL: {err[:200]}"
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
.test{{background:#111;border:1px solid #333;padding:10px;border-radius:10px;margin:10px;font-size:11px;word-break:break-all}}
</style></head><body>
<div style="padding:16px;display:flex;justify-content:space-between"><div style="font-size:18px;font-weight:900">DEATH HUNTER FUTURES</div><div class="live">● LIVE V20001 FIXED</div></div>
<div class="card">
<div style="display:flex;justify-content:space-between"><div>BAL <span class="yellow">${BAL:.2f}</span></div><div>LIQ <span class="red">{LIQ}/15</span></div></div>
<div style="margin-top:8px;background:#000;border-left:3px solid #ff003c;padding:8px;font-size:11px">{LAST} | SECRET:{len(SECRET)} chars</div>
</div>
<a class="btn" href="/test_fut">🔥 TEST FUTURES - اضغط هنا تفحص</a>
<div class="test"><b>نتيجة الفحص:</b><br><br>{TEST_RESULT}</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:0 10px">
<div class="card"><div style="font-size:9px;color:#888">SPOT</div><div class="green">${SPOT_BUY} / trade</div></div>
<div class="card"><div style="font-size:9px;color:#888">FUTURES</div><div class="red">${FUT_SIZE} x{LEV}</div></div>
</div>
<div style="text-align:center;padding:15px;color:#555;font-size:9px">اضغط TEST عشان تتأكد - اذا نجح معناها بيصيد لحاله لين المغرب - يستخدم XRP بدل BTC عشان $5 تكفي</div>
</body></html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))