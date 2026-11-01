import os, time, json, logging
from datetime import datetime, timezone
import ccxt, pandas as pd
from flask import Flask, jsonify

def get_env(*names):
    for n in names:
        v = os.getenv(n, "").strip()
        if v: return v
    return ""

CONFIG = {
    "SPOT_BUDGET": 15.0, "FUTURES_MARGIN": 5.0, "LEVERAGE": 3,
    "MAX_COINS": 30, "TIMEFRAME": "5m", "CANDLE_LIMIT": 100, "SCAN_INTERVAL": 30,
    "TAKE_PROFIT": 0.018, "TAKE_PROFIT_2": 0.035, "STOP_LOSS": 0.009,
    "TRAILING_TRIGGER": 0.008, "TRAILING_STEP": 0.004,
    "FEE_RATE": 0.0005, "MIN_NET": 0.008, "MIN_SIGNAL_SCORE": 3,
    "LIVE_TRADING": True,
    "ALLOW_SPOT": True, "ALLOW_FUTURES": True,
    "STATE_FILE": "bot_state.json", "MAX_SPOT_USD": 16.0, "MAX_FUTURES_USD": 6.0,
}

API_KEY = get_env("OKX_API_KEY","OKX_KEY")
API_SECRET = get_env("OKX_API_SECRET","OKX_SECRET_KEY","OKX_SECRET","SECRET")
API_PASSWORD = get_env("OKX_API_PASSWORD","OKX_PASSPHRASE","PASSPHRASE","OKX_PASS")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log=logging.getLogger("DEATH_HUNTER")
app=Flask(__name__)

exchange=ccxt.okx({"apiKey":API_KEY,"secret":API_SECRET,"password":API_PASSWORD,"enableRateLimit":True,"options":{"defaultType":"spot"}}) if API_SECRET else ccxt.okx({"enableRateLimit":True})

state={"running":True,"started":datetime.now(timezone.utc).isoformat(),"last_scan":None,"scanned":0,"signals":[],"trades":[],"errors":[],"spot_position":None,"future_position":None,"wins":0,"losses":0,"pnl":0.0,"pnl_net":0.0,"keys_found":{"api_key":bool(API_KEY),"secret":bool(API_SECRET),"password":bool(API_PASSWORD),"api_prefix":API_KEY[:8] if API_KEY else "none"}}

def save_state():
    try:
        with open(CONFIG["STATE_FILE"],"w") as f: json.dump(state,f,indent=2)
    except: pass
def load_state():
    try:
        with open(CONFIG["STATE_FILE"],"r") as f: state.update(json.load(f))
    except: pass
def record_error(msg):
    log.error(msg); state["errors"].append({"time":datetime.now(timezone.utc).isoformat(),"message":str(msg)}); state["errors"]=state["errors"][-20:]; save_state()

def get_market_symbols():
    markets=exchange.load_markets(); tickers=exchange.fetch_tickers(); candidates=[]
    for symbol,market in markets.items():
        try:
            if not market.get("active") or not market.get("spot") or market.get("quote")!="USDT": continue
            if market.get("base") in ("USDC","USDT","DAI"): continue
            vol=float(tickers.get(symbol,{}).get("quoteVolume") or 0)
            if vol<1000000: continue
            candidates.append((symbol,vol))
        except: continue
    candidates.sort(key=lambda x:x[1],reverse=True); return [x[0] for x in candidates[:CONFIG["MAX_COINS"]]]

def get_swap_symbol(spot_symbol):
    base=spot_symbol.split("/")[0]; symbol=base+"/USDT:USDT"
    if symbol not in exchange.markets: return None
    return symbol if exchange.markets[symbol].get("swap") else None

def fetch_candles(symbol):
    candles=exchange.fetch_ohlcv(symbol,timeframe=CONFIG["TIMEFRAME"],limit=CONFIG["CANDLE_LIMIT"])
    df=pd.DataFrame(candles,columns=["time","open","high","low","close","volume"])
    if len(df)<30: return None
    df=df.iloc[:-1].copy(); df["ema9"]=df["close"].ewm(span=9).mean(); df["ema21"]=df["close"].ewm(span=21).mean()
    delta=df["close"].diff(); gain=delta.clip(lower=0); loss=-delta.clip(upper=0)
    avg_gain=gain.ewm(alpha=1/14,adjust=False).mean(); avg_loss=loss.ewm(alpha=1/14,adjust=False).mean()
    rs=avg_gain/avg_loss.replace(0,0.00000001); df["rsi"]=100-(100/(1+rs)); df["volume_avg"]=df["volume"].rolling(20).mean()
    return df.dropna()

def analyze_market(symbol):
    try:
        df=fetch_candles(symbol)
        if df is None: return None
        prev,curr=df.iloc[-2],df.iloc[-1]; score_long=score_short=0
        if curr["ema9"]>curr["ema21"]: score_long+=1
        else: score_short+=1
        if 50<curr["rsi"]<68: score_long+=1
        elif 32<curr["rsi"]<50: score_short+=1
        if prev["ema9"]<=prev["ema21"] and curr["ema9"]>curr["ema21"]: score_long+=2
        if prev["ema9"]>=prev["ema21"] and curr["ema9"]<curr["ema21"]: score_short+=2
        if curr["volume"]>curr["volume_avg"]:
            if curr["close"]>curr["open"]: score_long+=1
            else: score_short+=1
        price=float(curr["close"])
        if score_long>=CONFIG["MIN_SIGNAL_SCORE"]: return {"symbol":symbol,"direction":"long","score":score_long,"price":price,"rsi":round(float(curr["rsi"]),2),"time":datetime.now(timezone.utc).isoformat()}
        if score_short>=CONFIG["MIN_SIGNAL_SCORE"]: return {"symbol":symbol,"direction":"short","score":score_short,"price":price,"rsi":round(float(curr["rsi"]),2),"time":datetime.now(timezone.utc).isoformat()}
    except: return None

def get_free_usdt():
    try: bal=exchange.fetch_balance(); return float(bal.get("USDT",{}).get("free",0) or 0)
    except Exception as e: record_error(f"Balance {e}"); return 0

def get_contract_amount(symbol,margin,price):
    market=exchange.market(symbol); contract_size=float(market.get("contractSize") or 1); notional=margin*CONFIG["LEVERAGE"]
    raw=notional/(price*contract_size); amount=float(exchange.amount_to_precision(symbol,raw))
    real_margin=(amount*price*contract_size)/CONFIG["LEVERAGE"]
    if real_margin>CONFIG["MAX_FUTURES_USD"]: raise ValueError(f"Margin {real_margin:.2f} > cap")
    return amount

def get_targets(entry,direction):
    if direction=="long": return {"tp1":entry*(1+CONFIG["TAKE_PROFIT"]),"tp2":entry*(1+CONFIG["TAKE_PROFIT_2"]),"sl":entry*(1-CONFIG["STOP_LOSS"])}
    else: return {"tp1":entry*(1-CONFIG["TAKE_PROFIT"]),"tp2":entry*(1-CONFIG["TAKE_PROFIT_2"]),"sl":entry*(1+CONFIG["STOP_LOSS"])}

def is_profitable(entry,tp):
    gross=abs(tp-entry)/entry; return (gross-CONFIG["FEE_RATE"]*2)>CONFIG["MIN_NET"]

def update_trailing(pos,current_price):
    entry,direction=pos["entry"],pos["side"]
    if direction=="long":
        profit=(current_price-entry)/entry
        if profit>=CONFIG["TRAILING_TRIGGER"]:
            new_sl=current_price*(1-CONFIG["TRAILING_STEP"])
            if new_sl>pos["stop"]: pos["stop"]=new_sl; log.info(f"TRAIL {pos['symbol']} SL->{new_sl:.4f} +{profit*100:.2f}%"); return True
    else:
        profit=(entry-current_price)/entry
        if profit>=CONFIG["TRAILING_TRIGGER"]:
            new_sl=current_price*(1+CONFIG["TRAILING_STEP"])
            if new_sl<pos["stop"]: pos["stop"]=new_sl; log.info(f"TRAIL {pos['symbol']} SL->{new_sl:.4f} +{profit*100:.2f}%"); return True
    return False

def place_spot_trade(signal):
    if state["spot_position"] or signal["direction"]!="long": return
    free=get_free_usdt(); budget=min(CONFIG["SPOT_BUDGET"],free*0.98)
    if budget<5: return
    price=signal["price"]; amount=float(exchange.amount_to_precision(signal["symbol"],budget/price))
    if amount*price>CONFIG["MAX_SPOT_USD"]: return
    try:
        order=exchange.create_market_buy_order(signal["symbol"],amount); avg=float(order.get("average") or price); filled=float(order.get("filled") or amount); t=get_targets(avg,"long")
        state["spot_position"]={"symbol":signal["symbol"],"amount":filled,"entry":avg,"stop":t["sl"],"tp1":t["tp1"],"tp2":t["tp2"],"side":"long","opened":datetime.now(timezone.utc).isoformat()}; save_state()
        log.info(f"SPOT OPEN {signal['symbol']} {filled} @ {avg}")
    except Exception as e: record_error(f"Spot {e}")

def place_future_trade(signal):
    if state["future_position"] or not CONFIG["ALLOW_FUTURES"]: return
    swap=get_swap_symbol(signal["symbol"])
    if not swap: return
    try:
        positions=exchange.fetch_positions([swap])
        for p in positions:
            if float(p.get("contracts") or 0)>0: return
    except: pass
    free=get_free_usdt(); margin=min(CONFIG["FUTURES_MARGIN"],free*0.95)
    if margin<4: return
    price=signal["price"]; t=get_targets(price,signal["direction"])
    if not is_profitable(price,t["tp1"]): return
    amount=get_contract_amount(swap,margin,price)
    side="buy" if signal["direction"]=="long" else "sell"
    posSide="long" if signal["direction"]=="long" else "short"
    try: exchange.set_leverage(CONFIG["LEVERAGE"],swap,{"mgnMode":"isolated"})
    except: pass
    try:
        # المحاولة 1: مع posSide (لـ Hedge Mode)
        order=exchange.create_order(swap,"market",side,amount,None,{"tdMode":"isolated","posSide":posSide,"lever":str(CONFIG["LEVERAGE"])})
        avg=float(order.get("average") or price); filled=float(order.get("filled") or amount); t_real=get_targets(avg,signal["direction"])
        state["future_position"]={"symbol":swap,"side":signal["direction"],"amount":filled,"entry":avg,"stop":t_real["sl"],"tp1":t_real["tp1"],"tp2":t_real["tp2"],"tp1_done":False,"opened":datetime.now(timezone.utc).isoformat()}
        log.info(f"FUT OPEN {side}/{posSide} {swap} {filled} @ {avg}"); save_state()
    except Exception as e:
        err=str(e)
        if "posSide" in err or "51000" in err:
            try:
                # المحاولة 2: بدون posSide (لـ One-Way Mode)
                log.info(f"Retry futures without posSide for {swap}")
                order=exchange.create_order(swap,"market",side,amount,None,{"tdMode":"isolated","lever":str(CONFIG["LEVERAGE"])})
                avg=float(order.get("average") or price); filled=float(order.get("filled") or amount); t_real=get_targets(avg,signal["direction"])
                state["future_position"]={"symbol":swap,"side":signal["direction"],"amount":filled,"entry":avg,"stop":t_real["sl"],"tp1":t_real["tp1"],"tp2":t_real["tp2"],"tp1_done":False,"opened":datetime.now(timezone.utc).isoformat()}
                save_state()
            except Exception as e2:
                record_error(f"Future retry {e2}")
        elif "50124" in err: CONFIG["ALLOW_FUTURES"]=False; record_error("Futures disabled - enable futures in OKX")
        else: record_error(f"Future {e}")

def monitor_positions():
    pos=state.get("spot_position")
    if pos:
        try:
            ticker=exchange.fetch_ticker(pos["symbol"]); price=float(ticker["last"]); update_trailing(pos,price)
            hit=price<=pos["stop"] or price>=pos["tp1"]
            if hit:
                base=pos["symbol"].split("/")[0]; bal=exchange.fetch_balance(); avail=float(bal.get(base,{}).get("free",0) or 0)
                amt=float(exchange.amount_to_precision(pos["symbol"],min(pos["amount"],avail)))
                if amt>0:
                    order=exchange.create_market_sell_order(pos["symbol"],amt); exit_price=float(order.get("average") or price)
                    fee=exit_price*amt*CONFIG["FEE_RATE"]; pnl=(exit_price-pos["entry"])*amt-fee
                    state["pnl"]+=pnl; state["pnl_net"]+=pnl
                    if pnl>=0: state["wins"]+=1
                    else: state["losses"]+=1
                    state["spot_position"]=None; save_state()
        except Exception as e: record_error(f"Spot mon {e}")
    fpos=state.get("future_position")
    if fpos:
        try:
            ticker=exchange.fetch_ticker(fpos["symbol"]); price=float(ticker["last"]); update_trailing(fpos,price)
            positions=exchange.fetch_positions([fpos["symbol"]]); open_pos=None
            for p in positions:
                if float(p.get("contracts") or 0)>0: open_pos=p; break
            if not open_pos: state["future_position"]=None; save_state(); return
            tp1_hit=(price>=fpos["tp1"] if fpos["side"]=="long" else price<=fpos["tp1"])
            if tp1_hit and not fpos.get("tp1_done"):
                half=float(exchange.amount_to_precision(fpos["symbol"],fpos["amount"]/2)); side_close="sell" if fpos["side"]=="long" else "buy"
                posSide_close="long" if fpos["side"]=="long" else "short"
                try:
                    exchange.create_order(fpos["symbol"],"market",side_close,half,None,{"posSide":posSide_close,"mgnMode":"isolated","reduceOnly":True})
                except:
                    exchange.create_order(fpos["symbol"],"market",side_close,half,None,{"mgnMode":"isolated","reduceOnly":True})
                fpos["stop"]=fpos["entry"]; fpos["tp1_done"]=True; fpos["amount"]-=half; save_state(); log.info(f"TP1 50% {fpos['symbol']}")
        except Exception as e: record_error(f"Fut mon {e}")

def scan_and_trade():
    symbols=get_market_symbols(); signals=[]
    for s in symbols:
        if not state["running"]: break
        sig=analyze_market(s)
        if sig: signals.append(sig)
        time.sleep(0.12)
    signals.sort(key=lambda x:x["score"],reverse=True); state["scanned"]=len(symbols); state["signals"]=signals[:10]; state["last_scan"]=datetime.now(timezone.utc).isoformat()
    if not signals: save_state(); return
    best=signals[0]; log.info(f"Best {best['symbol']} {best['direction']} {best['score']}")
    if CONFIG["ALLOW_SPOT"]: place_spot_trade(best)
    if CONFIG["ALLOW_FUTURES"]: place_future_trade(best)
    save_state()

def run_bot():
    load_state(); log.info(f"V3002 START keys={state['keys_found']} balance will be fetched")
    while state["running"]:
        try:
            monitor_positions()
            scan_and_trade()
        except Exception as e: record_error(str(e))
        time.sleep(CONFIG["SCAN_INTERVAL"])

@app.route("/")
def home(): 
    return jsonify({
        "bot":"V3002 FIXED posSide",
        "keys": state["keys_found"],
        "running":state["running"],
        "live":CONFIG["LIVE_TRADING"],
        "balance_usdt": get_free_usdt(),
        "tp1":f"{CONFIG['TAKE_PROFIT']*100}%","tp2":f"{CONFIG['TAKE_PROFIT_2']*100}%","sl":f"{CONFIG['STOP_LOSS']*100}%","trailing":f"{CONFIG['TRAILING_TRIGGER']*100}%/{CONFIG['TRAILING_STEP']*100}%",
        "scanned":state["scanned"],"last_scan":state["last_scan"],"signals":state["signals"],"spot_pos":state["spot_position"],"future_pos":state["future_position"],
        "wins":state["wins"],"losses":state["losses"],"pnl":round(state["pnl"],4),"pnl_net":round(state["pnl_net"],4),"errors":state["errors"][-5:]
    })

@app.route("/stop")
def stop_bot(): state["running"]=False; save_state(); return "<h1 style='color:red;text-align:center;margin-top:80px'>STOP</h1>"
@app.route("/start")
def start_bot(): state["running"]=True; save_state(); return "<h1 style='color:green;text-align:center;margin-top:80px'>RUNNING</h1>"
@app.route("/health")
def health(): return jsonify({"status":"online"})

if __name__=="__main__":
    import threading; threading.Thread(target=run_bot,daemon=True).start()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","5000")),debug=False,use_reloader=False)
