import os, time, threading, ccxt, random
from flask import Flask
from collections import deque

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = (os.getenv("OKX_SECRET_KEY","") or os.getenv("OKX_SECRET","")).strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

BAL=20.91; PNLS=0.0045; TRADES=1; WINS=0; LOSSES=1
LAST="GOD MODE V20012 - 5 صيادين جاهزين"
BEST="..."
RUN=True

COINS=["AVAX-USDT-SWAP","SOL-USDT-SWAP","DOGE-USDT-SWAP","XRP-USDT-SWAP","ARB-USDT-SWAP"]
prices_hist={c: deque(maxlen=20) for c in COINS}

app = Flask(__name__)

def get_ex():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True})

def close_all_sym(sym):
    try:
        ex=get_ex()
        ex.private_post_trade_close_positions({'instId':sym,'mgnMode':'isolated','posSide':'long'})
        ex.private_post_trade_close_positions({'instId':sym,'mgnMode':'isolated','posSide':'short'})
    except: pass

def close_all():
    for c in COINS:
        close_all_sym(c)

def calc_score(hist):
    if len(hist)<10: return 0
    # يحسب نزول + تذبذب
    recent=list(hist)
    drop=(recent[-4]-recent[-1])/recent[-4]*100 if recent[-4]!=0 else 0
    vol=max(recent)/min(recent)*100-100 if min(recent)!=0 else 0
    # يبغى drop موجب (نازل) و vol عالي
    score=drop*2 + vol
    return score

def god_hunter():
    global BAL, PNLS, TRADES, WINS, LOSSES, LAST, BEST
    close_all()
    while RUN:
        try:
            ex=get_ex()
            b=ex.fetch_balance()
            BAL=float(b.get('USDT',{}).get('free',0) or BAL)
            
            # 1. اسكان 5 عملات
            best_coin=None
            best_score=-999
            tickers={}
            
            for coin in COINS:
                try:
                    t=ex.fetch_ticker(coin.replace('-USDT-SWAP','/USDT:USDT'))
                    price=t['last']
                    tickers[coin]=price
                    prices_hist[coin].append(price)
                    score=calc_score(prices_hist[coin])
                    if score>best_score and score>0.5: # لازم نزول واضح
                        best_score=score
                        best_coin=coin
                except: continue
                time.sleep(0.3)
            
            wr=(WINS/(WINS+LOSSES)*100) if (WINS+LOSSES)>0 else 0
            coins_str=" | ".join([f"{c.split('-')[0]} ${tickers.get(c,0):.3f}" for c in COINS[:3]])
            BEST=f"{coins_str}"
            
            if not best_coin or best_score<1.0:
                LAST=f"🔍 يمسح السوق... | {BEST} | BAL ${BAL:.2f} | WR {wr:.0f}%"
                time.sleep(3)
                continue
            
            # 2. دخول على اقوى فرصة
            coin=best_coin
            entry=tickers[coin]
            short=coin.split('-')[0]
            
            LAST=f"🎯 لقى فرصة {short} Score {best_score:.2f} @ ${entry:.4f} - يدخل!"
            
            try:
                ex.private_post_account_set_leverage({
                    'instId':coin,'lever':'3','mgnMode':'isolated','posSide':'long'
                })
            except: pass
            
            # حجم ديناميكي: اذا BAL فوق 20 يدخل 1.5 واذا اقل يدخل 1
            sz = "1.5" if BAL>19 else "1"
            if "DOGE" in coin or "XRP" in coin: sz="30"  # عملات رخيصة
            
            ex.private_post_trade_order({
                'instId':coin,'tdMode':'isolated','side':'buy','posSide':'long','ordType':'market','sz':sz
            })
            TRADES+=1
            LAST=f"✅ دخل {short} LONG {sz} @ ${entry:.4f} | #{TRADES} | Score {best_score:.1f}"
            
            # TP/SL ديناميكي حسب Score
            tp_pct=0.008 + (best_score/1000)  # كل ما Score اعلى TP اعلى
            sl_pct=0.004
            tp=entry*(1+tp_pct)
            sl=entry*(1-sl_pct)
            
            # مراقبة 90 ثانية
            win=False
            for i in range(90):
                time.sleep(1)
                try:
                    curr=ex.fetch_ticker(coin.replace('-USDT-SWAP','/USDT:USDT'))['last']
                    pct=(curr-entry)/entry*100*3
                    if curr>=tp:
                        close_all_sym(coin)
                        profit=(curr-entry)*float(sz)
                        if "DOGE" in coin: profit=(curr-entry)*float(sz)*0.5
                        PNLS+=profit; WINS+=1; win=True
                        LAST=f"💎 {short} TP +{pct:.2f}% ${curr:.4f} +${profit:.4f} | الكلي ${PNLS:.4f} | WR {(WINS/(WINS+LOSSES)*100):.0f}%"
                        break
                    elif curr<=sl:
                        close_all_sym(coin)
                        loss=(curr-entry)*float(sz)
                        PNLS+=loss; LOSSES+=1
                        LAST=f"🔻 {short} SL {pct:.2f}% ${curr:.4f} | الكلي ${PNLS:.4f}"
                        break
                    else:
                        if i%5==0:
                            LAST=f"⏳ {short} ${curr:.4f} TP ${tp:.4f} | {pct:+.2f}% | {i}s | WR {wr:.0f}%"
                except: pass
            
            if not win and 'curr' in locals():
                close_all_sym(coin)
                try:
                    profit=(curr-entry)*float(sz)
                    PNLS+=profit
                    if profit>0: WINS+=1
                    else: LOSSES+=1
                    LAST=f"⏱ {short} سكر ${curr:.4f} {profit:+.4f} | الكلي ${PNLS:.4f}"
                except: pass
            
            close_all() # تأكيد
            time.sleep(3)
            
        except Exception as e:
            LAST=f"GOD Error: {str(e)[:90]}"; time.sleep(5)

threading.Thread(target=god_hunter, daemon=True).start()

@app.route('/close')
def force_close():
    close_all()
    return "GOD CLOSED - ارجع /"

@app.route('/')
def home():
    wr=(WINS/(WINS+LOSSES)*100) if (WINS+LOSSES)>0 else 0
    return f"""
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="3">
<style>
body{{margin:0;background:#000;color:#fff;font-family:monospace}}
.header{{padding:14px;display:flex;justify-content:space-between;align-items:center;background:linear-gradient(90deg,#a855f7,#ff003c)}}
.card{{background:linear-gradient(135deg,rgba(168,85,247,0.2),rgba(0,0,0,0.6));border:1px solid #a855f7;border-radius:16px;padding:14px;margin:10px}}
.live{{background:#00ff88;color:#000;padding:5px 12px;border-radius:20px;font-size:11px;animation:pulse 1s infinite}} @keyframes pulse{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.05)}}}}
.yellow{{color:#facc15}} .red{{color:#ff5555}} .green{{color:#00ff88}} .purple{{color:#a855f7}}
.log{{background:#0a0a0a;border-left:3px solid #a855f7;padding:12px;font-size:12px;margin:10px;border-radius:10px;min-height:38px}}
.coins{{background:#111;border:1px solid #333;padding:8px;border-radius:8px;margin:10px;font-size:10px;color:#888}}
.btn{{display:block;background:#222;color:#fff;text-align:center;padding:10px;border-radius:10px;text-decoration:none;font-size:11px;margin:10px;border:1px solid #444}}
.god{{background:linear-gradient(90deg,#a855f7,#ff003c);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:900}}
</style></head><body>
<div class="header"><div style="font-size:18px;font-weight:900">DEATH HUNTER <span class="god">GOD MODE</span></div><div class="live">● V20012 ULTRA</div></div>
<div class="card">
<div style="display:flex;justify-content:space-between;font-size:12px">
<div>BAL <span class="yellow">${BAL:.2f}</span></div>
<div>PNL <span class="green">${PNLS:.4f}</span></div>
<div>W/L <span class="green">{WINS}/{LOSSES}</span></div>
<div>WR <span class="yellow">{wr:.0f}%</span></div>
</div>
<div style="display:flex;justify-content:space-between;font-size:10px;margin-top:8px;color:#aaa">
<div>T <span class="green">{TRADES}</span></div>
<div style="color:#a855f7">5 COINS SCANNER</div>
<div>x3 LEV</div>
</div>
<div class="log">{LAST}</div>
<div class="coins">📡 SCAN: {BEST}</div>
</div>
<a class="btn" href="/close">🚨 طوارئ - سكر الكل</a>
<div style="text-align:center;color:#555;font-size:9px;padding:6px">AVAX SOL DOGE XRP ARB | يدخل على اقوى نزول | TP ديناميكي 0.8-1.5% | SL 0.4% | GOD MODE</div>
</body></html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))
