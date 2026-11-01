# V1000 LEGENDARY - FINAL - ALL COINS REAL + DASHBOARD
import os, time, threading
from flask import Flask
import ccxt

API_KEY = os.getenv("OKX_API_KEY", "").strip()
SECRET = os.getenv("OKX_SECRET_KEY", "").strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE", "").strip()

app = Flask(__name__)
LOGS = []

def log(m, typ="info"):
    t = time.strftime("%H:%M:%S")
    msg = f"{t} {m}"
    LOGS.append(msg)
    if len(LOGS) > 400: LOGS.pop(0)
    print(msg, flush=True)

def make_client(typ):
    return ccxt.okx({
        'apiKey': API_KEY, 'secret': SECRET, 'password': PASSPHRASE,
        'enableRateLimit': True,
        'options': {'defaultType': typ}
    })

class V1000_Spot_All:
    def __init__(self):
        self.amount_usd = 1
        self.drop_needed = 5.0
        self.vol_needed = 1_000_000
        self.positions = 0
        self.max_positions = 2
        self.banned = {}
        self.last_scan = 0
        self.last_found = 0
    def run(self):
        ex = make_client('spot')
        log("[SPOT] 🚀 شغال - يفحص جميع عملات السبوت")
        while True:
            try:
                tickers = ex.fetch_tickers()
                self.last_scan = len(tickers)
                cands = []
                for sym, tk in tickers.items():
                    if '/USDT' in sym and ':' not in sym and 'UP/' not in sym and 'DOWN/' not in sym:
                        ch = tk.get('percentage') or 0
                        vol = tk.get('quoteVolume') or 0
                        last = tk.get('last') or 0
                        if ch <= -self.drop_needed and vol >= self.vol_needed and last > 0.001:
                            if sym not in self.banned:
                                cands.append((sym, ch, vol, last))
                cands.sort(key=lambda x: x[1])
                self.last_found = len(cands)
                
                if cands:
                    log(f"[SPOT] 🔍 {len(tickers)} عملة | {len(cands)} نازلة -5% | أقوى: {cands[0][0]} {cands[0][1]:.1f}%")
                else:
                    log(f"[SPOT] 🔍 {len(tickers)} عملة | لا يوجد -5% الآن")

                if cands and self.positions < self.max_positions:
                    sym, ch, vol, last = cands[0]
                    # شيك الرصيد قبل الشراء
                    bal = ex.fetch_balance()
                    usdt = bal.get('USDT',{}).get('free',0)
                    if usdt < 0.9:
                        log(f"[SPOT] ⚠️ رصيدك ناقص ${usdt:.2f} - اشحن USDT في Funding", "warn")
                    else:
                        qty = self.amount_usd / last
                        try:
                            ex.create_market_buy_order(sym, qty)
                            log(f"[SPOT REAL] ✅ اشتريت {sym} {ch:.1f}% بـ 1$ عند {last}", "ok")
                            self.positions += 1
                            self.banned[sym] = time.time() + 3600
                            threading.Timer(3600, lambda: setattr(self, 'positions', max(0, self.positions-1))).start()
                        except Exception as e:
                            if "insufficient" in str(e).lower():
                                log(f"[SPOT] ❌ رصيد ناقص - اشحن USDT", "err")
                            else:
                                log(f"[SPOT ERR] {sym} {str(e)[:100]}", "err")
                
                now = time.time()
                for k in list(self.banned.keys()):
                    if self.banned[k] < now: del self.banned[k]
                time.sleep(15)
            except Exception as e:
                log(f"[SPOT ERR] {str(e)[:120]}", "err"); time.sleep(10)

class V1000_Future_All:
    def __init__(self):
        self.amount_usd = 1
        self.drop_needed = 5.0
        self.vol_needed = 5_000_000
        self.positions = 0
        self.max_positions = 1
        self.banned = {}
        self.last_scan = 0
        self.last_found = 0
    def run(self):
        ex = make_client('swap')
        log("[FUTURE] 🚀 شغال - يفحص جميع عملات الفيوتشر")
        while True:
            try:
                tickers = ex.fetch_tickers()
                self.last_scan = len(tickers)
                cands = []
                for sym, tk in tickers.items():
                    if 'USDT:USDT' in sym:
                        ch = tk.get('percentage') or 0
                        vol = tk.get('quoteVolume') or 0
                        last = tk.get('last') or 0
                        if ch <= -self.drop_needed and vol >= self.vol_needed and last > 0.01:
                            if sym not in self.banned:
                                cands.append((sym, ch, vol, last))
                cands.sort(key=lambda x: x[1])
                self.last_found = len(cands)
                if cands:
                    log(f"[FUTURE] 🔍 {len(tickers)} | {len(cands)} نازلة | أقوى: {cands[0][0]} {cands[0][1]:.1f}%")

                if cands and self.positions < self.max_positions:
                    sym, ch, vol, last = cands[0]
                    try:
                        ex.set_leverage(3, sym)
                        qty = (self.amount_usd * 3) / last
                        ex.create_market_buy_order(sym, qty)
                        log(f"[FUTURE REAL] ✅ دخول {sym} {ch:.1f}% بـ 1$ 3X عند {last}", "ok")
                        self.positions = 1
                        self.banned[sym] = time.time() + 1800
                        threading.Timer(300, lambda: setattr(self, 'positions', 0)).start()
                    except Exception as e:
                        log(f"[FUTURE ERR] {sym} {str(e)[:100]}", "err")
                time.sleep(10)
            except Exception as e:
                log(f"[FUTURE ERR] {str(e)[:120]}", "err"); time.sleep(5)

spot_bot = V1000_Spot_All()
future_bot = V1000_Future_All()
threading.Thread(target=spot_bot.run, daemon=True).start()
threading.Thread(target=future_bot.run, daemon=True).start()

@app.route('/')
def index():
    try:
        ex_spot = make_client('spot')
        bal = ex_spot.fetch_balance()
        usdt_spot = bal.get('USDT',{}).get('free',0)
    except:
        usdt_spot = 0

    logs_html = ""
    for l in LOGS[-100:][::-1]:
        cls = "log-line"
        if "REAL" in l and "✅" in l: cls += " ok"
        elif "ERR" in l or "❌" in l or "insufficient" in l: cls += " err"
        elif "⚠️" in l or "ناقص" in l: cls += " warn"
        logs_html += f"<div class='{cls}'>{l}</div>"

    return f"""
    <html><head><meta http-equiv='refresh' content='5'>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{background:#060a12;color:#e0e0e0;font-family: -apple-system, system-ui;padding:12px}}
    .header{{background:linear-gradient(135deg,#ff3c00,#ff8c00);padding:16px;border-radius:16px;text-align:center;margin-bottom:12px}}
    .header h1{{font-size:17px;color:#fff}} .header p{{font-size:11px;opacity:.9;margin-top:5px}}
    .grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}}
    .card{{background:#121827;border:1px solid #1e2a44;padding:12px;border-radius:14px}}
    .card h3{{font-size:10px;color:#8a9bb8;margin-bottom:6px;letter-spacing:1px}}
    .card .val{{font-size:19px;font-weight:800;color:#00ff88}}
    .card .sub{{font-size:11px;color:#5a6d8a;margin-top:3px}}
    .status{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}}
    .pill{{background:#121827;border-radius:12px;padding:10px;text-align:center;border:1px solid #1e2a44}}
    .pill b{{display:block;font-size:12px}} .pill span{{font-size:10px;color:#8a9bb8}}
    .dot{{width:8px;height:8px;background:#00ff88;border-radius:50%;display:inline-block;animation:blink 1s infinite}}
    @keyframes blink{{50%{{opacity:0.2}}}}
    .logs{{background:#0b1120;border:1px solid #1e2a44;border-radius:14px;padding:6px;height:500px;overflow-y:auto}}
    .log-line{{font-size:11px;padding:7px 8px;border-bottom:1px solid #141d31;font-family:monospace;word-break:break-all}}
    .err{{color:#ff5a5a;background:#1a0f14}} .ok{{color:#00ff88;background:#0f1a14}} .warn{{color:#ffaa00}}
    </style></head>
    <body>
    <div class="header">
        <h1>🔥 V1000 ALL COINS DASHBOARD 🔥</h1>
        <p><span class="dot"></span> LIVE REAL 1$ - SPOT + FUTURE - شغال مثل الحلاوة</p>
    </div>
    <div class="grid">
        <div class="card"><h3>USDT SPOT BALANCE</h3><div class="val">${usdt_spot:.2f}</div><div class="sub">{'✅ جاهز للشراء' if usdt_spot>=1 else '❌ اشحن USDT في Funding'}</div></div>
        <div class="card"><h3>SPOT SCAN</h3><div class="val">{spot_bot.last_scan} / {spot_bot.last_found}</div><div class="sub">فحص / لقى نازلة -5%</div></div>
    </div>
    <div class="status">
        <div class="pill"><b>SPOT: {spot_bot.positions}/{spot_bot.max_positions}</b><span>كل عملات USDT نازلة -5% = شراء 1$</span></div>
        <div class="pill"><b>FUTURE: {future_bot.positions}/{future_bot.max_positions}</b><span>كل عملات USDT:USDT نازلة -5% = 1$ 3X</span></div>
    </div>
    <div class="logs">{logs_html}</div>
    </body></html>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))