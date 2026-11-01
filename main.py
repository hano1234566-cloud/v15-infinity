# V1000 AUTONOMOUS - يفعل كل شي لحاله - يدرس ويبيع
import os, time, threading
from flask import Flask
import ccxt

API_KEY = os.getenv("OKX_API_KEY", "").strip()
SECRET = os.getenv("OKX_SECRET_KEY", "").strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE", "").strip()

app = Flask(__name__)
LOGS = []

def log(m):
    LOGS.append(f"{time.strftime('%H:%M:%S')} {m}")
    if len(LOGS) > 500: LOGS.pop(0)
    print(LOGS[-1], flush=True)

def make_client(typ):
    return ccxt.okx({'apiKey': API_KEY, 'secret': SECRET, 'password': PASSPHRASE, 'enableRateLimit': True, 'options': {'defaultType': typ}})

class Autonomous_Bot:
    def __init__(self):
        self.entries = {} # {COIN: price}
        self.last_scan = 0
        self.last_found = 0
        self.usdt = 0
        self.holdings = "جاري الفحص..."
        self.mode = "⏸️ ينتظر سيولة"

    def run(self):
        ex = make_client('spot')
        log("[AUTO] 🤖 بوت ذاتي - يفعل كل شي لحاله")
        while True:
            try:
                # 1. تحديث الرصيد والمحفظة القديمة
                bal = ex.fetch_balance()
                self.usdt = bal.get('USDT',{}).get('free',0)
                
                # 2. يدرس أوامرك القديمة ويبيعها اذا رابحة
                holdings_list = []
                for coin in bal['total']:
                    if coin == 'USDT': continue
                    total = bal['total'].get(coin,0)
                    if not total: continue
                    try:
                        tk = ex.fetch_ticker(f"{coin}/USDT")
                        price = tk['last']
                        value = total * price
                        if value < 0.05: continue
                        change = tk.get('percentage') or 0
                        holdings_list.append(f"{coin} ${value:.2f} {change:+.1f}%")
                        
                        # القرار الذاتي: يبيع لحاله اذا العملة رابحة +1.5% او نازلة كثير وبيصحح
                        if value > 0.3 and change >= 1.5:
                            ex.create_market_sell_order(f"{coin}/USDT", total)
                            log(f"[AUTO SELL] ✅ باع {coin} ربح {change:.1f}% جاب ${value:.2f} سيولة")
                            self.usdt += value
                            time.sleep(2)
                        elif value > 0.3 and change <= -15:
                            # نازلة بقوة - ينتظر
                            pass
                    except: pass
                self.holdings = " | ".join(holdings_list) if holdings_list else "ما عندك عملات"

                # 3. يفحص جميع العملات ويدرسها
                tickers = ex.fetch_tickers()
                self.last_scan = len(tickers)
                cands = []
                for sym, tk in tickers.items():
                    if '/USDT' in sym and ':' not in sym and 'UP/' not in sym and 'DOWN/' not in sym:
                        ch = tk.get('percentage') or 0
                        vol = tk.get('quoteVolume') or 0
                        last = tk.get('last') or 0
                        # يدرس: نازلة -5% وحجم عالي = فرصة
                        if ch <= -5.0 and vol >= 1_000_000 and last > 0.001 and sym not in self.entries:
                            cands.append((sym, ch, vol, last))
                cands.sort(key=lambda x: x[1])
                self.last_found = len(cands)

                if cands:
                    log(f"[AUTO] 🔍 {len(tickers)} | فرص: {len(cands)} | أقوى {cands[0][0]} {cands[0][1]:.1f}%")

                # 4. يشتري لحاله اذا عنده سيولة
                if cands and self.usdt >= 1:
                    sym, ch, vol, last = cands[0]
                    qty = 1 / last
                    try:
                        ex.create_market_buy_order(sym, qty)
                        self.entries[sym] = last
                        log(f"[AUTO BUY] ✅ اشترى {sym} نازلة {ch:.1f}% بـ 1$ عند {last} - بيدرسها للبيع")
                        self.usdt -= 1
                    except Exception as e:
                        log(f"[AUTO BUY ERR] {e}")
                elif cands and self.usdt < 1:
                    if len(LOGS) % 20 == 0:
                        log(f"[AUTO] ⏸️ لاقي {cands[0][0]} {cands[0][1]:.1f}% بس رصيدك ${self.usdt:.2f} - ينتظر بيع القديم")
                    self.mode = f"ينتظر بيع {holdings_list[0] if holdings_list else 'القديم'}"

                # 5. يبيع اللي اشتراه هو لحاله اذا ربح +2.5%
                for sym_entry, buy_price in list(self.entries.items()):
                    try:
                        tk = ex.fetch_ticker(sym_entry)
                        now_price = tk['last']
                        profit = ((now_price - buy_price) / buy_price) * 100
                        if profit >= 2.5:
                            coin = sym_entry.split('/')[0]
                            total = bal['total'].get(coin,0)
                            if total and total * now_price > 0.5:
                                ex.create_market_sell_order(sym_entry, total)
                                log(f"[AUTO SELL] 💰 باع {sym_entry} ربح {profit:.2f}% من {buy_price} الى {now_price}")
                                del self.entries[sym_entry]
                        elif profit <= -8: # وقف خسارة
                            coin = sym_entry.split('/')[0]
                            total = bal['total'].get(coin,0)
                            if total and total * now_price > 0.5:
                                ex.create_market_sell_order(sym_entry, total)
                                log(f"[AUTO STOP] 🛑 باع {sym_entry} خسارة {profit:.1f}%")
                                del self.entries[sym_entry]
                    except: pass

                time.sleep(12)
            except Exception as e:
                log(f"[AUTO ERR] {str(e)[:120]}"); time.sleep(10)

bot = Autonomous_Bot()
threading.Thread(target=bot.run, daemon=True).start()

@app.route('/')
def index():
    logs_html = "".join([f"<div class='l {('ok' if '✅' in l or '💰' in l else 'err' if 'ERR' in l else 'warn' if 'MANAGER' in l or 'AUTO' in l else '')}'>{l}</div>" for l in LOGS[-120:][::-1]])
    return f"""
    <html><head><meta http-equiv='refresh' content='4'><meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{{background:#060a12;color:#e0e0e0;font-family:system-ui;padding:12px}} .h{{background:linear-gradient(135deg,#00c853,#009624);padding:16px;border-radius:16px;text-align:center;margin-bottom:12px}} .g{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}} .c{{background:#121827;border:1px solid #1e2a44;padding:12px;border-radius:14px}} .c h3{{font-size:10px;color:#8a9bb8}} .c .v{{font-size:18px;font-weight:800;color:#00ff88}} .old{{background:#121827;border:1px solid #1e2a44;border-radius:12px;padding:10px;margin-bottom:12px;font-size:11px}} .logs{{background:#0b1120;border:1px solid #1e2a44;border-radius:14px;padding:6px;height:550px;overflow-y:auto}} .l{{font-size:11px;padding:7px 8px;border-bottom:1px solid #141d31;font-family:monospace}} .ok{{color:#00ff88}} .err{{color:#ff5a5a}} .warn{{color:#ffaa00}}</style>
    </head><body>
    <div class="h"><h1>🤖 V1000 AUTONOMOUS 🤖</h1><p>يفعل كل شي لحاله - يدرس - يشتري - يبيع - بدون أوامر</p></div>
    <div class="g">
        <div class="c"><h3>USDT</h3><div class="v">${bot.usdt:.2f}</div><div style="font-size:11px;color:#5a6d8a">{bot.mode}</div></div>
        <div class="c"><h3>SCAN</h3><div class="v">{bot.last_scan}/{bot.last_found}</div><div style="font-size:11px;color:#5a6d8a">فحص / فرص -5%</div></div>
    </div>
    <div class="old"><b>📦 أوامرك القديمة + الجديدة:</b><br>{bot.holdings}<br><br><b>🎯 صفقاته هو:</b> {', '.join([f"{k}@{v:.4f}" for k,v in bot.entries.items()]) if bot.entries else 'لا يوجد - ينتظر'}</div>
    <div class="logs">{logs_html}</div>
    </body></html>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))