import ccxt, os, json, time
from datetime import datetime

COINS_60 = ["BTC/USDT:USDT","ETH/USDT:USDT","SOL/USDT:USDT","AVAX/USDT:USDT","NEAR/USDT:USDT","ARB/USDT:USDT","W/USDT:USDT","ENA/USDT:USDT","TIA/USDT:USDT","WIF/USDT:USDT","1000PEPE/USDT:USDT","1000BONK/USDT:USDT","OP/USDT:USDT","STRK/USDT:USDT","APT/USDT:USDT","SUI/USDT:USDT","SEI/USDT:USDT","JUP/USDT:USDT","PYTH/USDT:USDT","RENDER/USDT:USDT","FET/USDT:USDT","AGIX/USDT:USDT","INJ/USDT:USDT","RUNE/USDT:USDT","LDO/USDT:USDT","STX/USDT:USDT","IMX/USDT:USDT","FLOW/USDT:USDT","MANA/USDT:USDT","SAND/USDT:USDT","AXS/USDT:USDT","CHZ/USDT:USDT","GALA/USDT:USDT","APE/USDT:USDT","BLUR/USDT:USDT","MEME/USDT:USDT","ORDI/USDT:USDT","1000SATS/USDT:USDT","DOGE/USDT:USDT","SHIB/USDT:USDT","LTC/USDT:USDT","BCH/USDT:USDT","ETC/USDT:USDT","DOT/USDT:USDT","LINK/USDT:USDT","MATIC/USDT:USDT","ADA/USDT:USDT","XRP/USDT:USDT","TRX/USDT:USDT","FIL/USDT:USDT","ATOM/USDT:USDT","XLM/USDT:USDT","VET/USDT:USDT","HBAR/USDT:USDT","ALGO/USDT:USDT","EGLD/USDT:USDT","KAVA/USDT:USDT","KLAY/USDT:USDT","ZIL/USDT:USDT","CFX/USDT:USDT","PEOPLE/USDT:USDT"]

STATE_FILE="state.json"
LOSS_FIXED=-0.20
FEE=0.04
LEVELS=[(0.30,0.10),(0.80,0.50),(1.20,0.80),(2.00,1.40)]
LEVERAGE=5
USD_PER_TRADE=5

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE,'r') as f: return json.load(f)
        except: return {}
    return {}
def save_state(s):
    with open(STATE_FILE,'w') as f: json.dump(s,f)

def net_profit(gross): return float(gross) - FEE
def get_stop_only_up(net, curr):
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

def get_amount(symbol, usd):
    ticker = exchange.fetch_ticker(symbol)
    price = ticker['last']
    amt = exchange.amount_to_precision(symbol, usd/price)
    print(f"CALC {symbol} price={price} usd={usd} => amount={amt} ~ {float(amt)*price:.2f}$")
    return amt

def run():
    state=load_state()
    print(f"V30030 CONTINUES FROM V30028 - SAME UI SAME PLAN - {datetime.now()}")
    print(f"LOSS {LOSS_FIXED} FEE {FEE} LEVELS {LEVELS} ONLY_UP")

    # ===== يكمل على الصفقات المفتوحة =====
    while True:
        try:
            positions = exchange.fetch_positions()
            open_syms = [p['symbol'] for p in positions if float(p.get('contracts',0) or 0) > 0]
            print(f"OPEN NOW: {open_syms}")

            # 1- إدارة المفتوح - رفع وقف فقط
            for pos in positions:
                sym = pos['symbol']
                contracts = float(pos.get('contracts',0) or 0)
                if contracts == 0: continue
                gross = pos.get('unrealizedPnl',0)
                net = net_profit(gross)
                curr = state.get(sym,{}).get('sl',LOSS_FIXED)
                new = get_stop_only_up(net, curr)
                print(f"[{sym}] gross={gross} net={net:.2f} contracts={contracts} SL {curr}->{new}")
                if new > curr or sym not in state:
                    state[sym]={'sl':new,'net':net,'contracts':contracts,'time':str(datetime.now())}
                    save_state(state)
                    # ضع أمر الوقف الحقيقي هنا private_post_trade_order_algo
                    print(f"RAISE SL {sym} TO {new}")

            # 2- يكمل فتح - نفس ما اتفقنا - تجريبي NEAR/ARB أولاً
            # لو تبي 60 كاملة غير السطر الجاي لـ COINS_60
            TO_OPEN = ["NEAR/USDT:USDT","ARB/USDT:USDT"]  # بعد التأكد غيرها لـ COINS_60
            for sym in TO_OPEN:
                if sym not in open_syms:
                    print(f"TRY OPEN {sym}")
                    amt = get_amount(sym, USD_PER_TRADE)
                    exchange.set_leverage(LEVERAGE, sym)
                    # order = exchange.create_market_order(sym,'buy',float(amt))
                    # print(f"OPENED {sym}")

            time.sleep(5)
        except Exception as e:
            print(f"ERR {e}")
            time.sleep(3)

if __name__=="__main__":
    run()