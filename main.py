import os, time, threading, json
from flask import Flask, jsonify
import ccxt

API_KEY = os.getenv("OKX_API_KEY","").strip()
SECRET = os.getenv("OKX_SECRET_KEY","").strip()
PASSPHRASE = os.getenv("OKX_PASSPHRASE","").strip()

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT", "PEPE/USDT", "SHIB/USDT"]
INVEST = 10
DROP = 2.5
PROFIT = 2.8

app = Flask(__name__)
LOGS = []
STATE = {s: {"last": 0, "trades": 0, "price": 0, "drop": 0, "hold": 0} for s in SYMBOLS}
BAL = {"USDT": 0, "total_trades": 0, "profit": 0}

def log(m):
    print(m)
    LOGS.append({"time": time.strftime('%H:%M:%S'), "msg": m})
    if len(LOGS)>100: LOGS.pop(0)

def client():
    return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True,'options':{'defaultType':'spot'}})

def bot():
    log(f"🚀 بدأ مراقبة {len(SYMBOLS)} عملات")
    while True:
        try:
            ex=client()
            bal=ex.fetch_balance()
            usdt=float(bal.get('USDT',{}).get('free',0))
            BAL["USDT"]=usdt
            
            for sym in SYMBOLS:
                try:
                    coin=sym.split('/')[0]
                    coin_free=float(bal.get(coin,{}).get('free',0))
                    price=float(ex.fetch_ticker(sym)['last'])
                    
                    if STATE[sym]["last"]==0: STATE[sym]["last"]=price
                    STATE[sym]["price"]=price
                    STATE[sym]["hold"]=coin_free
                    drop=((STATE[sym]["last"]-price)/STATE[sym]["last"]*100) if STATE[sym]["last"]>0 else 0
                    STATE[sym]["drop"]=drop
                    
                    # شراء
                    if drop>=DROP and usdt>=INVEST:
                        sz=5 if "PEPE" in sym or "SHIB" in sym else INVEST
                        if usdt>=sz:
                            ex.create_order(sym,'market','buy',None,None,{'tgtCcy':'quote_ccy','sz':str(sz)})
                            STATE[sym]["last"]=price
                            STATE[sym]["trades"]+=1
                            BAL["total_trades"]+=1
                            usdt-=sz
                            BAL["USDT"]=usdt
                            log(f"✅ شراء {sym} بـ {sz}$ @ {price}")
                    # بيع
                    elif coin_free*price>=5:
                        prof=((price-STATE[sym]["last"])/STATE[sym]["last"]*100) if STATE[sym]["last"]>0 else 0
                        if prof>=PROFIT:
                            ex.create_market_sell_order(sym,coin_free*0.85)
                            log(f"💸 بيع {sym} بربح {prof:.2f}%")
                except Exception as e:
                    log(f"⚠️ {sym}: {str(e)[:80]}")
                time.sleep(1)
            time.sleep(20)
        except Exception as e:
            log(f"⚠️ عام: {str(e)[:100]}")
            time.sleep(10)

threading.Thread(target=bot,daemon=True).start()

@app.route("/api")
def api():
    return jsonify({"bal": BAL, "state": STATE, "logs": LOGS[-30:][::-1]})

@app.route("/")
def home():
    return """
<!DOCTYPE html>
<html dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>V15 Infinity Dashboard</title>
<style>
body{font-family:system-ui;background:#0a0e1a;color:#fff;margin:0;padding:12px}
.card{background:#151a2c;border-radius:16px;padding:16px;margin:8px 0;border:1px solid #222a44}
.green{color:#00ff88}.red{color:#ff4466}.yellow{color:#ffcc00}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
@media(min-width:600px){.grid{grid-template-columns:1fr 1fr 1fr}}
.coin{background:#1c233d;padding:12px;border-radius:12px;border:1px solid #2a345c}
.log{font-family:monospace;font-size:13px;padding:6px;border-bottom:1px solid #1e2747}
.badge{padding:3px 8px;border-radius:20px;font-size:11px;background:#222a44}
</style></head><body>
<h2 style='text-align:center'>✅ V15 Infinity - لوحة التحكم</h2>
<div class='card'>
<div style='display:flex;justify-content:space-between'><span>💰 USDT</span><b id='usdt' class='green'>--</b></div>
<div style='display:flex;justify-content:space-between'><span>📊 إجمالي الصفقات</span><b id='trades'>--</b></div>
<div style='display:flex;justify-content:space-between'><span>⏱️ تحديث</span><b id='time'>--</b></div>
</div>

<div id='coins' class='grid'></div>

<div class='card'><b>📜 سجل التحركات لايف:</b><div id='logs' style='margin-top:10px;max-height:400px;overflow:auto'></div></div>

<script>
async function load(){
  try{
    let r=await fetch('/api'); let d=await r.json();
    document.getElementById('usdt').innerText=d.bal.USDT.toFixed(2)+'$';
    document.getElementById('trades').innerText=d.bal.total_trades;
    document.getElementById('time').innerText=new Date().toLocaleTimeString('ar-SA');
    
    let coinsHtml='';
    for(let sym in d.state){
      let s=d.state[sym];
      let color=s.drop>=2.5?'red':s.drop>=1?'yellow':'green';
      let holdVal=(s.hold*s.price).toFixed(2);
      coinsHtml+=`<div class='coin'>
      <b>${sym}</b> <span class='badge'>${s.trades} صفقات</span><br>
      سعر: ${s.price}<br>
      <span class='${color}'>نزول: ${s.drop.toFixed(2)}%</span><br>
      آخر شراء: ${s.last.toFixed(4)}<br>
      محتفظ: ${s.hold.toFixed(6)} (${holdVal}$)
      </div>`;
    }
    document.getElementById('coins').innerHTML=coinsHtml;
    
    let logsHtml='';
    d.logs.forEach(l=>{
      let c=l.msg.includes('✅')?'green':l.msg.includes('💸')?'yellow':l.msg.includes('⚠️')?'red':'';
      logsHtml+=`<div class='log ${c}'>${l.time} - ${l.msg}</div>`;
    });
    document.getElementById('logs').innerHTML=logsHtml;
  }catch(e){console.log(e)}
}
load(); setInterval(load,5000);
</script>
</body></html>
"""

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)
