import os, time, threading, random
from flask import Flask, render_template_string
import okx.Account as Account
import okx.Trade as Trade
import okx.MarketData as Market

app = Flask(__name__)
API_KEY = os.getenv("OKX_API_KEY")
SECRET = os.getenv("OKX_SECRET")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")
FLAG = "0"

GEN=216; IQ=568; TOTAL_PNL=0.0; COMPOUND_LEVEL=1
CONFIG={"lev":3,"status":"RUNNING","max_trades":2}
SPOT_TRADES=[]; FUT_TRADES=[]; HISTORY=["🔥 V29 HYBRID COMPOUND بدأ - سبوت+فيوتشر"]

acct = Account.AccountAPI(API_KEY, SECRET, PASSPHRASE, False, FLAG)
trade = Trade.TradeAPI(API_KEY, SECRET, PASSPHRASE, False, FLAG)
market = Market.MarketAPI(API_KEY, SECRET, PASSPHRASE, False, FLAG)

COINS_SPOT=["DOGE-USDT","PEPE-USDT","SHIB-USDT","BONK-USDT"]
COINS_FUT=["DOGE-USDT-SWAP","PEPE-USDT-SWAP","SHIB-USDT-SWAP","BONK-USDT-SWAP"]

def get_price(inst):
    try: return float(market.get_ticker(instId=inst)['data'][0]['last'])
    except: return None

def open_spot(inst):
    try:
        p=get_price(inst)
        sz="20" if "DOGE" in inst else "1000000"
        o=trade.place_order(instId=inst, tdMode="cash", side="buy", ordType="market", sz=sz)
        SPOT_TRADES.append({"coin":inst,"entry":p,"pnl":0,"highest":p,"type":"SPOT"})
        HISTORY.append(f"💎 SPOT BUY {inst} @ {p}")
        return True
    except Exception as e:
        HISTORY.append(f"SPOT FAIL {e}"); return False

def open_fut(inst, side):
    try:
        acct.set_leverage(instId=inst, lever=str(CONFIG["lev"]), mgnMode="isolated")
        sz="15"
        posSide="long" if side=="buy" else "short"
        side_o="buy" if side=="buy" else "sell"
        trade.place_order(instId=inst, tdMode="isolated", side=side_o, posSide=posSide, ordType="market", sz=sz)
        p=get_price(inst)
        FUT_TRADES.append({"coin":inst,"side":side,"entry":p,"pnl":0,"highest":p,"lowest":p,"type":"FUT"})
        HISTORY.append(f"⚡ FUT {side.upper()} {inst} x{CONFIG['lev']} @ {p}")
        return True
    except Exception as e:
        HISTORY.append(f"FUT FAIL {e}"); return False

def close_trade(t, lst):
    try:
        if t["type"]=="SPOT":
            trade.place_order(instId=t["coin"], tdMode="cash", side="sell", ordType="market", sz="20")
        else:
            side="sell" if t["side"]=="buy" else "buy"
            posSide="long" if t["side"]=="buy" else "short"
            trade.place_order(instId=t["coin"], tdMode="isolated", side=side, posSide=posSide, ordType="market", sz="15")
        global TOTAL_PNL
        TOTAL_PNL+=t["pnl"]
        HISTORY.append(f"💰 CLOSE {t['coin']} {t['pnl']:.1f}% | اجمالي {TOTAL_PNL:.1f}%")
        lst.remove(t)
        # كومباوند - كل ما ربح يزود صفقات
        if TOTAL_PNL>10 and CONFIG["max_trades"]==2:
            CONFIG["max_trades"]=3; HISTORY.append("🚀 LEVEL UP! صار يفتح 3 صفقات!")
        if TOTAL_PNL>25 and CONFIG["max_trades"]==3:
            CONFIG["max_trades"]=4; HISTORY.append("🚀🚀 LEVEL UP! صار يفتح 4 صفقات!")
        if TOTAL_PNL>50:
            CONFIG["max_trades"]=5; HISTORY.append("🔥🔥🔥 وحش! 5 صفقات بنفس الوقت!")
    except Exception as e: HISTORY.append(f"CLOSE ERR {e}")

def hybrid_loop():
    global GEN, IQ
    while True:
        try:
            all_trades=SPOT_TRADES+FUT_TRADES
            # ادارة
            for t in all_trades[:]:
                p=get_price(t["coin"])
                if not p: continue
                t["highest"]=max(t["highest"],p)
                if "lowest" in t: t["lowest"]=min(t["lowest"],p)
                if t["type"]=="SPOT":
                    t["pnl"]=((p-t["entry"])/t["entry"])*100
                    if t["pnl"]<=-2 or t["pnl"]>=5:
                        close_trade(t, SPOT_TRADES); GEN+=1; IQ+=1
                else:
                    if t["side"]=="buy":
                        t["pnl"]=((p-t["entry"])/t["entry"])*100*CONFIG["lev"]
                        trail=(t["highest"]-p)/t["highest"]*100*CONFIG["lev"]
                    else:
                        t["pnl"]=((t["entry"]-p)/t["entry"])*100*CONFIG["lev"]
                        trail=(p-t["lowest"])/t["lowest"]*100*CONFIG["lev"]
                    if t["pnl"]<=-10 or (t["pnl"]>=18) or t["pnl"]>=30:
                        close_trade(t, FUT_TRADES); GEN+=1; IQ+=2

            # دخول جديد - مركب
            if len(all_trades)<CONFIG["max_trades"] and CONFIG["status"]=="RUNNING":
                # 50% سبوت 50% فيوتشر
                if random.random()>0.5 and len(SPOT_TRADES)<3:
                    inst=random.choice(COINS_SPOT)
                    if get_price(inst): open_spot(inst); GEN+=1
                else:
                    if len(FUT_TRADES)<3:
                        inst=random.choice(COINS_FUT)
                        side=random.choice(["buy","sell"])
                        if get_price(inst): open_fut(inst, side); GEN+=1
            time.sleep(15)
        except Exception as e:
            HISTORY.append(f"LOOP {e}"); time.sleep(5)

threading.Thread(target=hybrid_loop, daemon=True).start()

HTML="""
<!DOCTYPE html><html dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V29 HYBRID</title><style>
body{background:#07070c;color:#fff;font-family:system-ui;margin:0;padding:10px}
.card{background:#13131d;border-radius:14px;padding:12px;margin-bottom:8px;border:1px solid #222}
.big{font-size:22px;font-weight:900} .green{color:#00ff88} .red{color:#ff3b3b} .yellow{color:#ffcc00}
.grid{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:6px}
.badge{padding:2px 7px;border-radius:20px;background:#222;font-size:10px}
</style><meta http-equiv="refresh" content="5"></head><body>
<h3>👑 V29 HYBRID COMPOUND <span class="badge">GEN {{GEN}} IQ {{IQ}}</span></h3>

<div class="card" style="border:1px solid #00ff88">
<div>💰 اجمالي الربح المركب: <b class="big {{'green' if total>=0 else 'red'}}">{{"%.2f"|format(total)}}%</b> | مستوى {{level}} | يفتح {{cfg.max_trades}} صفقات</div>
<div style="background:#222;height:8px;border-radius:4px;margin-top:6px"><div style="width:{{[total,100]|min}}%;background:#00ff88;height:8px;border-radius:4px"></div></div>
<div style="font-size:10px;margin-top:4px">10% -> 3 صفقات | 25% -> 4 صفقات | 50% -> 5 صفقات (كرة ثلج)</div>
</div>

<div class="grid">
<div class="card"><div style="font-size:10px">سبوت</div><div class="big">{{spot|length}}</div></div>
<div class="card"><div style="font-size:10px">فيوتشر</div><div class="big">{{fut|length}}</div></div>
<div class="card"><div style="font-size:10px">الكل</div><div class="big">{{spot|length + fut|length}}/{{cfg.max_trades}}</div></div>
<div class="card"><div style="font-size:10px">رافعة</div><div class="big">x{{cfg.lev}}</div></div>
</div>

<div class="card">
<h4>💎 سبوت (آمن - يحتفظ بالعملة)</h4>
{% for t in spot %}
<div style="background:#1a1a2a;padding:8px;border-radius:8px;margin-top:5px;border-right:3px solid {{'green' if t.pnl>0 else 'red'}}">
{{t.coin}} | {{t.entry}} -> PnL <b class="{{'green' if t.pnl>0 else 'red'}}">{{"%.2f"|format(t.pnl)}}%</b>
</div>
{% else %}<div style="font-size:12px">لا يوجد سبوت</div>{% endfor %}
</div>

<div class="card">
<h4>⚡ فيوتشر (صياد x{{cfg.lev}})</h4>
{% for t in fut %}
<div style="background:#1a1a2a;padding:8px;border-radius:8px;margin-top:5px;border-right:3px solid {{'green' if t.pnl>0 else 'red'}}">
{{t.coin.replace('-USDT-SWAP','')}} {{t.side.upper()}} x{{cfg.lev}} | PnL <b class="{{'green' if t.pnl>0 else 'red'}}">{{"%.2f"|format(t.pnl)}}%</b>
</div>
{% else %}<div style="font-size:12px">لا يوجد فيوتشر</div>{% endfor %}
</div>

<div class="card"><h4>📜 سجل الوحش</h4>
{% for h in history[::-1][:12] %}<div style="font-size:11px;padding:2px 0;border-bottom:1px solid #1a1a1a">{{h}}</div>{% endfor %}
</div>
</body></html>
"""

@app.route("/")
def index():
    level=1
    if TOTAL_PNL>50: level=4
    elif TOTAL_PNL>25: level=3
    elif TOTAL_PNL>10: level=2
    return render_template_string(HTML, GEN=GEN, IQ=IQ, spot=SPOT_TRADES, fut=FUT_TRADES, history=HISTORY, cfg=CONFIG, total=TOTAL_PNL, level=level)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
