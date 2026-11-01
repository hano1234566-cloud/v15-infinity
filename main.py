# V1000 LEGENDARY - ALL COINS - REAL 1$ - SPOT + FUTURE
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

class V1000_Spot_All:
    def __init__(self):
        self.amount_usd = 1
        self.drop_needed = 5.0
        self.vol_needed = 1_000_000
        self.positions = 0
        self.max_positions = 2
        self.banned = {}
    def run(self):
        ex = make_client('spot')
        log("[SPOT ALL] شغال حقيقي - يفحص جميع العملات سبوت")
        while True:
            try:
                tickers = ex.fetch_tickers()
                cands = []
                for sym, tk in tickers.items():
                    if '/USDT' in sym and ':' not in sym:
                        ch = tk.get('percentage') or 0
                        vol = tk.get('quoteVolume') or 0
                        last = tk.get('last') or 0
                        if ch <= -self.drop_needed and vol >= self.vol_needed and last > 0.001:
                            if sym not in self.banned:
                                cands.append((sym, ch, vol, last))
                cands.sort(key=lambda x: x[1])
                if cands:
                    log(f"[SPOT ALL] فحص {len(tickers)} | لقى {len(cands)} عملة نازلة | أقوى نزول {cands[0][0]} {cands[0][1]:.2f}%")
                else:
                    log(f"[SPOT ALL] فحص {len(tickers)} | ما في عملة تحقق -5% الآن")
                
                if cands and self.positions < self.max_positions:
                    sym, ch, vol, last = cands[0]
                    try:
                        qty = self.amount_usd / last
                        ex.create_market_buy_order(sym, qty)
                        log(f"[SPOT REAL] ✅ اشتريت {sym} نازلة {ch:.2f}% بـ 1$ حقيقي عند {last}")
                        self.positions += 1
                        self.banned[sym] = time.time() + 3600
                        threading.Timer(3600, lambda: setattr(self, 'positions', max(0, self.positions-1))).start()
                    except Exception as e:
                        log(f"[SPOT REAL ERR] {sym} {e}")
                
                # فك الباند
                now = time.time()
                for k in list(self.banned.keys()):
                    if self.banned[k] < now: del self.banned[k]
                time.sleep(15)
            except Exception as e:
                log(f"[SPOT ALL ERR] {e}"); time.sleep(10)

class V1000_Future_All:
    def __init__(self):
        self.amount_usd = 1
        self.drop_needed = 5.0
        self.vol_needed = 5_000_000
        self.positions = 0
        self.max_positions = 1
        self.banned = {}
    def run(self):
        ex = make_client('swap')
        log("[FUTURE ALL] شغال حقيقي - يفحص جميع العملات فيوتشر")
        while True:
            try:
                tickers = ex.fetch_tickers()
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
                if cands:
                    log(f"[FUTURE ALL] فحص {len(tickers)} | لقى {len(cands)} عملة نازلة | أقوى نزول {cands[0][0]} {cands[0][1]:.2f}%")
                
                if cands and self.positions < self.max_positions:
                    sym, ch, vol, last = cands[0]
                    try:
                        ex.set_leverage(3, sym)
                        qty = (self.amount_usd * 3) / last
                        ex.create_market_buy_order(sym, qty)
                        log(f"[FUTURE REAL] ✅ دخول {sym} نازلة {ch:.2f}% بـ 1$ حقيقي 3X عند {last}")
                        self.positions = 1
                        self.banned[sym] = time.time() + 1800
                        threading.Timer(300, lambda: setattr(self, 'positions', 0)).start()
                    except Exception as e:
                        log(f"[FUTURE REAL ERR] {sym} {e}")
                time.sleep(10)
            except Exception as e:
                log(f"[FUTURE ALL ERR] {e}"); time.sleep(5)

threading.Thread(target=V1000_Spot_All().run, daemon=True).start()
threading.Thread(target=V1000_Future_All().run, daemon=True).start()

@app.route('/')
def index():
    logs_html = "<br>".join(LOGS[-150:])
    return f"""<html><head><meta http-equiv='refresh' content='3'>
    <style>body{{background:#0a0a0a;color:#00ff88;font-family:monospace;padding:12px;font-size:13px}}h2{{color:#fff;text-align:center}}.box{{background:#111;border:1px solid #222;padding:10px;border-radius:10px;margin:8px 0}}</style>
    </head><body><h2>🔥 V1000 ALL COINS REAL 1$ 🔥</h2>
    <div class="box">SPOT: يفحص كل العملات سبوت نازلة -5% | 1$ حقيقي | 2 صفقات</div>
    <div class="box">FUTURE: يفحص كل العملات فيوتشر نازلة -5% | 1$ 3X حقيقي</div>
    <div class="box">{logs_html}</div></body></html>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))