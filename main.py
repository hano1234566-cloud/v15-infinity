# V1000 LEGENDARY MERGED - FIXED FOR RENDER
import os, time, threading
from flask import Flask
import ccxt

API_KEY = os.getenv("OKX_API_KEY", "ضع مفتاحك").strip()
SECRET = os.getenv("OKX_SECRET_KEY", "ضع سرك").strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE", "ضع باسوردك").strip()

app = Flask(__name__)
LOGS = []

def log(m):
    t = time.strftime("%H:%M:%S")
    msg = f"{t} {m}"
    LOGS.append(msg)
    if len(LOGS) > 200: LOGS.pop(0)
    print(msg, flush=True)

def make_client(typ):
    return ccxt.okx({
        'apiKey': API_KEY, 'secret': SECRET, 'password': PASSPHRASE,
        'enableRateLimit': True,
        'options': {'defaultType': typ}
    })

# ===== SPOT =====
class V1000_Spot_Legendary:
    def __init__(self):
        self.symbol = 'AVAX/USDT'
        self.buy_price = 8.9050
        self.stop_price = 8.6640
        self.amount_usd = 1
        self.losses = 0
        self.bought = False

    def run(self):
        ex = make_client('spot')
        log("[SPOT] أسطوري شغال مثل الحلاوة - يشتري AVAX")
        while True:
            try:
                price = ex.fetch_ticker(self.symbol)['last']
                log(f"[SPOT] AVAX {price} | شراء {self.buy_price} | ستوب {self.stop_price}")
                if price <= self.buy_price and not self.bought:
                    log(f"[SPOT] >>> شراء 1$ عند {price}")
                    # ex.create_market_buy_order(self.symbol, self.amount_usd/price)
                    self.bought = True
                if price <= self.stop_price and self.bought:
                    log(f"[SPOT] >>> ستوب حماية عند {price}")
                    self.bought = False
                if price > self.buy_price + 0.2: # إعادة تفعيل الشراء اذا طلع
                    self.bought = False
                time.sleep(5)
            except Exception as e:
                log(f"[SPOT ERR] {e} - أصلح نفسي بعد 5 ثواني")
                time.sleep(5)

# ===== FUTURE =====
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
        log("[FUTURE] سكانر 200 عملة شغال مثل الحلاوة")
        while True:
            try:
                tickers = ex.fetch_tickers()
                cands = []
                for sym, tk in tickers.items():
                    if 'USDT:USDT' in sym:
                        ch = tk.get('percentage') or 0
                        vol = tk.get('quoteVolume') or 0
                        if ch <= -self.drop_needed and vol >= self.volume_needed:
                            if sym not in self.banned:
                                cands.append((sym, ch, vol))
                cands.sort(key=lambda x: x[1])
                log(f"[FUTURE] فحصت {len(tickers)} | لقيت {len(cands)} عملة تحقق -5%")
                if cands and self.current_positions < self.max_positions:
                    sym, ch, vol = cands[0]
                    log(f"[FUTURE] >>> دخول {sym} نازلة {ch:.2f}% حجم {vol} - 1$ 3X")
                    self.current_positions = 1
                    # هنا تحط أمرك الحقيقي + بعد 2 دقيقة تسوي current_positions=0 عشان يدخل غيرها
                    threading.Timer(120, lambda: setattr(self, 'current_positions', 0)).start()
                time.sleep(10)
            except Exception as e:
                log(f"[FUTURE ERR] {e}")
                time.sleep(5)

# تشغيل الاثنين
spot = V1000_Spot_Legendary()
future = V1000_Future_Legendary()
threading.Thread(target=spot.run, daemon=True).start()
threading.Thread(target=future.run, daemon=True).start()

@app.route('/')
def index():
    return f"<h2>V1000 LEGENDARY MERGED - شغال مثل الحلاوة</h2><h3>SPOT: AVAX يشتري عند 8.9050</h3><h3>FUTURE: سكانر 200 عملة</h3><pre>{chr(10).join(LOGS[-80:])}</pre><meta http-equiv='refresh' content='3'>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))