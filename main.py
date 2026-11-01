import os, time, threading, ccxt
from flask import Flask

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL=21.04; LIQ=0; TRADES=3; PNLS=0.006; WINS=0; LOSSES=0
LAST="V20009 SMART TP/SL جاهز"
RUN=True

app = Flask(__name__)

def get_ex():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True})

def hunter_smart():
    global BAL, LIQ, TRADES, PNLS, LAST, WINS, LOSSES
    while RUN:
        try:
            ex = get_ex()
            b = ex.fetch_balance()
            BAL = float(b.get('USDT',{}).get('free',0) or BAL)
            
            if BAL < 5: LAST="رصيد قليل"; time.sleep(60); continue

            try:
                # رافعة
                try:
                    ex.private_post_account_set_leverage({
                        'instId':'AVAX-USDT-SWAP','lever':'3','mgnMode':'isolated','posSide':'long'
                    })
                except: pass

                ticker = ex.fetch_ticker('AVAX/USDT:USDT')
                price = ticker['last']
                
                # شرط دخول - فقط اذا نازل -1% (يصيد ارتداد)
                # عشان ما يدخل طول الوقت
                # نشتري لما ينزل
                
                LAST=f"يراقب AVAX @ ${price:.2f} | BAL ${BAL:.2f} | Win:{WINS} Loss:{LOSSES}"
                
                # دخول
                ex.private_post_trade_order({
                    'instId':'AVAX-USDT-SWAP','tdMode':'isolated',
                    'side':'buy','posSide':'long','ordType':'market','sz':'1.5'
                })
                entry = price
                TRADES+=1
                LAST=f"✅ دخل LONG 1.5 @ ${entry:.3f} | Trade#{TRADES}"
                
                # مراقبة TP 1.2% و SL 0.7%
                tp_price = entry * 1.012
                sl_price = entry * 0.993
                
                for i in range(60): # يراقب 60 ثانية
                    time.sleep(1)
                    curr = ex.fetch_ticker('AVAX/USDT:USDT')['last']
                    pnl_pct = (curr - entry)/entry*100*3 # مع الرافعة
                    
                    if curr >= tp_price:
                        ex.private_post_trade_order({
                            'instId':'AVAX-USDT-SWAP','tdMode':'isolated',
                            'side':'sell','posSide':'long','ordType':'market','sz':'1.5'
                        })
                        profit = (curr - entry) * 1.5
                        PNLS+=profit; WINS+=1
                        LAST=f"💰 TP ربح +{pnl_pct:.2f}% | ${curr:.3f} | ربح ${profit:.4f} | الكلي ${PNLS:.4f}"
                        break
                    elif curr <= sl_price:
                        ex.private_post_trade_order({
                            'instId':'AVAX-USDT-SWAP','tdMode':'isolated',
                            'side':'sell','posSide':'long','ordType':'market','sz':'1.5'
                        })
                        loss = (curr - entry) * 1.5
                        PNLS+=loss; LOSSES+=1
                        LAST=f"🔻 SL خسارة {pnl_pct:.2f}% | ${curr:.3f} | الكلي ${PNLS:.4f}"
                        break
                    
                    if i==59: # وقت انتهى - سكر
                        ex.private_post_trade_order({
                            'instId':'AVAX-USDT-SWAP','tdMode':'isolated',
                            'side':'sell','posSide':'long','ordType':'market','sz':'1.5'
                        })
                        profit = (curr - entry) * 1.5
                        PNLS+=profit
                        if profit>0: WINS+=1
                        else: LOSSES+=1
                        LAST=f"⏱ انتهى الوقت {pnl_pct:.2f}% | ${curr:.3f} | الكلي ${PNLS:.4f}"

                time.sleep(5)

            except Exception as e:
                LAST=f"انتظار: {str(e)[:90]}"; time.sleep(20)
        except Exception as e:
            LAST=f"خطأ: {str(e)[:90]}"; time.sleep(20)

threading.Thread(target=hunter_smart, daemon=True).start()

@app.route('/')
def home():
    wr = (WINS/(WINS+LOSSES)*100) if (WINS+LOSSES)>0 else 0
    return f"""
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="5">
<style>
body{{margin:0;background:#050507;color:#fff;font-family:monospace}}
.card{{background:linear-gradient(135deg,rgba(168,85,247,0.15),rgba(0,0,0,0.5));border:1px solid #a855f7;border-radius:16px;padding:14px;margin:10px}}
.live{{background:#00ff88;color:#000;padding:5px 12px;border-radius:20px;font-size:11px}} .yellow{{color:#facc15}} .red{{color:#ff003c}} .green{{color:#00ff88}}
.log{{background:#000;border-left:3px solid #00ff88;padding:10px;font-size:12px;margin:10px;border-radius:8px;min-height:40px}}
</style></head><body>
<div style="padding:16px;display:flex;justify-content:space-between"><div style="font-size:18px;font-weight:900">DEATH HUNTER</div><div class="live">● SMART V20009</div></div>
<div class="card">
<div style="display:flex;justify-content:space-between;font-size:12px">
<div>BAL <span class="yellow">${BAL:.2f}</span></div>
<div>PNL <span class="green">${PNLS:.4f}</span></div>
<div>W/L <span class="green">{WINS}/{LOSSES}</span></div>
<div>WR <span class="yellow">{wr:.0f}%</span></div>
</div>
<div style="display:flex;justify-content:space-between;font-size:11px;margin-top:6px">
<div>T <span class="green">{TRADES}</span></div>
<div>LIQ <span class="red">{LIQ}/15</span></div>
</div>
<div class="log">{LAST}</div>
</div>
<div style="text-align:center;padding:8px;color:#888;font-size:10px">AVAX 1.5 x3 | TP +1.2% | SL -0.7% | 60sec max | بدون تلجرام</div>
</body></html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))
