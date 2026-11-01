# V1000 LEGENDARY MERGED - REAL MONEY 1$ - SPOT + FUTURE
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
    if len(LOGS) > 300: LOGS.pop(0)
    print(msg, flush=True)

def make_client(typ):
    return ccxt.okx({
        'apiKey': API_KEY, 'secret': SECRET, 'password': PASSPHRASE,
        'enableRateLimit': True,
        'options': {'defaultType': typ}
    })

class V1000_Spot_Legendary:
    def __init__(self):
        self.symbol = 'AVAX/USDT'
        self.buy_price = 8.9050
        self.stop_price = 8.6640
        self.amount_usd = 1
        self.bought = False
    def run(self):
        ex = make_client('spot')
        log("[SPOT] شغال حقيقي - يشتري AVAX بـ 1$ حقيقي")
        while True:
            try:
                price = ex.fetch_ticker(self.symbol)['last']
                log(f"[SPOT] AVAX {price} | شراء {self.buy_price}")
                if price <= self.buy_price and not self.bought:
                    qty = self.amount_usd / price
                    try:
                        ex.create_market_buy_order(self.symbol, qty)
                        log(f"[SPOT REAL] ✅ اشتريت {qty:.5f} AVAX بـ 1$ حقيقي عند {price}")
                        self.bought = True
                    except Exception as e:
                        log(f"[SPOT REAL ERR] {e}")
                if price <= self.stop_price and self.bought:
                    try:
                        bal = ex.fetch_balance()
                        avax_free = bal.get('AVAX',{}).get('free',0)
                        if avax_free > 0:
                            ex.create_market_sell_order(self.symbol, avax_free)
                            log(f"[SPOT REAL] 🛑 ستوب بعت {avax_free} عند {price}")
                        self.bought = False
                    except Exception as e:
                        log(f"[SPOT ERR] {e}")
                if price > self.buy_price + 0.5:
                    self.bought = False
                time.sleep(5)
            except Exception as e:
                log(f"[SPOT ERR] {e}"); time.sleep(5)

class V1000_Future_Legendary:
    def __init__(self):
        self.amount_usd = 1
        self.drop_needed = 5.0
        self.volume_needed = 10_000_000
        self.current_positions = 0
        self.max_positions = 1
        self.banned = {}
    def run(self):
        ex = make_client('swap')
        log("[FUTURE] سكانر 200 عملة شغال حقيقي - 1$ 3X")
        while True:
            try:
                tickers = ex.fetch_tickers()
                cands = []
                for sym, tk in tickers.items():
                    if 'USDT:USDT' in sym:
                        ch = tk.get('percentage') or 0
                        vol = tk.get('quoteVolume') or 0
                        last = tk.get('last') or 0
                        if ch <= -self.drop_needed and vol >= self.volume_needed and last > 0.01:
                            if sym not in self.banned:
                                cands.append((sym, ch, vol, last))
                cands.sort(key=lambda x: x[1])
                log(f"[FUTURE] فحص {len(tickers)} | لقى {len(cands)} عملة -5%")
                if cands and self.current_positions < self.max_positions:
                    sym, ch, vol, last = cands[0]
                    try:
                        ex.set_leverage(3, sym)
                        qty = (self.amount_usd * 3) / last
                        ex.create_market_buy_order(sym, qty)
                        log(f"[FUTURE REAL] ✅ دخول {sym} نازلة {ch:.2f}% بـ 1$ حقيقي 3X كمية {qty} عند {last}")
                        self.current_positions = 1
                        # يفك بعد 5 دقائق عشان يدخل غيرها
                        threading.Timer(300, lambda: setattr(self, 'current_positions', 0)).start()
                    except Exception as e:
                        log(f"[FUTURE REAL ERR] {sym} {e}")
                time.sleep(10)
            except Exception as e:
                log(f"[FUTURE ERR] {e}"); time.sleep(5)

# تشغيل
threading.Thread(target=V1000_Spot_Legendary().run, daemon=True).start()
threading.Thread(target=V1000_Future_Legendary().run, daemon=True).start()

@app.route('/')
def index():
    logs_html = "<br>".join(LOGS[-120:])
    return f"""
    <html><head><meta http-equiv='refresh' content='3'>
    <style>body{{background:#0a0a0a;color:#00ff88;font-family:monospace;padding:12px;font-size:13px}}h2{{color:#fff;text-align:center}}.box{{background:#111;border:1px solid #222;padding:10px;border-radius:10px;margin:8px 0}}.spot{{color:#00d4ff}}.future{{color:#ffaa00}}</style>
    </head><body>
    <h2>🔥 V1000 LEGENDARY REAL - 1$ حقيقي 🔥</h2>
    <div class="box spot">SPOT: AVAX يشتري 8.9050 | ستوب 8.6640 | حقيقي</div>
    <div class="box future">FUTURE: سكانر 200 عملة -5% | 1$ 3X | حقيقي</div>
    <div class="box">{logs_html}</div>
    </body></html>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))