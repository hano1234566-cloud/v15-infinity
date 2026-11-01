
import os
import time
import json
import logging
from datetime import datetime, timezone

import ccxt
import pandas as pd
from flask import Flask, jsonify

# =========================================================
# DEATH HUNTER V30000 - OKX MULTI COIN TRADING BOT
# Spot: 15 USDT | Futures: 5 USDT | Leverage: 3x
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
}

API_KEY = os.getenv("OKX_API_KEY", "")
API_SECRET = os.getenv("OKX_API_SECRET", "")
API_PASSWORD = os.getenv("OKX_API_PASSWORD", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("DEATH_HUNTER")

app = Flask(__name__)

exchange = ccxt.okx({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "password": API_PASSWORD,
    "enableRateLimit": True,
    "options": {
        "defaultType": "spot",
    },
})

state = {
    "running": True,
    "started": datetime.now(timezone.utc).isoformat(),
    "last_scan": None,
    "scanned": 0,
    "signals": [],
    "trades": [],
    "errors": [],
    "spot_position": None,
    "future_position": None,
    "wins": 0,
    "losses": 0,
    "pnl": 0.0,
}


def save_state():
    try:
        with open(CONFIG["STATE_FILE"], "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log.error("State save error: %s", e)


def load_state():
    global state
    try:
        with open(CONFIG["STATE_FILE"], "r") as f:
            saved = json.load(f)
            state.update(saved)
    except FileNotFoundError:
        pass
    except Exception as e:
        log.error("State load error: %s", e)


def record_error(message):
    log.error(message)
    state["errors"].append({
        "time": datetime.now(timezone.utc).isoformat(),
        "message": str(message),
    })
    state["errors"] = state["errors"][-30:]
    save_state()


def initialize():
    if not CONFIG["LIVE_TRADING"]:
        log.warning("LIVE_TRADING is disabled. No real orders will be sent.")
    if not all([API_KEY, API_SECRET, API_PASSWORD]):
        log.warning("OKX API credentials are not configured.")


def get_market_symbols():
    markets = exchange.load_markets()
    tickers = exchange.fetch_tickers()

    candidates = []

    for symbol, market in markets.items():
        try:
            if not market.get("active"):
                continue
            if not market.get("spot"):
                continue
            if market.get("quote") != "USDT":
                continue
            if market.get("base") in ("USDC", "USDT", "DAI", "FDUSD"):
                continue

            ticker = tickers.get(symbol, {})
            volume = ticker.get("quoteVolume")

            if volume is None:
                continue

            volume = float(volume)

            if volume < 1_000_000:
                continue

            candidates.append((symbol, volume))

        except Exception:
            continue

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in candidates[:CONFIG["MAX_COINS"]]]


def get_swap_symbol(spot_symbol):
    base = spot_symbol.split("/")[0]
    symbol = base + "/USDT:USDT"

    markets = exchange.markets

    if symbol not in markets:
        return None

    market = markets[symbol]

    if not market.get("swap") or not market.get("active"):
        return None

    return symbol


def fetch_candles(symbol):
    candles = exchange.fetch_ohlcv(
        symbol,
        timeframe=CONFIG["TIMEFRAME"],
        limit=CONFIG["CANDLE_LIMIT"],
    )

    df = pd.DataFrame(
        candles,
        columns=["time", "open", "high", "low", "close", "volume"]
    )

    if len(df) < 30:
        return None

    # Ignore the currently forming candle
    df = df.iloc[:-1].copy()

    df["ema9"] = df["close"].ewm(span=9).mean()
    df["ema21"] = df["close"].ewm(span=21).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, 0.00000001)
    df["rsi"] = 100 - (100 / (1 + rs))

    df["volume_avg"] = df["volume"].rolling(20).mean()

    return df.dropna()


def analyze_market(symbol):
    try:
        df = fetch_candles(symbol)

        if df is None or len(df) < 25:
            return None

        previous = df.iloc[-2]
        current = df.iloc[-1]

        score_long = 0
        score_short = 0

        # EMA direction
        if current["ema9"] > current["ema21"]:
            score_long += 1
        elif current["ema9"] < current["ema21"]:
            score_short += 1

        # RSI momentum
        if 50 < current["rsi"] < 68:
            score_long += 1
        elif 32 < current["rsi"] < 50:
            score_short += 1

        # EMA crossover
        if (
            previous["ema9"] <= previous["ema21"]
            and current["ema9"] > current["ema21"]
        ):
            score_long += 2

        if (
            previous["ema9"] >= previous["ema21"]
            and current["ema9"] < current["ema21"]
        ):
            score_short += 2

        # Volume confirmation
        if current["volume"] > current["volume_avg"]:
            if current["close"] > current["open"]:
                score_long += 1
            elif current["close"] < current["open"]:
                score_short += 1

        price = float(current["close"])

        if score_long >= CONFIG["MIN_SIGNAL_SCORE"]:
            direction = "long"
            score = score_long
        elif score_short >= CONFIG["MIN_SIGNAL_SCORE"]:
            direction = "short"
            score = score_short
        else:
            return None

        return {
            "symbol": symbol,
            "direction": direction,
            "score": score,
            "price": price,
            "rsi": round(float(current["rsi"]), 2),
            "time": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        log.warning("Analysis failed for %s: %s", symbol, e)
        return None


def get_free_usdt():
    balance = exchange.fetch_balance()
    return float(balance.get("USDT", {}).get("free", 0) or 0)


def has_spot_position(symbol):
    base = symbol.split("/")[0]
    balance = exchange.fetch_balance()
    amount = float(balance.get(base, {}).get("total", 0) or 0)

    return amount > 0.00000001


def get_contract_amount(symbol, margin, price):
    market = exchange.market(symbol)
    contract_size = float(market.get("contractSize") or 1)

    notional = margin * CONFIG["LEVERAGE"]
    raw_contracts = notional / (price * contract_size)

    amount = float(exchange.amount_to_precision(symbol, raw_contracts))

    minimum = market.get("limits", {}).get("amount", {}).get("min")

    if minimum is not None and amount < float(minimum):
        raise ValueError(
            f"Contract minimum is {minimum}; calculated amount is {amount}"
        )

    if amount <= 0:
        raise ValueError("Invalid contract amount")

    return amount


def place_spot_trade(signal):
    if state["spot_position"] is not None:
        return

    symbol = signal["symbol"]

    if has_spot_position(symbol):
        log.info("Existing spot balance found for %s. Skipping.", symbol)
        return

    free = get_free_usdt()
    budget = min(CONFIG["SPOT_BUDGET"], free * 0.98)

    if budget < 5:
        log.info("Insufficient free USDT for spot.")
        return

    if signal["direction"] != "long":
        return

    price = signal["price"]
    amount = float(exchange.amount_to_precision(symbol, budget / price))

    market = exchange.market(symbol)
    minimum_cost = market.get("limits", {}).get("cost", {}).get("min")

    if minimum_cost and amount * price < float(minimum_cost):
        log.info("Spot order below exchange minimum: %s", symbol)
        return

    log.info("SPOT BUY signal: %s amount=%s", symbol, amount)

    if not CONFIG["LIVE_TRADING"]:
        return

    order = exchange.create_market_buy_order(symbol, amount)

    average = float(order.get("average") or price)
    filled = float(order.get("filled") or amount)

    state["spot_position"] = {
        "symbol": symbol,
        "amount": filled,
        "entry": average,
        "stop": average * (1 - CONFIG["STOP_LOSS"]),
        "target": average * (1 + CONFIG["TAKE_PROFIT"]),
        "opened": datetime.now(timezone.utc).isoformat(),
    }

    state["trades"].append({
        "market": "spot",
        "symbol": symbol,
        "side": "buy",
        "price": average,
        "amount": filled,
        "time": datetime.now(timezone.utc).isoformat(),
    })

    save_state()


def set_isolated_leverage(symbol):
    exchange.set_leverage(
        CONFIG["LEVERAGE"],
        symbol,
        {"mgnMode": "isolated"},
    )


def get_open_swap_position(symbol):
    positions = exchange.fetch_positions([symbol])

    for position in positions:
        contracts = float(position.get("contracts") or 0)

        if contracts > 0:
            return position

    return None


def place_future_trade(signal):
    if state["future_position"] is not None:
        return

    swap_symbol = get_swap_symbol(signal["symbol"])

    if not swap_symbol:
        return

    existing = get_open_swap_position(swap_symbol)

    if existing:
        log.info("Existing futures position found for %s. Skipping.", swap_symbol)
        return

    free = get_free_usdt()
    margin = min(CONFIG["FUTURES_MARGIN"], free * 0.95)

    if margin < 5:
        log.info("Insufficient free USDT for futures.")
        return

    price = signal["price"]
    amount = get_contract_amount(swap_symbol, margin, price)

    side = "buy" if signal["direction"] == "long" else "sell"

    set_isolated_leverage(swap_symbol)

    entry_price = price

    if signal["direction"] == "long":
        stop_price = price * (1 - CONFIG["STOP_LOSS"])
        target_price = price * (1 + CONFIG["TAKE_PROFIT"])
    else:
        stop_price = price * (1 + CONFIG["STOP_LOSS"])
        target_price = price * (1 - CONFIG["TAKE_PROFIT"])

    stop_price = exchange.price_to_precision(swap_symbol, stop_price)
    target_price = exchange.price_to_precision(swap_symbol, target_price)

    params = {
        "tdMode": "isolated",
        "lever": str(CONFIG["LEVERAGE"]),
        "attachAlgoOrds": [{
            "tpTriggerPx": str(target_price),
            "tpOrdPx": "-1",
            "tpTriggerPxType": "mark",
            "slTriggerPx": str(stop_price),
            "slOrdPx": "-1",
            "slTriggerPxType": "mark",
        }],
    }

    log.info(
        "FUTURES %s %s amount=%s entry=%s SL=%s TP=%s",
        side, swap_symbol, amount, price, stop_price, target_price
    )

    if not CONFIG["LIVE_TRADING"]:
        return

    order = exchange.create_order(
        swap_symbol,
        "market",
        side,
        amount,
        None,
        params,
    )

    average = float(order.get("average") or price)
    filled = float(order.get("filled") or 0)

    if filled <= 0:
        log.warning("Futures order has no confirmed fill.")
        return

    state["future_position"] = {
        "symbol": swap_symbol,
        "side": signal["direction"],
        "amount": filled,
        "entry": average,
        "stop": float(stop_price),
        "target": float(target_price),
        "order_id": order.get("id"),
        "opened": datetime.now(timezone.utc).isoformat(),
    }

    state["trades"].append({
        "market": "futures",
        "symbol": swap_symbol,
        "side": side,
        "price": average,
        "amount": filled,
        "time": datetime.now(timezone.utc).isoformat(),
    })

    save_state()


def monitor_spot_position():
    position = state.get("spot_position")

    if not position:
        return

    symbol = position["symbol"]

    ticker = exchange.fetch_ticker(symbol)
    price = float(ticker["last"])

    should_close = (
        price <= position["stop"]
        or price >= position["target"]
    )

    if not should_close:
        return

    base = symbol.split("/")[0]
    balance = exchange.fetch_balance()
    available = float(balance.get(base, {}).get("free", 0) or 0)

    amount = min(float(position["amount"]), available)

    if amount <= 0:
        log.warning("No available spot amount to close.")
        state["spot_position"] = None
        save_state()
        return

    amount = float(exchange.amount_to_precision(symbol, amount))

    log.warning("Closing spot position: %s", symbol)

    if not CONFIG["LIVE_TRADING"]:
        return

    order = exchange.create_market_sell_order(symbol, amount)

    exit_price = float(order.get("average") or price)
    pnl = (exit_price - position["entry"]) * amount

    state["pnl"] += pnl

    if pnl >= 0:
        state["wins"] += 1
    else:
        state["losses"] += 1

    state["spot_position"] = None
    save_state()


def reconcile_futures_position():
    position = state.get("future_position")

    if not position:
        return

    try:
        current = get_open_swap_position(position["symbol"])

        if current:
            return

        log.info("Futures position is no longer open: %s", position["symbol"])

        # The exchange-managed TP/SL may have closed the position.
        # Realized PnL must be reconciled from exchange bills/fills.
        state["future_position"] = None
        save_state()

    except Exception as e:
        record_error("Futures reconciliation: " + str(e))


def scan_and_trade():
    symbols = get_market_symbols()
    signals = []

    for symbol in symbols:
        if not state["running"]:
            break

        signal = analyze_market(symbol)

        if signal:
            signals.append(signal)

        time.sleep(0.15)

    signals.sort(key=lambda x: x["score"], reverse=True)

    state["scanned"] = len(symbols)
    state["signals"] = signals[:10]
    state["last_scan"] = datetime.now(timezone.utc).isoformat()

    if not signals:
        log.info("No valid trading opportunities.")
        save_state()
        return

    best = signals[0]

    log.info(
        "Best opportunity: %s %s score=%s",
        best["symbol"],
        best["direction"],
        best["score"],
    )

    if CONFIG["ALLOW_SPOT"]:
        if best["direction"] == "long":
            place_spot_trade(best)

    if CONFIG["ALLOW_FUTURES"]:
        place_future_trade(best)

    save_state()


def run_bot():
    initialize()
    load_state()

    log.info("DEATH HUNTER V30000 started.")

    while state["running"]:
        try:
            if CONFIG["LIVE_TRADING"]:
                monitor_spot_position()
                reconcile_futures_position()

            scan_and_trade()

        except Exception as e:
            record_error(str(e))

        time.sleep(CONFIG["SCAN_INTERVAL"])


@app.route("/")
def home():
    return jsonify({
        "bot": "DEATH HUNTER V30000",
        "running": state["running"],
        "live_trading": CONFIG["LIVE_TRADING"],
        "spot_budget": CONFIG["SPOT_BUDGET"],
        "futures_margin": CONFIG["FUTURES_MARGIN"],
        "leverage": CONFIG["LEVERAGE"],
        "scanned_coins": state["scanned"],
        "last_scan": state["last_scan"],
        "signals": state["signals"],
        "spot_position": state["spot_position"],
        "future_position": state["future_position"],
        "wins": state["wins"],
        "losses": state["losses"],
        "pnl": round(state["pnl"], 4),
        "errors": state["errors"][-5:],
    })


@app.route("/health")
def health():
    return jsonify({"status": "online"})


if __name__ == "__main__":
    import threading

    load_state()

    worker = threading.Thread(target=run_bot, daemon=True)
    worker.start()

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=False,
        use_reloader=False,
    )
