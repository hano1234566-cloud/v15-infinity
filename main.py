import os, time, threading, ccxt
from flask import Flask

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL=18.07; LIQ=0; TRADES=4; PNLS=0.0045; WINS=0; LOSSES=1
LAST="V20010 FIX - يسكر الصفقات المعلقة"
RUN=True

app = Flask(__name__)

def get_ex():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True})

def close_all():
    try:
        ex=get_ex()
        pos = ex.private_get_account_positions({'instType':'SWAP','instId':'AVAX-USDT-SWAP'})
        for p in pos['data']:
            if float(p.get('pos','0'))!=0:
                sz = p['pos']
                side = 'sell' if float(sz)>0 else 'buy'
                posSide = p.get('posSide','long')
                ex.private_post_trade_close_positions({
                    'instId':'AVAX-USDT-SWAP','mgnMode':'isolated','posSide':posSide
                })
    except Exception as e:
        pass

def hunter_fix():
    global BAL, LIQ, TRADES, PNLS, LAST, WINS, LOSSES
    # سكر اول شي
    close_all()
    time.sleep(2)
    while RUN:
        try:
            ex=get_ex()
            b=ex.fetch_balance()
            BAL=float(b.get('USDT',{}).get('free',0) or BAL)
            # شيك اذا في صفقات عالقة
            try:
                pos = ex.private_get_account_positions({'instType':'SWAP'})
                has_pos = any(float(p.get('pos','0'))!=0 for p in pos['data'])
                if has_pos:
                    LAST=f"⚠️ في صفقة معلقة - يسكرها... BAL ${BAL:.2f}"
                    close_all()
                    time.sleep(5)
                    continue
            except: pass
            
            try:
                ex.private_post_account_set_leverage({
                    'instId':'AVAX-USDT-SWAP','lever':'3','mgnMode':'isolated','posSide':'long'
                })
            except: pass
            
            ticker=ex.fetch_ticker('AVAX/USDT:USDT')
            price=ticker['last']
            LAST=f"يراقب ${price:.3f} | BAL ${BAL:.2f} | آمن 1 AVAX | W:{WINS} L:{LOSSES}"

            # فقط 1 AVAX مو 1.5
            ex.private_post_trade_order({
                'instId':'AVAX-USDT-SWAP','tdMode':'isolated',
                'side':'buy','posSide':'long','ordType':'market','sz':'1'
            })
            entry=price
            TRADES+=1
            
            # TP 0.8% SL 0.5% - اسرع وآمن
            tp=entry*1.008
            sl=entry*0.995
            
            for i in range(40):
                time.sleep(1)
                curr=ex.fetch_ticker('AVAX/USDT:USDT')['last']
                if curr>=tp:
                    ex.private_post_trade_close_positions({
                        'instId':'AVAX-USDT-SWAP','mgnMode':'isolated','posSide':'long'
                    })
                    profit=(curr-entry)*1
                    PNLS+=profit; WINS+=1
                    LAST=f"💰 TP +0.8% ${curr:.3f} +${profit:.4f} الكلي ${PNLS:.4f}"
                    break
                elif curr<=sl:
                    ex.private_post_trade_close_positions({
                        'instId':'AVAX-USDT-SWAP','mgnMode':'isolated','posSide':'long'
                    })
                    loss=(curr-entry)*1
                    PNLS+=loss; LOSSES+=1
                    LAST=f"🔻 SL -0.5% ${curr:.3f} الكلي ${PNLS:.4f}"
                    break
                if i==39:
                    ex.private_post_trade_close_positions({
                        'instId':'AVAX-USDT-SWAP','mgnMode':'isolated','posSide':'long'
                    })
                    profit=(curr-entry)*1
                    PNLS+=profit
                    if profit>0: WINS+=1
                    else: LOSSES+=1
                    LAST=f"⏱ سكر ${curr:.3f} {profit:+.4f} الكلي ${PNLS:.4f}"
            time.sleep(5)
        except Exception as e:
            LAST=f"انتظار: {str(e)[:90]}"; time.sleep(15)

threading.Thread(target=hunter_fix, daemon=True).start()

@app.route('/close')
def force_close():
    close_all()
    return "Closed all - ارجع للرئيسية"

@app.route('/')
def home():
    wr=(WINS/(WINS+LOSSES)*100) if (WINS+LOSSES)>0 else 0
    return f"""
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="5">
<style>
body{{margin:0;background:#050507;color:#fff;font-family:monospace}}
.card{{background:linear-gradient(135deg,rgba(168,85,247,0.15),rgba(0,0,0,0.5));border:1px solid #a855f7;border-radius:16px;padding:14px;margin:10px}}
.live{{background:#ffcc00;color:#000;padding:5px 12px;border-radius:20px;font-size:11px}} .yellow{{color:#facc15}} .red{{color:#ff003c}} .green{{color:#00ff88}}
.log{{background:#000;border-left:3px solid #ffcc00;padding:10px;font-size:12px;margin:10px;border-radius:8px}}
.btn{{display:block;background:#ff003c;color:#fff;text-align:center;padding:12px;border-radius:10px;text-decoration:none;font-weight:900;margin:10px}}
</style></head><body>
<div style="padding:16px;display:flex;justify-content:space-between"><div style="font-size:18px;font-weight:900">DEATH HUNTER</div><div class="live">● FIX V20010</div></div>
<div class="card">
<div style="display:flex;justify-content:space-between;font-size:12px">
<div>BAL <span class="yellow">${BAL:.2f}</span></div>
<div>PNL <span class="green">${PNLS:.4f}</span></div>
<div>W/L <span class="green">{WINS}/{LOSSES}</span></div>
<div>WR <span class="yellow">{wr:.0f}%</span></div>
</div>
<div class="log">{LAST}</div>
</div>
<a class="btn" href="/close">🚨 سكر كل الصفقات المعلقة - اضغط لو BAL ناقص</a>
<div style="text-align:center;color:#888;font-size:10px">1 AVAX x3 | TP 0.8% SL 0.5% | يسكر تلقائي</div>
</body></html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))
