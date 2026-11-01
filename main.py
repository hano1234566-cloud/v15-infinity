import os
from flask import Flask

BAL=9.69
LAST="🚨 EMERGENCY STOP - تم ايقاف الصيد - WR 24% خطر - حافظ على الباقي"
app = Flask(__name__)

@app.route('/close')
def close():
    return "STOPPED"

@app.route('/')
def home():
    return f"""
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{margin:0;background:#000;color:#fff;font-family:monospace}}
.card{{background:#111;border:2px solid #ff003c;border-radius:16px;padding:20px;margin:15px;text-align:center}}
</style></head><body>
<div style="padding:16px;background:#ff003c;text-align:center;font-weight:900">🚨 STOPPED - V20012 موقف</div>
<div class="card">
<div style="font-size:50px">🛑</div>
<div style="color:#ff003c;font-size:18px;font-weight:900">البوت موقف نهائي</div>
<div style="margin:15px;color:#888">BAL ${BAL}<br>W/L 4/13 WR 24%<br>T 16 صفقة - Overtrading</div>
<div style="background:#000;padding:10px;border-radius:8px;font-size:12px">{LAST}</div>
<div style="margin-top:20px;font-size:11px;color:#555">لا تخليه يصيد لحاله<br>5 عملات كثير على $20<br>لازم نرجع لعملة وحدة واستراتيجية هادئة</div>
</div>
</body></html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))
