import os, time, json, logging, threading
from datetime import datetime, timezone, date
import ccxt, pandas as pd
from flask import Flask, jsonify
import numpy as np

CONFIG = {
    "RISK_PER_TRADE": 0.01,
    "MAX_POSITIONS": 2,
    "LEVERAGE": 3,
    "TIMEFRAME": "15m",
    "TIMEFRAME_HTF": "1h",
    "CANDLE_LIMIT": 300,
    "SCAN_INTERVAL": 25,
    "STOP_LOSS": 0.011,
    "MAX_CONSECUTIVE_LOSSES": 2,
    "DAILY_LOSS_LIMIT": 2.5,
    "BTC_VOLATILITY_LIMIT": 0.04,
    "STATE_FILE": "bot_state.json",
    "TRADES_FILE": "trades_log.json",
    "TRAILING_ENABLED": True,
}

API_KEY=os.getenv("OKX_API_KEY","").strip()
API_SECRET=os.getenv("OKX_API_SECRET","").strip() or os.getenv("OKX_SECRET","").strip()
API_PASSWORD=os.getenv("OKX_API_PASSWORD","").strip() or os.getenv("OKX_PASSPHRASE","").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log=logging.getLogger("FINAL")
app=Flask(__name__)
exchange=ccxt.okx({"apiKey":API_KEY,"secret":API_SECRET,"password":API_PASSWORD,"enableRateLimit":True,"options":{"defaultType":"swap"}})

def load_state():
    try:
        with open(CONFIG["STATE_FILE"],"r") as f: return json.load(f)
    except: return {}
saved=load_state()
state={
    "running":True,"started":datetime.now(timezone.utc).isoformat(),"last_scan":None,"scanned":0,"signals":[],"errors":[],"loop":0,
    "btc_trend":"unknown","btc_vol":0.0,
    "daily_pnl": saved.get("daily_pnl",0.0) if saved.get("daily_date")==str(date.today()) else 0.0,
    "daily_date": str(date.today()),
    "consecutive_losses": saved.get("consecutive_losses",0),
    "stopped_by_loss": False,"open_trades": saved.get("open_trades",{}),
}

def save_state():
    try:
        with open(CONFIG["STATE_FILE"],"w") as f:
            json.dump({"daily_pnl":state["daily_pnl"],"daily_date":state["daily_date"],"consecutive_losses":state["consecutive_losses"],"open_trades":state["open_trades"]}, f)
    except: pass
def load_trades():
    try:
        with open(CONFIG["TRADES_FILE"],"r") as f: return json.load(f)
    except: return []
def save_trade_log(entry):
    try:
        trades=load_trades(); trades.append(entry)
        with open(CONFIG["TRADES_FILE"],"w") as f: json.dump(trades[-500:], f, indent=2)
    except: pass
def get_free_usdt():
    try: bal=exchange.fetch_balance(); return float(bal.get("USDT",{}).get("free",0) or 0)
    except: return 0
def get_all_equity_breakdown():
    try:
        bal=exchange.fetch_balance()
        futures_free = float(bal.get("USDT",{}).get("free",0) or 0)
        total_spot=0.0
        for coin, total_amt in bal.get("total",{}).items():
            if coin=="USDT": continue
            try:
                amt=float(total_amt or 0)
                if amt<=0: continue
                symbol=f"{coin}/USDT"
                ticker=exchange.fetch_ticker(symbol)
                price=float(ticker["last"])
                value=amt*price
                if value>=0.3: total_spot+=value
            except: continue
        return {"futures_free":futures_free,"spot_all":total_spot,"total":futures_free+total_spot}
    except: 
        free=get_free_usdt()
        return {"futures_free":free,"spot_all":0,"total":free}
def get_auto_config():
    eq=get_all_equity_breakdown()
    total=eq["total"]
    if total < 50: return {"RISK":0.01, "LEV":3, "TP":0.025, "MAX":2, "MODE":"🛡️ حماية", "TOTAL":total, "EQ":eq}
    elif total < 100: return {"RISK":0.015, "LEV":4, "TP":0.03, "MAX":2, "MODE":"🚀 نمو", "TOTAL":total, "EQ":eq}
    else: return {"RISK":0.02, "LEV":5, "TP":0.035, "MAX":3, "MODE":"🔥 تعويض", "TOTAL":total, "EQ":eq}
def calc_margin(price):
    try:
        cfg=get_auto_config()
        bal=get_free_usdt()
        if bal<2: bal=9.0
        risk_usd=bal*cfg["RISK"]
        margin_needed=risk_usd/CONFIG["STOP_LOSS"]
        margin=margin_needed/cfg["LEV"]
        return round(max(2.0,min(margin,6.0)),2)
    except: return 2.5
def get_targets(entry,direction):
    cfg=get_auto_config()
    tp_pct=cfg["TP"]
    if direction=="long": return {"tp":entry*(1+tp_pct),"sl":entry*(1-CONFIG["STOP_LOSS"])}
    else: return {"tp":entry*(1-tp_pct),"sl":entry*(1+CONFIG["STOP_LOSS"])}
def calc_true_atr(df, period=14):
    hl=df["high"]-df["low"]; hc=(df["high"]-df["close"].shift()).abs(); lc=(df["low"]-df["close"].shift()).abs()
    tr=pd.concat([hl,hc,lc],axis=1).max(axis=1); atr=tr.rolling(period).mean(); return atr
def get_positions():
    try:
        positions=exchange.fetch_positions()
        total=0; count=0; symbols=[]; pos_list=[]
        for p in positions:
            if float(p.get("contracts") or 0)>0:
                margin=float(p.get("initialMargin") or p.get("collateral") or 0)
                if margin==0:
                    notional=float(p.get("notional") or 0); leverage=float(p.get("leverage") or get_auto_config()["LEV"])
                    if notional>0: margin=notional/leverage
                total+=margin; count+=1; symbols.append(p["symbol"]); pos_list.append(p)
        return total, count, pos_list, symbols
    except: return 0,0,[],[]
def fetch_df(symbol, tf):
    try:
        candles=exchange.fetch_ohlcv(symbol,timeframe=tf,limit=CONFIG["CANDLE_LIMIT"])
        df=pd.DataFrame(candles,columns=["time","open","high","low","close","volume"])
        if len(df)<200: return None
        df=df.iloc[:-1].copy()
        if df["close"].iloc[-1] < 0.005: return None
        df["ema9"]=df["close"].ewm(span=9).mean(); df["ema21"]=df["close"].ewm(span=21).mean(); df["ema50"]=df["close"].ewm(span=50).mean(); df["ema200"]=df["close"].ewm(span=200).mean()
        delta=df["close"].diff(); gain=delta.clip(lower=0); loss=-delta.clip(upper=0)
        avg_gain=gain.ewm(alpha=1/14,adjust=False).mean(); avg_loss=loss.ewm(alpha=1/14,adjust=False).mean()
        rs=avg_gain/avg_loss.replace(0,1e-8); df["rsi"]=100-(100/(1+rs))
        df["vol_avg"]=df["volume"].rolling(20).mean(); df["atr"]=calc_true_atr(df,14)
        return df.dropna()
    except: return None
def get_btc_status():
    try:
        df=fetch_df("BTC/USDT", CONFIG["TIMEFRAME"])
        if df is None: return "neutral",0
        curr=df.iloc[-1]
        atr_pct=curr["atr"]/curr["close"]
        if curr["close"]>curr["ema200"] and curr["ema9"]>curr["ema21"]: trend="bull"
        elif curr["close"]<curr["ema200"] and curr["ema9"]<curr["ema21"]: trend="bear"
        else: trend="neutral"
        return trend, atr_pct
    except: return "neutral",0
def analyze(symbol, btc_trend):
    try:
        df=fetch_df(symbol, CONFIG["TIMEFRAME"])
        df_h=fetch_df(symbol, CONFIG["TIMEFRAME_HTF"])
        if df is None or df_h is None: return None
        curr=df.iloc[-1]; curr_h=df_h.iloc[-1]; prev=df.iloc[-2]
        if curr["volume"] < curr["vol_avg"]*1.2: return None
        atr_pct=curr["atr"]/curr["close"]
        if atr_pct > 0.05 or atr_pct < 0.0008: return None
        score=0; direction=None
        if curr["ema9"]>curr["ema21"]>curr["ema50"] and curr["close"]>curr["ema200"]:
            if 48 < curr["rsi"] < 70:
                if curr_h["close"] < curr_h["ema200"] and btc_trend=="bear": return None
                score+=6
                if prev["ema9"]<=prev["ema21"] and curr["ema9"]>curr["ema21"]: score+=3
                if btc_trend=="bull": score+=1
                direction="long"
        if curr["ema9"]<curr["ema21"]<curr["ema50"] and curr["close"]<curr["ema200"]:
            if 28 < curr["rsi"] < 50:
                if curr_h["close"] > curr_h["ema200"] and btc_trend=="bull": return None
                s_score=6
                if prev["ema9"]>=prev["ema21"] and curr["ema9"]<curr["ema21"]: s_score+=3
                if btc_trend=="bear": s_score+=1
                if s_score>score:
                    score=s_score; direction="short"
        if direction and score>=7:
            return {"symbol":symbol,"direction":direction,"score":score,"price":float(curr["close"]),"rsi":round(float(curr["rsi"]),1),"atr_pct":round(atr_pct*100,3)}
    except: return None
def get_amount(symbol,margin,price):
    try:
        market=exchange.market(symbol); contract_size=float(market.get("contractSize") or 1)
        notional=margin*get_auto_config()["LEV"]; raw=notional/(price*contract_size)
        return float(exchange.amount_to_precision(symbol,raw))
    except: return 0
def verify_sl(swap):
    try:
        positions=exchange.fetch_positions([swap])
        for p in positions:
            if float(p.get("contracts") or 0)>0:
                if p.get("stopLossPrice") or float(p.get("info",{}).get("stopLossPrice") or 0)>0: return True
        return False
    except: return False

def local_protection_loop():
    while state["running"]:
        try:
            _, _, pos_list, _ = get_positions()
            for p in pos_list:
                symbol=p["symbol"]
                trade=state["open_trades"].get(symbol)
                if not trade: continue
                entry=trade["entry"]
                direction=trade["direction"]
                amount=float(p.get("contracts") or trade.get("amount") or 0)
                if amount==0: continue
                mark=float(p.get("markPrice") or entry)
                lev=get_auto_config()["LEV"]
                pnl_pct = (entry - mark)/entry*100*lev if direction=="short" else (mark-entry)/entry*100*lev
                if pnl_pct >= 0.8 and trade.get("sl_moved",0) < 1:
                    new_sl = entry * 1.0005 if direction=="short" else entry * 0.9995
                    try:
                        exchange.create_order(symbol,"market","buy" if direction=="short" else "sell",amount,None,{"tdMode":"isolated","posSide":direction,"stopLoss":{"triggerPrice":new_sl,"orderPrice":"-1"}})
                        trade["sl_moved"]=1; save_state()
                        log.info(f"BE SECURED {symbol} {pnl_pct:.2f}%")
                    except: pass
                elif pnl_pct >= 1.5 and trade.get("sl_moved",0) < 2:
                    new_sl = entry * (1 - 0.007) if direction=="short" else entry * (1 + 0.007)
                    try:
                        exchange.create_order(symbol,"market","buy" if direction=="short" else "sell",amount,None,{"tdMode":"isolated","posSide":direction,"stopLoss":{"triggerPrice":new_sl,"orderPrice":"-1"}})
                        trade["sl_moved"]=2; save_state()
                        log.info(f"LOCK 0.7% {symbol}")
                    except: pass
                elif pnl_pct >= 2.5 and trade.get("sl_moved",0) < 3:
                    new_sl = entry * (1 - 0.015) if direction=="short" else entry * (1 + 0.015)
                    try:
                        exchange.create_order(symbol,"market","buy" if direction=="short" else "sell",amount,None,{"tdMode":"isolated","posSide":direction,"stopLoss":{"triggerPrice":new_sl,"orderPrice":"-1"}})
                        trade["sl_moved"]=3; save_state()
                        log.info(f"LOCK 1.5% {symbol}")
                    except: pass
            time.sleep(8)
        except: time.sleep(10)

def place_trade(signal):
    total, cnt, _, open_syms = get_positions()
    cfg=get_auto_config()
    if cnt >= cfg["MAX"]: return
    if state["stopped_by_loss"]: return
    base=signal["symbol"].split("/")[0]; swap=base+"/USDT:USDT"
    if any(base in s for s in open_syms): return
    try:
        margin=calc_margin(signal["price"])
        amount=get_amount(swap,margin,signal["price"])
        if amount==0: return
        try: exchange.set_leverage(cfg["LEV"],swap,{"mgnMode":"isolated"})
        except: pass
        side="buy" if signal["direction"]=="long" else "sell"; posSide="long" if signal["direction"]=="long" else "short"
        order=exchange.create_order(swap,"market",side,amount,None,{"tdMode":"isolated","posSide":posSide,"lever":str(cfg["LEV"])})
        avg=float(order.get("average") or signal["price"]); filled=float(order.get("filled") or amount)
        t=get_targets(avg, signal["direction"])
        for _ in range(3):
            try:
                exchange.create_order(swap, "market", "sell" if signal["direction"]=="long" else "buy", filled, None, {"tdMode":"isolated","posSide":posSide,"stopLoss":{"triggerPrice":t["sl"],"orderPrice":"-1"}})
                time.sleep(1)
                if verify_sl(swap): break
            except: time.sleep(1)
        state["open_trades"][swap]={"entry":avg,"direction":signal["direction"],"margin":margin,"amount":filled,"sl_moved":0}
        save_state()
        save_trade_log({"time":datetime.now(timezone.utc).isoformat(),"type":"ENTRY","symbol":swap,"direction":signal["direction"],"entry":avg})
    except Exception as e: state["errors"].append(str(e)[-150:])

def check_closed_and_update_pnl():
    try:
        today=str(date.today())
        if state["daily_date"]!=today:
            state["daily_pnl"]=0.0; state["consecutive_losses"]=0; state["daily_date"]=today; state["stopped_by_loss"]=False; save_state()
        _, _, _, current_syms = get_positions()
        closed_syms = [s for s in list(state["open_trades"].keys()) if s not in current_syms]
        for sym in closed_syms:
            try:
                trades=exchange.fetch_my_trades(sym, limit=20); pnl=0.0
                for t in reversed(trades[-10:]):
                    info=t.get("info",{})
                    if info.get("realizedPnl") or info.get("pnl"):
                        pnl=float(info.get("realizedPnl") or info.get("pnl") or 0)
                        if pnl!=0: break
                if pnl!=0:
                    state["daily_pnl"]=round(state["daily_pnl"]+pnl,4)
                    if pnl<0: state["consecutive_losses"]+=1
                    else: state["consecutive_losses"]=0
                    save_trade_log({"time":datetime.now(timezone.utc).isoformat(),"type":"EXIT","symbol":sym,"pnl":pnl})
                del state["open_trades"][sym]; save_state()
            except: 
                try: del state["open_trades"][sym]
                except: pass
        if state["daily_pnl"] <= -CONFIG["DAILY_LOSS_LIMIT"]:
            state["stopped_by_loss"]=True
        if state["consecutive_losses"] >= CONFIG["MAX_CONSECUTIVE_LOSSES"]:
            state["stopped_by_loss"]=True
    except: pass

def scan_and_trade():
    try: exchange.load_markets()
    except: pass
    check_closed_and_update_pnl()
    if state["stopped_by_loss"]: return
    btc_trend, btc_vol = get_btc_status()
    state["btc_trend"]=btc_trend; state["btc_vol"]=round(btc_vol*100,2)
    if btc_vol > CONFIG["BTC_VOLATILITY_LIMIT"]: return
    cfg=get_auto_config()
    _, cnt, _, open_syms = get_positions()
    if cnt>=cfg["MAX"]: return
    signals=[]; scanned=0
    TOP_COINS = ["BTC/USDT","ETH/USDT","SOL/USDT","AVAX/USDT","LINK/USDT","ADA/USDT","LTC/USDT","DOT/USDT","ARB/USDT","ENA/USDT","FET/USDT","TAO/USDT","RENDER/USDT","SUI/USDT","SEI/USDT","APT/USDT","NEAR/USDT","OP/USDT"]
    for s in TOP_COINS:
        base=s.split("/")[0]
        if any(base in sym for sym in open_syms): continue
        sig=analyze(s, btc_trend); scanned+=1
        if sig: signals.append(sig)
        time.sleep(0.15)
    signals.sort(key=lambda x:x["score"],reverse=True)
    state["scanned"]=scanned; state["signals"]=signals[:5]; state["last_scan"]=datetime.now(timezone.utc).isoformat(); state["loop"]+=1
    if signals: place_trade(signals[0])

def run_bot():
    while state["running"]:
        try: scan_and_trade()
        except Exception as e: state["errors"].append(str(e)[-100:]); state["errors"]=state["errors"][-5:]
        time.sleep(CONFIG["SCAN_INTERVAL"])

DASHBOARD_HTML = """
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FINAL TRAILING</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{background:#0a0e14;color:#e5e7eb}.card{background:#111827;border:1px solid #1f2937}</style>
</head><body class="p-3"><div class="max-w-7xl mx-auto">
<div class="flex justify-between mb-4"><h1 class="text-xl font-bold">FINAL <span class="text-green-400">TRAILING 🔒</span></h1><span class="w-3 h-3 bg-green-500 rounded-full animate-pulse mt-2"></span></div>
<div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">فيوتشر</p><p id="balance" class="text-lg font-bold">--</p></div>
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">ربح اليوم</p><p id="daily" class="text-lg font-bold">--</p></div>
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">صفقات</p><p id="open" class="text-lg font-bold">--</p></div>
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">BTC</p><p id="btc" class="text-xs font-bold">--</p></div>
</div>
<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
<div class="card rounded-xl p-4"><h3 class="font-bold text-sm mb-2">صفقات</h3><div id="positions" class="space-y-2 text-xs"></div></div>
<div class="card rounded-xl p-4"><h3 class="font-bold text-sm mb-2">إشارات</h3><div id="signals" class="space-y-2 text-xs"></div></div>
</div>
</div>
<script>
async function load(){
 try{
  const res = await fetch('/api/status'); const d = await res.json();
  document.getElementById('balance').textContent = d.futures_free.toFixed(2) + ' USDT';
  document.getElementById('daily').textContent = d.daily_pnl + ' $';
  document.getElementById('open').textContent = d.open_count + ' / ' + d.max_positions;
  document.getElementById('btc').textContent = d.btc_trend;
  const posDiv = document.getElementById('positions');
  if(d.positions && d.positions.length>0){ posDiv.innerHTML = d.positions.map(p=>`<div class="bg-[#0a0e14] border border-gray-800 rounded p-2 flex justify-between"><div><p class="font-bold">${p.symbol}</p></div><div class="text-left"><p class="font-bold ${p.pnl>=0?'text-green-400':'text-red-400'}">${p.pnl} $ (${p.pnl_pct}%)</p></div></div>`).join(''); } else { posDiv.innerHTML = '<p class="text-gray-500">ينتظر إشارة قوية</p>'; }
  const sigDiv = document.getElementById('signals');
  if(d.signals && d.signals.length>0){ sigDiv.innerHTML = d.signals.map(s=>`<div class="flex justify-between bg-[#0a0e14] rounded p-2"><span>${s.symbol} ${s.direction}</span><span class="bg-blue-900 px-2 rounded">${s.score}/10</span></div>`).join(''); } else { sigDiv.innerHTML = '<p class="text-gray-500">لا إشارات</p>'; }
 }catch(e){}
}
load(); setInterval(load, 8000);
</script></body></html>
"""

@app.route("/")
def dashboard(): return DASHBOARD_HTML, 200, {'Content-Type':'text/html; charset=utf-8'}
@app.route("/api/status")
def api_status():
    total,cnt,pos,syms=get_positions()
    cfg=get_auto_config()
    eq=cfg["EQ"]
    btc_trend, btc_vol = get_btc_status()
    return jsonify({
        "futures_free":round(eq["futures_free"],4),
        "btc_trend":btc_trend,
        "btc_vol":round(btc_vol*100,3),
        "open_count":cnt,
        "max_positions":cfg["MAX"],
        "daily_pnl":state["daily_pnl"],
        "signals":state["signals"],
        "positions":[{"symbol":p["symbol"],"pnl":round(float(p.get("unrealizedPnl") or 0),4),"pnl_pct":round(float(p.get("percentage") or 0),2)} for p in pos if float(p.get("contracts") or 0)>0],
    })
@app.route("/trades")
def trades(): return jsonify(load_trades()[-100:])
@app.route("/ping")
def ping(): return jsonify({"pong":True})

if __name__=="__main__":
    threading.Thread(target=run_bot,daemon=True).start()
    threading.Thread(target=local_protection_loop,daemon=True).start()
    log.info("FINAL TRAILING started")
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")),debug=False,use_reloader=False)
