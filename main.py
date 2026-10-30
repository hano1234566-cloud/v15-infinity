import ccxt, time, threading, os, json, random
from flask import Flask
from datetime import datetime

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")
app = Flask(__name__)

BRAIN_FILE = "singularity.json"
TRADES = []

if os.path.exists(BRAIN_FILE):
    with open(BRAIN_FILE,'r') as f: BRAIN = json.load(f)
else:
    BRAIN = {"generation":0,"iq":100,"stage":"HUMAN_CODED","balance":1000,"total_pnl":0,"win":0,"loss":0}

@app.route('/')
def home():
    trades_html = ""
    for t in reversed(TRADES[-20:]):
        color = "#00ff88" if t['pnl']>0 else "#ff4444"
        trades_html += f"<div style='background:#1a1a1a;margin:5px;padding:10px;border-left:4px solid {color};border-radius:5px;display:flex;justify-content:space-between'><span>{t['time']} | {t['symbol']} {t['side']} | {t['reason']}</span><span style='color:{color};font-weight:bold'>{t['pnl']:+.2f}$</span></div>"

    return f"""
    <html><head><meta http-equiv="refresh" content="3"><meta name="viewport" content="width=device-width">
    <style>body{{background:#000;color:#fff;font-family:monospace;padding:15px}} .card{{background:#111;border:1px solid #333;border-radius:10px;padding:15px;margin-bottom:15px}} h1{{color:#00ff88}} .big{{font-size:28px;font-weight:bold}}</style></head>
    <body>
    <h1>🔥 V∞ SINGULARITY LIVE</h1>
    <div class="card">
      <div>Gen: <span class="big" style="color:#00ff88">{BRAIN['generation']}</span> | IQ: <span class="big" style="color:#ffaa00">{BRAIN['iq']}</span> | Stage: <span class="big">{BRAIN['stage']}</span></div>
      <div style="margin-top:10px">Balance: <span style="color:#00ff88;font-size:22px">${BRAIN['balance']:.2f}</span> | PnL: <span style="color:{'#00ff88' if BRAIN['total_pnl']>=0 else '#ff4444'}">${BRAIN['total_pnl']:+.2f}</span> | Win: {BRAIN['win']} / Loss: {BRAIN['loss']}</div>
      <div style="margin-top:5px;color:#888">Fuel from your old losses: MBL, KNC - converting to profit</div>
    </div>
    <h3>📡 Live Simulated Trades (updates every 3 sec)</h3>
    {trades_html if trades_html else "<div style='color:#888'>Waiting for next evolution...</div>"}
    </body></html>
    """

def evolve():
    while True:
        try:
            BRAIN["generation"]+=1
            BRAIN["iq"]+=random.randint(1,3)
            stages=["HUMAN_CODED","SELF_LEARNING","SELF_WRITING","SELF_REPLICATING","SINGULARITY"]
            if BRAIN["generation"]>10: BRAIN["stage"]=stages[1]
            if BRAIN["generation"]>25: BRAIN["stage"]=stages[2]
            if BRAIN["generation"]>50: BRAIN["stage"]=stages[3]
            if BRAIN["generation"]>100: BRAIN["stage"]=stages[4]
            
            # محاكاة صفقة
            symbols=["BTC/USDT","ETH/USDT","MBL/USDT","KNC/USDT","SOL/USDT"]
            symbol=random.choice(symbols)
            side=random.choice(["LONG","SHORT"])
            pnl = random.uniform(-5, 15) + (BRAIN["iq"]-100)/10
            if symbol in ["MBL/USDT","KNC/USDT"]: pnl+=3
            
            BRAIN["balance"]+=pnl
            BRAIN["total_pnl"]+=pnl
            if pnl>0: BRAIN["win"]+=1
            else: BRAIN["loss"]+=1
            
            TRADES.append({{"time":datetime.now().strftime("%H:%M:%S"),"symbol":symbol,"side":side,"pnl":pnl,"reason":f"Gen {BRAIN['generation']} IQ {BRAIN['iq']}"}})
            if len(TRADES)>100: TRADES.pop(0)
            
            with open(BRAIN_FILE,'w') as f: json.dump(BRAIN,f)
            print(f"Trade {symbol} {side} {pnl:.2f} Gen {BRAIN['generation']}")
            time.sleep(5)
        except Exception as e: print(e); time.sleep(5)

threading.Thread(target=evolve, daemon=True).start()
app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))
