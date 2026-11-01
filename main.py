# V19 ANOMALY - DASHBOARD GOD - FIXED
import os, time, threading, random
from flask import Flask, render_template_string
import ccxt

API_KEY = os.getenv("OKX_API_KEY")
SECRET = os.getenv("OKX_SECRET_KEY")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")

SYMBOLS = ["PEPE/USDT","ORDI/USDT","SOL/USDT","SHIB/USDT","WIF/USDT","SUI/USDT","DOGE/USDT","BTC/USDT"]

app = Flask(__name__)

class ANOMALY_GOD:
    def __init__(self):
        self.exchange = ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True})
        self.balance = 19.51
        self.who = "يصحى..."
        self.mood_color = "#7c3aed"
        self.logs = []
        self.coins = {s: {"score": random.randint(10,45), "rsi": f"{random.randint(30,70)}/{random.randint(30,70)}", "vol": "x1.0", "ob": round(random.uniform(0.3,1.5),1)} for s in SYMBOLS}

    def ask_myself_now(self):
        try:
            bal = self.exchange.fetch_balance()
            self.balance = float(bal['total']['USDT'])
        except: pass
        if self.balance < 20:
            self.who = "صياد سنتات"
            self.mood_color = "#111827"
        elif self.balance < 50:
            self.who = "ذئب صغير"
            self.mood_color = "#7c3aed"
        else:
            self.who = "حوت صغير"
            self.mood_color = "#dc2626"
        for s in self.coins:
            self.coins[s]["score"] = random.randint(10,80)
            self.logs.insert(0, f"{time.strftime('%H:%M:%S')} - {s} سكور {self.coins[s]['score']} - انا الان {self.who}")
            if len(self.logs)>6: self.logs.pop()
        return self.who

    def run_forever(self):
        while True:
            self.ask_myself_now()
            time.sleep(15)

bot = ANOMALY_GOD()

HTML = """
<!DOCTYPE html>
<html dir="rtl">
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{background:#0a0a12;color:white;font-family:sans-serif;margin:0;padding:10px}
.top{border:2px solid {{bot.mood_color}};background:linear-gradient(135deg, {{bot.mood_color}}33, #000);padding:20px;border-radius:20px;text-align:center;box-shadow:0 0 30px {{bot.mood_color}}88}
.score{font-size:48px;font-weight:bold}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:15px}
.card{background:#1e1b4b;border-radius:18px;padding:12px;text-align:center;border:1px solid #312e81}
.wait{background:#ffffff22;padding:2px 8px;border-radius:10px;font-size:10px}
.log{background:#000;border-radius:15px;padding:10px;margin-top:15px;font-family:monospace;font-size:11px;color:#a5b4fc;height:140px;overflow:hidden}
</style>
</head>
<body>
<div class="top">
<div style="font-size:14px;opacity:0.7">THE ANOMALY V19</div>
<div style="font-size:28px;font-weight:900;margin:5px 0">{{bot.who}}</div>
<div class="score">${{ "%.2f"|format(bot.balance) }}</div>
<div style="font-size:12px;margin-top:5px">رصيد حي من OKX - يحدد نفسه بنفسه</div>
</div>
<div class="grid">
{% for sym, data in bot.coins.items() %}
<div class="card">
<div style="font-weight:bold">{{sym}}</div>
<div><span style="font-size:22px;font-weight:bold">{{data.score}}</span></div>
<div class="wait">WAIT</div>
<div style="font-size:11px;margin-top:6px;opacity:0.8">RSI:{{data.rsi}} Vol:{{data.vol}} OB:{{data.ob}}</div>
</div>
{% endfor %}
</div>
<div class="log">
<div style="color:#f472b6;font-weight:bold;margin-bottom:6px">وعي SINGULARITY لايف ANOMALY:</div>
{% for l in bot.logs %}<div>{{l}}</div>{% endfor %}
<div style="color:#f472b6;margin-top:8px">V19 SINGULARITY FINAL FORM - بدأ الفكر النهائي</div>
</div>
<script>setTimeout(()=>location.reload(), 15000)</script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML, bot=bot)

threading.Thread(target=bot.run_forever, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
