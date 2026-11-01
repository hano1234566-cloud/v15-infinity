# V20001 - FAST FOR CRON - FU 5$ MAX
import os, time, threading
from flask import Flask
import ccxt
API_KEY=os.getenv("OKX_API_KEY","").strip()
SECRET=os.getenv("OKX_SECRET_KEY","").strip()
PASSPHRASE=os.getenv("OKX_PASSPHRASE","").strip()
app=Flask(__name__)
LOGS=[];CACHE={"rows":"","bal":0,"old":"يفحص..."}
MAX_FUTURES_USD = 5.0  # <-- الحد
COST_PER_LIQ = 0.5     # <-- تكلفة كل صفقة فيوتشر
def log(m):
 LOGS.append(f"{time.strftime('%H:%M:%S')} {m}")
 if len(LOGS)>500: LOGS.pop(0)
 print(LOGS[-1],flush=True)
def make(t): return ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True,'options':{'defaultType':t}})
class Bot:
 def __init__(self): self.pos={};self.bal_s=0;self.hunts=0;self.kills=0;self.old="يفحص..."
bot=Bot()
def manager():
 while True:
  try:
   ex_s=make('spot');ex_f=make('swap')
   try:
    bot.bal_s=ex_s.fetch_balance().get('USDT',{}).get('free',0)
    b=ex_s.fetch_balance();holds=[]
    for c in b['total']:
     if c!='USDT' and b['total'][c]>0:
      try: holds.append(f"{c}:${b['total'][c]*ex_s.fetch_ticker(f'{c}/USDT')['last']:.2f}")
      except: pass
    bot.old=" | ".join(holds) if holds else "فاضي";CACHE["old"]=bot.old;CACHE["bal"]=bot.bal_s
   except: pass
   try: ts=ex_s.fetch_tickers();tf=ex_f.fetch_tickers()
   except: time.sleep(5);continue
   rows=""
   for k,buy in list(bot.pos.items()):
    base=k.split(":")[1];is_fut='LIQ' in k;tickers=tf if is_fut else ts
    sym_match=[s for s in tickers if base==s.split('/')[0] and (':USDT' in s if is_fut else '/USDT' in s and ':' not in s)]
    if not sym_match: continue
    now=tickers[sym_match[0]]['last'];prof=((now-buy)/buy)*100
    if 'SHORT' in k: prof=((buy-now)/buy)*100
    if is_fut: prof*=10
    if prof>=5 or prof<=-7 or ('DEATH' in k and prof>=15):
     try:
      if is_fut: ex_f.create_market_sell_order(sym_match[0],0.5/now,{'tdMode':'isolated','posSide':'long'})
      else:
       tot=ex_s.fetch_balance()['total'].get(base,0)
       if tot: ex_s.create_market_sell_order(sym_match[0],tot)
      log(f"[SELL] {base} {prof:+.1f}%");del bot.pos[k];bot.kills+=1
     except Exception as e: log(f"[SELL ERR] {e}")
    rows+=f"<tr><td>{k.split(':')[0]}</td><td>{base}</td><td>{prof:+.1f}%</td></tr>"
   CACHE["rows"]=rows
   for sym,tk in ts.items():
    if '/USDT' not in sym or ':' in sym: continue
    ch=tk.get('percentage') or 0
    if ch<=-18:
     base=sym.split('/')[0]
     if f"DEATH:{base}" not in bot.pos:
      try:
       free=ex_s.fetch_balance().get('USDT',{}).get('free',0)
       if free>=1: ex_s.create_market_buy_order(sym,1/tk['last']);bot.pos[f"DEATH:{base}"]=tk['last'];bot.hunts+=1;log(f"[DEATH BUY] {base} {ch:.1f}%")
      except Exception as e: log(f"[DEATH ERR] {e}")
   # ===== فيوتشر بحد 5$ فقط =====
   liq_count = len([k for k in bot.pos if k.startswith("LIQ:")])
   fut_used = liq_count * COST_PER_LIQ
   for sym,tk in tf.items():
    if ':USDT' not in sym: continue
    if fut_used >= MAX_FUTURES_USD: break
    ch=tk.get('percentage') or 0;vol=tk.get('quoteVolume') or 0;base=sym.split('/')[0]
    if ch<=-8 and vol>3000000 and f"LIQ:{base}" not in bot.pos:
     try: ex_f.set_leverage(10,None,{'mgnMode':'isolated'});ex_f.create_market_buy_order(sym,COST_PER_LIQ/tk['last'],{'tdMode':'isolated','posSide':'long'});bot.pos[f"LIQ:{base}"]=tk['last'];bot.hunts+=1;log(f"[LIQ BUY] {base} {ch:.1f}% ${COST_PER_LIQ} [{fut_used+0.5}/{MAX_FUTURES_USD}]")
     except Exception as e: log(f"[LIQ ERR] {e}")
   time.sleep(4)
  except Exception as e: log(f"[MNG ERR] {e}");time.sleep(5)
threading.Thread(target=manager,daemon=True).start()
@app.route('/')
def idx():
 rows=CACHE["rows"]
 if not rows: rows="<tr><td colspan=3 style='text-align:center;color:#666'>يترصد الحيتان...</td></tr>"
 logs_html="".join([f"<div class='log'>{l}</div>" for l in LOGS[-150:][::-1]])
 liq_count = len([k for k in bot.pos if k.startswith("LIQ:")])
 return f"<html><head><meta http-equiv='refresh' content='5'><meta name='viewport' content='width=device-width, initial-scale=1'><style>body{{background:#0a0a0a;color:#eee;font-family:monospace;padding:10px;font-size:12px}}.top{{display:flex;gap:8px;margin-bottom:10px}}.box{{background:#111;border:1px solid #222;border-radius:8px;padding:10px;flex:1;text-align:center}}.box b{{display:block;font-size:18px;color:#0f0}}table{{width:100%;background:#111;border:1px solid #222;border-radius:8px;border-collapse:collapse;margin-bottom:10px}}th{{background:#1a1a1a;padding:8px;text-align:left;font-size:10px;color:#888}}td{{padding:8px;border-top:1px solid #222;font-size:11px}}.logs{{background:#111;border:1px solid #222;border-radius:8px;padding:6px;height:400px;overflow:auto}}.log{{padding:3px 0;border-bottom:1px solid #1a1a1a;font-size:10px}}.ok{{color:#0f0}}</style></head><body><div style='text-align:center;padding:5px' class='ok'>● LIVE V20001 FAST - cron OK - FU MAX ${MAX_FUTURES_USD} | LIQ {liq_count*0.5:.1f}/${MAX_FUTURES_USD}</div><div class='top'><div class='box'><small>HUNTS</small><b>{bot.hunts}</b></div><div class='box'><small>KILLS</small><b>{bot.kills}</b></div><div class='box'><small>BAL</small><b>${CACHE['bal']:.2f}</b></div><div class='box'><small>POS</small><b>{len(bot.pos)}</b></div></div><table><tr><th>نوع</th><th>عملة</th><th>ربح%</th></tr>{rows}</table><div style='background:#111;border:1px solid #222;border-radius:8px;padding:8px;font-size:10px;margin-bottom:10px;color:#aaa'>{CACHE['old']}</div><div class='logs'>{logs_html}</div></body></html>"
@app.route('/ping')
def ping(): return "ok",200
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))
