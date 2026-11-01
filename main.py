import os
import time
import json
import logging
from datetime import datetime, timezone

import ccxt
import pandas as pd
from flask import Flask, jsonify

# =========================================================
# DEATH HUNTER V30000 PRO - SAFE EDITION
# Spot: 15 USDT | Futures: 5 USDT | Leverage: 3x Isolated
# With Dollar Cap Protection + Emergency Stop
# =========================================================

CONFIG = {
    "SPOT_BUDGET": 15.0,
    "FUTURES_MARGIN": 5.0,
    "LEVERAGE": 3,
    "MAX_COINS": 30,
    "TIMEFRAME": "5m",
    "CANDLE_LIMIT": 100,
    "SCAN_INTERVAL": 30,
    "STOP_LOSS": 0.012,
    "TAKE_PROFIT": 0.024,
    "MIN_SIGNAL_SCORE": 3,
    "LIVE_TRADING": os.getenv("LIVE_TRADING", "NO").upper() == "YES",
    "ALLOW_SPOT": True,
    "ALLOW_FUTURES": True,
    "STATE_FILE": "bot_state.json",
    "MAX_SPOT_USD": 16.0,  # حماية: أقصى 16$
    "MAX_FUTURES_USD": 6.0,  # حماية: أقصى 6$ هامش
}

API_KEY = os.getenv("OKX_API_KEY", "")
API_SECRET = os.getenv("OKX_API_SECRET", "")
API_PASSWORD = os.getenv("OKX_API_PASSWORD", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("DEATH_HUNTER")
app = Flask(__name__)

exchange = ccxt.okx({
    "apiKey": API_KEY, "secret": API_SECRET, "password": API_PASSWORD,
    "enableRateLimit": True, "options": {"defaultType": "spot"},
})

state = {
    "running": True, "started": datetime.now(timezone.utc).isoformat(),
    "last_scan": None, "scanned": 0, "signals": [], "trades": [], "errors": [],
    "spot_position": None, "future_position": None, "wins": 0, "losses": 0, "pnl": 0.0,
}

def save_state():
    try:
        with open(CONFIG["STATE_FILE"], "w") as f: json.dump(state, f, indent=2)
    except: pass

def load_state():
    try:
        with open(CONFIG["STATE_FILE"], "r") as f: state.update(json.load(f))
    except: pass

def record_error(msg):
    log.error(msg)
    state["errors"].append({"time": datetime.now(timezone.utc).isoformat(), "message": str(msg)})
    state["errors"] = state["errors"][-30:]
    save_state()

def validate_dollar_cap(symbol, amount, price, max_usd):
    notional = amount * price
    if notional > max_usd:
        raise ValueError(f"⛔ صفقة مرفوضة: {notional:.2f}$ > {max_usd}$ في {symbol}")
    return True

def initialize():
    if not CONFIG["LIVE_TRADING"]: log.warning("LIVE_TRADING disabled - paper mode")
    if not all([API_KEY, API_SECRET, API_PASSWORD]): log.warning("API not configured")

def get_market_symbols():
    markets = exchange.load_markets()
    tickers = exchange.fetch_tickers()
    candidates = []
    for symbol, market in markets.items():
        try:
            if not market.get("active"): continue
            if not market.get("spot"): continue
            if market.get("quote") != "USDT": continue
            if market.get("base") in ("USDC", "USDT", "DAI", "FDUSD"): continue
            ticker = tickers.get(symbol, {})
            vol = ticker.get("quoteVolume")
            if vol is None: continue
            if float(vol) < 1_000_000: continue
            candidates.append((symbol, float(vol)))
        except: continue
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in candidates[:CONFIG["MAX_COINS"]]]

def get_swap_symbol(spot_symbol):
    base = spot_symbol.split("/")[0]
    symbol = base + "/USDT:USDT"
    if symbol not in exchange.markets: return None
    market = exchange.markets[symbol]
    if not market.get("swap") or not market.get("active"): return None
    return symbol

def fetch_candles(symbol):
    candles = exchange.fetch_ohlcv(symbol, timeframe=CONFIG["TIMEFRAME"], limit=CONFIG["CANDLE_LIMIT"])
    df = pd.DataFrame(candles, columns=["time", "open", "high", "low", "close", "volume"])
    if len(df) < 30: return None
    df = df.iloc[:-1].copy()
    df["ema9"] = df["close"].ewm(span=9).mean()
    df["ema21"] = df["close"].ewm(span=21).mean()
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 0.00000001)
    df["rsi"] = 100 - (100 / (1 + rs))
    df["volume_avg"] = df["volume"].rolling(20).mean()
    return df.dropna()

def analyze_market(symbol):
    try:
        df = fetch_candles(symbol)
        if df is None or len(df) < 25: return None
        prev = df.iloc[-2]; curr = df.iloc[-1]
        score_long = 0; score_short = 0
        if curr["ema9"] > curr["ema21"]: score_long += 1
        elif curr["ema9"] < curr["ema21"]: score_short += 1
        if 50 < curr["rsi"] < 68: score_long += 1
        elif 32 < curr["rsi"] < 50: score_short += 1
        if prev["ema9"] <= prev["ema21"] and curr["ema9"] > curr["ema21"]: score_long += 2
        if prev["ema9"] >= prev["ema21"] and curr["ema9"] < curr["ema21"]: score_short += 2
        if curr["volume"] > curr["volume_avg"]:
            if curr["close"] > curr["open"]: score_long += 1
            elif curr["close"] < curr["open"]: score_short += 1
        price = float(curr["close"])
        if score_long >= CONFIG["MIN_SIGNAL_SCORE"]:
            return {"symbol": symbol, "direction": "long", "score": score_long, "price": price, "rsi": round(float(curr["rsi"]),2), "time": datetime.now(timezone.utc).isoformat()}
        elif score_short >= CONFIG["MIN_SIGNAL_SCORE"]:
            return {"symbol": symbol, "direction": "short", "score": score_short, "price": price, "rsi": round(float(curr["rsi"]),2), "time": datetime.now(timezone.utc).isoformat()}
        return None
    except Exception as e:
        log.warning(f"Analysis {symbol}: {e}")
        return None

def get_free_usdt():
    bal = exchange.fetch_balance()
    return float(bal.get("USDT", {}).get("free", 0) or 0)

def has_spot_position(symbol):
    base = symbol.split("/")[0]
    bal = exchange.fetch_balance()
    return float(bal.get(base, {}).get("total", 0) or 0) > 0.00000001

def get_contract_amount(symbol, margin, price):
    market = exchange.market(symbol)
    contract_size = float(market.get("contractSize") or 1)
    notional = margin * CONFIG["LEVERAGE"]
    raw_contracts = notional / (price * contract_size)
    amount = float(exchange.amount_to_precision(symbol, raw_contracts))
    minimum = market.get("limits", {}).get("amount", {}).get("min")
    if minimum and amount < float(minimum): raise ValueError(f"Min {minimum} < {amount}")
    if amount <= 0: raise ValueError("Invalid amount")
    # حماية إضافية
    real_margin = (amount * price * contract_size) / CONFIG["LEVERAGE"]
    if real_margin > CONFIG["MAX_FUTURES_USD"]:
        raise ValueError(f"⛔ هامش {real_margin:.2f}$ > {CONFIG['MAX_FUTURES_USD']}$")
    return amount

def place_spot_trade(signal):
    if state["spot_position"] is not None: return
    symbol = signal["symbol"]
    if has_spot_position(symbol): return
    free = get_free_usdt()
    budget = min(CONFIG["SPOT_BUDGET"], free * 0.98)
    if budget < 5: return
    if signal["direction"] != "long": return
    price = signal["price"]
    amount = float(exchange.amount_to_precision(symbol, budget / price))
    market = exchange.market(symbol)
    min_cost = market.get("limits", {}).get("cost", {}).get("min")
    if min_cost and amount * price < float(min_cost): return
    validate_dollar_cap(symbol, amount, price, CONFIG["MAX_SPOT_USD"])
    log.info(f"SPOT BUY {symbol} {amount} @ {price}")
    if not CONFIG["LIVE_TRADING"]: return
    order = exchange.create_market_buy_order(symbol, amount)
    avg = float(order.get("average") or price)
    filled = float(order.get("filled") or amount)
    state["spot_position"] = {"symbol": symbol, "amount": filled, "entry": avg, "stop": avg*(1-CONFIG["STOP_LOSS"]), "target": avg*(1+CONFIG["TAKE_PROFIT"]), "opened": datetime.now(timezone.utc).isoformat()}
    state["trades"].append({"market":"spot","symbol":symbol,"side":"buy","price":avg,"amount":filled,"time":datetime.now(timezone.utc).isoformat()})
    save_state()

def set_isolated_leverage(symbol):
    exchange.set_leverage(CONFIG["LEVERAGE"], symbol, {"mgnMode": "isolated"})

def get_open_swap_position(symbol):
    positions = exchange.fetch_positions([symbol])
    for p in positions:
        if float(p.get("contracts") or 0) > 0: return p
    return None

def place_future_trade(signal):
    if state["future_position"] is not None: return
    swap = get_swap_symbol(signal["symbol"])
    if not swap: return
    if get_open_swap_position(swap): return
    free = get_free_usdt()
    margin = min(CONFIG["FUTURES_MARGIN"], free * 0.95)
    if margin < 5: return
    price = signal["price"]
    amount = get_contract_amount(swap, margin, price)
    side = "buy" if signal["direction"]=="long" else "sell"
    set_isolated_leverage(swap)
    stop_price = price*(1-CONFIG["STOP_LOSS"]) if signal["direction"]=="long" else price*(1+CONFIG["STOP_LOSS"])
    target_price = price*(1+CONFIG["TAKE_PROFIT"]) if signal["direction"]=="long" else price*(1-CONFIG["TAKE_PROFIT"])
    stop_price = exchange.price_to_precision(swap, stop_price)
    target_price = exchange.price_to_precision(swap, target_price)
    params = {"tdMode":"isolated","lever":str(CONFIG["LEVERAGE"]),"attachAlgoOrds":[{"tpTriggerPx":str(target_price),"tpOrdPx":"-1","tpTriggerPxType":"mark","slTriggerPx":str(stop_price),"slOrdPx":"-1","slTriggerPxType":"mark"}]}
    log.info(f"FUTURES {side} {swap} {amount} SL={stop_price} TP={target_price}")
    if not CONFIG["LIVE_TRADING"]: return
    order = exchange.create_order(swap, "market", side, amount, None, params)
    avg = float(order.get("average") or price)
    filled = float(order.get("filled") or 0)
    if filled <= 0: return
    state["future_position"] = {"symbol":swap,"side":signal["direction"],"amount":filled,"entry":avg,"stop":float(stop_price),"target":float(target_price),"order_id":order.get("id"),"opened":datetime.now(timezone.utc).isoformat()}
    state["trades"].append({"market":"futures","symbol":swap,"side":side,"price":avg,"amount":filled,"time":datetime.now(timezone.utc).isoformat()})
    save_state()

def monitor_spot_position():
    pos = state.get("spot_position")
    if not pos: return
    ticker = exchange.fetch_ticker(pos["symbol"])
    price = float(ticker["last"])
    if not (price <= pos["stop"] or price >= pos["target"]): return
    base = pos["symbol"].split("/")[0]
    bal = exchange.fetch_balance()
    avail = float(bal.get(base,{}).get("free",0) or 0)
    amt = min(float(pos["amount"]), avail)
    if amt <= 0:
        state["spot_position"]=None; save_state(); return
    amt = float(exchange.amount_to_precision(pos["symbol"], amt))
    if not CONFIG["LIVE_TRADING"]: return
    order = exchange.create_market_sell_order(pos["symbol"], amt)
    exit_price = float(order.get("average") or price)
    pnl = (exit_price - pos["entry"])*amt
    state["pnl"]+=pnl
    if pnl>=0: state["wins"]+=1
    else: state["losses"]+=1
    state["spot_position"]=None; save_state()

def reconcile_futures_position():
    pos = state.get("future_position")
    if not pos: return
    try:
        cur = get_open_swap_position(pos["symbol"])
        if cur: return
        log.info(f"Futures closed: {pos['symbol']}")
        state["future_position"]=None; save_state()
    except Exception as e: record_error("Futures recon: "+str(e))

def scan_and_trade():
    symbols = get_market_symbols()
    signals = []
    for symbol in symbols:
        if not state["running"]: break
        sig = analyze_market(symbol)
        if sig: signals.append(sig)
        time.sleep(0.15)
    signals.sort(key=lambda x: x["score"], reverse=True)
    state["scanned"]=len(symbols); state["signals"]=signals[:10]; state["last_scan"]=datetime.now(timezone.utc).isoformat()
    if not signals: save_state(); return
    best = signals[0]
    log.info(f"Best: {best['symbol']} {best['direction']} {best['score']}")
    if CONFIG["ALLOW_SPOT"] and best["direction"]=="long": place_spot_trade(best)
    if CONFIG["ALLOW_FUTURES"]: place_future_trade(best)
    save_state()

def run_bot():
    initialize(); load_state()
    log.info("DEATH HUNTER V30000 PRO SAFE started")
    while state["running"]:
        try:
            if CONFIG["LIVE_TRADING"]:
                monitor_spot_position(); reconcile_futures_position()
            scan_and_trade()
        except Exception as e: record_error(str(e))
        time.sleep(CONFIG["SCAN_INTERVAL"])

# ====== ROUTES - مع حماية طارئة ======
@app.route("/")
def home():
    return jsonify({"bot":"DEATH HUNTER V30000 PRO SAFE","running":state["running"],"live_trading":CONFIG["LIVE_TRADING"],"spot_budget":CONFIG["SPOT_BUDGET"],"futures_margin":CONFIG["FUTURES_MARGIN"],"leverage":CONFIG["LEVERAGE"],"scanned":state["scanned"],"last_scan":state["last_scan"],"signals":state["signals"],"spot_position":state["spot_position"],"future_position":state["future_position"],"wins":state["wins"],"losses":state["losses"],"pnl":round(state["pnl"],4),"errors":state["errors"][-5:]})

@app.route("/stop")
def stop_bot():
    state["running"]=False; save_state()
    return "<h1 style='color:red;text-align:center;margin-top:100px'>⛔ البوت توقف - ما راح يدخل صفقات<br><br><a href='/start'>تشغيل</a> | <a href='/'>الرئيسية</a></h1>"

@app.route("/start")
def start_bot():
    state["running"]=True; save_state()
    return "<h1 style='color:green;text-align:center;margin-top:100px'>✅ البوت اشتغل<br><br><a href='/stop'>إيقاف</a> | <a href='/'>الرئيسية</a></h1>"

@app.route("/close-all")
def close_all():
    try:
        if state.get("spot_position"):
            s=state["spot_position"]["symbol"]; base=s.split("/")[0]
            bal=exchange.fetch_balance(); amt=float(bal.get(base,{}).get("free",0) or 0)
            if amt>0 and CONFIG["LIVE_TRADING"]: exchange.create_market_sell_order(s, amt)
        if state.get("future_position"):
            sym=state["future_position"]["symbol"]; pos=get_open_swap_position(sym)
            if pos and CONFIG["LIVE_TRADING"]:
                side='sell' if pos['side']=='long' else 'buy'
                exchange.create_order(sym,"market",side,float(pos['contracts']),None,{"posSide":pos['side'],"mgnMode":"isolated"})
        state["spot_position"]=None; state["future_position"]=None; save_state()
        return "<h1 style='text-align:center'>✅ تم إغلاق الكل</h1><a href='/'>رجوع</a>"
    except Exception as e: return f"خطأ: {e}"

@app.route("/health")
def health(): return jsonify({"status":"online"})

if __name__ == "__main__":
    import threading
    load_state()
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","5000")), debug=False, use_reloader=False)
