import ccxt, os, json, time, threading
from datetime import datetime
from flask import Flask

STATE_FILE="state.json"
LOSS_FIXED=-0.20
FEE=0.04
LEVELS=[(0.30,0.10),(0.80,0.50),(1.20,0.80),(2.00,1.40),(5.00,3.00)]
LEVERAGE=5
USD_PER_TRADE=6
MAX_OPEN=5
COINS_60 = ["ARB/USDT:USDT","NEAR/USDT:USDT","STRK/USDT:USDT","OP/USDT:USDT","APT/USDT:USDT","SOL/USDT:USDT","AVAX/USDT:USDT","W/USDT:USDT","ENA/USDT:USDT","TIA/USDT:USDT","WIF/USDT:USDT","1000PEPE/USDT:USDT","1000BONK/USDT:USDT","SEI/USDT:USDT","JUP/USDT:USDT","PYTH/USDT:USDT","RENDER/USDT:USDT","FET/USDT:USDT","SUI/USDT:USDT","BTC/USDT:USDT","ETH/USDT:USDT","DOGE/USDT:USDT","SHIB/USDT:USDT","DOT/USDT:USDT","LINK/USDT:USDT","ADA/USDT:USDT","XRP/USDT:USDT","LTC/USDT:USDT","MATIC/USDT:USDT","ETC/USDT:USDT","FIL/USDT:USDT","ATOM/USDT:USDT","TRX/USDT:USDT","BCH/USDT:USDT"]
SPOT_RESERVE = ["AAVE/USDT:USDT","DOGE/USDT:USDT"]

app = Flask(__name__)
state_global={}
open_global=[]
log_global="V30026 starting"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE,'r') as f: return json.load(f)
        except: return {}
    return {}
def save_state(s):
    with open(STATE_FILE,'w') as f: json.dump(s,f)

exchange = ccxt.okx({
    'apiKey': os.getenv('OKX_API_KEY'),
    'secret': os.getenv('OKX_SECRET'),
    'password': os.getenv('OKX_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

def net_profit(g):
    try: return float(g)-FEE
    except: return -10
def get_stop(net,curr):
    t=LOSS_FIXED
    for p,sl in LEVELS:
        if net>=p: t=sl
    return max(t,curr)

def run_bot():
    global state_global, open_global, log_global
    state=load_state()
    while True:
        try:
            positions = exchange.fetch_positions()
            open_syms=[]
            for pos in positions:
                if float(pos.get('contracts',0) or 0) > 0:
                    sym=pos['symbol']
                    open_syms.append(sym)
                    gross=pos.get('unrealizedPnl',0)
                    net=net_profit(gross)
                    curr=state.get(sym,{}).get('sl',LOSS_FIXED)
                    new=get_stop(net,curr)
                    if new>curr or sym not in state:
                        state[sym]={'sl':new,'net':net}
                        save_state(state)

            open_global=open_syms
            state_global=state
            log_global=f"OK {len(open_syms)}/5 at {datetime.now().strftime('%H:%M:%S')}"

            need = MAX_OPEN - len(open_syms)
            if need > 0:
                for sym in COINS_60:
                    if sym not in open_syms and sym not in SPOT_RESERVE and need>0:
                        try:
                            t=exchange.fetch_ticker(sym)
                            amt=float(exchange.amount_to_precision(sym, USD_PER_TRADE/t['last']))
                            exchange.set_leverage(LEVERAGE, sym)
                            exchange.create_market_order(sym,'buy',amt)
                            need-=1
                            time.sleep(1.2)
                        except Exception as e:
                            log_global=f"FAIL {sym} {e}"
                            time.sleep(0.5)
            time.sleep(5)
        except Exception as e:
            log_global=f"ERR {e}"
            time.sleep(3)

@app.route("/")
def index():
    opens="<br>".join(open_global) or "0 - سيفتح الآن"
    states="<br>".join([f"{k}: SL={v['sl']} net={v.get('net',0):.2f}" for k,v in state_global.items()])
    return f"V30026 CONTINUOUS (الأصلي)<br><br>OPEN {len(open_global)}/{MAX_OPEN}:<br>{opens}<br><br>STATE:<br>{states}<br><br>LOG: {log_global}<br><br>SPOT محفوظ AAVE/DOGE"

threading.Thread(target=run_bot, daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))