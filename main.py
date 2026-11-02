import os, time, json, logging
from datetime import datetime, timezone, date
import ccxt, pandas as pd
from flask import Flask, jsonify, request

CONFIG = {
    "RISK_PER_TRADE": 0.01,
    "MAX_POSITIONS": 2,
    "LEVERAGE": 3,
    "MAX_COINS": 18,
    "TIMEFRAME": "15m",
    "TIMEFRAME_HTF": "1h",
    "CANDLE_LIMIT": 150,
    "SCAN_INTERVAL": 25,
    "TAKE_PROFIT": 0.025,
    "STOP_LOSS": 0.011,
    "DAILY_LOSS_LIMIT": 4.0,
    "MAX_CONSECUTIVE_LOSSES": 3,
    "BTC_VOLATILITY_LIMIT": 0.04,
    "STATE_FILE": "bot_state.json",
    "TRADES_FILE": "trades_log.json",
}

API_KEY=os.getenv("OKX_API_KEY","").strip() or os.getenv("OKX_KEY","").strip()
API_SECRET=os.getenv("OKX_API_SECRET","").strip() or os.getenv("OKX_SECRET_KEY","").strip() or os.getenv("OKX_SECRET","").strip()
API_PASSWORD=os.getenv("OKX_API_PASSWORD","").strip() or os.getenv("OKX_PASSPHRASE","").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log=logging.getLogger("V100SAFE")
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
    "stopped_by_loss": False,
    "stopped_reason": "",
    "open_trades": saved.get("open_trades",{}),
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
        with open(CONFIG["TRADES_FILE"],"w") as f: json.dump(trades[-300:], f, indent=2)
    except: pass

CORRELATED_GROUPS = {
    "MAJORS": ["BTC/USDT:USDT","ETH/USDT:USDT","SOL/USDT:USDT","AVAX/USDT:USDT","ADA/USDT:USDT","DOT/USDT:USDT"],
    "L2": ["ARB/USDT:USDT","OP/USDT:USDT"],
    "AI": ["FET/USDT:USDT","TAO/USDT:USDT","RENDER/USDT:USDT","NEAR/USDT:USDT"],
}

def is_correlated(new_symbol, open_symbols):
    for group, members in CORRELATED_GROUPS.items():
        if new_symbol in members:
            for s in open_symbols:
                if s in members and s!=new_symbol:
                    return True, group
    if "BTC/USDT:USDT" in open_symbols and new_symbol in ["ETH/USDT:USDT","SOL/USDT:USDT"]:
        return True, "BTC-CORR"
    return False, ""

def get_positions():
    try:
        positions=exchange.fetch_positions()
        total=0; count=0; symbols=[]; pos_list=[]
        for p in positions:
            if float(p.get("contracts") or 0)>0:
                margin=float(p.get("initialMargin") or p.get("collateral") or 0)
                if margin==0:
                    notional=float(p.get("notional") or 0)
                    leverage=float(p.get("leverage") or CONFIG["LEVERAGE"])
                    if notional>0: margin=notional/leverage
                total+=margin; count+=1
                symbols.append(p["symbol"])
                pos_list.append(p)
        return total, count, pos_list, symbols
    except: return 0,0,[],[]

def fetch_df(symbol, tf):
    try:
        candles=exchange.fetch_ohlcv(symbol,timeframe=tf,limit=CONFIG["CANDLE_LIMIT"])
        df=pd.DataFrame(candles,columns=["time","open","high","low","close","volume"])
        if len(df)<60: return None
        df=df.iloc[:-1].copy()
        if df["close"].iloc[-1] < 0.005: return None
        df["ema9"]=df["close"].ewm(span=9).mean()
        df["ema21"]=df["close"].ewm(span=21).mean()
        df["ema50"]=df["close"].ewm(span=50).mean()
        df["ema200"]=df["close"].ewm(span=200).mean()
        delta=df["close"].diff(); gain=delta.clip(lower=0); loss=-delta.clip(upper=0)
        avg_gain=gain.ewm(alpha=1/14,adjust=False).mean(); avg_loss=loss.ewm(alpha=1/14,adjust=False).mean()
        rs=avg_gain/avg_loss.replace(0,1e-8); df["rsi"]=100-(100/(1+rs))
        df["vol_avg"]=df["volume"].rolling(20).mean()
        df["atr"]= (df["high"]-df["low"]).rolling(14).mean()
        df["bb_mid"]=df["close"].rolling(20).mean()
        return df.dropna()
    except: return None

def get_btc_status():
    try:
        df=fetch_df("BTC/USDT", CONFIG["TIMEFRAME"])
        if df is None: return "neutral",0
        curr=df.iloc[-1]
        atr_pct=curr["atr"]/curr["close"]
        trend="neutral"
        if curr["ema9"]>curr["ema21"]>curr["ema50"] and curr["close"]>curr["ema200"]: trend="bull"
        elif curr["ema9"]<curr["ema21"]<curr["ema50"] and curr["close"]<curr["ema200"]: trend="bear"
        return trend, atr_pct
    except: return "neutral",0

def analyze(symbol, btc_trend):
    try:
        df=fetch_df(symbol, CONFIG["TIMEFRAME"])
        df_h=fetch_df(symbol, CONFIG["TIMEFRAME_HTF"])
        if df is None or df_h is None: return None
        curr=df.iloc[-1]; prev=df.iloc[-2]; curr_h=df_h.iloc[-1]
        if curr["volume"] < curr["vol_avg"]*1.3: return None
        atr_pct=curr["atr"]/curr["close"]
        if atr_pct > 0.05 or atr_pct < 0.001: return None
        score=0; direction=None
        if curr["ema9"]>curr["ema21"]>curr["ema50"] and curr["close"]>curr["ema200"]:
            if 50 < curr["rsi"] < 70 and curr["close"]>curr["bb_mid"]:
                if curr_h["ema9"]<=curr_h["ema21"]: return None
                score+=7
                if prev["ema9"]<=prev["ema21"] and curr["ema9"]>curr["ema21"]: score+=3
                if btc_trend=="bear" and score<7: return None
                direction="long"
        if curr["ema9"]<curr["ema21"]<curr["ema50"] and curr["close"]<curr["ema200"]:
            if 30 < curr["rsi"] < 50 and curr["close"]<curr["bb_mid"]:
                if curr_h["ema9"]>=curr_h["ema21"]: return None
                score+=7
                if prev["ema9"]>=prev["ema21"] and curr["ema9"]<curr["ema21"]: score+=3
                if btc_trend=="bull" and score<7: return None
                direction="short" if direction is None else direction
        if direction and score>=7:
            return {"symbol":symbol,"direction":direction,"score":score,"price":float(curr["close"]),"rsi":round(float(curr["rsi"]),1),"atr_pct":atr_pct}
    except: return None

def get_free_usdt():
    try: bal=exchange.fetch_balance(); return float(bal.get("USDT",{}).get("free",0) or 0)
    except: return 0

def calc_margin(price):
    try:
        bal=get_free_usdt()
        if bal<2: bal=9.0
        risk_usd=bal*CONFIG["RISK_PER_TRADE"]
        margin_needed=risk_usd/CONFIG["STOP_LOSS"]
        margin=margin_needed/CONFIG["LEVERAGE"]
        return round(max(2.0,min(margin,4.5)),2)
    except: return 2.5

def get_amount(symbol,margin,price):
    try:
        market=exchange.market(symbol); contract_size=float(market.get("contractSize") or 1)
        notional=margin*CONFIG["LEVERAGE"]; raw=notional/(price*contract_size)
        return float(exchange.amount_to_precision(symbol,raw))
    except: return 0

def get_targets(entry,direction):
    if direction=="long": return {"tp":entry*(1+CONFIG["TAKE_PROFIT"]),"sl":entry*(1-CONFIG["STOP_LOSS"])}
    else: return {"tp":entry*(1-CONFIG["TAKE_PROFIT"]),"sl":entry*(1+CONFIG["STOP_LOSS"])}

def verify_sl(swap):
    try:
        positions=exchange.fetch_positions([swap])
        for p in positions:
            if float(p.get("contracts") or 0)>0:
                if p.get("stopLossPrice") or float(p.get("info",{}).get("stopLossPrice") or 0)>0:
                    return True
        return False
    except: return False

def emergency_close(swap, direction, amount, reason):
    try:
        side_close="sell" if direction=="long" else "buy"
        posSide="long" if direction=="long" else "short"
        exchange.create_order(swap,"market",side_close,amount,None,{"tdMode":"isolated","posSide":posSide})
        log.warning(f"EMERGENCY CLOSE {swap} reason:{reason}")
        save_trade_log({"time":datetime.now(timezone.utc).isoformat(),"type":"EMERGENCY_CLOSE","symbol":swap,"reason":reason})
    except Exception as e:
        state["errors"].append(f"emergency fail {e}")

def place_trade(signal):
    total, cnt, _, open_syms = get_positions()
    if cnt >= CONFIG["MAX_POSITIONS"]: return
    if state["stopped_by_loss"]: return
    base=signal["symbol"].split("/")[0]; swap=base+"/USDT:USDT"
    if any(base in s for s in open_syms): return
    corr, group = is_correlated(swap, open_syms)
    if corr:
        log.info(f"SKIP CORRELATED {swap} group {group}")
        return
    try:
        margin=calc_margin(signal["price"])
        amount=get_amount(swap,margin,signal["price"])
        if amount==0: return
        try: exchange.set_leverage(CONFIG["LEVERAGE"],swap,{"mgnMode":"isolated"})
        except: pass
        side="buy" if signal["direction"]=="long" else "sell"; posSide="long" if signal["direction"]=="long" else "short"
        order=exchange.create_order(swap,"market",side,amount,None,{"tdMode":"isolated","posSide":posSide,"lever":str(CONFIG["LEVERAGE"])})
        avg=float(order.get("average") or signal["price"]); filled=float(order.get("filled") or amount)
        t=get_targets(avg, signal["direction"])
        sl_ok=False
        for attempt in range(2):
            try:
                exchange.create_order(swap, "market", "sell" if signal["direction"]=="long" else "buy", filled, None, {"tdMode":"isolated","posSide":posSide,"stopLoss":{"triggerPrice":t["sl"],"orderPrice":"-1"}})
                try: exchange.create_order(swap, "market", "sell" if signal["direction"]=="long" else "buy", filled, None, {"tdMode":"isolated","posSide":posSide,"takeProfit":{"triggerPrice":t["tp"],"orderPrice":"-1"}})
                except: pass
                time.sleep(1)
                if verify_sl(swap):
                    sl_ok=True; break
            except Exception as e:
                state["errors"].append(f"SL try {attempt}: {str(e)[-60:]}")
                time.sleep(1)
        if not sl_ok:
            emergency_close(swap, signal["direction"], filled, "SL_FAILED")
            save_trade_log({"time":datetime.now(timezone.utc).isoformat(),"type":"FAIL_SL_CLOSE","symbol":swap,"entry":avg,"reason":"SL not verified"})
            return
        state["open_trades"][swap]={"entry":avg,"direction":signal["direction"],"margin":margin,"amount":filled,"time":datetime.now(timezone.utc).isoformat()}
        save_state()
        save_trade_log({"time":datetime.now(timezone.utc).isoformat(),"type":"ENTRY","symbol":swap,"direction":signal["direction"],"entry":avg,"margin":margin,"amount":filled,"score":signal["score"],"sl_verified":True})
        log.info(f"SAFE OPEN {swap} {signal['direction']} margin:{margin}$ SL OK")
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
                trades=exchange.fetch_my_trades(sym, limit=20)
                pnl=0.0
                for t in reversed(trades[-5:]):
                    info=t.get("info",{})
                    if info.get("realizedPnl") or info.get("pnl"):
                        pnl=float(info.get("realizedPnl") or info.get("pnl") or 0)
                        if pnl!=0: break
                if pnl!=0:
                    state["daily_pnl"]=round(state["daily_pnl"]+pnl,4)
                    if pnl<0: state["consecutive_losses"]+=1
                    else: state["consecutive_losses"]=0
                    save_trade_log({"time":datetime.now(timezone.utc).isoformat(),"type":"EXIT","symbol":sym,"pnl":pnl,"daily_pnl":state["daily_pnl"],"consecutive":state["consecutive_losses"]})
                del state["open_trades"][sym]
                save_state()
            except Exception as e:
                del state["open_trades"][sym]
        if state["daily_pnl"] <= -CONFIG["DAILY_LOSS_LIMIT"]:
            state["stopped_by_loss"]=True; state["stopped_reason"]=f"DAILY LOSS {state['daily_pnl']}$"
        if state["consecutive_losses"] >= CONFIG["MAX_CONSECUTIVE_LOSSES"]:
            state["stopped_by_loss"]=True; state["stopped_reason"]=f"{state['consecutive_losses']} LOSSES IN ROW"
    except Exception as e: state["errors"].append(f"check closed {e}")

def scan_and_trade():
    try: exchange.load_markets()
    except: pass
    check_closed_and_update_pnl()
    if state["stopped_by_loss"]: return
    btc_trend, btc_vol = get_btc_status()
    state["btc_trend"]=btc_trend; state["btc_vol"]=round(btc_vol*100,2)
    if btc_vol > CONFIG["BTC_VOLATILITY_LIMIT"]:
        log.info(f"BTC VOLATILE {btc_vol*100:.2f}% SKIP")
        return
    _, cnt, _, open_syms = get_positions()
    if cnt>=CONFIG["MAX_POSITIONS"]: return
    signals=[]; scanned=0
    TOP_COINS = ["BTC/USDT","ETH/USDT","SOL/USDT","AVAX/USDT","LINK/USDT","ADA/USDT","LTC/USDT","DOT/USDT","ARB/USDT","ENA/USDT","FET/USDT","TAO/USDT","RENDER/USDT","SUI/USDT","SEI/USDT","APT/USDT","NEAR/USDT","OP/USDT"]
    for s in TOP_COINS:
        base=s.split("/")[0]; swap=base+"/USDT:USDT"
        if any(base in sym for sym in open_syms): continue
        sig=analyze(s, btc_trend)
        scanned+=1
        if sig: signals.append(sig)
        time.sleep(0.2)
    signals.sort(key=lambda x:x["score"],reverse=True)
    state["scanned"]=scanned; state["signals"]=signals[:5]; state["last_scan"]=datetime.now(timezone.utc).isoformat(); state["loop"]+=1
    if signals: place_trade(signals[0])

def run_bot():
    log.info("V100000 FINAL SAFE + SPOT STARTED")
    while state["running"]:
        try: scan_and_trade()
        except Exception as e: state["errors"].append(str(e)[-100:]); state["errors"]=state["errors"][-5:]
        time.sleep(CONFIG["SCAN_INTERVAL"])

@app.route("/")
def home():
    total,cnt,pos,syms=get_positions()
    return jsonify({
        "bot":"V100000 FINAL SAFE + SPOT",
        "balance":round(get_free_usdt(),4),
        "btc_trend":state["btc_trend"],
        "btc_vol":f"{state['btc_vol']}%",
        "open_count":cnt,
        "max_positions":CONFIG["MAX_POSITIONS"],
        "open_symbols":syms,
        "total_margin":round(total,2),
        "daily_pnl":state["daily_pnl"],
        "daily_limit":-CONFIG["DAILY_LOSS_LIMIT"],
        "consecutive_losses":state["consecutive_losses"],
        "stopped":state["stopped_by_loss"],
        "stopped_reason":state["stopped_reason"],
        "risk":f"{CONFIG['RISK_PER_TRADE']*100}%",
        "scanned":state["scanned"],
        "loop":state["loop"],
        "signals":state["signals"],
        "positions":[{"symbol":p["symbol"],"side":p.get("side"),"entry":p.get("entryPrice"),"pnl":round(float(p.get("unrealizedPnl") or 0),4)} for p in pos if float(p.get("contracts") or 0)>0],
        "errors":state["errors"][-3:],
        "endpoints":["/ping","/trades","/spot","/reset_daily"]
    })

@app.route("/ping")
def ping(): return jsonify({"pong":True,"loop":state["loop"],"daily_pnl":state["daily_pnl"],"stopped":state["stopped_by_loss"],"btc_vol":state["btc_vol"]})

@app.route("/health")
def health(): return jsonify({"status":"online","loop":state["loop"]})

@app.route("/trades")
def trades(): return jsonify(load_trades()[-40:])

@app.route("/reset_daily")
def reset_daily():
    state["daily_pnl"]=0.0; state["consecutive_losses"]=0; state["stopped_by_loss"]=False; state["stopped_reason"]=""; state["daily_date"]=str(date.today()); save_state()
    return jsonify({"reset":True})

@app.route("/spot")
def spot_analysis():
    try:
        # نجيب رصيد السبوت عبر REST مباشرة
        bal=exchange.fetch_balance()
        spot_holdings=[]
        for coin, data in bal.get("total",{}).items():
            if coin=="USDT": continue
            total_amt=float(data or 0)
            if total_amt>0:
                try:
                    symbol=f"{coin}/USDT"
                    ticker=exchange.fetch_ticker(symbol)
                    price=float(ticker["last"])
                    df=fetch_df(symbol, "1h")
                    if df is None:
                        trend="غير معروف"; advice="انتظر - ما قدر يقرأ الشارت"; rsi_val=None
                    else:
                        curr=df.iloc[-1]
                        rsi_val=round(float(curr["rsi"]),1)
                        if curr["close"]<curr["ema50"] and curr["rsi"]<40:
                            trend="هابط قرب قاع"; advice="لا تبيع الآن - انتظر ارتداد"
                        elif curr["close"]>curr["ema50"] and curr["rsi"]>70:
                            trend="قمة محتملة"; advice="بيع 50% الآن"
                        elif curr["close"]>curr["ema200"] and curr["rsi"]<65:
                            trend="صاعد قوي"; advice="انتظر - لا تبيع"
                        elif curr["close"]<curr["ema200"]:
                            trend="هابط"; advice="انتظر أو بيع وادخل فيوتشر"
                        else:
                            trend="عرضي"; advice="انتظر"
                    value=total_amt*price
                    if value>=0.5:  # اكثر من 0.5$
                        spot_holdings.append({
                            "coin":coin,
                            "amount":total_amt,
                            "price":price,
                            "value_usdt":round(value,2),
                            "trend":trend,
                            "advice":advice,
                            "rsi":rsi_val
                        })
                except Exception as e:
                    spot_holdings.append({"coin":coin,"amount":total_amt,"price":0,"value_usdt":0,"trend":"خطأ","advice":str(e)[:50]})
        spot_holdings.sort(key=lambda x:x["value_usdt"], reverse=True)
        total_value=sum([h["value_usdt"] for h in spot_holdings])
        return jsonify({
            "total_spot_value":round(total_value,2),
            "count":len(spot_holdings),
            "holdings":spot_holdings,
            "summary": f"عندك {len(spot_holdings)} عملة قديمة قيمتها {total_value:.2f}$ - ادخل /spot/sell?coin=XXX&pct=50 للبيع"
        })
    except Exception as e:
        return jsonify({"error":str(e)})

@app.route("/spot/sell")
def spot_sell():
    try:
        coin=request.args.get("coin","").upper()
        pct=float(request.args.get("pct","50"))
        if not coin: return jsonify({"error":"اكتب ?coin=BTC&pct=50"})
        bal=exchange.fetch_balance()
        amount=float(bal.get("total",{}).get(coin,0) or bal.get("free",{}).get(coin,0) or 0)
        if amount==0: return jsonify({"error":f"ما عندك {coin} في السبوت"})
        sell_amount=amount*pct/100
        symbol=f"{coin}/USDT"
        # بيع سبوت - نستخدم spot type
        exchange.options["defaultType"]="spot"
        try:
            order=exchange.create_market_sell_order(symbol, sell_amount)
        except:
            order=exchange.create_order(symbol, "market", "sell", sell_amount)
        exchange.options["defaultType"]="swap"
        save_trade_log({"time":datetime.now(timezone.utc).isoformat(),"type":"SPOT_SELL","symbol":symbol,"amount":sell_amount,"pct":pct})
        return jsonify({"sold":f"{sell_amount} {coin}", "order_id":order.get("id"), "symbol":symbol})
    except Exception as e:
        exchange.options["defaultType"]="swap"
        return jsonify({"error":str(e)})

if __name__=="__main__":
    import threading; threading.Thread(target=run_bot,daemon=True).start()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","5000")),debug=False,use_reloader=False)