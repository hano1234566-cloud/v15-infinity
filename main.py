# V1000 FINAL - ALL COINS + OLD ORDERS MANAGER + CLEAN DASHBOARD
import os, time, threading
from flask import Flask
import ccxt

API_KEY = os.getenv("OKX_API_KEY", "").strip()
SECRET = os.getenv("OKX_SECRET_KEY", "").strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE", "").strip()

app = Flask(__name__)
LOGS = []

def log(m):
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
        self.last_warn = 0
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
                    log(f"[SPOT] 🔍 {len(tickers)} | {len(cands)} نازلة | أقوى: {cands[0][0]} {cands[0][1]:.1f}%")
                else:
                    log(f"[SPOT] 🔍 {len(tickers)} | لا يوجد -5% الآن")

                if cands and self.positions < self.max_positions:
                    sym, ch, vol, last = cands[0]
                    bal = ex.fetch_balance()
                    usdt = bal.get('USDT',{}).get('free',0)
                    if usdt < 0.9:
                        if time.time() - self.last_warn > 600:
                            log(f"[SPOT] ⏸️ متوقف - رصيدك ${usdt:.2f} - ينتظر ربح من أوامرك القديمة - لاقي {sym} {ch:.1f}%")
                            self.last_warn = time.time()
                        time.sleep(30)
                        continue
                    qty = self.amount_usd / last
                    try:
                        ex.create_market_buy_order(sym, qty)
                        log(f"[SPOT REAL] ✅ اشتريت {sym} {ch:.1f}% بـ 1$ عند {last}")
                        self.positions += 1
                        self.banned[sym] = time.time() + 3600
                        threading.Timer(3600, lambda: setattr(self, 'positions', max(0, self.positions-1))).start()
                    except Exception as e:
                        log(f"[SPOT ERR] {sym} {str(e)[:100]}")
                
                now = time.time()
                for k in list(self.banned.keys()):
                    if self.banned[k] < now: del self.banned[k]
                time.sleep(15)
            except Exception as e:
                log(f"[SPOT ERR] {str(e)[:120]}"); time.sleep(10)

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
                time.sleep(10)
            except Exception as e:
                log(f"[FUTURE ERR] {str(e)[:120]}"); time.sleep(5)

class Manager_Old_Orders:
    def __init__(self):
        self.holdings_text = "جاري الفحص..."
    def run(self):
        ex = make_client('spot')
        log("[MANAGER] 🧠 شغال - يراقب أوامرك المفتوحة من قبل")
        while True:
            try:
                bal = ex.fetch_balance()
                holdings = []
                for coin in bal['total']:
                    if coin == 'USDT': continue
                    total = bal['total'].get(coin,0)
                    if not total or total == 0: continue
                    try:
                        ticker = ex.fetch_ticker(f"{coin}/USDT")
                        price = ticker['last']
                        value = total * price
                        if value > 0.05:
                            change = ticker.get('percentage') or 0
                            holdings.append(f"{coin}: {total:.4f} (${value:.2f}) {change:+.1f}%")
                            # لو تبغاه يبيع اوتوماتيك اذا ربح +2% شيل # من السطرين الجايين
                            # if change >= 2.0 and value > 0.5:
                            #     ex.create_market_sell_order(f"{coin}/USDT", total)
                            #     log(f"[MANAGER SELL] ✅ باع {coin} ربح {change:.1f}% ${value:.2f}")
                    except: pass
                if holdings:
                    self.holdings_text = " | ".join(holdings)
                    log(f"[MANAGER] 📦 عندك: {self.holdings_text}")
                else:
                    self.holdings_text = "ما عندك عملات قديمة"
                time.sleep(30)
            except Exception as e:
                log(f"[MANAGER ERR] {str(e)[:100]}"); time.sleep(15)

spot_bot = V1000_Spot_All()
future_bot = V1000_Future_All()
manager_bot = Manager_Old_Orders()

threading.Thread(target=spot_bot.run, daemon=True).start()
threading.Thread(target=future_bot.run, daemon=True).start()
threading.Thread(target=manager_bot.run, daemon=True).start()

@app.route('/')
def index():
    try:
        ex_spot = make_client('spot')
        bal = ex_spot.fetch_balance()
        usdt_spot = bal.get('USDT',{}).get('free',0)
    except:
        usdt_spot = 0

    logs_html = ""
    for l in LOGS[-120:][::-1]:
        cls = "log-line"
        if "REAL" in l or "SELL" in l: cls += " ok"
        elif "ERR" in l: cls += " err"
        elif "⏸️" in l or "MANAGER" in l: cls += " warn"
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
    .old{{background:#121827;border:1px solid #1e2a44;border-radius:12px;padding:10px;margin-bottom:12px;font-size:11px}}
    .dot{{width:8px;height:8px;background:#00ff88;border-radius:50%;display:inline-block;animation:blink 1s infinite}}
    @keyframes blink{{50%{{opacity:0.2}}}}
    .logs{{background:#0b1120;border:1px solid #1e2a44;border-radius:14px;padding:6px;height:520px;overflow-y:auto}}
    .log-line{{font-size:11px;padding:7px 8px;border-bottom:1px solid #141d31;font-family:monospace;word-break:break-all}}
    .err{{color:#ff5a5a}} .ok{{color:#00ff88;background:#0f1a14}} .warn{{color:#ffaa00}}
    </style></head>
    <body>
    <div class="header">
        <h1>🔥 V1000 ALL COINS + OLD ORDERS 🔥</h1>
        <p><span class="dot"></span> LIVE - يراقب الجديد والقديم - شغال مثل الحلاوة</p>
    </div>
    <div class="grid">
        <div class="card"><h3>USDT BALANCE</h3><div class="val">${usdt_spot:.2f}</div><div class="sub">{'✅ جاهز' if usdt_spot>=1 else '⏸️ ينتظر ربح من القديم'}</div></div>
        <div class="card"><h3>SPOT SCAN</h3><div class="val">{spot_bot.last_scan}/{spot_bot.last_found}</div><div class="sub">فحص / لقى نازلة -5%</div></div>
    </div>
    <div class="old"><b>📦 أوامرك المفتوحة من قبل:</b><br>{manager_bot.holdings_text}</div>
    <div class="status">
        <div class="pill"><b>SPOT: {spot_bot.positions}/{spot_bot.max_positions}</b><span>كل عملات USDT نازلة -5% = 1$</span></div>
        <div class="pill"><b>FUTURE: {future_bot.positions}/{future_bot.max_positions}</b><span>كل عملات USDT:USDT نازلة -5%</span></div>
    </div>
    <div class="logs">{logs_html}</div>
    </body></html>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))