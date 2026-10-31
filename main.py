import os, time, threading, random
from flask import Flask, render_template_string
import okx.Account as Account
import okx.Trade as Trade
import okx.MarketData as Market
app=Flask(__name__)
API_KEY=os.getenv("OKX_API_KEY"); SECRET=os.getenv("OKX_SECRET"); PASSPHRASE=os.getenv("OKX_PASSPHRASE"); FLAG="0"
GEN=300; IQ=600; TOTAL=0.0
SPOT=[]; FUT=[]; LOG=["✅ V29.2 تم اصلاح حجم PEPE - 2 مليون عملة"]
acct=Account.AccountAPI(API_KEY,SECRET,PASSPHRASE,False,FLAG)
trade=Trade.TradeAPI(API_KEY,SECRET,PASSPHRASE,False,FLAG)
market=Market.MarketAPI(API_KEY,SECRET,PASSPHRASE,False,FLAG)

def price(inst):
    try: return float(market.get_ticker(instId=inst)['data'][0]['last'])
    except: return 0

def open_all():
    p=price("PEPE-USDT")
    if p==0: return
    qty_spot=str(int(10/p)) # 10$ / سعر PEPE
    qty_fut=str(int(9/p))
    LOG.append(f"سعر PEPE {p} الكمية {qty_spot}")
    try:
        r1=trade.place_order(instId="PEPE-USDT", tdMode="cash", side="buy", ordType="market", sz=qty_spot)
        LOG.append(f"SPOT OK {r1['data']}")
        SPOT.append({"coin":"PEPE-USDT","entry":p,"pnl":0,"qty":qty_spot})
    except Exception as e: LOG.append(f"SPOT ERR {e}")
    try:
        acct.set_leverage(instId="PEPE-USDT-SWAP", lever="3", mgnMode="isolated")
        r2=trade.place_order(instId="PEPE-USDT-SWAP", tdMode="isolated", side="buy", posSide="long", ordType="market", sz=qty_fut)
        LOG.append(f"FUT OK {r2['data']}")
        FUT.append({"coin":"PEPE-USDT-SWAP","entry":p,"pnl":0,"qty":qty_fut,"side":"buy"})
    except Exception as e: LOG.append(f"FUT ERR {e}")

def loop():
    open_all()
    while True:
        try:
            for t in SPOT+FUT:
                cur=price(t["coin"])
                if cur==0: continue
                if t in SPOT:
                    t["pnl"]=((cur-t["entry"])/t["entry"])*100
                    if t["pnl"]>=3 or t["pnl"]<=-2:
                        trade.place_order(instId=t["coin"], tdMode="cash", side="sell", ordType="market", sz=t["qty"])
                        LOG.append(f"💰 سبوت قفل {t['pnl']:.2f}%"); SPOT.remove(t)
                else:
                    t["pnl"]=((cur-t["entry"])/t["entry"])*100*3
                    if t["pnl"]>=9 or t["pnl"]<=-6:
                        trade.place_order(instId=t["coin"], tdMode="isolated", side="sell", posSide="long", ordType="market", sz=t["qty"])
                        LOG.append(f"💰 فيوتشر قفل {t['pnl']:.2f}%"); FUT.remove(t)
            if len(SPOT)==0: open_all()
            time.sleep(10)
        except Exception as e: LOG.append(f"LOOP {e}"); time.sleep(5)

threading.Thread(target=loop, daemon=True).start()
HTML="""<!DOCTYPE html><html dir=rtl><head><meta charset=utf-8><meta name=viewport content=width=device-width,initial-scale=1><title>V29.2 FIX</title><style>body{background:#0a0a0f;color:#fff;font-family:system-ui;padding:12px}.c{background:#1a1a25;padding:12px;border-radius:12px;margin-bottom:8px}</style><meta http-equiv=refresh content=4></head><body><h3>👑 V29.2 FIX - 2M PEPE</h3><div class=c>سبوت: {{spot}} | فيوتشر: {{fut}}</div><div class=c>{% for l in log[::-1][:12] %}<div style=font-size:11px;border-bottom:1px solid #222;padding:3px>{{l}}</div>{% endfor %}</div></body></html>"""
@app.route("/")
def index(): return render_template_string(HTML, spot=len(SPOT), fut=len(FUT), log=LOG)
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
