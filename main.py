import os, time, threading
from flask import Flask, render_template_string
import okx.Account as Account
import okx.Trade as Trade
import okx.MarketData as Market

app = Flask(__name__)

API_KEY = os.getenv("OKX_API_KEY")
SECRET = os.getenv("OKX_SECRET")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")
FLAG = "0"  # 0=حقيقي

GEN = 216
IQ = 568
ACTIVE_TRADES = []
HISTORY = ["V26 REAL ACTIVATED - REAL MONEY MODE"]
BALANCE = 19.49

account_api = Account.AccountAPI(API_KEY, SECRET, PASSPHRASE, False, FLAG)
trade_api = Trade.TradeAPI(API_KEY, SECRET, PASSPHRASE, False, FLAG)
market_api = Market.MarketAPI(API_KEY, SECRET, PASSPHRASE, False, FLAG)

def get_price(inst):
    try:
        r = market_api.get_ticker(instId=inst)
        return float(r['data'][0]['last'])
    except: return None

def buy_real(inst, usd=5):
    try:
        price = get_price(inst)
        if not price: return False
        sz = str(round(usd/price, 2))  # كمية DOGE
        # أمر سوق حقيقي
        order = trade_api.place_order(instId=inst, tdMode="cash", side="buy", ordType="market", sz=sz)
        HISTORY.append(f"REAL BUY {inst} {sz} @ {price} | {order['data'][0]['sMsg']}")
        ACTIVE_TRADES.append({"coin":inst,"buy_price":price,"size":usd,"highest":price,"pnl":0,"sz":sz})
        return True
    except Exception as e:
        HISTORY.append(f"BUY FAIL {inst}: {e}")
        return False

def sell_real(trade):
    try:
        order = trade_api.place_order(instId=trade['coin'], tdMode="cash", side="sell", ordType="market", sz=trade['sz'])
        HISTORY.append(f"REAL SELL {trade['coin']} PnL {trade['pnl']:.2f}% | {order['data'][0]['sMsg']}")
        ACTIVE_TRADES.remove(trade)
        return True
    except Exception as e:
        HISTORY.append(f"SELL FAIL {e}")
        return False

def auto_trader():
    global GEN, IQ
    while True:
        try:
            # 1. ادارة الصفقات المفتوحة
            for t in ACTIVE_TRADES[:]:
                price = get_price(t['coin'])
                if not price: continue
                t['highest'] = max(t['highest'], price)
                t['pnl'] = ((price - t['buy_price'])/t['buy_price'])*100
                trailing = ((t['highest'] - price)/t['highest'])*100
                if t['pnl'] <= -1.2 or (t['pnl'] >= 2.8 and trailing >= 1.0):
                    sell_real(t)
                    GEN+=1; IQ+=1
            
            # 2. دخول جديد اذا ما فيه صفقات
            if len(ACTIVE_TRADES) < 1:
                # يختار عملة فيها سيولة عالية
                for inst in ["DOGE-USDT","PEPE-USDT","SHIB-USDT","BTC-USDT"]:
                    price = get_price(inst)
                    if price:
                        buy_real(inst, 5)
                        GEN+=1; IQ+=1
                        break
            time.sleep(15)
        except Exception as e:
            HISTORY.append(f"ERR {e}")
            time.sleep(10)

threading.Thread(target=auto_trader, daemon=True).start()

HTML = """
<!DOCTYPE html><html dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V26 REAL</title><style>
body{background:#0a0a0f;color:#fff;font-family:system-ui;margin:0;padding:15px}
.card{background:#15151f;border-radius:16px;padding:15px;margin-bottom:12px;border:1px solid #222}
.green{color:#00ff88} .red{color:#ff3b3b} .yellow{color:#ffcc00}
.big{font-size:28px;font-weight:800}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.badge{padding:4px 10px;border-radius:20px;font-size:12px;background:#222}
</style><meta http-equiv="refresh" content="5"></head><body>
<h2>🔴 V26 REAL MONEY <span style="background:red;padding:4px 10px;border-radius:20px">حقيقي</span></h2>
<div class="grid">
<div class="card"><div>الجيل</div><div class="big yellow">GEN {{GEN}}</div></div>
<div class="card"><div>الذكاء</div><div class="big green">IQ {{IQ}}</div></div>
<div class="card"><div>صفقات</div><div class="big">{{trades|length}} مفتوحة</div></div>
<div class="card"><div>الوضع</div><div class="big red">● حقيقي</div></div>
</div>
<div class="card"><h3>📈 صفقات حقيقية في OKX</h3>
{% for t in trades %}
<div style="background:#1f1f2e;padding:12px;border-radius:12px;margin-top:8px;border-right:4px solid {{'green' if t.pnl>0 else 'red'}}">
<b>{{t.coin}}</b> | دخول {{t.buy_price}} | <b class="{{'green' if t.pnl>0 else 'red'}}">{{"%.2f"|format(t.pnl)}}%</b>
<br><small>حجم ${{t.size}} | كمية {{t.sz}}</small>
</div>
{% else %}
<div>لا يوجد صفقات - سيشتري خلال 15 ثانية...</div>
{% endfor %}
</div>
<div class="card"><h3>📜 سجل الأوامر الحقيقية</h3>
{% for h in history[::-1][:10] %}<div style="font-size:12px;padding:4px 0;border-bottom:1px solid #222">{{h}}</div>{% endfor %}
</div>
<div class="card" style="text-align:center;color:#ff3b3b">⚠️ هذا تداول حقيقي بفلوسك - SL -1.2% | TP 2.8%</div>
</body></html>
"""

@app.route("/")
def index():
    return render_template_string(HTML, GEN=GEN, IQ=IQ, trades=ACTIVE_TRADES, history=HISTORY)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
