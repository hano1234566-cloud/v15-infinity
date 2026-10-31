import os, time, threading
from flask import Flask, render_template_string
import okx.Account as Account
import okx.Trade as Trade
import okx.MarketData as Market
app=Flask(__name__)
API_KEY=os.getenv("OKX_API_KEY"); SECRET=os.getenv("OKX_SECRET"); PASSPHRASE=os.getenv("OKX_PASSPHRASE"); FLAG="0"
SPOT=[]; FUT=[]; LOG=[]
acct=Account.AccountAPI(API_KEY,SECRET,PASSPHRASE,False,FLAG)
trade=Trade.TradeAPI(API_KEY,SECRET,PASSPHRASE,False,FLAG)
market=Market.MarketAPI(API_KEY,SECRET,PASSPHRASE,False,FLAG)

def price(inst):
    try: return float(market.get_ticker(instId=inst)['data'][0]['last'])
    except: return 0

def log(msg): LOG.append(msg); print(msg)

def try_orders():
    p=price("PEPE-USDT")
    log(f"سعر PEPE {p}")
    # 1- سبوت: اشتر بـ 10 دولار - الطريقة الصحيحة
    try:
        r=trade.place_order(instId="PEPE-USDT", tdMode="cash", side="buy", ordType="market", sz="10", tgtCcy="quoteCcy")
        log(f"SPOT RESP {r}")
        if r['code']=='0': SPOT.append({"entry":p}); log("✅ SPOT نجح!")
        else: log(f"❌ SPOT فشل كود {r['code']} رسالة {r.get('msg')}")
    except Exception as e: log(f"SPOT EX {e}")
    # 2- فيوتشر: PEPE swap - OKX يستخدم عملة PEPE ككمية
    try:
        acct.set_leverage(instId="PEPE-USDT-SWAP", lever="3", mgnMode="isolated")
        # جرب 2000000
        r=trade.place_order(instId="PEPE-USDT-SWAP", tdMode="isolated", side="buy", posSide="long", ordType="market", sz="2000000")
        log(f"FUT RESP {r}")
        if r['code']=='0': FUT.append({"entry":p}); log("✅ FUT نجح!")
        else: log(f"❌ FUT فشل كود {r['code']} رسالة {r.get('msg')} {r.get('data')}")
    except Exception as e: log(f"FUT EX {e}")

def loop():
    try_orders()
    while True:
        time.sleep(15)
        if len(SPOT)==0 and len(FUT)==0: try_orders()

threading.Thread(target=loop, daemon=True).start()
HTML="""<!DOCTYPE html><html dir=rtl><head><meta charset=utf-8><meta name=viewport content=width=device-width,initial-scale=1><title>V29.3 LOG</title><style>body{background:#0a0a0f;color:#fff;font-family:system-ui;padding:12px}.c{background:#1a1a25;padding:12px;border-radius:12px}</style><meta http-equiv=refresh content=3></head><body><h3>V29.3 - يوري الخطأ الحقيقي</h3><div class=c>{% for l in log[::-1][:20] %}<div style=font-size:11px;border-bottom:1px solid #222;padding:4px>{{l}}</div>{% endfor %}</div></body></html>"""
@app.route("/")
def index(): return render_template_string(HTML, log=LOG)
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
