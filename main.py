# V20000 HIDDEN WORLD - FINAL - الخلاصة المفيدة
import os, time, threading
from flask import Flask
import ccxt

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = os.getenv("OKX_SECRET_KEY","").strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

app = Flask(__name__)
LOGS = []
def log(m):
    LOGS.append(f"{time.strftime('%H:%M:%S')} {m}")
    if len(LOGS)>800: LOGS.pop(0)
    print(LOGS[-1], flush=True)

def make(t): return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True,'options':{'defaultType':t}})

class Bot:
    def __init__(self):
        self.pos = {} # key -> buy_price
        self.bal_s = 0
        self.hunts = 0
        self.kills = 0
        self.old = "يفحص..."

    def liq_hunter(self):
        ex = make('swap')
        log("[LIQ] 👁️ صياد التصفية صحى")
        while True:
            try:
                tickers = ex.fetch_tickers()
                for sym, tk in tickers.items():
                    if ':USDT' not in sym: continue
                    ch = tk.get('percentage') or 0
                    vol = tk.get('quoteVolume') or 0
                    base = sym.split('/')[0]
                    if ch <= -8 and vol > 3000000 and f"LIQ:{base}" not in self.pos and f"LIQSHORT:{base}" not in self.pos:
                        try:
                            ex.set_leverage(10, None, {'mgnMode':'isolated'})
                            ex.create_market_buy_order(sym, 0.5/tk['last'], {'tdMode':'isolated','posSide':'long'})
                            self.pos[f"LIQ:{base}"] = tk['last']
                            self.hunts+=1
                            log(f"[LIQ BUY] 👁️ {base} نازل {ch:.1f}% - دخل لونج مع الحوت")
                        except Exception as e: log(f"[LIQ ERR] {e}")
                    if ch >= 10 and vol > 3000000 and f"LIQSHORT:{base}" not in self.pos and f"LIQ:{base}" not in self.pos:
                        try:
                            ex.create_market_sell_order(sym, 0.5/tk['last'], {'tdMode':'isolated','posSide':'short'})
                            self.pos[f"LIQSHORT:{base}"] = tk['last']
                            self.hunts+=1
                            log(f"[LIQ SHORT] 👁️ {base} صاعد +{ch:.1f}% - دخل شورت")
                        except: pass
                time.sleep(5)
            except Exception as e: log(f"[LIQ ERR] {e}"); time.sleep(5)

    def death_wick(self):
        ex = make('spot')
        log("[DEATH] 💀 قناص شمعة الموت صحى")
        while True:
            try:
                tickers = ex.fetch_tickers()
                for sym, tk in tickers.items():
                    if '/USDT' not in sym or ':' in sym: continue
                    ch = tk.get('percentage') or 0
                    if ch <= -18 and tk['last']>0.001:
                        base = sym.split('/')[0]
                        if f"DEATH:{base}" not in self.pos:
                            try:
                                b = ex.fetch_balance()
                                free = b.get('USDT',{}).get('free',0)
                                if free>=1:
                                    ex.create_market_buy_order(sym, 1/tk['last'])
                                    self.pos[f"DEATH:{base}"] = tk['last']
                                    self.hunts+=1
                                    log(f"[DEATH BUY] 💎 {base} {ch:.1f}% شمعة موت - كنز")
                            except Exception as e: log(f"[DEATH ERR] {e}")
                time.sleep(4)
            except: time.sleep(5)

    def ghost(self):
        ex = make('spot')
        log("[GHOST] 👻 كاشف الجدران الوهمية صحى")
        while True:
            try:
                tickers = ex.fetch_tickers()
                for sym, tk in tickers.items():
                    if '/USDT' not in sym or ':' in sym: continue
                    ch = tk.get('percentage') or 0
                    vol = tk.get('quoteVolume') or 0
                    if -5 <= ch <= -3.5 and vol>800000:
                        base = sym.split('/')[0]
                        if f"GHOST:{base}" not in self.pos:
                            try:
                                b = ex.fetch_balance()
                                if b.get('USDT',{}).get('free',0)>=0.5:
                                    ex.create_market_buy_order(sym, 0.5/tk['last'])
                                    self.pos[f"GHOST:{base}"] = tk['last']
                                    log(f"[GHOST BUY] 👻 {base} {ch:.1f}% - جدار وهمي انشال")
                            except: pass
                time.sleep(8)
            except: time.sleep(8)

    def manager(self):
        while True:
            try:
                ex_s = make('spot')
                ex_f = make('swap')
                tickers_s = ex_s.fetch_tickers()
                tickers_f = ex_f.fetch_tickers()
                self.bal_s = ex_s.fetch_balance().get('USDT',{}).get('free',0)

                # محفظتك القديمة
                try:
                    b = ex_s.fetch_balance()
                    holds=[]
                    for c in b['total']:
                        if c!='USDT' and b['total'][c]>0:
                            try: holds.append(f"{c}:${b['total'][c]*ex_s.fetch_ticker(f'{c}/USDT')['last']:.2f}")
                            except: pass
                    self.old = " | ".join(holds) if holds else "فاضي"
                except: pass

                # بيع
                for k, buy in list(self.pos.items()):
                    base = k.split(":")[1]
                    try:
                        is_fut = 'LIQ' in k
                        tickers = tickers_f if is_fut else tickers_s
                        sym_match = [s for s in tickers if base == s.split('/')[0] and (':USDT' in s if is_fut else '/USDT' in s and ':' not in s)]
                        if not sym_match: continue
                        now = tickers[sym_match[0]]['last']
                        prof = ((now-buy)/buy)*100
                        if 'SHORT' in k: prof = ((buy-now)/buy)*100
                        if is_fut: prof*=10

                        close=False
                        if 'LIQ' in k and prof>=5: close=True
                        if 'SHORT' in k and prof>=4: close=True
                        if 'DEATH' in k and prof>=15: close=True
                        if 'GHOST' in k and prof>=4: close=True
                        if prof<=-7: close=True

                        if close:
                            if is_fut:
                                if 'SHORT' in k: ex_f.create_market_buy_order(sym_match[0], 0.5/now, {'tdMode':'isolated','posSide':'short'})
                                else: ex_f.create_market_sell_order(sym_match[0], 0.5/now, {'tdMode':'isolated','posSide':'long'})
                            else:
                                tot = ex_s.fetch_balance()['total'].get(base,0)
                                if tot: ex_s.create_market_sell_order(sym_match[0], tot)
                            log(f"[SELL] 👁️ خرج {base} {prof:+.1f}% {k.split(':')[0]}")
                            del self.pos[k]
                            self.kills+=1
                    except Exception as e: log(f"[MNG ERR] {e}")
                time.sleep(3)
            except Exception as e: log(f"[MNG ERR] {e}"); time.sleep(5)

bot = Bot()
threading.Thread(target=bot.liq_hunter, daemon=True).start()
threading.Thread(target=bot.death_wick, daemon=True).start()
threading.Thread(target=bot.ghost, daemon=True).start()
threading.Thread(target=bot.manager, daemon=True).start()

@app.route('/')
def idx():
    # حساب ربح لحظي صحيح 100%
    rows=""
    try:
        ex_s = make('spot')
        ex_f = make('swap')
        ts = ex_s.fetch_tickers()
        tf = ex_f.fetch_tickers()
        for k, buy in bot.pos.items():
            base = k.split(":")[1]
            is_fut = 'LIQ' in k
            tickers = tf if is_fut else ts
            sym_match = [s for s in tickers if base == s.split('/')[0] and (':USDT' in s if is_fut else '/USDT' in s and ':' not in s)]
            now = tickers[sym_match[0]]['last'] if sym_match else buy
            prof = ((now-buy)/buy)*100
            if 'SHORT' in k: prof = ((buy-now)/buy)*100
            if is_fut: prof*=10
            color = "#0f0" if prof>0 else "#f44"
            rows+=f"<tr><td>{k.split(':')[0]}</td><td>{base}</td><td>{buy:.4f}</td><td>{now:.4f}</td><td style='color:{color};font-weight:700'>{prof:+.1f}%</td></tr>"
    except Exception as e: rows=f"<tr><td colspan=5>يحسب... {e}</td></tr>"
    if not rows: rows="<tr><td colspan=5 style='text-align:center;color:#666'>لا يوجد - يترصد الحيتان</td></tr>"

    logs_html="".join([f"<div class='log'>{l}</div>" for l in LOGS[-200:][::-1]])

    return f"""
    <html><head><meta http-equiv='refresh' content='3'><meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
    body{{background:#0a0a0a;color:#eee;font-family:monospace;padding:10px;font-size:12px}}
    .top{{display:flex;gap:8px;margin-bottom:10px}} .box{{background:#111;border:1px solid #222;border-radius:8px;padding:10px;flex:1;text-align:center}}
    .box b{{display:block;font-size:18px;color:#0f0}} .box.hunt b{{color:#f0a}} .box.kill b{{color:#0ff}}
    table{{width:100%;background:#111;border:1px solid #222;border-radius:8px;border-collapse:collapse;margin-bottom:10px}}
    th{{background:#1a1a1a;padding:8px;text-align:left;font-size:10px;color:#888}} td{{padding:8px;border-top:1px solid #222;font-size:11px}}
    .logs{{background:#111;border:1px solid #222;border-radius:8px;padding:6px;height:500px;overflow:auto}}
    .log{{padding:4px 0;border-bottom:1px solid #1a1a1a;font-size:10px}}
    h2{{font-size:11px;color:#888;margin:10px 0 5px;letter-spacing:1px}}
    </style></head><body>
    <div class="top">
        <div class="box hunt"><small>HUNTS</small><b>{bot.hunts}</b></div>
        <div class="box kill"><small>KILLS</small><b>{bot.kills}</b></div>
        <div class="box"><small>BALANCE</small><b>${bot.bal_s:.2f}</b></div>
        <div class="box"><small>POS</small><b>{len(bot.pos)}</b></div>
    </div>
    <h2>🎯 صفقات حية - ربح لحظي 100%</h2>
    <table><tr><th>نوع</th><th>عملة</th><th>دخول</th><th>سعر الآن</th><th>ربح%</th></tr>{rows}</table>
    <h2>📦 محفظتك</h2>
    <div style="background:#111;border:1px solid #222;border-radius:8px;padding:8px;font-size:10px;margin-bottom:10px;color:#aaa">{bot.old}</div>
    <h2>📜 السجل</h2>
    <div class="logs">{logs_html}</div>
    </body></html>
    """

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
