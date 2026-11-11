# V30030 MERGED CORRECTED - UI version: same interface layout as screenshot, live OKX numbers
# Correction 2026-11-04: OKX secret now uses V30026 working names:
#   OKX_SECRET_KEY primary, OKX_SECRET fallback (merged draft used ONLY OKX_SECRET,
#   so a key set as OKX_SECRET_KEY was ignored - that was a key-name bug, fixed here).
# Base: V30030 as found on GitHub (workspace/bot/v30030_github.py)
#   - kept: its run-loop structure, USD_PER_TRADE=5, get_amount, raise-stop-only logic
#   - V30030 itself is preserved locally, so nothing is lost by choosing this draft
# Merged in from the fixed draft (workspace/bot/v30029_fixed_draft.py):
#   - final 60-coin list: CFX in, PEOPLE out (V30030 had 61, both in)
#   - real trial opening for NEAR/ARB only, $5 notional, 5x isolated,
#     skipping symbols already open, printing amount before and
#     contracts/entryPrice/notional after opening
#   - real stop attempt (stop_market via ccxt) instead of V30030's commented-out
#     stop line; state is saved ONLY if the exchange returns an order id
#   - old open positions are logged even if not in the list
# NOT verified live: the real stop conversion uses pos['contracts'] as size and
# the stop_market params have NOT been confirmed against a live OKX position.
# Test on the $5 NEAR/ARB trial first and read the order back before trusting it.
# V30032 change 2026-11-04 evening: posSide 'net' FAILED live (Render logs 18:25 still 51000).
# This draft sends posSide by position side instead: 'long' for long, 'short' for short.
# Also: stop orders are skipped (not sent) when the trigger would be on the wrong side
# of the last price (long trigger >= last, short trigger <= last) — that was OKX 51280.
# V30033 change 2026-11-04 evening (DRAFT ONLY, NOT PUSHED):
# V30032 FAILED its live test (Render logs 18:47: partial closes now 51169
# 'no positions in this direction', stop orders SKIPped by the guard, e.g. STX
# trigger 0.3857 vs last 0.3436). Two hypotheses, both addressed here, nothing else changed:
# (1) Close orders sent NO tdMode, while the open order sends tdMode='isolated' and the
#     old positions are isolated — OKX may therefore look for a cross position and fail
#     with 51169. This draft adds 'tdMode': 'isolated' to stop, emergency and partial orders.
# (2) Stop trigger used contracts as coins. STX: 15 contracts x 10 coins = 150 coins;
#     old trigger 0.3324 + 0.80/15 = 0.3857 (above last price, correctly SKIPped),
#     corrected 0.3324 + 0.80/150 = 0.3377 (below last price, guard passes).
#     This draft derives coin size from pos notional/entry when available
#     (size_coins = notional / entry), falling back to contracts with a warning,
#     instead of hard-coding 10 for every coin. Order sizes stay in contracts.
# Thresholds, coin list, leverage, $5 notional, fees and partial/emergency levels UNCHANGED.
# Do NOT push until the user approves this exact file (stop-after-failure rule).
# Muse does NOT run this live; the user runs it himself on Render with his own
# OKX keys. Do NOT push until the user approves this exact file.
# V30036 change 2026-11-11 (protection fixes only, from external code review
# CODE-REVIEW-001, approved by the owner). FOUR fixes, nothing else:
# (1) Initial stop: check_positions now places the stop at the CURRENT level
#     (starting at LOSS_FIXED -0.20) whenever no stop order is proven in state
#     (no order_id), not only when the level rises. State updates only on a
#     confirmed placement; a price-side guard skip leaves state untouched so
#     placement is retried next cycle.
# (2) Position counting: open_trial_positions ABORTS opening entirely if
#     fetch_positions fails (no more continuing with an empty dict), and counts
#     every position with contracts > 0 in a list instead of a symbol dict.
# (3) State cleanup: check_positions deletes state entries whose symbol is no
#     longer actually open, saving once if anything was removed.
# (4) Post-close verification: emergency close deletes state and prints
#     "closed" ONLY after re-fetching positions and confirming the position is
#     gone (else prints EMERGENCY CLOSE UNCONFIRMED and keeps state); partial
#     close sets partial_closed ONLY after verifying contracts decreased (else
#     prints PARTIAL CLOSE UNCONFIRMED and leaves the flag unset).
# ALL financial constants UNCHANGED: LOSS_FIXED -0.20, FEE 0.04, LEVELS,
# PARTIAL_CLOSE_NET 1.20, PARTIAL_CLOSE_FRACTION 0.5, LEVERAGE 5,
# USD_PER_TRADE 5, MAX_OPEN_TRADES 6, EMERGENCY_CLOSE_NET -1.00, COINS_60.
# DRAFT — لا يُدفع إلا باعتماد المالك لهذا الملف بالضبط.
# (Do NOT push unless the owner approves THIS exact file.)

import ccxt, os, json, time, threading
from datetime import datetime
# UI cache, updated by a background scanner, so the homepage is fast.
# Numbers on the page are LIVE from OKX, never copied from a screenshot.
UI_CACHE = {'total_net': 0.0, 'open_count': 0, 'scanned': 0, 'current': '', 'rsi_list': [], 'open_list': [], 'updated': ''}

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, period + 1):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)

def ui_scanner():
    idx = 0
    while True:
        try:
            poss = exchange.fetch_positions()
            total = 0.0
            open_count = 0
            open_list = []
            for pos in poss:
                if float(pos.get('contracts', 0) or 0) > 0:
                    open_count += 1
                    net_p = float(pos.get('unrealizedPnl', 0) or 0) - 0.04
                    total += net_p
                    open_list.append({'coin': pos['symbol'].split('/')[0], 'side': pos.get('side'), 'entry': pos.get('entryPrice'), 'contracts': pos.get('contracts'), 'net': round(net_p, 2)})
            # Scan 5 coins per cycle, rotating, like the old 5/60 UI.
            batch = COINS_60[idx:idx+5]
            if not batch:
                idx = 0
                batch = COINS_60[0:5]
            rsi_list = []
            for symbol in batch:
                try:
                    ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=20)
                    closes = [c[4] for c in ohlcv]
                    rsi = calc_rsi(closes)
                    price = closes[-1] if closes else 0
                    coin = symbol.split('/')[0]
                    rsi_list.append({'coin': coin, 'rsi': rsi, 'price': price})
                except Exception:
                    continue
            UI_CACHE.update({'total_net': round(total, 2), 'open_count': open_count, 'open_list': open_list, 'scanned': min(idx+5, 60), 'current': batch[0].split('/')[0] if batch else '', 'rsi_list': rsi_list, 'updated': datetime.now().strftime('%H:%M:%S')})
            idx = (idx + 5) % 60
        except Exception as e:
            print(f"[UI] scanner error: {e}")
        time.sleep(60)

try:
    from flask import Flask
    app = Flask(__name__)
    @app.route('/')
    def home():
        cards = ''
        for item in UI_CACHE['rsi_list']:
            cards += f"<div class='card'><div><b>{item['coin']}</b> <span class='long'>LONG</span></div><div class='sub'>RSI {item['rsi']} ${item['price']:.4f}</div></div>"
        if not cards:
            cards = "<div class='card'>جاري فحص العملات... انتظر دقيقة</div>"
        open_cards = ''
        for item in UI_CACHE['open_list']:
            open_cards += f"<div class='card'><div><b>{item['coin']}</b> {item['side']}</div><div class='sub'>دخول {item['entry']} | عقود {item['contracts']} | صافي ${item['net']}</div></div>"
        if not open_cards:
            open_cards = "<div class='card'>لا توجد صفقات مفتوحة ظاهرة الآن</div>"
        return f'''<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V30030</title><style>body{{background:#000;color:#fff;font-family:system-ui;margin:0;padding:12px}} .top{{border:2px solid #1a7a3a;border-radius:20px;padding:16px;background:#111}} .big{{font-size:42px;font-weight:bold}} .pill{{background:#f5b301;color:#000;border-radius:20px;padding:4px 12px;display:inline-block}} .card{{border:2px solid #1a7a3a;border-radius:16px;padding:12px;margin:10px 0;background:#0d1a2a}} .long{{background:#22c55e;color:#000;border-radius:12px;padding:2px 8px;font-size:12px}} .sub{{color:#aaa;margin-top:6px}} .btn{{background:#1a2a3a;border-radius:20px;padding:6px 14px;display:inline-block;margin:4px}} h2{{margin:20px 0 0}}</style></head><body><div class="top"><div>60 <span style="float:left">V30030 عقد صحيح 🟢</span></div><div class="big">${UI_CACHE['total_net']}</div><div>صافي كلي (بعد 0.04 رسوم لكل صفقة)</div><div>🔍 فحص LIVE - {UI_CACHE['current']} &nbsp; {UI_CACHE['scanned']}/60</div><div><span class="btn">{UI_CACHE['open_count']}/2 مفتوح</span> <span class="btn">{UI_CACHE['scanned']}/60</span></div><div>آخر تحديث: {UI_CACHE['updated']}</div></div><h2>📈 الصفقات المفتوحة</h2>{open_cards}<h2>📊 كل العملات RSI</h2>{cards}</body></html>''', 200
    @app.route('/health')
    def health():
        return {'bot': 'v30030_merged_corrected', 'live': True}, 200
except Exception:
    app = None

COINS_60 = ["BTC/USDT:USDT","ETH/USDT:USDT","SOL/USDT:USDT","AVAX/USDT:USDT","NEAR/USDT:USDT","ARB/USDT:USDT","W/USDT:USDT","ENA/USDT:USDT","TIA/USDT:USDT","WIF/USDT:USDT","1000PEPE/USDT:USDT","1000BONK/USDT:USDT","OP/USDT:USDT","STRK/USDT:USDT","APT/USDT:USDT","SUI/USDT:USDT","SEI/USDT:USDT","JUP/USDT:USDT","PYTH/USDT:USDT","RENDER/USDT:USDT","FET/USDT:USDT","AGIX/USDT:USDT","INJ/USDT:USDT","RUNE/USDT:USDT","LDO/USDT:USDT","STX/USDT:USDT","IMX/USDT:USDT","FLOW/USDT:USDT","MANA/USDT:USDT","SAND/USDT:USDT","AXS/USDT:USDT","CHZ/USDT:USDT","GALA/USDT:USDT","APE/USDT:USDT","BLUR/USDT:USDT","MEME/USDT:USDT","ORDI/USDT:USDT","1000SATS/USDT:USDT","DOGE/USDT:USDT","SHIB/USDT:USDT","LTC/USDT:USDT","BCH/USDT:USDT","ETC/USDT:USDT","DOT/USDT:USDT","LINK/USDT:USDT","MATIC/USDT:USDT","ADA/USDT:USDT","XRP/USDT:USDT","TRX/USDT:USDT","FIL/USDT:USDT","ATOM/USDT:USDT","XLM/USDT:USDT","VET/USDT:USDT","HBAR/USDT:USDT","ALGO/USDT:USDT","EGLD/USDT:USDT","KAVA/USDT:USDT","KLAY/USDT:USDT","ZIL/USDT:USDT","CFX/USDT:USDT"]
# 60 coins exactly: CFX in, PEOPLE out (final list confirmed 2026-11-03).

STATE_FILE = "state.json"
LOSS_FIXED = -0.20
FEE = 0.04
LEVELS = [(0.30, 0.10), (0.80, 0.50), (1.20, 0.80), (2.00, 1.40), (3.00, 2.50), (5.00, 4.20)]
# Best profit-taking, added 2026-11-04 on user 'add the best':
# - Closer trailing stops at high profits (3.00->2.50, 5.00->4.20) so less peak profit is given back.
# - Partial close: first time net >= 1.20, close 50% at market, lock that profit, rest runs with trailing stop.
PARTIAL_CLOSE_NET = 1.20
PARTIAL_CLOSE_FRACTION = 0.5
LEVERAGE = 5
USD_PER_TRADE = 5
MAX_OPEN_TRADES = 6  # User approved 2026-11-05: 6 open trades TOTAL, including already-open ones
# Emergency close, authorized by user 2026-11-04: if a trade is still open and net <= -1.00,
# the stop has failed to close it, so close it at market immediately to keep loss small.
# -1.00 is the max emergency loss per trade in this version, not -12, not unlimited.
EMERGENCY_CLOSE_NET = -1.00

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f: return json.load(f)
        except: return {}
    return {}

def save_state(s):
    with open(STATE_FILE, 'w') as f: json.dump(s, f)

def net_profit(gross): return float(gross) - FEE

def get_stop_only_up(net, curr):
    target = LOSS_FIXED
    for p, sl in LEVELS:
        if net >= p: target = sl
    return max(target, curr)  # يطلع فقط، أبداً ما ينزل

# Exact working key names from V30026 FINAL BLACK - do NOT change these names.
API_KEY = os.getenv("OKX_API_KEY", "").strip()
SECRET = (os.getenv("OKX_SECRET_KEY", "") or os.getenv("OKX_SECRET", "")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE", "").strip()
# Bool only, never print key values.
print(f"KEYS OKX_API_KEY={bool(API_KEY)} OKX_SECRET={bool(SECRET)} OKX_PASSPHRASE={bool(PASSPHRASE)}")

exchange = ccxt.okx({
    'apiKey': API_KEY,
    'secret': SECRET,
    'password': PASSPHRASE,
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

def get_amount(symbol, usd):
    ticker = exchange.fetch_ticker(symbol)
    price = ticker['last']
    amt = exchange.amount_to_precision(symbol, usd / price)
    print(f"CALC {symbol} price={price} usd={usd} => amount={amt} ~ {float(amt) * price:.2f}$")
    return amt

def select_strong_coins(limit=MAX_OPEN_TRADES):
    """Strong-chart selection, NOT fixed NEAR/ARB.
    User rule 2026-11-04: entry coin is not necessarily NEAR/ARB, important is
    the chart is strong for entry.
    Strong = defined here, transparently, so it can be tuned after live test:
      - fetch 1h OHLCV, last 50 candles
      - 24h-style momentum: last close > close 24 candles ago
      - trend: last close > simple average of last 20 closes
      - volume: last candle volume > average volume of last 20
    Coins failing any filter are skipped. Rank passing coins by momentum %.
    If NO coin passes, return [] (do NOT fall back to a weak coin blindly).
    This is NOT a proven profitable signal, it is a transparent filter to test.
    """
    scored = []
    for symbol in COINS_60:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe="1h", limit=50)
            if len(ohlcv) < 25:
                continue
            closes = [c[4] for c in ohlcv]
            volumes = [c[5] for c in ohlcv]
            last = closes[-1]
            prev24 = closes[-25]
            avg20 = sum(closes[-20:]) / 20
            avg_vol20 = sum(volumes[-20:]) / 20
            momentum_pct = (last - prev24) / prev24 * 100 if prev24 else 0
            if last <= prev24:
                continue
            if last <= avg20:
                continue
            if volumes[-1] <= avg_vol20:
                continue
            scored.append((momentum_pct, symbol))
        except Exception as e:
            print(f"[SELECT] {symbol} skipped: {e}")
            continue
    scored.sort(reverse=True)
    result = [s for _, s in scored[:limit]]
    print(f"[SELECT] Strong coins: {result} from {len(scored)} passing filters")
    return result


def position_size_coins(pos, contracts):
    # Coins, not contracts, for the stop-trigger price only. Order sizes stay in contracts.
    # notional ~= contracts * contract_size * entry, so coins = notional / entry.
    try:
        notional = float(pos.get('notional') or 0)
        entry = float(pos.get('entryPrice') or 0)
        if notional > 0 and entry > 0:
            return notional / entry
    except Exception:
        pass
    print(f"[{pos.get('symbol')}] WARN: no usable notional/entry, falling back to contracts as coins")
    return contracts

def profit_dollar_to_trigger_price(entry_price, desired_profit_dollar, position_size_coins, side='long'):
    # LONG: trigger = entry + desired_profit / size; SHORT: entry - desired_profit / size
    # TODO: confirm the size field on a real position before live use: contracts
    # here may be contracts, not coins, which changes the trigger price.
    if not entry_price or not position_size_coins or position_size_coins <= 0:
        return None
    per_coin = desired_profit_dollar / position_size_coins
    return entry_price + per_coin if side == 'long' else entry_price - per_coin

def place_stop_loss_real(symbol, trigger_price, position_size, side='long', last_price=None):
    # Returns (True, order_id) only if the exchange confirms, else (False, None).
    pos_side = 'long' if side == 'long' else 'short'
    if last_price:
        if side == 'long' and trigger_price >= last_price:
            print(f"[{symbol}] SKIP SL: trigger={trigger_price} >= last={last_price} (would fail OKX 51280)")
            return False, None
        if side == 'short' and trigger_price <= last_price:
            print(f"[{symbol}] SKIP SL: trigger={trigger_price} <= last={last_price} (would fail OKX 51280)")
            return False, None
    try:
        order_side = 'sell' if side == 'long' else 'buy'
        order = exchange.create_order(symbol, 'stop_market', order_side, position_size, None,
                                      {'stopLossPrice': trigger_price, 'reduceOnly': True, 'tdMode': 'isolated', 'posSide': pos_side})
        order_id = order.get('id') if isinstance(order, dict) else None
        print(f"[{symbol}] REAL SL placed trigger={trigger_price} id={order_id}")
        return (order_id is not None), order_id
    except Exception as e:
        print(f"SL Error {symbol}: {e}")
        return False, None

def open_trial_positions(symbols=None, usd=USD_PER_TRADE, leverage=LEVERAGE):
    # Once at startup only, NOT every loop. $5 notional per position
    # (margin about $1 at 5x isolated, NOT $5 margin / $25 notional).
    # User rule: symbols are NOT fixed to NEAR/ARB. Select strong-chart coins.
    if symbols is None:
        symbols = select_strong_coins(limit=MAX_OPEN_TRADES)
        if not symbols:
            print("[OPEN] No strong-chart coin passed filters, opening NOTHING this cycle.")
            return
    try:
        # V30036 fix (2): count EVERY open position (contracts > 0) in a list,
        # not one entry per symbol in a dict; and if fetch_positions fails,
        # ABORT opening entirely instead of continuing with an empty count.
        existing = []
        try:
            for pos in exchange.fetch_positions():
                if float(pos.get('contracts', 0) or 0) > 0:
                    existing.append(pos)
        except Exception as e:
            print(f"[OPEN] ABORT: fetch existing positions failed: {e} - opening NOTHING this cycle.")
            return
        if len(existing) >= MAX_OPEN_TRADES:
            print(f"[OPEN] SKIP NEW: {len(existing)} trades already open, managing old trades first, no new trades.")
            return
        slots = MAX_OPEN_TRADES - len(existing)
        opened = 0
        for symbol in symbols:
            if opened >= slots:
                print(f"[OPEN] CAP: open-trade limit {MAX_OPEN_TRADES} total reached, no more new trades.")
                break
            already = [p for p in existing if p['symbol'] == symbol]
            if already:
                pos = already[0]
                print(f"[{symbol}] SKIP OPEN: already open contracts={pos.get('contracts')} entryPrice={pos.get('entryPrice')}")
                continue
            try:
                exchange.set_leverage(leverage, symbol, {'mgnMode': 'isolated'})
            except Exception as e:
                print(f"[{symbol}] set_leverage failed (continuing, check OKX settings): {e}")
            amount = get_amount(symbol, usd)
            try:
                order = exchange.create_market_buy_order(symbol, float(amount),
                                                         {'tdMode': 'isolated', 'posSide': 'long'})
                print(f"[{symbol}] OPEN order id={order.get('id') if isinstance(order, dict) else order}")
                opened += 1
            except Exception as e:
                print(f"[{symbol}] OPEN FAILED: {e}")
                continue
            try:
                time.sleep(2)
                for pos in exchange.fetch_positions():
                    if pos['symbol'] == symbol and pos.get('contracts'):
                        print(f"[{symbol}] OPEN LOG AFTER: contracts={pos.get('contracts')} entryPrice={pos.get('entryPrice')} notional={pos.get('notional')} side={pos.get('side')}")
                        break
            except Exception as e:
                print(f"[{symbol}] verify position failed: {e}")
    except Exception as e:
        print(f"open_trial_positions error: {e}")

def check_positions():
    state = load_state()
    try:
        positions = exchange.fetch_positions()
        open_syms = [p['symbol'] for p in positions if float(p.get('contracts', 0) or 0) > 0]
        print(f"OPEN NOW: {open_syms}")
        # V30036 fix (3): drop state entries for symbols no longer actually
        # open, so a later new position on the same symbol cannot inherit a
        # stale stop level or partial_closed flag. Keys stay symbol-based.
        stale = [s for s in list(state.keys()) if s not in open_syms]
        if stale:
            for s in stale:
                del state[s]
                print(f"[STATE] removed stale entry for no-longer-open symbol {s}")
            save_state(state)
        for pos in positions:
            symbol = pos['symbol']
            contracts = float(pos.get('contracts', 0) or 0)
            if contracts == 0: continue
            gross = pos.get('unrealizedPnl', 0)
            net = net_profit(gross)
            # Manage EVERY open position, old or new, in-list or not.
            # User rule 2026-11-04: trades must be present whether old or new, and bot follows them.
            # Previously old trades outside COINS_60 were logged only and skipped for stop/partial/emergency.
            print(f"PERF {symbol} side={pos.get('side')} entry={pos.get('entryPrice')} contracts={contracts} gross={gross} net_after_fee={net:.2f} in_list={symbol in COINS_60} MANAGED=True")
            # Emergency act: stop failed, position still open and bleeding past -1.00.
            if net <= EMERGENCY_CLOSE_NET:
                try:
                    close_side = 'sell' if pos.get('side', 'long') == 'long' else 'buy'
                    pos_side = 'long' if pos.get('side', 'long') == 'long' else 'short'
                    order = exchange.create_order(symbol, 'market', close_side, contracts, None, {'reduceOnly': True, 'tdMode': 'isolated', 'posSide': pos_side})
                    oid = order.get('id') if isinstance(order, dict) else None
                    # V30036 fix (4a): verify BEFORE claiming the close and
                    # BEFORE deleting state - re-fetch positions and confirm
                    # this symbol is gone or its contracts are zero. If it is
                    # still open (or verification itself failed), keep state;
                    # the main loop retries the emergency close next cycle.
                    still_open = None
                    try:
                        for p2 in exchange.fetch_positions():
                            if p2['symbol'] == symbol:
                                still_open = float(p2.get('contracts', 0) or 0)
                                break
                        if still_open is None:
                            still_open = 0.0
                    except Exception as ve:
                        print(f"[EMERGENCY CLOSE] {symbol} post-close verify failed: {ve}")
                        still_open = None
                    if still_open == 0.0:
                        print(f"[EMERGENCY CLOSE] {symbol} net={net:.2f} closed at market id={oid}")
                        if symbol in state:
                            del state[symbol]
                            save_state(state)
                    else:
                        print(f"[EMERGENCY CLOSE UNCONFIRMED] {symbol} net={net:.2f} order id={oid} contracts after={still_open} - state kept, will retry next cycle")
                except Exception as e:
                    print(f"[EMERGENCY CLOSE FAILED] {symbol} net={net:.2f} error={e}")
                continue
            # Partial close: first time only, lock half the profit at market.
            if net >= PARTIAL_CLOSE_NET and not state.get(symbol, {}).get('partial_closed'):
                try:
                    close_side = 'sell' if pos.get('side', 'long') == 'long' else 'buy'
                    partial_amt = contracts * PARTIAL_CLOSE_FRACTION
                    pos_side = 'long' if pos.get('side', 'long') == 'long' else 'short'
                    order = exchange.create_order(symbol, 'market', close_side, partial_amt, None, {'reduceOnly': True, 'tdMode': 'isolated', 'posSide': pos_side})
                    oid = order.get('id') if isinstance(order, dict) else None
                    # V30036 fix (4b): set partial_closed ONLY after verifying
                    # the contracts actually decreased versus before the order.
                    # If they did not decrease, or verification failed, leave
                    # the flag unset so the partial close is retried later.
                    after_contracts = None
                    try:
                        for p2 in exchange.fetch_positions():
                            if p2['symbol'] == symbol:
                                after_contracts = float(p2.get('contracts', 0) or 0)
                                break
                    except Exception as ve:
                        print(f"[PARTIAL CLOSE] {symbol} post-close verify failed: {ve}")
                    if after_contracts is not None and after_contracts < contracts:
                        print(f"[PARTIAL CLOSE] {symbol} net={net:.2f} closed 50% id={oid} contracts {contracts}->{after_contracts}")
                        state[symbol] = {**state.get(symbol, {}), 'partial_closed': True, 'partial_net': net, 'partial_time': str(datetime.now())}
                        save_state(state)
                    else:
                        print(f"[PARTIAL CLOSE UNCONFIRMED] {symbol} net={net:.2f} order id={oid} contracts before={contracts} after={after_contracts} - flag NOT set, will retry")
                except Exception as e:
                    print(f"[PARTIAL CLOSE FAILED] {symbol} net={net:.2f} error={e}")
            curr = state.get(symbol, {}).get('sl', LOSS_FIXED)
            new = get_stop_only_up(net, curr)
            print(f"[{symbol}] gross={gross} net={net:.2f} contracts={contracts} SL {curr}->{new}")
            # V30036 fix (1): initial stop. Previously place_stop_loss_real ran
            # ONLY when the level rose (new > curr), so a fresh position never
            # got its -0.20 stop on the exchange. Now, if no stop order is
            # proven in state (no order_id recorded), place the stop at the
            # CURRENT level (new == curr, starting at LOSS_FIXED) as well.
            # State is updated only on success (same pattern as before); if
            # the price-side guard inside place_stop_loss_real skips it, state
            # stays untouched and placement is retried next cycle.
            if new > curr or not state.get(symbol, {}).get('order_id'):
                size_coins = position_size_coins(pos, contracts)
                trigger = profit_dollar_to_trigger_price(pos.get('entryPrice'), new, size_coins, pos.get('side', 'long'))
                if trigger is None:
                    print(f"{symbol} SKIP: cannot compute trigger price")
                    continue
                print(f"{symbol} NET:{net:.2f} -> UP SL ${curr} => ${new} trigger={trigger}")
                ok, order_id = place_stop_loss_real(symbol, trigger, contracts, pos.get('side', 'long'), pos.get('markPrice') or pos.get('lastPrice'))
                if ok:
                    state[symbol] = {**state.get(symbol, {}), 'sl': new, 'trigger': trigger, 'order_id': order_id, 'net': net, 'time': str(datetime.now())}
                    save_state(state)
                else:
                    print(f"{symbol} STOP NOT PLACED - state NOT updated")
    except Exception as e:
        print(f"check error: {e}")

def run():
    print(f"V30030 MERGED - ONLY_UP - NET_AFTER_FEE - {datetime.now()}")
    if app is not None:
        threading.Thread(target=ui_scanner, daemon=True).start()
        threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000))), daemon=True).start()
    print(f"LOSS {LOSS_FIXED} FEE {FEE} LEVELS {LEVELS} ONLY_UP COINS={len(COINS_60)}")
    try:
        _existing = {p['symbol'] for p in exchange.fetch_positions() if p.get('contracts')}
        print(f"OLD OPEN POSITIONS: {sorted(_existing)}")
    except Exception as e:
        print(f"fetch old positions failed: {e}")
    # Trial only: NEAR/ARB $5, skipped if already open.
    open_trial_positions()
    while True:
        try:
            check_positions()
            time.sleep(5)
        except Exception as e:
            print(f"ERR {e}")
            time.sleep(3)

if __name__ == "__main__":
    run()
