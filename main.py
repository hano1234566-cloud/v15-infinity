import os, time, threading, random
from flask import Flask, render_template_string
import okx.Account as Account
import okx.Trade as Trade
import okx.MarketData as Market
app=Flask(__name__)
API_KEY=os.getenv("OKX_API_KEY"); SECRET=os.getenv("OKX_SECRET"); PASSPHRASE=os.getenv("OKX_PASSPHRASE"); FLAG="0"
GEN=216; IQ=570; TOTAL_PNL=0.0
CONFIG={"lev":3,"status":"RUNNING"}
SPOT_TRADES=[]; FUT_TRADES=[]; HISTORY=["✅ V29.1 تم التعديل - صفقة سبوت 10$ + فيوتشر 9$"]

acct=Account.AccountAPI(API_KEY,SECRET,PASSPHRASE,False,FLAG)
trade=Trade.TradeAPI(API_KEY,SECRET,PASSPHRASE,False,FLAG)
market=Market.MarketAPI(API_KEY,SECRET,PASSPHRASE,False,FLAG)
COINS_SPOT=["DOGE-USDT","PEPE-USDT"]
COINS_FUT=["DOGE-USDT-SWAP","PEPE-USDT-SWAP","SHIB-USDT-SWAP"]

def get_price(inst):
    try: return float(market.get_ticker(instId=inst)['data'][0]['last'])
    except: return None

def open_spot_10():
    if SPOT_TRADES: return False
    inst=random.choice(COINS_SPOT)
    try:
        # OKX spot يحتاج قيمة بالدولار - نستخدم quote ccY
        # نشتري بـ 10 USDT
        o=trade.place_order(instId=inst, tdMode="cash", side="buy", ordType="market", sz="10", tgtCcy="quoteCcy")
        p=get_price(inst)
        SPOT_TRADES.append({"coin":inst,"entry":p,"pnl":0,"highest":p,"type":"SPOT","usd":10})
        HISTORY.append(f"💎 SPOT BUY {inst} بـ 10$ @ {p}")
        return True
    except Exception as e:
        HISTORY.append(f"SPOT FAIL {inst} {e}"); return False

def open_fut_9():
    if FUT_TRADES: return False
    inst=random.choice(COINS_FUT)
    try:
        acct.set_leverage(instId=inst, lever="3", mgnMode="isolated")
        side=random.choice(["buy","sell"])
        # نفتح بـ 9$ تقريبا - 9 DOGE ~ 2$ لكن نحط 10 للامان
        trade.place_order(instId=inst, tdMode="isolated", side=side, posSide="long" if side=="buy" else "short", ordType="market", sz="20", ccy="USDT")
        p=get_price(inst)
        FUT_TRADES.append({"coin":inst,"side":side,"entry":p,"pnl":0,"highest":p,"lowest":p,"type":"FUT"})
        HISTORY.append(f"⚡ FUT {side.upper()} {inst} x3 بـ 9$ @ {p}")
        return True
    except Exception as e:
        HISTORY.append(f"FUT FAIL {inst} {e}"); return False

def close_trade(t, lst):
    try:
        if t["type"]=="SPOT":
            # بيع كل الكمية
            bal=acct.get_account_balance()
            # بيع ماركت
            trade.place_order(instId=t["coin"], tdMode="cash", side="sell", ordType="market", sz="100", tgtCcy="baseCcy")
        else:
            side="sell" if t["side"]=="buy" else "buy"
            posSide="long" if t["side"]=="buy" else "short"
            trade.place_order(instId=t["coin"], tdMode="isolated", side=side, posSide=posSide, ordType="market", sz="20")
        global TOTAL_PNL; TOTAL_PNL+=t["pnl"]
        HISTORY.append(f"💰 CLOSE {t['coin']} {t['pnl']:.2f}% | اجمالي {TOTAL_PNL:.2f}%")
        lst.remove(t)
    except Exception as e: HISTORY.append(f"CLOSE ERR {e}")

def loop():
    global GEN,IQ
    while True:
        try:
            all_t=SPOT_TRADES+FUT_TRADES
            for t in all_t[:]:
                p=get_price(t["coin"])
                if not p: continue
                t["highest"]=max(t["highest"],p)
                if "lowest" in t: t["lowest"]=min(t["lowest"],p)
                if t["type"]=="SPOT":
                    t["pnl"]=((p-t["entry"])/t["entry"])*100
                    if t["pnl"]>=4 or t["pnl"]<=-3:
                        close_trade(t, SPOT_TRADES); GEN+=1; IQ+=1
                else:
                    if t["side"]=="buy":
                        t["pnl"]=((p-t["entry"])/t["entry"])*100*3
                    else:
                        t["pnl"]=((t["entry"]-p)/t["entry"])*100*3
                    if t["pnl"]>=15 or t["pnl"]<=-8:
                        close_trade(t, FUT_TRADES); GEN+=1; IQ+=2
            if len(SPOT_TRADES)==0 and CONFIG["status"]=="RUNNING":
                open_spot_10(); time.sleep(2)
            if len(FUT_TRADES)==0 and CONFIG["status"]=="RUNNING":
                open_fut_9()
            time.sleep(12)
        except Exception as e:
            HISTORY.append(f"LOOP {e}"); time.sleep(5)

threading.Thread(target=loop, daemon=True).start()
HTML="""
<!DOCTYPE html><html dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V29.1 10$</title><style>body{background:#07070c;color:#fff;font-family:system-ui;padding:10px}.card{background:#13131d;border-radius:12px;padding:12px;margin-bottom:8px;border:1px solid #222}.green{color:#00ff88}.red{color:#ff3b3b}.big{font-size:20px;font-weight:900}</style><meta http-equiv="refresh" content="5"></head><body>
<h3>👑 V29.1 - مقسم 10$+9$ <span style="background:#222;padding:2px 8px;border-radius:10px;font-size:10px">GEN {{GEN}}</span></h3>
<div class="card" style="border-color:#00ff88">اجمالي: <b class="big {{'green' if total>=0 else 'red'}}">{{"%.2f"|format(total)}}%</b> | {{spot|length}} سبوت | {{fut|length}} فيوتشر</div>
<div class="card">💎 سبوت (10$){% for t in spot %}<div style="margin-top:6px">{{t.coin}} PnL <b class="{{'green' if t.pnl>0 else 'red'}}">{{"%.2f"|format(t.pnl)}}%</b></div>{% else %}<div>جاري فتح صفقة 10$...</div>{% endfor %}</div>
<div class="card">⚡ فيوتشر (9$ x3){% for t in fut %}<div style="margin-top:6px">{{t.coin}} {{t.side}} PnL <b class="{{'green' if t.pnl>0 else 'red'}}">{{"%.2f"|format(t.pnl)}}%</b></div>{% else %}<div>جاري فتح صفقة 9$...</div>{% endfor %}</div>
<div class="card">{% for h in history[::-1][:15] %}<div style="font-size:11px;padding:2px 0;border-bottom:1px solid #1a1a1a">{{h}}</div>{% endfor %}</div>
</body></html>
"""
@app.route("/")
def index(): return render_template_string(HTML, GEN=GEN, spot=SPOT_TRADES, fut=FUT_TRADES, history=HISTORY, total=TOTAL_PNL)
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
