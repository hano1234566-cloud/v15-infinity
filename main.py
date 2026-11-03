import ccxt, os, json, time, threading
from datetime import datetime
from flask import Flask, jsonify

# ===== الإعدادات =====
COINS_60 = [
"ARB/USDT:USDT","NEAR/USDT:USDT","STRK/USDT:USDT","OP/USDT:USDT","APT/USDT:USDT",
"SOL/USDT:USDT","AVAX/USDT:USDT","W/USDT:USDT","ENA/USDT:USDT","TIA/USDT:USDT",
"WIF/USDT:USDT","1000PEPE/USDT:USDT","1000BONK/USDT:USDT","SEI/USDT:USDT","JUP/USDT:USDT",
"PYTH/USDT:USDT","RENDER/USDT:USDT","FET/USDT:USDT","SUI/USDT:USDT","BTC/USDT:USDT",
"ETH/USDT:USDT","DOGE/USDT:USDT","SHIB/USDT:USDT","DOT/USDT:USDT","LINK/USDT:USDT",
"ADA/USDT:USDT","XRP/USDT:USDT","LTC/USDT:USDT","MATIC/USDT:USDT","ETC/USDT:USDT",
"FIL/USDT:USDT","ATOM/USDT:USDT","TRX/USDT:USDT","BCH/USDT:USDT","AAVE/USDT:USDT"
]

# عملاتك السبوت الرئيسية - ما يفتح عليها فيوتشر عشان ما تتضاعف الخسارة
SPOT_RESERVE = ["AAVE/USDT:USDT", "DOGE/USDT:USDT"] 
DUST_COINS = ["XPL","SOPH","WIF","WET","CORE","ARB","AVAX","BONK"] # اللي <0.01$ حسب صورتك

STATE_FILE="state.json"
LOSS_FIXED=-0.20
FEE=0.04
LEVELS=[(0.30,0.10),(0.80,0.50),(1.20,0.80),(2.00,1.40),(5.00,3.00)]
LEVERAGE=5
USD_PER_TRADE=5
MAX_OPEN=5

app = Flask(__name__)
state_global = {}
open_global = []
spot_global = []

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE,'r') as f: return json.load(f)
        except: return {}
    return {}
def save_state(s):
    with open(STATE_FILE,'w') as f: json.dump(s,f)

def net_profit(g): 
    try: return float(g) - FEE
    except: return -10

def get_stop_only_up(net,curr):
    target=LOSS_FIXED
    for p,sl in LEVELS:
        if net>=p: target=sl
    return max(target,curr)

exchange = ccxt.okx({
    'apiKey': os.getenv('OKX_API_KEY'),
    'secret': os.getenv('OKX_SECRET'),
    'password': os.getenv('OKX_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})
exchange_spot = ccxt.okx({
    'apiKey': os.getenv('OKX_API_KEY'),
    'secret': os.getenv('OKX_SECRET'),
    'password': os.getenv('OKX_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

def get_amount(sym, usd):
    try:
        t = exchange.fetch_ticker(sym)
        price = t['last']
        amt = exchange.amount_to_precision(sym, usd/price)
        return float(amt)
    except Exception as e:
        print(f"AMOUNT ERR {sym} {e}")
        return 0

def get_spot_holdings():
    try:
        bal = exchange_spot.fetch_balance()
        spots=[]
        for coin in bal['total']:
            amt = bal['total'][coin]
            if amt and amt > 0.00001 and coin != 'USDT':
                try:
                    if f"{coin}/USDT" in exchange_spot.markets or True:
                        ticker = exchange_spot.fetch_ticker(f"{coin}/USDT")
                        usd = amt * ticker['last']
                        spots.append({"coin":coin,"amt":amt,"usd":usd})
                except:
                    spots.append({"coin":coin,"amt":amt,"usd":0})
        return spots
    except Exception as e:
        print(f"SPOT ERR {e}")
        return []

def run_bot():
    global state_global, open_global, spot_global
    state = load_state()
    print(f"V30032 CONTINUOUS + SPOT SAFE + AUTO REOPEN START {datetime.now()}")
    
    while True:
        try:
            positions = exchange.fetch_positions()
            open_syms = []
            for pos in positions:
                contracts = float(pos.get('contracts',0) or 0)
                if contracts > 0:
                    sym = pos['symbol']
                    open_syms.append(sym)
                    gross = pos.get('unrealizedPnl',0)
                    net = net_profit(gross)
                    curr = state.get(sym,{}).get('sl',LOSS_FIXED)
                    new = get_stop_only_up(net,curr)
                    if new > curr or sym not in state:
                        state[sym]={'sl':new,'net':net,'time':str(datetime.now())}
                        save_state(state)
                        print(f"RAISE SL {sym} {curr} -> {new} net={net:.2f}")

            spots = get_spot_holdings()
            spot_global = spots
            open_global = open_syms
            state_global = state

            print(f"SPOT: {spots}")
            print(f"OPEN NOW {len(open_syms)}/{MAX_OPEN}: {open_syms}")

            need = MAX_OPEN - len(open_syms)
            if need > 0:
                print(f"NEED {need} NEW TRADES - AUTO OPENING (skip SPOT_RESERVE {SPOT_RESERVE})")
                for sym in COINS_60:
                    if sym not in open_syms and sym not in SPOT_RESERVE and need > 0:
                        try:
                            amt = get_amount(sym, USD_PER_TRADE)
                            if amt == 0: continue
                            exchange.set_leverage(LEVERAGE, sym)
                            exchange.create_market_order(sym,'buy',amt)
                            print(f"*** OPENED NEW {sym} amount={amt} ***")
                            need -= 1
                            time.sleep(1.2)
                        except Exception as e:
                            print(f"OPEN FAIL {sym}: {e}")
            time.sleep(5)
        except Exception as e:
            print(f"LOOP ERR {e}")
            time.sleep(3)

@app.route("/")
def index():
    spots_str = "<br>".join([f"{s['coin']}: {s['amt']:.4f} (${s['usd']:.2f})" for s in spot_global])
    opens_str = "<br>".join(open_global) if open_global else "لا يوجد"
    state_str = "<br>".join([f"{k}: SL={v['sl']} net={v.get('net',0):.2f}" for k,v in state_global.items()])
    return f"""
    <h2>V30032 CONTINUOUS + SPOT SAFE</h2>
    <b>OPEN FUTURES {len(open_global)}/{MAX_OPEN}:</b><br>{opens_str}<br><br>
    <b>STATE SL:</b><br>{state_str}<br><br>
    <b>SPOT HOLDINGS (AAVE/DOGE محفوظة):</b><br>{spots_str}<br><br>
    <b>PLAN:</b> SPOT AAVE/DOGE لا يفتح عليها فيوتشر - الغبار ينباع من /sell-dust - أول ما تقفل صفقة يفتح غيرها
    """

@app.route("/api/pnl")
def api_pnl():
    return jsonify({"open":open_global,"state":state_global,"spot":spot_global,"time":str(datetime.now())})

@app.route("/sell-dust")
def sell_dust():
    logs=[]
    try:
        for coin in DUST_COINS:
            try:
                bal = exchange_spot.fetch_balance()
                amt = bal['total'].get(coin,0)
                if amt and amt > 0:
                    sym = f"{coin}/USDT"
                    # حول لكمية دقيقة
                    amount = exchange_spot.amount_to_precision(sym, amt)
                    if float(amount) > 0:
                        order = exchange_spot.create_market_order(sym,'sell',float(amount))
                        logs.append(f"SOLD {coin} {amount}")
                    else:
                        logs.append(f"SKIP {coin} too small {amt}")
            except Exception as e:
                logs.append(f"FAIL {coin}: {e}")
        return jsonify({"sold":logs})
    except Exception as e:
        return jsonify({"error":str(e)})

# شغل البوت في الخلفية
threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)