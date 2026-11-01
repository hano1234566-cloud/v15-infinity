import os, time, threading, ccxt
from flask import Flask
app = Flask(__name__)

KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASS = os.getenv("OKX_PASSPHRASE","").strip()

TRADE = 5.0
FEE = 0.16
STOP = -1.5
TARGET = 2.5

SPOT_COINS = ["TRX/USDT","DOGE/USDT","LSK/USDT"]
FUT_COINS = ["TRX/USDT:USDT","DOGE/USDT:USDT","BTC/USDT:USDT"]

state = {"spot_usdt":0,"spot":{},"fut":{},"log":"يبدأ","spot_buy":{},"fut_buy":{}}

def get_ex(t='spot'):
    return ccxt.okx({'apiKey':KEY,'secret':SECRET,'password':PASS,'enableRateLimit':True,'options':{'defaultType':t}})

def bot():
    # قراءة القديم
    try:
        es = get_ex('spot'); es.load_markets()
        b = es.fetch_balance()
        for s in SPOT_COINS:
            coin = s.split('/')[0]
            free = float(b.get(coin,{}).get('free',0) or 0)
            if free*es.fetch_ticker(s)['last']>1:
                state["spot_buy"][s]=es.fetch_ticker(s)['last']
    except: pass

    while True:
        try:
            # ===== SPOT 5$ =====
            es = get_ex('spot'); es.load_markets()
            bal = es.fetch_balance()
            state["spot_usdt"]=float(bal.get('USDT',{}).get('free',0) or 0)
            spot={}
            for sym in list(state["spot_buy"].keys()):
                coin=sym.split('/')[0]
                free=float(bal.get(coin,{}).get('free',0) or 0)
                last=es.fetch_ticker(sym)['last']
                if free*last<0.5: 
                    del state["spot_buy"][sym]; continue
                buy=state["spot_buy"][sym]
                pnl=(last-buy)/buy*100-FEE
                spot[coin]={"amt":free,"buy":buy,"last":last,"pnl":pnl}
                if pnl<=STOP or pnl>=TARGET:
                    es.create_market_sell_order(sym, free)
                    state["log"]=f"سبوت {coin} {pnl:.2f}%"
                    del state["spot_buy"][sym]
            state["spot"]=spot

            if state["spot_usdt"]>=6 and len(state["spot_buy"])<1:
                for sym in SPOT_COINS:
                    if sym in state["spot_buy"]: continue
                    tk=es.fetch_ticker(sym)
                    if -4 < (tk.get('percentage') or 0) < -1.2:
                        amt=es.amount_to_precision(sym, TRADE/tk['last'])
                        es.create_market_buy_order(sym, float(amt))
                        state["spot_buy"][sym]=tk['last']
                        state["log"]=f"سبوت شراء {sym}"
                        break

            # ===== FUTURES 5$ =====
            try:
                ef=get_ex('swap'); ef.load_markets()
                # ضبط رافعة قليلة
                for sym in FUT_COINS:
                    try: ef.set_leverage(3, sym, params={'mgnMode':'isolated'})
                    except: pass

                poss=ef.fetch_positions()
                fut={}
                open_syms=[]
                for p in poss:
                    if float(p.get('contracts') or 0)>0:
                        sym=p['symbol']
                        open_syms.append(sym)
                        entry=float(p['entryPrice'] or 0)
                        mark=float(p['markPrice'] or 0)
                        pnl=float(p['percentage'] or 0)
                        fut[sym]={"side":p['side'],"entry":entry,"last":mark,"pnl":pnl,"contracts":p['contracts']}
                        # وقف فيوتشر
                        if pnl<=STOP or pnl>=TARGET:
                            side = 'sell' if p['side']=='long' else 'buy'
                            ef.create_market_order(sym, side, p['contracts'], None, params={'posSide':p['side'],'mgnMode':'isolated'})
                            state["log"]=f"فيوتشر {sym} {pnl:.2f}%"
                state["fut"]=fut

                # دخول فيوتشر 5$
                if len(open_syms)<1:
                    for sym in FUT_COINS:
                        if sym in open_syms: continue
                        tk=ef.fetch_ticker(sym)
                        if -4 < (tk.get('percentage') or 0) < -1.2:
                            price=tk['last']
                            amount = TRADE / price / 3 * price # تقريب 5$ مع رافعة 3
                            contracts = ef.amount_to_precision(sym, TRADE / price)
                            try:
                                ef.create_market_order(sym, 'buy', float(contracts), None, params={'posSide':'long','mgnMode':'isolated'})
                                state["log"]=f"فيوتشر شراء {sym} 5$"
                                break
                            except Exception as fe:
                                state["log"]=f"فيوتشر خطأ {str(fe)[:30]}"
            except Exception as fe:
                state["log"]=f"فيوتشر {str(fe)[:40]}"

            time.sleep(20)
        except Exception as e:
            state["log"]=str(e)[:60]
            time.sleep(20)

threading.Thread(target=bot,daemon=True).start()

@app.route('/')
def home():
    spot_html="".join([f"<tr><td>{k}</td><td>{v['amt']:.1f}</td><td>{v['buy']:.5f}</td><td>{v['last']:.5f}</td><td>{v['pnl']:+.2f}%</td></tr>" for k,v in state["spot"].items()]) or "<tr><td colspan=5>فاضي</td></tr>"
    fut_html="".join([f"<tr><td>{k}</td><td>{v['side']}</td><td>{v['entry']:.5f}</td><td>{v['last']:.5f}</td><td>{v['pnl']:+.2f}%</td></tr>" for k,v in state["fut"].items()]) or "<tr><td colspan=5>فاضي</td></tr>"

    return f"""
    <body style="background:#000;color:#fff;font-family:monospace;padding:10px">
    <div style="border:2px solid #0f0;padding:10px">
    <h2 style="color:#0f0;margin:0">SPOT 5$ - {state['spot_usdt']:.2f} USDT</h2>
    <table border=1 width=100% cellpadding=5 style="border-collapse:collapse"><tr><th>عملة</th><th>كمية</th><th>شراء</th><th>حالي</th><th>PnL صافي</th></tr>{spot_html}</table>
    </div>
    <div style="border:2px solid #ff0;padding:10px;margin-top:15px">
    <h2 style="color:#ff0;margin:0">FUTURES 5$ فقط - رافعة 3x</h2>
    <table border=1 width=100% cellpadding=5 style="border-collapse:collapse"><tr><th>رمز</th><th>اتجاه</th><th>دخول</th><th>حالي</th><th>PnL</th></tr>{fut_html}</table>
    </div>
    <p style="text-align:center;color:#0af">{state['log']} | وقف {STOP}% | هدف {TARGET}%</p>
    </body>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=int(os.getenv("PORT",10000)))
