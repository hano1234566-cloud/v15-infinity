import os, time, threading, ccxt
from flask import Flask

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL=21.06; LIQ=0; TRADES=0; PNLS=0.0
LAST="🔥 صياد شغال - V20008 HUNTER ACTIVE"
RUN=True

app = Flask(__name__)

def get_ex():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True})

def hunter_loop():
    global BAL, LIQ, TRADES, PNLS, LAST
    while RUN:
        try:
            ex = get_ex()
            b = ex.fetch_balance()
            BAL = float(b.get('USDT',{}).get('free',0) or BAL)
            
            if BAL < 5:
                LAST="رصيد قليل - انتظر"; time.sleep(60); continue
            
            # صيد
            try:
                # رافعة
                try:
                    ex.private_post_account_set_leverage({
                        'instId':'AVAX-USDT-SWAP','lever':'3',
                        'mgnMode':'isolated','posSide':'long'
                    })
                except: pass
                
                LAST=f"يبحث عن دخول... BAL ${BAL:.2f} | Trades:{TRADES}"
                
                # دخول LONG
                ex.private_post_trade_order({
                    'instId':'AVAX-USDT-SWAP','tdMode':'isolated',
                    'side':'buy','posSide':'long','ordType':'market','sz':'1'
                })
                TRADES+=1
                entry_price = ex.fetch_ticker('AVAX/USDT:USDT')['last']
                LAST=f"✅ دخل LONG 1 AVAX @ ${entry_price:.2f} | x3 | Trade#{TRADES}"
                
                # انتظر 45 ثانية - يصيد ربح
                time.sleep(45)
                
                # خروج
                ex.private_post_trade_order({
                    'instId':'AVAX-USDT-SWAP','tdMode':'isolated',
                    'side':'sell','posSide':'long','ordType':'market','sz':'1'
                })
                exit_price = ex.fetch_ticker('AVAX/USDT:USDT')['last']
                pnl = (exit_price - entry_price) * 1 * 3
                PNLS+=pnl
                LAST=f"💰 سكر @ ${exit_price:.2f} | PnL ${pnl:.3f} | الكلي ${PNLS:.3f} | BAL ${BAL:.2f}"
                LIQ=0
                time.sleep(10)
                
            except Exception as e:
                LAST=f"انتظار السوق: {str(e)[:100]}"
                time.sleep(30)
                
        except Exception as e:
            LAST=f"Loop error: {str(e)[:100]}"; time.sleep(30)

threading.Thread(target=hunter_loop, daemon=True).start()

@app.route('/')
def home():
    return f"""
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="8">
<style>
body{{margin:0;background:#050507;color:#fff;font-family:monospace}}
.card{{background:linear-gradient(135deg,rgba(168,85,247,0.15),rgba(0,0,0,0.5));border:1px solid #a855f7;border-radius:16px;padding:14px;margin:10px}}
.live{{background:#00ff88;color:#000;padding:5px 12px;border-radius:20px;font-size:11px;animation:blink 1s infinite}} @keyframes blink{{50%{{opacity:0.5}}}}
.yellow{{color:#facc15}} .red{{color:#ff003c}} .green{{color:#00ff88}}
.log{{background:#000;border-left:3px solid #00ff88;padding:10px;font-size:12px;margin:10px;border-radius:8px}}
</style></head><body>
<div style="padding:16px;display:flex;justify-content:space-between"><div style="font-size:18px;font-weight:900">DEATH HUNTER</div><div class="live">● HUNTING V20008</div></div>
<div class="card">
<div style="display:flex;justify-content:space-between">
<div>BAL <span class="yellow">${BAL:.2f}</span></div>
<div>PNL <span class="green">${PNLS:.3f}</span></div>
<div>T <span class="green">{TRADES}</span></div>
<div>LIQ <span class="red">{LIQ}/15</span></div>
</div>
<div class="log">{LAST}</div>
</div>
<div style="text-align:center;padding:10px;color:#888;font-size:11px">AVAX x3 isolated | long_short_mode | يصيد كل 60 ثانية لين المغرب<br>سيب الموقع مفتوح - يحدث كل 8 ثواني</div>
</body></html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))
