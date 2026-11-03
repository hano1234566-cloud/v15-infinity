import ccxt, os, json, time, threading
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
log_global="starting"

def get_key(n):
    v=os.getenv(n)
    if v: return v.strip()
    for p in [f"/etc/secrets/{n}", f"./{n}"]:
        if os.path.exists(p):
            with open(p) as f: return f.read().strip()
    return None

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE,'r') as f: return json.load(f)
        except: return {}
    return {}
def save_state(s):
    with open(STATE_FILE,'w') as f: json.dump(s,f)

def make_exchange():
    k=get_key('OKX_API_KEY') or get_key('OKX_AP') or get_key('FUTURE_API_KEY')
    s=get_key('OKX_SECRET') or get_key('OKX_SE') or get_key('FUTURE_SECRET')
    p=get_key('OKX_PASSPHRASE') or get_key('OKX_PA') or get_key('FUTURE_PASSPHRASE')
    return ccxt.okx({'apiKey':k,'secret':s,'password':p,'enableRateLimit':True,'timeout':30000,'options':{'defaultType':'swap'}})

def net_profit(g):
    try: return float(g)-FEE
    except: return -10
def get_stop(net,curr):
    t=LOSS_FIXED
    for pr,sl in LEVELS:
        if net>=pr: t=sl
    return max(t,curr)

def run_bot():
    global state_global, open_global, log_global
    state=load_state()
    retry=0
    while True:
        try:
            ex=make_exchange()
            # اختبار اتصال
            bal=ex.fetch_balance()
            log_global=f"CONNECTED OK retry={retry}"
            retry=0
            
            while True:
                try:
                    positions=ex.fetch_positions()
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
                            # تشييك تقفيل
                            if net<=curr:
                                try:
                                    amt=float(pos['contracts'])
                                    ex.create_market_order(sym,'sell',amt)
                                    log_global=f"CLOSED {sym} net={net:.2f}"
                                    del state[sym]
                                    save_state(state)
                                except Exception as e:
                                    log_global=f"CLOSE FAIL {sym} {e}"

                    open_global=open_syms
                    state_global=state
                    
                    need=MAX_OPEN-len(open_syms)
                    if need>0:
                        for sym in COINS_60:
                            if sym not in open_syms and sym not in SPOT_RESERVE and need>0:
                                try:
                                    t=ex.fetch_ticker(sym)
                                    amt=float(ex.amount_to_precision(sym, USD_PER_TRADE/t['last']))
                                    ex.set_leverage(LEVERAGE, sym)
                                    ex.create_market_order(sym,'buy',amt)
                                    need-=1
                                    time.sleep(1.5)
                                except: time.sleep(0.5)
                    time.sleep(4)
                except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as e:
                    log_global=f"NET ERR {e} - reconnect in 5s"
                    time.sleep(5)
                    break # يطلع ويعيد make_exchange
                except Exception as e:
                    log_global=f"LOOP ERR {e}"
                    time.sleep(3)

        except Exception as e:
            retry+=1
            log_global=f"CONN FAIL {e} retry {retry}/10"
            time.sleep(min(5*retry, 60))

@app.route("/")
def index():
    opens="<br>".join(open_global) or "جاري..."
    states="<br>".join([f"{k}: SL={v['sl']} net={v.get('net',0):.2f}" for k,v in state_global.items()])
    return f"V30029 FIXED CONNECTION<br><br>OPEN {len(open_global)}/5:<br>{opens}<br><br>STATE:<br>{states}<br><br>LOG: {log_global}"

threading.Thread(target=run_bot, daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))