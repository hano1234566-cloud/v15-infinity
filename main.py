import os, time, threading
from flask import Flask, render_template_string
import okx.Account as Account
import okx.Trade as Trade
import okx.MarketData as Market
app=Flask(__name__)
API_KEY=os.getenv("OKX_API_KEY"); SECRET=os.getenv("OKX_SECRET"); PASSPHRASE=os.getenv("OKX_PASSPHRASE"); FLAG="0"
SPOT=[]; FUT=[]; LOG=[]; PROFIT=0.0
acct=Account.AccountAPI(API_KEY,SECRET,PASSPHRASE,False,FLAG)
trade=Trade.TradeAPI(API_KEY,SECRET,PASSPHRASE,False,FLAG)
market=Market.MarketAPI(API_KEY,SECRET,PASSPHRASE,False,FLAG)

def price(inst):
    try: return float(market.get_ticker(instId=inst)['data'][0]['last'])
    except: return 0

def log(m): LOG.append(m); print(m)

def buy():
    p=price("PEPE-USDT")
    log(f"سعر PEPE {p}")
    try:
        r=trade.place_order(instId="PEPE-USDT", tdMode="cash", side="buy", ordType="market", sz="10", tgtCcy="quoteCcy")
        log(f"SPOT {r}")
        if r['code']=='0': SPOT.append({"entry":p}); log("✅ SPOT نجح - شراء 10$"); return True
        else: log(f"❌ SPOT {r.get('msg')}")
    except Exception as e: log(f"SPOT EX {e}")
    try:
        acct.set_leverage(instId="PEPE-USDT-SWAP", lever="3", mgnMode="isolated")
        r=trade.place_order(instId="PEPE-USDT-SWAP", tdMode="isolated", side="buy", posSide="long", ordType="market", sz="2000000")
        log(f"FUT {r}")
        if r['code']=='0': FUT.append({"entry":p}); log("✅ FUT نجح"); return True
        else: log(f"❌ FUT {r.get('msg')}")
    except Exception as e: log(f"FUT EX {e}")
    return False

def loop():
    while len(SPOT)==0 and len(FUT)==0:
        buy(); time.sleep(20)
    log("♾️ بدأ Infinity!")
    while True:
        try:
            p=price("PEPE-USDT")
            if not p: time.sleep(10); continue
            for lst in [SPOT,FUT]:
                for pos in lst[:]:
                    if p >= pos['entry']*1.005: 
                        # هنا يبيع بربح 0.5%
                        lst.remove(pos)
                        log(f"بيع بربح {p}")
            if p and len(SPOT)+len(FUT)<5: buy()
        except Exception as e: log(f"LOOP {e}")
        time.sleep(15)

threading.Thread(target=loop, daemon=True).start()
HTML="""<!DOCTYPE html><html dir=rtl><head><meta charset=utf-8><meta name=viewport content=width=device-width,initial-scale=1><title>V30 FINAL</title><style>body{background:#0a0a0f;color:#fff;font-family:system-ui;padding:12px}.ok{color:#0f0}.bad{color:#f55}</style><meta http-equiv=refresh content=3></head><body><h3>V30 FINAL</h3><div>سبوت: {{s}} | فيوتشر: {{f}}</div><div style=background:#1a1a25;padding:10px;border-radius:10px;margin-top:10px>{% for l in logs[::-1][:25] %}<div style=font-size:11px;border-bottom:1px solid #222;padding:3px>{{l}}</div>{% endfor %}</div></body></html>"""
@app.route("/")
def index(): return render_template_string(HTML, s=len(SPOT), f=len(FUT), logs=LOG)
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
