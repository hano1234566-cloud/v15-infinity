import ccxt, os, json, time, threading
from flask import Flask

STATE_FILE="state.json"
LOSS_FIXED=-0.20
FEE=0.04
LEVELS=[(0.30,0.10),(0.80,0.50),(1.20,0.80),(2.00,1.40),(5.00,3.00)]
LEVERAGE=5
USD_PER_TRADE=6
MAX_OPEN=5
COINS_60 = ["ARB/USDT:USDT","NEAR/USDT:USDT","STRK/USDT:USDT","OP/USDT:USDT","APT/USDT:USDT","SOL/USDT:USDT","AVAX/USDT:USDT","W/USDT:USDT","ENA/USDT:USDT","TIA/USDT:USDT","WIF/USDT:USDT","1000PEPE/USDT:USDT","1000BONK/USDT:USDT","SEI/USDT:USDT","JUP/USDT:USDT","PYTH/USDT:USDT","RENDER/USDT:USDT","FET/USDT:USDT","SUI/USDT:USDT"]
SPOT_RESERVE = ["AAVE/USDT:USDT","DOGE/USDT:USDT"]

app = Flask(__name__)
state_global={}
open_global=[]
log_global="V30026 WORKING - Waiting for keys"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE,'r') as f: return json.load(f)
        except: return {}
    return {}

def save_state(s):
    with open(STATE_FILE,'w') as f: json.dump(s,f)

# يقرأ المفاتيح بأي اسم حطيته في Render
API_KEY = os.getenv('OKX_API_KEY','').strip()
SECRET = (os.getenv('OKX_SECRET_KEY','') or os.getenv('OKX_SECRET','')).strip()
PASSPHRASE = os.getenv('OKX_PASSPHRASE','').strip()

exchange = ccxt.okx({
    'apiKey': API_KEY,
    'secret': SECRET,
    'password': PASSPHRASE,
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
    
    # فحص المفاتيح أول ما يشتغل
    if not API_KEY or not SECRET:
        log_global = f"ERR Keys missing! API:{bool(API_KEY)} SECRET:{bool(SECRET)} PASS:{bool(PASSPHRASE)}"
        print(log_global)
        return

    log_global = "OK - Connected - Fetching positions"
    
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
            log_global=f"OK {len(open_syms)}/{MAX_OPEN} - {', '.join([s.split('/')[0] for s in open_syms])}"

            for sym in list(open_syms):
                try:
                    net=state.get(sym,{}).get('net',0)
                    sl=state.get(sym,{}).get('sl',LOSS_FIXED)
                    if net<=sl:
                        for pos in positions:
                            if pos['symbol']==sym and float(pos.get('contracts',0) or 0)>0:
                                amt=float(pos['contracts'])
                                exchange.create_market_order(sym,'sell',amt)
                                if sym in state:
                                    del state[sym]
                                    save_state(state)
                except: pass

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
                        except: time.sleep(0.5)
            time.sleep(5)
        except Exception as e:
            log_global=f"ERR {str(e)[:100]}"
            print(log_global)
            time.sleep(3)

@app.route("/")
def index():
    opens="<br>".join(open_global) or "0"
    states="<br>".join([f"{k}: SL={v['sl']} net={v.get('net',0):.2f}" for k,v in state_global.items()])
    return f"V30026 WORKING<br>OPEN {len(open_global)}/{MAX_OPEN}: {opens}<br>STATE: {states}<br>LOG: {log_global}<br>KEYS: API={bool(API_KEY)} SECRET={bool(SECRET)}"

threading.Thread(target=run_bot, daemon=True).start()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))