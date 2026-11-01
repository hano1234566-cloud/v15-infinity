import os, time, json, logging
from datetime import datetime, timezone
import ccxt, pandas as pd
from flask import Flask, jsonify

def get_env(*names):
    for n in names:
        v=os.getenv(n,"").strip()
        if v: return v
    return ""

CONFIG = {
    "FUTURES_MARGIN": 5.0,
    "MAX_TOTAL_FUTURES": 10.0,
    "LEVERAGE": 3,
    "MAX_COINS": 40,
    "TIMEFRAME": "15m", # غيرتها من 5m لـ 15m عشان أدق
    "CANDLE_LIMIT": 100,
    "SCAN_INTERVAL": 30,
    "TAKE_PROFIT": 0.018,
    "STOP_LOSS": 0.012,
    "LIVE_TRADING": True,
    "ALLOW_FUTURES": True,
    "STATE_FILE": "bot_state.json",
}

API_KEY=get_env("OKX_API_KEY","OKX_KEY")
API_SECRET=get_env("OKX_API_SECRET","OKX_SECRET_KEY","OKX_SECRET","SECRET")
API_PASSWORD=get_env("OKX_API_PASSWORD","OKX_PASSPHRASE","PASSPHRASE","OKX_PASS")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log=logging.getLogger("V3005")
app=Flask(__name__)
exchange=ccxt.okx({"apiKey":API_KEY,"secret":API_SECRET,"password":API_PASSWORD,"enableRateLimit":True,"options":{"defaultType":"swap"}})
state={"running":True,"started":datetime.now(timezone.utc).isoformat(),"last_scan":None,"scanned":0,"signals":[],"errors":[],"wins":0,"losses":0}

def save_state():
    try:
        with open(CONFIG["STATE_FILE"],"w") as f: json.dump(state,f,indent=2)
    except: pass
def record_error(msg):
    log.error(msg); state["errors"].append({"time":datetime.now(timezone.utc).isoformat(),"message":str(msg)}); state["errors"]=state["errors"][-10:]

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
    except: return 0,0,[]

def get_swap_symbol(s): 
    base=s.split("/")[0]; sym=base+"/USDT:USDT"
    return sym if sym in exchange.markets else None

def fetch_candles(symbol):
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

def analyze_market_pro(symbol):
    try:
        df=fetch_candles(symbol)
        if df is None: return None
        curr=df.iloc[-1]; prev=df.iloc[-2]
        
        score_long=0; score_short=0
        reasons=[]

        # شرط 1: ترند قوي EMA9>EMA21>EMA50
        if curr["ema9"]>curr["ema21"]>curr["ema50"]:
            score_long+=2; reasons.append("ترند صاعد قوي")
        elif curr["ema9"]<curr["ema21"]<curr["ema50"]:
            score_short+=2; reasons.append("ترند هابط قوي")
        else:
            return None # ما في ترند واضح - لا تفتح

        # شرط 2: RSI في منطقة آمنة
        if 50 < curr["rsi"] < 68:
            score_long+=2; reasons.append(f"RSI {curr['rsi']:.0f} ممتاز")
        elif 32 < curr["rsi"] < 50:
            score_short+=2; reasons.append(f"RSI {curr['rsi']:.0f} ممتاز")
        else:
            return None # RSI متضخم

        # شرط 3: حجم تداول أعلى من المتوسط
        if curr["volume"] > curr["volume_avg"]*1.3:
            score_long+=1; score_short+=1; reasons.append("سيولة عالية")
        else:
            return None # بدون سيولة لا تفتح

        # شرط 4: تقاطع جديد
        if prev["ema9"]<=prev["ema21"] and curr["ema9"]>curr["ema21"]:
            score_long+=2; reasons.append("تقاطع ذهبي جديد")
        if prev["ema9"]>=prev["ema21"] and curr["ema9"]<curr["ema21"]:
            score_short+=2; reasons.append("تقاطع موت جديد")

        # شرط 5: ATR مو عالي (تجنب التقلب المجنون)
        atr_pct = curr["atr"]/curr["close"]
        if atr_pct > 0.04: return None

        price=float(curr["close"])
        if score_long>=5: return {"symbol":symbol,"direction":"long","score":score_long,"price":price,"reasons":reasons,"rsi":curr["rsi"]}
        if score_short>=5: return {"symbol":symbol,"direction":"short","score":score_short,"price":price,"reasons":reasons,"rsi":curr["rsi"]}
    except: return None

def get_free_usdt():
    try: bal=exchange.fetch_balance(); return float(bal.get("USDT",{}).get("free",0) or 0)
    except: return 0

def get_contract_amount(symbol,margin,price):
    market=exchange.market(symbol); contract_size=float(market.get("contractSize") or 1); notional=margin*CONFIG["LEVERAGE"]
    raw=notional/(price*contract_size); return float(exchange.amount_to_precision(symbol,raw))

def get_targets(entry,direction):
    if direction=="long": return {"tp1":entry*(1+CONFIG["TAKE_PROFIT"]),"sl":entry*(1-CONFIG["STOP_LOSS"])}
    else: return {"tp1":entry*(1-CONFIG["TAKE_PROFIT"]),"sl":entry*(1+CONFIG["STOP_LOSS"])}

def place_sl_tp_orders(swap, direction, amount, entry):
    try:
        t=get_targets(entry,direction)
        posSide="long" if direction=="long" else "short"
        side_close="sell" if direction=="long" else "buy"
        exchange.create_order(swap, "market", side_close, amount, None, {
            "tdMode":"isolated","posSide":posSide,
            "stopLoss":{"triggerPrice":t["sl"],"orderPrice":"-1"},
        })
        log.info(f"✅ SL {swap} @{t['sl']:.4f}")
        try:
            exchange.create_order(swap, "market", side_close, amount, None, {
                "tdMode":"isolated","posSide":posSide,
                "takeProfit":{"triggerPrice":t["tp1"],"orderPrice":"-1"}
            })
        except: pass
        return True
    except Exception as e:
        record_error(f"SL {e}"); return False

def place_future_trade(signal):
    total_margin, open_count, _ = get_total_futures_margin()
    if total_margin >= CONFIG["MAX_TOTAL_FUTURES"] or open_count >=2: return
    swap=get_swap_symbol(signal["symbol"])
    if not swap: return
    price=signal["price"]; amount=get_contract_amount(swap,CONFIG["FUTURES_MARGIN"],price)
    side="buy" if signal["direction"]=="long" else "sell"
    posSide="long" if signal["direction"]=="long" else "short"
    try: exchange.set_leverage(CONFIG["LEVERAGE"],swap,{"mgnMode":"isolated"})
    except: pass
    try:
        order=exchange.create_order(swap,"market",side,amount,None,{"tdMode":"isolated","posSide":posSide,"lever":str(CONFIG["LEVERAGE"])})
        avg=float(order.get("average") or price); filled=float(order.get("filled") or amount)
        log.info(f"OPEN {swap} {signal['direction']} score:{signal['score']} {signal['reasons']}")
        time.sleep(1); place_sl_tp_orders(swap, signal["direction"], filled, avg)
    except Exception as e: record_error(f"Future {e}")

def scan_and_trade():
    symbols=exchange.load_markets(); candidates=[]
    tickers=exchange.fetch_tickers()
    for sym,market in exchange.markets.items():
        try:
            if not market.get("active") or not market.get("spot") or market.get("quote")!="USDT": continue
            vol=float(tickers.get(sym,{}).get("quoteVolume") or 0)
            if vol<5000000: continue # رفعنا من 2M لـ 5M - بس العملات القوية
            candidates.append((sym,vol))
        except: continue
    candidates.sort(key=lambda x:x[1],reverse=True); top=[x[0] for x in candidates[:CONFIG["MAX_COINS"]]]
    signals=[]
    for s in top:
        sig=analyze_market_pro(s)
        if sig: signals.append(sig)
        time.sleep(0.15)
    signals.sort(key=lambda x:x["score"],reverse=True)
    state["scanned"]=len(top); state["signals"]=signals[:5]; state["last_scan"]=datetime.now(timezone.utc).isoformat()
    if signals: place_future_trade(signals[0])
    save_state()

def run_bot():
    log.info(f"V3005 PRO - 5 شروط + 15m")
    while state["running"]:
        try: scan_and_trade()
        except Exception as e: record_error(str(e))
        time.sleep(CONFIG["SCAN_INTERVAL"])

@app.route("/")
def home():
    total,cnt,pos=get_total_futures_margin()
    return jsonify({
        "bot":"V3005 PRO - دقيق 5 شروط",
        "balance": get_free_usdt(),
        "total_margin": round(total,2),
        "open_count": cnt,
        "timeframe": CONFIG["TIMEFRAME"],
        "scanned": state["scanned"],
        "signals": state["signals"],
        "positions": [{"symbol":p["symbol"],"side":p.get("side"),"entry":p.get("entryPrice"),"pnl":p.get("unrealizedPnl")} for p in pos if float(p.get("contracts") or 0)>0],
        "errors": state["errors"][-3:]
    })

@app.route("/health")
def health(): return jsonify({"status":"online"})

@app.route("/add_sl")
def add_sl():
    try:
        positions=exchange.fetch_positions(); added=[]
        for p in positions:
            if float(p.get("contracts") or 0)>0:
                sym=p["symbol"]; side=p.get("side"); entry=float(p.get("entryPrice") or 0); contracts=float(p.get("contracts")); direction="long" if side=="long" else "short"
                t=get_targets(entry,direction); posSide="long" if direction=="long" else "short"; side_close="sell" if direction=="long" else "buy"
                try:
                    exchange.create_order(sym,"market",side_close,contracts,None,{"tdMode":"isolated","posSide":posSide,"stopLoss":{"triggerPrice":t["sl"],"orderPrice":"-1"}})
                    added.append(f"{sym} SL@{t['sl']:.4f}")
                except Exception as e: added.append(f"{sym} fail {e}")
        return jsonify({"added":added})
    except Exception as e: return jsonify({"error":str(e)})

if __name__=="__main__":
    import threading; threading.Thread(target=run_bot,daemon=True).start()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","5000")),debug=False,use_reloader=False)
