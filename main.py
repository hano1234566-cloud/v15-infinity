import os, time, threading, ccxt
from flask import Flask

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL=20.91; PNLS=0.0045; TRADES=1; WINS=0; LOSSES=1
LAST="V20011 ULTRA - ينتظر فرصة قوية"
RUN=True

app = Flask(__name__)

def get_ex():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True})

def close_all_safe():
    try:
        ex=get_ex()
        ex.private_post_trade_close_positions({'instId':'AVAX-USDT-SWAP','mgnMode':'isolated','posSide':'long'})
        ex.private_post_trade_close_positions({'instId':'AVAX-USDT-SWAP','mgnMode':'isolated','posSide':'short'})
    except: pass

def hunter_ultra():
    global BAL, PNLS, TRADES, WINS, LOSSES, LAST
    close_all_safe()
    time.sleep(1)
    last_price=0
    dip_count=0
    while RUN:
        try:
            ex=get_ex()
            bal=ex.fetch_balance()
            BAL=float(bal.get('USDT',{}).get('free',0) or BAL)
            
            # تأكد ما في صفقات معلقة
            try:
                pos=ex.private_get_account_positions({'instType':'SWAP','instId':'AVAX-USDT-SWAP'})
                for p in pos['data']:
                    if float(p.get('pos','0'))!=0:
                        LAST=f"⚠️ لقى صفقة معلقة {p.get('pos')} - يسكرها"
                        close_all_safe()
                        time.sleep(3)
            except: pass

            ticker=ex.fetch_ticker('AVAX/USDT:USDT')
            price=ticker['last']
            
            # منطق ذكي: يصيد نزول فقط
            if last_price>0:
                if price < last_price:
                    dip_count+=1
                else:
                    dip_count=0
            
            last_price=price
            wr=(WINS/(WINS+LOSSES)*100) if (WINS+LOSSES)>0 else 0
            
            # يدخل فقط اذا نزل 3 مرات ورا بعض - ارتداد
            if dip_count>=3 and BAL>=5:
                try:
                    try:
                        ex.private_post_account_set_leverage({
                            'instId':'AVAX-USDT-SWAP','lever':'3',
                            'mgnMode':'isolated','posSide':'long'
                        })
                    except: pass
                    
                    ex.private_post_trade_order({
                        'instId':'AVAX-USDT-SWAP','tdMode':'isolated',
                        'side':'buy','posSide':'long','ordType':'market','sz':'1'
                    })
                    entry=price
                    TRADES+=1
                    dip_count=0
                    LAST=f"✅ دخل LONG 1 @ ${entry:.3f} بعد نزول #{TRADES}"
                    
                    tp=entry*1.009  # 0.9%
                    sl=entry*0.996  # 0.4% فقط
                    
                    for i in range(50):
                        time.sleep(1)
                        curr=ex.fetch_ticker('AVAX/USDT:USDT')['last']
                        pct=(curr-entry)/entry*100*3
                        
                        if curr>=tp:
                            close_all_safe()
                            profit=(curr-entry)*1
                            PNLS+=profit; WINS+=1
                            LAST=f"💰 ربح +{pct:.2f}% ${curr:.3f} +${profit:.4f} | WR {wr:.0f}%"
                            break
                        elif curr<=sl:
                            close_all_safe()
                            loss=(curr-entry)*1
                            PNLS+=loss; LOSSES+=1
                            LAST=f"🔻 خسارة {pct:.2f}% ${curr:.3f} | الكلي ${PNLS:.4f}"
                            break
                        LAST=f"⏳ يراقب ${curr:.3f} / TP ${tp:.3f} | {pct:+.2f}% | {i}s"
                    
                    close_all_safe() # تأكيد اغلاق
                    time.sleep(5)
                    
                except Exception as e:
                    LAST=f"فشل دخول: {str(e)[:70]}"
                    close_all_safe()
                    time.sleep(10)
            else:
                LAST=f"يراقب ${price:.3f} | نزل {dip_count}/3 | BAL ${BAL:.2f} | WR {wr:.0f}%"
                time.sleep(2)
                
        except Exception as e:
            LAST=f"خطأ: {str(e)[:80]}"; time.sleep(5)

threading.Thread(target=hunter_ultra, daemon=True).start()

@app.route('/close')
def force_close():
    close_all_safe()
    return "✅ Closed all - ارجع /"

@app.route('/')
def home():
    wr=(WINS/(WINS+LOSSES)*100) if (WINS+LOSSES)>0 else 0
    return f"""
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="4">
<style>
body{{margin:0;background:#050507;color:#fff;font-family:monospace}}
.card{{background:linear-gradient(135deg,rgba(168,85,247,0.15),rgba(0,0,0,0.5));border:1px solid #a855f7;border-radius:16px;padding:14px;margin:10px}}
.live{{background:#00ff88;color:#000;padding:5px 12px;border-radius:20px;font-size:11px;animation:blink 1s infinite}} @keyframes blink{{50%{{opacity:0.6}}}}
.yellow{{color:#facc15}} .red{{color:#ff003c}} .green{{color:#00ff88}}
.log{{background:#000;border-left:3px solid #00ff88;padding:10px;font-size:12px;margin:10px;border-radius:8px;min-height:36px}}
.btn{{display:block;background:#222;color:#fff;text-align:center;padding:10px;border-radius:10px;text-decoration:none;font-size:11px;margin:10px;border:1px solid #444}}
</style></head><body>
<div style="padding:16px;display:flex;justify-content:space-between"><div style="font-size:18px;font-weight:900">DEATH HUNTER</div><div class="live">● ULTRA V20011</div></div>
<div class="card">
<div style="display:flex;justify-content:space-between;font-size:12px">
<div>BAL <span class="yellow">${BAL:.2f}</span></div>
<div>PNL <span class="green">${PNLS:.4f}</span></div>
<div>W/L <span class="green">{WINS}/{LOSSES}</span></div>
<div>WR <span class="yellow">{wr:.0f}%</span></div>
</div>
<div class="log">{LAST}</div>
</div>
<a class="btn" href="/close">سكر كل الصفقات (طوارئ)</a>
<div style="text-align:center;color:#666;font-size:10px">1 AVAX x3 | يدخل بعد 3 نزول | TP 0.9% SL 0.4% | يصيد ذكي</div>
</body></html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))
