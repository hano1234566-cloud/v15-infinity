import os, ccxt, pandas as pd, ta, json, math
from flask import Flask, render_template_string
from datetime import datetime, timedelta

app = Flask(__name__)
exchange = ccxt.okx({
    'apiKey': os.getenv("OKX_API_KEY"),
    'secret': os.getenv("OKX_SECRET"),
    'password': os.getenv("OKX_PASSPHRASE"),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

SYMBOLS = ["SOL/USDT:USDT", "LINK/USDT:USDT", "FET/USDT:USDT", "BTC/USDT:USDT", "AVAX/USDT:USDT"]
MODE_FILE = "/tmp/bot_mode.json"

def get_mode():
    try:
        with open(MODE_FILE, 'r') as f:
            d = json.load(f)
            if d['mode'] == 'PROTECTION':
                t = datetime.fromisoformat(d['since'])
                if datetime.now() - t > timedelta(minutes=20):
                    return {'mode': 'ATTACK', 'since': str(datetime.now()), 'losses': 0}
            return d
    except: pass
    return {'mode': 'ATTACK', 'since': str(datetime.now()), 'losses': 0}

def set_mode(mode, losses=0):
    with open(MODE_FILE, 'w') as f:
        json.dump({'mode': mode, 'since': str(datetime.now()), 'losses': losses}, f)

HTML = "<h3>${{w}} | {{mode}} | فيوتشر ${{f}}</h3><p>BTC bear ATR:{{a}} EMA{{e}} RSI{{r}}</p><p>صفقات {{p}} | GOD {{g}}/10</p>{% for s in sig %}<p>{{s}}</p>{% endfor %}<hr><b>{{log}}</b>"

def get_score(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, '5m', limit=120)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        df['rsi'] = ta.momentum.RSIIndicator(df['c'], 14).rsi()
        df['ema9'] = ta.trend.EMAIndicator(df['c'], 9).ema_indicator()
        df['atr'] = ta.volatility.AverageTrueRange(df['h'],df['l'],df['c'],14).average_true_range()
        last = df.iloc[-1]
        atr_pct = (last['atr']/last['c'])*100
        rsi = float(last['rsi'])
        score = 0
        if rsi < 42: score += 5
        if rsi < 39: score += 3
        if last['c'] < last['ema9']: score += 3
        if atr_pct > 0.5: score += 1
        if score >= 7:
            return f"{sym.replace('/USDT:USDT','')} short {score}/10 RSI:{rsi:.1f} ATR:{atr_pct:.3f}%", score, atr_pct, rsi, float(last['ema9']), float(last['c']), sym
    except: return None
    return None

def open_short(symbol, capital_usdt, lev):
    try:
        price = float(exchange.fetch_ticker(symbol)['last'])
        # تحويل USDT إلى كمية عقود
        amount = capital_usdt / price
        amount = float(exchange.amount_to_precision(symbol, amount))
        if amount <= 0: return False
        try: exchange.set_leverage(lev, symbol, {'mgnMode':'isolated'})
        except: pass
        exchange.create_market_order(symbol, 'sell', amount)
        return True
    except Exception as e:
        print(f"Open failed {symbol}: {e}")
        return False

@app.route('/')
def index():
    mode_data = get_mode()
    mode = mode_data['mode']
    GOD_MIN, ATR_MAX, LEV, TP, CAPITAL_PCT = 10, 0.90, 2, 1.5, 0.35
    
    sigs, best, log = [], None, ""
    fut, atr_btc, ema_btc, rsi_btc, close_btc, open_cnt = 62.43, 0.42, 77839, 35, 77516, 0
    
    try:
        bal = exchange.fetch_balance()
        fut = float(bal['total'].get('USDT', 62.43))
        capital_usdt = fut * CAPITAL_PCT * LEV  # قيمة حقيقية مع الرافعة
        
        for sym in SYMBOLS:
            r = get_score(sym)
            if r:
                txt, score, atr_p, rsi_v, ema_v, close_v, full_sym = r
                sigs.append(txt)
                if "BTC" in sym: atr_btc, ema_btc, rsi_btc, close_btc = atr_p, ema_v, rsi_v, close_v
                if score >= GOD_MIN and atr_p <= ATR_MAX:
                    if not best or score > best[1]: best = (full_sym, score, close_v)

        positions = exchange.fetch_positions()
        open_pos = [p for p in positions if float(p.get('contracts',0) or 0) > 0]
        open_cnt = len(open_pos)

        if open_cnt > 0:
            pnl = float(open_pos[0].get('unrealizedPnl', 0))
            pnl_pct = float(open_pos[0].get('percentage', 0) or 0)
            
            if pnl >= 0.8 or pnl_pct >= TP:
                # قفل ربح
                exchange.create_market_order(open_pos[0]['symbol'], 'buy', float(open_pos[0]['contracts']), params={'reduceOnly': True})
                log = f"✅ قفل ربح ${pnl:.2f} ({pnl_pct:.1f}%) - "
                # إعادة فحص سريعة بعد القفل عشان يلقى صفقة
                if best:
                    ok = open_short(best[0], capital_usdt, LEV)
                    if ok:
                        log += f"ودخل فوراً {best[0]} {best[1]}/10 حلقة مستمرة 🔁"
                        set_mode('ATTACK', 0)
                    else: log += "حاول يدخل وفشل، سيحاول التحديث القادم"
                else:
                    log += "لا توجد صفقة كويسة حالياً، انتظار..."
                    set_mode('ATTACK', 0)
            elif pnl <= -1.2 or pnl_pct <= -1.0:
                exchange.create_market_order(open_pos[0]['symbol'], 'buy', float(open_pos[0]['contracts']), params={'reduceOnly': True})
                losses = mode_data.get('losses',0) + 1
                if losses >= 2:
                    set_mode('PROTECTION', losses)
                    log = f"⚠️ خسارتين ${pnl:.2f} - حماية 20د"
                else:
                    set_mode('ATTACK', losses)
                    log = f"⚠️ خسارة ${pnl:.2f} - خسائر {losses}"
            else:
                log = f"مفتوحة {open_pos[0]['symbol']} PnL ${pnl:.2f} ({pnl_pct:.1f}%) | هجوم مستمر"
        else:
            if mode == 'PROTECTION':
                remain = (datetime.fromisoformat(mode_data['since'])+timedelta(minutes=20)-datetime.now()).seconds//60
                log = f"🛡️ حماية {remain}د بسبب خسائر"
            elif best:
                ok = open_short(best[0], capital_usdt, LEV)
                if ok: log = f"🔥 هجوم: دخل {best[0]} {best[1]}/10 - بعد الربح سيدخل التالية 🔁"
                else: log = f"يحاول يدخل {best[0]} لكن OKX رفض الكمية"
            else:
                log = f"وضع هجوم - انتظار إشارة {GOD_MIN}/10 قوية"

    except Exception as e:
        log = f"خطأ: {str(e)[:250]} | وضع {mode}"

    return render_template_string(HTML, w=f"{fut+20.49:.2f}", f=f"{fut:.2f}", mode=mode, a=f"{atr_btc:.2f}", e=int(ema_btc), r=int(rsi_btc), c=int(close_btc), p=f"{open_cnt}/1", g=GOD_MIN, sig=sigs, log=log)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
