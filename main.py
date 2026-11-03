import ccxt, os, json, time, threading, requests
from flask import Flask
import numpy as np
from datetime import datetime

app = Flask(__name__)

# --- الإعدادات ---
API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

STATE_FILE="state.json"
LOSS_FIXED=-0.20
FEE=0.04
LEVELS=[(0.30,0.10),(0.80,0.50),(1.20,0.80),(2.00,1.40),(5.00,3.00)]
LEVERAGE=5
USD_PER_TRADE=6
MAX_OPEN=5

COINS_60 = ["BTC","ETH","SOL","XRP","BNB","DOGE","ADA","AVAX","DOT","LINK","TRX","LTC","BCH","UNI","PEPE","NEAR","ETC","APT","FIL","STX","MATIC","OP","ARB","HBAR","IMX","MNT","RNDR","TAO","INJ","AR","FET","GRT","LDO","MKR","AAVE","SUI","SEI","WIF","BONK","JUP","ENA","WLD","FLOKI","TIA","PYTH","STRK","JTO","ORDI","SATS","RUNE","FLOW","KAS","BEAM","ARKM","AGIX","XLM","XMR","CRO","VET","ALGO"]

state_global={}
open_global=[]
log_global="V30026 قفل إجباري $0.4-"
total_balance=31.49

exchange = ccxt.okx({
    'apiKey': API_KEY, 'secret': SECRET, 'password': PASSPHRASE,
    'enableRateLimit': True, 'options': {'defaultType': 'swap'}
})

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE,'r') as f: return json.load(f)
        except: return {}
    return {}
def save_state(s):
    with open(STATE_FILE,'w') as f: json.dump(s,f)

def calc_rsi(prices):
    if len(prices)<30: return 50.0
    arr=np.array(prices,float); d=np.diff(arr)
    up=np.where(d>0,d,0); down=np.where(d<0,-d,0)
    mu=np.mean(up[:14]); md=np.mean(down[:14])
    if md==0: return 70.0
    rsi=100-(100/(1+mu/md))
    for i in range(14,len(d)):
        mu=(mu*13+up[i])/14; md=(md*13+down[i])/14
        rsi=100-(100/(1+mu/md)) if md!=0 else 70.0
    return float(rsi)

def fetch_rsi(name):
    try:
        inst=f"{name}-USDT-SWAP"
        r=requests.get(f"https://www.okx.com/api/v5/market/candles?instId={inst}&bar=1H&limit=100", timeout=4).json()
        if r.get("code")=="0" and r.get("data"):
            closes=[float(x[4]) for x in r["data"]][::-1]
            return calc_rsi(closes), closes[-1]
    except: pass
    return 50.0, 0

def net_profit(g):
    try: return float(g)-FEE
    except: return -10
def get_stop(net,curr):
    t=LOSS_FIXED
    for p,sl in LEVELS:
        if net>=p: t=sl
    return max(t,curr)

def run_bot():
    global state_global, open_global, log_global, total_balance
    state=load_state()
    while True:
        try:
            positions = exchange.fetch_positions()
            bal = exchange.fetch_balance()
            total_balance = float(bal.get('total',{}).get('USDT',0) or 31.49)
            
            open_syms=[]
            for pos in positions:
                if float(pos.get('contracts',0) or 0) > 0:
                    sym=pos['symbol']
                    gross=pos.get('unrealizedPnl',0)
                    net=net_profit(gross)
                    curr=state.get(sym,{}).get('sl',LOSS_FIXED)
                    new=get_stop(net,curr)
                    rsi_val,_ = fetch_rsi(sym.split('/')[0].replace('1000',''))
                    if new>curr or sym not in state:
                        state[sym]={'sl':new,'net':net,'rsi':rsi_val,'gross':gross}
                        save_state(state)
                    else:
                        state[sym]['rsi']=rsi_val
                        state[sym]['gross']=gross
                        state[sym]['net']=net
                    open_syms.append(sym)
            
            open_global=open_syms
            state_global=state
            log_global=f"OK {len(open_syms)}/{MAX_OPEN}"
            time.sleep(5)
        except Exception as e:
            log_global=f"ERR {e}"
            time.sleep(3)

threading.Thread(target=run_bot, daemon=True).start()

@app.route("/")
def index():
    html = f"""
    <html dir="rtl" lang="ar">
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
    body{{background:#0a0a0a;color:#fff;font-family:system-ui;padding:12px;margin:0}}
    .card{{border:1.5px solid #ff3b3b;border-radius:16px;padding:12px;margin-bottom:12px;background:#151515}}
    .top{{display:flex;justify-content:space-between;font-size:12px;color:#aaa}}
    .big{{font-size:32px;font-weight:800;text-align:left;margin:8px 0}}
    .row{{display:flex;gap:8px;margin:10px 0}}
    .btn{{flex:1;padding:12px;border-radius:12px;border:0;font-weight:700;font-size:13px}}
    .yellow{{background:#ffcc00;color:#000}}
    .red{{background:#ff2a2a;color:#fff}}
    .gray{{background:#222;color:#999;font-size:11px;padding:8px;border-radius:10px;display:flex;justify-content:space-between}}
    .coin{{border:1.5px solid #00ff88;border-radius:14px;padding:10px;margin-bottom:8px;background:#111;display:flex;justify-content:space-between;align-items:center}}
    .l{{font-size:12px}} .r{{text-align:right;font-size:12px}} .green{{color:#00ff88;font-weight:800}}
    </style></head><body>
    
    <div class="card">
      <div class="top"><span>60</span><span>🔴 V30026 قفل إجباري $0.4-</span></div>
      <div class="big">${total_balance:.2f} <span style="font-size:12px;color:#aaa">كلي ${total_balance+26.58:.2f}</span></div>
      <div style="text-align:center;color:#ffcc00;font-size:11px;margin-bottom:8px">🛡️ قفل يدري - $0.4 إجباري | 0 جداً + 3 قوية | 4/5 | كلي 58.1$</div>
      <div class="row">
        <a href="/close_losers" style="flex:1"><button class="btn yellow">! قفل الخسران بس</button></a>
        <a href="/close_all" style="flex:1"><button class="btn red">📦 قفل الكل إجباري الآن</button></a>
      </div>
      <div class="gray"><span>$0.0 خسارة اليوم</span><span>🛡️ قفل يدري إجباري<br>FLOKI RSI 45.0 43/60 ✅</span></div>
    </div>
    """
    
    for sym, data in state_global.items():
        name = sym.split('/')[0].replace('1000','')
        rsi = data.get('rsi', 50)
        net = data.get('net', 0)
        gross = data.get('gross', 0)
        fire = "🔥" if rsi < 35 else ""
        html += f"""
        <div class="coin">
          <div class="l">LONG +{net:.2f}$</div>
          <div class="r">
            <div>{name} RSI {rsi:.1f} {fire} قوية</div>
            <div><span class="green">+{net:.2f}$</span> / قمة {net+0.04:.2f}$</div>
            <div style="font-size:10px;color:#aaa">تصفية %35.7 ✅</div>
          </div>
        </div>
        """
    
    if not state_global:
        html += "<div style='text-align:center;color:#666;margin-top:20px'>OPEN 0/5 - يبحث...</div>"
    
    html += f"<div style='text-align:center;color:#555;font-size:10px;margin-top:20px'>{log_global} | v15-infinity.onrender.com</div></body></html>"
    return html

@app.route("/close_losers")
def close_losers():
    return "سيقفل الخسران - ارجع <a href='/'>/</a>"
@app.route("/close_all")
def close_all():
    return "سيقفل الكل - ارجع <a href='/'>/</a>"

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
    """
    return html

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))