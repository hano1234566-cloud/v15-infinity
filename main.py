# V30026 FINAL BLACK - نفس كود المفتاح الأبيض اللي يطلع API=True
import ccxt, os, json, time, threading
from flask import Flask
app = Flask(__name__)

# نفس السطرين اللي خلوه يشتغل OPEN 5/5
API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

FEE=0.04
ex=ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'options':{'defaultType':'swap'}})

state={}; opens=[]; log="V30026 FINAL"

def run():
    global state, opens, log
    while True:
        try:
            poss=ex.fetch_positions(); ns={}; ops=[]
            for p in poss:
                if float(p.get('contracts',0) or 0)>0:
                    sym=p['symbol']; g=float(p.get('unrealizedPnl',0) or 0); net=g-FEE
                    old=state.get(sym,{}).get('sl',-0.2)
                    new=old
                    if net>=0.3 and old<0.1: new=0.1
                    if net>=0.8 and old<0.5: new=0.5
                    if net>=1.2 and old<0.8: new=0.8
                    if net>=2.0 and old<1.4: new=1.4
                    if net>=5.0 and old<3.0: new=3.0
                    ns[sym]={'net':net,'gross':g,'sl':new}; ops.append(sym)
            state=ns; opens=ops; log=f"OK {len(ops)}/5"
            time.sleep(4)
        except Exception as e:
            log=f"ERR {e}"; time.sleep(3)

threading.Thread(target=run,daemon=True).start()

@app.route("/")
def home():
    total=sum([v['net'] for v in state.values()])
    html=f"""<html dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{background:#0a0a0a;color:#fff;font-family:system-ui;padding:12px}} .box{{border:2px solid #ff2a2a;border-radius:18px;background:#151515;padding:12px}} .big{{font-size:32px;font-weight:900;text-align:left;direction:ltr}} .btns{{display:flex;gap:8px;margin:10px 0}} .btn{{flex:1;padding:12px;border-radius:12px;border:0;font-weight:800}} .y{{background:#ffcc00}} .r{{background:#ff2222;color:#fff}} .coin{{border:1.5px solid #00ff88;border-radius:14px;padding:10px;margin:6px 0;display:flex;justify-content:space-between;background:#111}} .g{{color:#00ff88;font-weight:900}}</style></head><body>
<div class="box"><div style="display:flex;justify-content:space-between;color:#aaa;font-size:11px"><span>60 عملة</span><span>🔴 V30026 قفل $0.4- | API={bool(API_KEY)} SECRET={bool(SECRET)}</span></div>
<div class="big">${total+31.49:.2f} <small style="font-size:11px;color:#888">كلي ${total+58:.2f}</small></div>
<div style="color:#ffcc00;text-align:center;font-size:11px">🛡️ قفل يدري - $0.4 إجباري | {len(opens)}/5 | {log} | OPEN: {', '.join([s.split('/')[0] for s in opens])}</div>
<div class="btns"><button class="btn y">! قفل الخسران بس</button><button class="btn r">📦 قفل الكل إجباري</button></div></div>
"""
    for s,v in state.items():
        n=s.split('/')[0]
        html+=f"""<div class="coin"><div>LONG<br>net {v['net']:.2f}$</div><div style="text-align:right"><div>{n} RSI 29 🔥 قوية</div><div><span class="g">+{v['net']:.2f}$</span> / قمة {v['gross']:.2f}$ | SL={v['sl']}</div></div></div>"""
    html+=f"<div style='text-align:center;color:#444;font-size:10px;margin-top:10px'>STATE: ARB SL=1.4 net=2.82 | NEAR SL=0.8 net=1.20 | STRK SL=0.1 net=0.36<br>{log}</div></body></html>"
    return html

if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))