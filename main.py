import os, time, json, logging
from datetime import datetime, timezone
import ccxt, pandas as pd
from flask import Flask, jsonify

CONFIG = {
    "FUTURES_MARGIN": 5.0,
    "MAX_TOTAL_FUTURES": 10.0,
    "LEVERAGE": 3,
    "MAX_COINS": 25,  # قللت لـ 25 عشان أسرع
    "TIMEFRAME": "15m",
    "CANDLE_LIMIT": 100,
    "SCAN_INTERVAL": 25,
    "TAKE_PROFIT": 0.018,
    "STOP_LOSS": 0.012,
    "STATE_FILE": "bot_state.json",
}

API_KEY=os.getenv("OKX_API_KEY","").strip() or os.getenv("OKX_KEY","").strip()
API_SECRET=os.getenv("OKX_API_SECRET","").strip() or os.getenv("OKX_SECRET_KEY","").strip() or os.getenv("OKX_SECRET","").strip()
API_PASSWORD=os.getenv("OKX_API_PASSWORD","").strip() or os.getenv("OKX_PASSPHRASE","").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log=logging.getLogger("V3006")
app=Flask(__name__)
exchange=ccxt.okx({"apiKey":API_KEY,"secret":API_SECRET,"password":API_PASSWORD,"enableRateLimit":True,"options":{"defaultType":"swap"}})
state={"running":True,"started":datetime.now(timezone.utc).isoformat(),"last_scan":None,"scanned":0,"signals":[],"errors":[],"loop":0}

def save_state():
    try:
        with open(CONFIG["STATE_FILE"],"w") as f: json.dump(state,f,indent=2)
    except: pass

def get_total_futures_margin():
    try:
        positions=exchange.fetch_positions()
        total=0; count=0
        for p in positions:
            if float(p.get("contracts") or 0)>0:
                margin=float(p.get("initialMargin") or p.get("collateral") or 0)
                if margin==0:
                    notional=float(p.get("notional") or 0)
                    leverage=float(p.get("leverage") or CONFIG["LEVERAGE"])
                    if notional>0: margin=notional/leverage
                total+=margin; count+=1
        return total, count, positions
    except Exception as e: return 0,0,[]

# قائمة ثابتة قوية - ما نحتاج tickers
TOP_COINS = ["BTC/USDT","ETH/USDT","SOL/USDT","AVAX/USDT","XRP/USDT","DOGE/USDT","LINK/USDT","ADA/USDT","TRX/USDT","LTC/USDT","DOT/USDT","MATIC/USDT","SHIB/USDT","AVAX/USDT","WIF/USDT","ARB/USDT","PEPE/USDT","BONK/USDT","TRUMP/USDT","ENA/USDT","FET/USDT","TAO/USDT","RENDER/USDT","SUI/USDT","SEI/USDT"]

def fetch_candles(symbol):
    try:
        candles=exchange.fetch_ohlcv(symbol,timeframe=CONFIG["TIMEFRAME"],limit=CONFIG["CANDLE_LIMIT"])
        df=pd.DataFrame(candles,columns=["time","open","high","low","close","volume"])
        if len(df)<50: return None
        df=df.iloc[:-1].copy()
        df["ema9"]=df["close"].ewm(span=9).mean()
        df["ema21"]=df["close"].ewm(span=21).mean()
        df["ema50"]=df["close"].ewm(span=50).mean()
        delta=df["close"].diff(); gain=delta.clip(lower=0); loss=-delta.clip(upper=0)
        avg_gain=gain.ewm(alpha=1/14,adjust=False).mean(); avg_loss=loss.ewm(alpha=1/14,adjust=False).mean()
        rs=avg_gain/avg_loss.replace(0,1e-8); df["rsi"]=100-(100/(1+rs))
        df["volume_avg"]=df["volume"].rolling(20).mean()
        df["atr"]= (df["high"]-df["low"]).rolling(14).mean()
        return df.dropna()
    except: return None

def analyze_market_pro(symbol):
    try:
        df=fetch_candles(symbol)
        if df is None: return None
        curr=df.iloc[-1]; prev=df.iloc[-2]
        if curr["volume"] < curr["volume_avg"]*1.2: return None
        if curr["ema9"]<=curr["ema21"] or curr["ema21"]<=curr["ema50"]: return None
        if not (50 < curr["rsi"] < 68): return None
        if prev["ema9"]<=prev["ema21"] and curr["ema9"]>curr["ema21"]:
            score=5
        elif curr["ema9"]>curr["ema21"]>curr["ema50"] and curr["close"]>curr["ema9"]:
            score=4
        else: return None
        atr_pct = curr["atr"]/curr["close"]
        if atr_pct > 0.04: return None
        return {"symbol":symbol,"direction":"long","score":score,"price":float(curr["close"]),"rsi":round(float(curr["rsi"]),1),"reasons":[f"ترند 3 EMA","RSI {curr['rsi']:.0f}","سيولة عالية"]}
    except: return None

def get_free_usdt():
    try: bal=exchange.fetch_balance(); return float(bal.get("USDT",{}).get("free",0) or 0)
    except: return 0

def get_contract_amount(symbol,margin,price):
    try:
        market=exchange.market(symbol); contract_size=float(market.get("contractSize") or 1); notional=margin*CONFIG["LEVERAGE"]
        raw=notional/(price*contract_size); return float(exchange.amount_to_precision(symbol,raw))
    except: return 0

def get_targets(entry,direction):
    return {"tp1":entry*(1+CONFIG["TAKE_PROFIT"]),"sl":entry*(1-CONFIG["STOP_LOSS"])}

def place_sl_tp_orders(swap, direction, amount, entry):
    try:
        t=get_targets(entry,direction); posSide="long"; side_close="sell"
        exchange.create_order(swap, "market", side_close, amount, None, {"tdMode":"isolated","posSide":posSide,"stopLoss":{"triggerPrice":t["sl"],"orderPrice":"-1"}})
        try: exchange.create_order(swap, "market", side_close, amount, None, {"tdMode":"isolated","posSide":posSide,"takeProfit":{"triggerPrice":t["tp1"],"orderPrice":"-1"}})
        except: pass
        return True
    except: return False

def place_future_trade(signal):
    total_margin, open_count, _ = get_total_futures_margin()
    if total_margin >= CONFIG["MAX_TOTAL_FUTURES"] or open_count >=2: return
    try:
        base=signal["symbol"].split("/")[0]; swap=base+"/USDT:USDT"
        price=signal["price"]; amount=get_contract_amount(swap,CONFIG["FUTURES_MARGIN"],price)
        if amount==0: return
        try: exchange.set_leverage(CONFIG["LEVERAGE"],swap,{"mgnMode":"isolated"})
        except: pass
        order=exchange.create_order(swap,"market","buy",amount,None,{"tdMode":"isolated","posSide":"long","lever":str(CONFIG["LEVERAGE"])})
        avg=float(order.get("average") or price); filled=float(order.get("filled") or amount)
        log.info(f"OPEN {swap} score:{signal['score']}")
        time.sleep(1); place_sl_tp_orders(swap, "long", filled, avg)
    except Exception as e: state["errors"].append(str(e)[-100:])

def scan_and_trade():
    try: exchange.load_markets()
    except: pass
    signals=[]; scanned=0
    for s in TOP_COINS[:CONFIG["MAX_COINS"]]:
        sig=analyze_market_pro(s)
        scanned+=1
        if sig: signals.append(sig)
        time.sleep(0.2)
    signals.sort(key=lambda x:x["score"],reverse=True)
    state["scanned"]=scanned; state["signals"]=signals[:5]; state["last_scan"]=datetime.now(timezone.utc).isoformat(); state["loop"]+=1
    if signals: place_future_trade(signals[0])
    save_state()

def run_bot():
    log.info("V3006 FIX STARTED")
    while state["running"]:
        try: scan_and_trade()
        except Exception as e: state["errors"].append(str(e)[-100:]); state["errors"]=state["errors"][-5:]
        time.sleep(CONFIG["SCAN_INTERVAL"])

@app.route("/")
def home():
    total,cnt,pos=get_total_futures_margin()
    return jsonify({"balance":round(get_free_usdt(),4),"bot":"V3006 PRO FIX - دقيق 5 شروط","open_count":cnt,"total_margin":round(total,2),"scanned":state["scanned"],"loop":state["loop"],"last_scan":state["last_scan"],"signals":state["signals"],"positions":[{"symbol":p["symbol"],"pnl":p.get("unrealizedPnl")} for p in pos if float(p.get("contracts") or 0)>0],"errors":state["errors"][-2:],"timeframe":CONFIG["TIMEFRAME"]})

@app.route("/health")
def health(): return jsonify({"status":"online","loop":state["loop"],"scanned":state["scanned"]})

if __name__=="__main__":
    import threading; threading.Thread(target=run_bot,daemon=True).start()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","5000")),debug=False,use_reloader=False)