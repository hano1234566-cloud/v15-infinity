import os, time, json, logging
from datetime import datetime, timezone, date
import ccxt, pandas as pd
from flask import Flask, jsonify, request

CONFIG = {
    "MAX_COINS": 18,
    "TIMEFRAME": "15m",
    "TIMEFRAME_HTF": "1h",
    "CANDLE_LIMIT": 150,
    "SCAN_INTERVAL": 25,
    "STOP_LOSS": 0.011,
    "DAILY_LOSS_LIMIT": 4.0,
    "MAX_CONSECUTIVE_LOSSES": 3,
    "BTC_VOLATILITY_LIMIT": 0.04,
    "STATE_FILE": "bot_state.json",
    "TRADES_FILE": "trades_log.json",
    "CONFIG_FILE": "config.json",
    "SPOT_AUTO_SELL_WEAK": True,
    "SPOT_WEAK_COINS": ["SOPH","CORE","XPL","WET","BONK"],
    "SPOT_STRONG_COINS": ["AAVE","DOGE","TRX"],
    "SPOT_SELL_RSI_PEAK": 70,
    "SPOT_SELL_RSI_TOP": 75,
}

try:
    if os.path.exists(CONFIG["CONFIG_FILE"]):
        with open(CONFIG["CONFIG_FILE"],"r") as f:
            ext=json.load(f); CONFIG.update(ext)
except: pass

API_KEY=os.getenv("OKX_API_KEY","").strip() or os.getenv("OKX_KEY","").strip()
API_SECRET=os.getenv("OKX_API_SECRET","").strip() or os.getenv("OKX_SECRET_KEY","").strip() or os.getenv("OKX_SECRET","").strip()
API_PASSWORD=os.getenv("OKX_API_PASSWORD","").strip() or os.getenv("OKX_PASSPHRASE","").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log=logging.getLogger("V100001")
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
    "stopped_by_loss": False,"stopped_reason": "",
    "open_trades": saved.get("open_trades",{}),
    "spot_sold": saved.get("spot_sold",[]),
    "auto_mode":"🛡️ حماية","auto_risk":0.01,"auto_lev":3,
}

def save_state():
    try:
        with open(CONFIG["STATE_FILE"],"w") as f:
            json.dump({"daily_pnl":state["daily_pnl"],"daily_date":state["daily_date"],"consecutive_losses":state["consecutive_losses"],"open_trades":state["open_trades"],"spot_sold":state["spot_sold"]}, f)
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
def save_config(new_cfg):
    try:
        with open(CONFIG["CONFIG_FILE"],"w") as f: json.dump(new_cfg, f, indent=2)
        CONFIG.update(new_cfg); return True
    except Exception as e:
        state["errors"].append(f"save cfg {e}"); return False

# ===== AUTO-SCALE SYSTEM =====
def get_free_usdt():
    try: bal=exchange.fetch_balance(); return float(bal.get("USDT",{}).get("free",0) or 0)
    except: return 0

def get_total_equity():
    try:
        free=get_free_usdt()
        bal=exchange.fetch_balance()
        spot_val=0
        for coin in CONFIG["SPOT_STRONG_COINS"]+CONFIG["SPOT_WEAK_COINS"]:
            amt=float(bal.get("total",{}).get(coin,0) or 0)
            if amt>0:
                try:
                    price=float(exchange.fetch_ticker(f"{coin}/USDT")["last"])
                    spot_val+=amt*price
                except: pass
        return free+spot_val, free, spot_val
    except:
        return get_free_usdt(), get_free_usdt(), 0

def get_auto_config():
    total, free, spot = get_total_equity()
    if total < 50:
        return {"RISK":0.01, "LEV":3, "TP":0.025, "MAX":2, "MODE":"🛡️ حماية", "NEXT":50-total, "TOTAL":total}
    elif total < 100:
        return {"RISK":0.015, "LEV":4, "TP":0.03, "MAX":2, "MODE":"🚀 نمو", "NEXT":100-total, "TOTAL":total}
    else:
        return {"RISK":0.02, "LEV":5, "TP":0.035, "MAX":3, "MODE":"🔥 مصغر JohnBread", "NEXT":0, "TOTAL":total}

def calc_margin(price):
    try:
        cfg=get_auto_config()
        bal=get_free_usdt()
        if bal<2: bal=9.0
        risk_usd=bal*cfg["RISK"]
        margin_needed=risk_usd/CONFIG["STOP_LOSS"]
        margin=margin_needed/cfg["LEV"]
        state["auto_mode"]=cfg["MODE"]; state["auto_risk"]=cfg["RISK"]; state["auto_lev"]=cfg["LEV"]
        return round(max(2.0,min(margin,6.0)),2)
    except: return 2.5

def get_targets(entry,direction):
    cfg=get_auto_config()
    tp_pct=cfg["TP"]
    if direction=="long": return {"tp":entry*(1+tp_pct),"sl":entry*(1-CONFIG["STOP_LOSS"])}
    else: return {"tp":entry*(1-tp_pct),"sl":entry*(1+CONFIG["STOP_LOSS"])}

# ===== REST OF BOT (same logic) =====
CORRELATED_GROUPS = {
    "MAJORS": ["BTC/USDT:USDT","ETH/USDT:USDT","SOL/USDT:USDT","AVAX/USDT:USDT","ADA/USDT:USDT","DOT/USDT:USDT"],
    "L2": ["ARB/USDT:USDT","OP/USDT:USDT"],
    "AI": ["FET/USDT:USDT","TAO/USDT:USDT","RENDER/USDT:USDT","NEAR/USDT:USDT"],
}
def is_correlated(new_symbol, open_symbols):
    for group, members in CORRELATED_GROUPS.items():
        if new_symbol in members:
            for s in open_symbols:
                if s in members and s!=new_symbol: return True, group
    if "BTC/USDT:USDT" in open_symbols and new_symbol in ["ETH/USDT:USDT","SOL/USDT:USDT"]: return True, "BTC-CORR"
    return False, ""
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
        if len(df)<60: return None
        df=df.iloc[:-1].copy()
        if df["close"].iloc[-1] < 0.005: return None
        df["ema9"]=df["close"].ewm(span=9).mean(); df["ema21"]=df["close"].ewm(span=21).mean(); df["ema50"]=df["close"].ewm(span=50).mean(); df["ema200"]=df["close"].ewm(span=200).mean()
        delta=df["close"].diff(); gain=delta.clip(lower=0); loss=-delta.clip(upper=0)
        avg_gain=gain.ewm(alpha=1/14,adjust=False).mean(); avg_loss=loss.ewm(alpha=1/14,adjust=False).mean()
        rs=avg_gain/avg_loss.replace(0,1e-8); df["rsi"]=100-(100/(1+rs))
        df["vol_avg"]=df["volume"].rolling(20).mean(); df["atr"]= (df["high"]-df["low"]).rolling(14).mean(); df["bb_mid"]=df["close"].rolling(20).mean()
        return df.dropna()
    except: return None
def get_btc_status():
    try:
        df=fetch_df("BTC/USDT", CONFIG["TIMEFRAME"])
        if df is None: return "neutral",0
        curr=df.iloc[-1]; atr_pct=curr["atr"]/curr["close"]
        trend="neutral"
        if curr["ema9"]>curr["ema21"]>curr["ema50"] and curr["close"]>curr["ema200"]: trend="bull"
        elif curr["ema9"]<curr["ema21"]<curr["ema50"] and curr["close"]<curr["ema200"]: trend="bear"
        return trend, atr_pct
    except: return "neutral",0
def analyze(symbol, btc_trend):
    try:
        df=fetch_df(symbol, CONFIG["TIMEFRAME"]); df_h=fetch_df(symbol, CONFIG["TIMEFRAME_HTF"])
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
def emergency_close(swap, direction, amount, reason):
    try:
        pos_check = exchange.fetch_positions([swap])
        has_pos = any(float(p.get("contracts") or 0)>0 for p in pos_check)
        if not has_pos: return
        side_close="sell" if direction=="long" else "buy"; posSide="long" if direction=="long" else "short"
        exchange.create_order(swap,"market",side_close,amount,None,{"tdMode":"isolated","posSide":posSide})
        save_trade_log({"time":datetime.now(timezone.utc).isoformat(),"type":"EMERGENCY_CLOSE","symbol":swap,"reason":reason})
    except Exception as e:
        if "51169" not in str(e): state["errors"].append(f"emergency {e}")
def place_trade(signal):
    total, cnt, _, open_syms = get_positions()
    cfg=get_auto_config()
    if cnt >= cfg["MAX"]: return
    if state["stopped_by_loss"]: return
    base=signal["symbol"].split("/")[0]; swap=base+"/USDT:USDT"
    if any(base in s for s in open_syms): return
    corr, group = is_correlated(swap, open_syms)
    if corr: return
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
        sl_ok=False
        for attempt in range(2):
            try:
                exchange.create_order(swap, "market", "sell" if signal["direction"]=="long" else "buy", filled, None, {"tdMode":"isolated","posSide":posSide,"stopLoss":{"triggerPrice":t["sl"],"orderPrice":"-1"}})
                try: exchange.create_order(swap, "market", "sell" if signal["direction"]=="long" else "buy", filled, None, {"tdMode":"isolated","posSide":posSide,"takeProfit":{"triggerPrice":t["tp"],"orderPrice":"-1"}})
                except: pass
                time.sleep(1)
                if verify_sl(swap): sl_ok=True; break
            except: time.sleep(1)
        if not sl_ok: emergency_close(swap, signal["direction"], filled, "SL_FAILED"); return
        state["open_trades"][swap]={"entry":avg,"direction":signal["direction"],"margin":margin,"amount":filled,"time":datetime.now(timezone.utc).isoformat()}
        save_state()
        save_trade_log({"time":datetime.now(timezone.utc).isoformat(),"type":"ENTRY","symbol":swap,"direction":signal["direction"],"entry":avg,"margin":margin,"amount":filled,"score":signal["score"],"mode":cfg["MODE"]})
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
                for t in reversed(trades[-5:]):
                    info=t.get("info",{})
                    if info.get("realizedPnl") or info.get("pnl"):
                        pnl=float(info.get("realizedPnl") or info.get("pnl") or 0)
                        if pnl!=0: break
                if pnl!=0:
                    state["daily_pnl"]=round(state["daily_pnl"]+pnl,4)
                    if pnl<0: state["consecutive_losses"]+=1
                    else: state["consecutive_losses"]=0
                    save_trade_log({"time":datetime.now(timezone.utc).isoformat(),"type":"EXIT","symbol":sym,"pnl":pnl,"daily_pnl":state["daily_pnl"]})
                del state["open_trades"][sym]; save_state()
            except: del state["open_trades"][sym]
        if state["daily_pnl"] <= -CONFIG["DAILY_LOSS_LIMIT"]:
            state["stopped_by_loss"]=True; state["stopped_reason"]=f"DAILY LOSS {state['daily_pnl']}$"
        if state["consecutive_losses"] >= CONFIG["MAX_CONSECUTIVE_LOSSES"]:
            state["stopped_by_loss"]=True; state["stopped_reason"]=f"{state['consecutive_losses']} LOSSES IN ROW"
    except: pass
def auto_spot_manager():
    try:
        bal=exchange.fetch_balance(); sold_now=[]
        if CONFIG["SPOT_AUTO_SELL_WEAK"]:
            for coin in CONFIG["SPOT_WEAK_COINS"]:
                amt=float(bal.get("total",{}).get(coin,0) or 0)
                if amt>0 and coin not in state["spot_sold"]:
                    try:
                        symbol=f"{coin}/USDT"; ticker=exchange.fetch_ticker(symbol); value=amt*float(ticker["last"])
                        if value>=0.3:
                            exchange.options["defaultType"]="spot"; exchange.create_market_sell_order(symbol, amt); exchange.options["defaultType"]="swap"
                            state["spot_sold"].append(coin)
                            save_trade_log({"time":datetime.now(timezone.utc).isoformat(),"type":"SPOT_AUTO_SELL_WEAK","symbol":symbol,"amount":amt,"value":value})
                            sold_now.append(f"{coin} {value:.2f}$"); save_state(); time.sleep(1)
                    except: exchange.options["defaultType"]="swap"
        for coin in CONFIG["SPOT_STRONG_COINS"]:
            amt=float(bal.get("total",{}).get(coin,0) or 0)
            if amt>0:
                try:
                    symbol=f"{coin}/USDT"; df=fetch_df(symbol, "1h")
                    if df is None: continue
                    curr=df.iloc[-1]; rsi=float(curr["rsi"])
                    if rsi>=CONFIG["SPOT_SELL_RSI_TOP"]: action="SELL 100%"; pct=100
                    elif rsi>=CONFIG["SPOT_SELL_RSI_PEAK"]:
                        if f"{coin}_50" not in state["spot_sold"]: action="SELL 50%"; pct=50
                        else: action=None
                    else: action=None
                    if action:
                        exchange.options["defaultType"]="spot"; sell_amt=amt*pct/100; exchange.create_market_sell_order(symbol, sell_amt); exchange.options["defaultType"]="swap"
                        if pct==50: state["spot_sold"].append(f"{coin}_50")
                        else: state["spot_sold"].append(coin)
                        save_trade_log({"time":datetime.now(timezone.utc).isoformat(),"type":"SPOT_PEAK_SELL","symbol":symbol,"rsi":rsi,"pct":pct})
                        sold_now.append(f"{coin} {action} RSI:{rsi:.0f}"); save_state()
                except: exchange.options["defaultType"]="swap"
        return sold_now
    except: exchange.options["defaultType"]="swap"; return []
def scan_and_trade():
    try: exchange.load_markets()
    except: pass
    check_closed_and_update_pnl()
    if state["loop"]%5==0: auto_spot_manager()
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
        base=s.split("/")[0]; swap=base+"/USDT:USDT"
        if any(base in sym for sym in open_syms): continue
        sig=analyze(s, btc_trend); scanned+=1
        if sig: signals.append(sig)
        time.sleep(0.2)
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
<title>V100001 AUTO</title><script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700;800&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
<style>body{font-family:'Tajawal',sans-serif;background:#0a0e14;color:#e5e7eb}.card{background:#111827;border:1px solid #1f2937}.mono{font-family:'JetBrains Mono',monospace}</style>
</head><body class="p-3 md:p-6"><div class="max-w-7xl mx-auto">
<div class="flex justify-between items-center mb-4">
<div><h1 class="text-2xl font-extrabold">V100001 <span class="text-green-400">AUTO</span></h1><p id="autoModeTop" class="text-xs font-bold text-yellow-400">جاري التحميل...</p></div>
<div class="flex gap-2"><button onclick="showTab('dash')" id="btn-dash" class="bg-blue-600 px-3 py-1 rounded text-xs">الرئيسية</button><button onclick="showTab('editor')" id="btn-editor" class="bg-gray-800 px-3 py-1 rounded text-xs">⚙️ محرر</button><span id="status-dot" class="w-3 h-3 bg-green-500 rounded-full animate-pulse mt-2"></span></div>
</div>
<div id="tab-dash">
<div class="card rounded-xl p-3 mb-4 bg-gradient-to-r from-blue-900/30 to-purple-900/30 border-blue-800">
<div class="flex justify-between items-center"><div><p class="text-[11px] text-gray-400">الوضع الأوتوماتيكي</p><p id="autoMode" class="font-bold">--</p><p id="autoDetail" class="text-[11px] text-gray-400">--</p></div><div class="text-left"><p class="text-[11px] text-gray-400">إجمالي الثروة</p><p id="totalEq" class="text-xl font-bold">--</p><p id="nextTarget" class="text-[11px] text-yellow-400">--</p></div></div>
<div class="w-full bg-gray-800 rounded-full h-2 mt-3"><div id="progressBar" class="bg-green-500 h-2 rounded-full" style="width:0%"></div></div>
</div>
<div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">الرصيد الحر</p><p id="balance" class="text-lg font-bold">--</p></div>
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">ربح اليوم</p><p id="daily" class="text-lg font-bold">--</p></div>
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">صفقات</p><p id="open" class="text-lg font-bold">-- / 2</p></div>
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">BTC</p><p id="btc" class="text-xs font-bold">--</p></div>
<div class="card rounded-xl p-3"><p class="text-[11px] text-gray-400">خسائر</p><p id="consec" class="text-lg font-bold">--</p></div>
</div>
<div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
<div class="lg:col-span-2 space-y-4">
<div class="card rounded-xl p-4"><div class="flex justify-between mb-2"><h3 class="font-bold text-sm">📊 صفقات الفيوتشر</h3><span class="text-[10px] bg-blue-900 px-2 py-1 rounded">SL محمي</span></div><div id="positions" class="space-y-2 text-xs"></div></div>
<div class="card rounded-xl p-4"><h3 class="font-bold text-sm mb-2">🎯 إشارات GOD</h3><div id="signals" class="space-y-2 text-xs"></div></div>
<div class="card rounded-xl p-4"><h3 class="font-bold text-sm mb-2">📜 سجل</h3><div id="trades" class="space-y-1 text-[11px] max-h-40 overflow-y-auto mono"></div></div>
</div>
<div class="space-y-4">
<div class="card rounded-xl p-4 border-yellow-900"><h3 class="font-bold text-sm mb-2">💰 السبوت القديم</h3><div id="spot" class="space-y-2 text-xs"></div><button onclick="forceSell()" class="bg-yellow-600 hover:bg-yellow-700 text-white text-[11px] px-3 py-2 rounded w-full mt-2">بيع الضعاف الآن</button></div>
<div class="card rounded-xl p-4"><h3 class="font-bold text-xs mb-2">⚙️ تحكم</h3><div class="grid grid-cols-2 gap-2"><button onclick="resetDaily()" class="bg-gray-800 text-[11px] px-2 py-2 rounded">إعادة ضبط يومي</button><button onclick="load()" class="bg-blue-900 text-[11px] px-2 py-2 rounded">تحديث</button></div><div id="stopped" class="hidden mt-2 bg-red-900/30 border border-red-700 p-2 rounded text-[11px]"></div></div>
<div class="card rounded-xl p-4"><p class="text-[11px] text-gray-400">فحص: <span id="scanned">--</span> | لفة: <span id="loop">--</span> | آخر: <span id="last">--</span></p><p class="text-[10px] text-gray-500 mt-1">باع: <span id="spotsold">--</span></p><div id="errors" class="mt-1 text-[10px] text-red-400"></div></div>
</div>
</div>
</div>
<div id="tab-editor" class="hidden">
<div class="card rounded-xl p-4 mb-4">
<h3 class="font-bold mb-3">🔧 محرر الإعدادات + AUTO-SCALE</h3>
<div class="bg-blue-900/20 border border-blue-700 p-3 rounded mb-3 text-[11px]"><p>🤖 الأوتوماتيك شغال: البوت يغير المخاطرة لحاله حسب رصيدك. تقدر تعدل الحدود هنا.</p></div>
<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
<div><label class="text-xs text-gray-400">RSI قمة أولى (بيع 50%)</label><input id="cfg_RSI70" type="number" class="w-full bg-[#0a0e14] border border-gray-700 rounded p-2 text-xs mt-1"></div>
<div><label class="text-xs text-gray-400">RSI قمة نهائية (بيع 100%)</label><input id="cfg_RSI75" type="number" class="w-full bg-[#0a0e14] border border-gray-700 rounded p-2 text-xs mt-1"></div>
<div><label class="text-xs text-gray-400">حد الخسارة اليومي $</label><input id="cfg_DAILYLOSS" type="number" class="w-full bg-[#0a0e14] border border-gray-700 rounded p-2 text-xs mt-1"></div>
<div><label class="text-xs text-gray-400">Stop Loss %</label><input id="cfg_SL" type="number" step="0.001" class="w-full bg-[#0a0e14] border border-gray-700 rounded p-2 text-xs mt-1"></div>
</div>
<div class="mt-4"><label class="text-xs text-gray-400">العملات الضعيفة (تنباع تلقائياً)</label><input id="cfg_WEAK" type="text" class="w-full bg-[#0a0e14] border border-gray-700 rounded p-2 text-xs mt-1 mono"></div>
<div class="mt-2"><label class="text-xs text-gray-400">العملات القوية (تنباع في القمة)</label><input id="cfg_STRONG" type="text" class="w-full bg-[#0a0e14] border border-gray-700 rounded p-2 text-xs mt-1 mono"></div>
<div class="flex gap-2 mt-4"><button onclick="saveCfg()" class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded text-xs font-bold">💾 حفظ</button><button onclick="loadCfg()" class="bg-gray-800 px-4 py-2 rounded text-xs">↩️ إلغاء</button></div>
<div id="cfgMsg" class="mt-2 text-xs"></div>
</div>
</div>
</div>
<script>
function showTab(t){
 document.getElementById('tab-dash').classList.toggle('hidden', t!=='dash');
 document.getElementById('tab-editor').classList.toggle('hidden', t!=='editor');
 document.getElementById('btn-dash').className = t==='dash' ? 'bg-blue-600 px-3 py-1 rounded text-xs' : 'bg-gray-800 px-3 py-1 rounded text-xs';
 document.getElementById('btn-editor').className = t==='editor' ? 'bg-blue-600 px-3 py-1 rounded text-xs' : 'bg-gray-800 px-3 py-1 rounded text-xs';
 if(t==='editor') loadCfg();
}
async function load(){
 try{
  const res = await fetch('/api/status'); const d = await res.json();
  document.getElementById('balance').textContent = d.balance + ' USDT';
  document.getElementById('daily').textContent = (d.daily_pnl>=0?'+':'') + d.daily_pnl + ' $';
  document.getElementById('daily').className = 'text-lg font-bold ' + (d.daily_pnl>=0?'text-green-400':'text-red-400');
  document.getElementById('open').textContent = d.open_count + ' / ' + d.max_positions;
  document.getElementById('btc').textContent = d.btc_trend + ' | ' + d.btc_vol;
  document.getElementById('consec').textContent = d.consecutive_losses + ' / 3';
  document.getElementById('scanned').textContent = d.scanned;
  document.getElementById('loop').textContent = d.loop;
  document.getElementById('last').textContent = d.last_scan ? new Date(d.last_scan).toLocaleTimeString('ar-SA') : '--';
  document.getElementById('spotsold').textContent = (d.spot_sold||[]).join(', ') || 'لم يبع';
  document.getElementById('autoMode').textContent = d.auto_mode;
  document.getElementById('autoModeTop').textContent = d.auto_mode;
  document.getElementById('autoDetail').textContent = 'مخاطرة ' + (d.auto_risk*100).toFixed(1) + '% | رافعة ' + d.auto_lev + 'x | TP ' + (d.auto_tp*100).toFixed(1) + '% | ' + d.max_positions + ' صفقات';
  document.getElementById('totalEq').textContent = d.total_equity.toFixed(2) + ' $';
  if(d.next_to_target>0){
   document.getElementById('nextTarget').textContent = 'باقي ' + d.next_to_target.toFixed(2) + '$ للترقية لـ ' + d.next_mode;
   const pct = Math.min(100, (d.total_equity / (d.total_equity + d.next_to_target))*100);
   document.getElementById('progressBar').style.width = pct + '%';
  } else {
   document.getElementById('nextTarget').textContent = '🎉 وصلت أعلى مستوى - JohnBread49 مصغر';
   document.getElementById('progressBar').style.width = '100%';
  }
  const stoppedDiv = document.getElementById('stopped');
  if(d.stopped){ stoppedDiv.classList.remove('hidden'); stoppedDiv.textContent = '⛔ متوقف: ' + d.stopped_reason; document.getElementById('status-dot').className='w-3 h-3 bg-red-500 rounded-full mt-2'; } else { stoppedDiv.classList.add('hidden'); document.getElementById('status-dot').className='w-3 h-3 bg-green-500 rounded-full animate-pulse mt-2'; }
  const posDiv = document.getElementById('positions');
  if(d.positions && d.positions.length>0){ posDiv.innerHTML = d.positions.map(p=>{ const pnlClass = p.pnl>=0?'text-green-400':'text-red-400'; return `<div class="bg-[#0a0e14] border border-gray-800 rounded p-2 flex justify-between"><div><p class="font-bold">${p.symbol} <span class="text-[10px] ${p.side=='long'?'text-green-400':'text-red-400'}">${p.side}</span></p><p class="text-[10px] text-gray-400">دخول: ${p.entry}</p></div><div class="text-left"><p class="font-bold ${pnlClass}">${p.pnl} $</p><p class="text-[9px] text-green-500">✓ SL</p></div></div>`; }).join(''); } else { posDiv.innerHTML = '<p class="text-gray-500">لا صفقات - ينتظر GOD 7/10</p>'; }
  const sigDiv = document.getElementById('signals');
  if(d.signals && d.signals.length>0){ sigDiv.innerHTML = d.signals.map(s=>`<div class="flex justify-between bg-[#0a0e14] rounded p-2"><span>${s.symbol} ${s.direction} RSI:${s.rsi}</span><span class="bg-blue-900 px-2 rounded">${s.score}/10</span></div>`).join(''); } else { sigDiv.innerHTML = '<p class="text-gray-500">لا إشارات قوية</p>'; }
  document.getElementById('errors').textContent = (d.errors||[]).join(' | ');
  const spotRes = await fetch('/api/spot'); const spotData = await spotRes.json();
  const spotDiv = document.getElementById('spot');
  if(spotData.holdings){ spotDiv.innerHTML = spotData.holdings.map(h=>{ const adviceClass = h.advice.includes('بيع')?'text-yellow-400':'text-green-400'; return `<div class="bg-[#0a0e14] border border-gray-800 rounded p-2"><div class="flex justify-between"><span class="font-bold">${h.coin}</span><span>${h.value_usdt}$</span></div><p class="text-[11px] text-gray-400">${h.trend} RSI:${h.rsi||'--'}</p><p class="text-[11px] ${adviceClass}">${h.advice}</p></div>`; }).join('') + `<p class="text-[11px] text-gray-500 mt-2">الإجمالي: ${spotData.total_spot_value}$</p>`; }
  const tradesRes = await fetch('/trades'); const tradesData = await tradesRes.json();
  document.getElementById('trades').innerHTML = tradesData.slice(-10).reverse().map(t=>{ const color = t.type.includes('ENTRY')?'text-blue-400': t.pnl>0?'text-green-400':'text-red-400'; return `<p class="${color}">${new Date(t.time).toLocaleTimeString('ar-SA')} - ${t.type} ${t.symbol||''} ${t.pnl!=undefined?'PnL:'+t.pnl:''}</p>`; }).join('') || '<p class="text-gray-500">لا سجل</p>';
 }catch(e){}
}
async function forceSell(){ if(!confirm('بيع الضعاف؟')) return; const r=await fetch('/spot/force_sell_weak'); const d=await r.json(); alert('تم: '+(d.sold_now||[]).join(', ')); load(); }
async function resetDaily(){ if(!confirm('إعادة ضبط؟')) return; await fetch('/reset_daily'); load(); }
async function loadCfg(){
 const r = await fetch('/api/config'); const c = await r.json();
 document.getElementById('cfg_RSI70').value = c.SPOT_SELL_RSI_PEAK;
 document.getElementById('cfg_RSI75').value = c.SPOT_SELL_RSI_TOP;
 document.getElementById('cfg_DAILYLOSS').value = c.DAILY_LOSS_LIMIT;
 document.getElementById('cfg_SL').value = c.STOP_LOSS;
 document.getElementById('cfg_WEAK').value = (c.SPOT_WEAK_COINS||[]).join(',');
 document.getElementById('cfg_STRONG').value = (c.SPOT_STRONG_COINS||[]).join(',');
}
async function saveCfg(){
 const newCfg = {
  SPOT_SELL_RSI_PEAK: parseFloat(document.getElementById('cfg_RSI70').value),
  SPOT_SELL_RSI_TOP: parseFloat(document.getElementById('cfg_RSI75').value),
  DAILY_LOSS_LIMIT: parseFloat(document.getElementById('cfg_DAILYLOSS').value),
  STOP_LOSS: parseFloat(document.getElementById('cfg_SL').value),
  SPOT_WEAK_COINS: document.getElementById('cfg_WEAK').value.split(',').map(s=>s.trim().toUpperCase()).filter(s=>s),
  SPOT_STRONG_COINS: document.getElementById('cfg_STRONG').value.split(',').map(s=>s.trim().toUpperCase()).filter(s=>s),
 };
 const r = await fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(newCfg)});
 const d = await r.json();
 document.getElementById('cfgMsg').textContent = d.ok ? '✅ تم الحفظ' : '❌ خطأ: '+d.error;
 document.getElementById('cfgMsg').className = 'mt-2 text-xs ' + (d.ok ? 'text-green-400' : 'text-red-400');
}
load(); setInterval(load, 10000);
</script></body></html>
"""

@app.route("/")
def dashboard(): return DASHBOARD_HTML, 200, {'Content-Type':'text/html; charset=utf-8'}

@app.route("/api/status")
def api_status():
    total,cnt,pos,syms=get_positions()
    auto=get_auto_config()
    next_mode="🚀 نمو" if auto["TOTAL"]<50 else "🔥 مصغر JohnBread" if auto["TOTAL"]<100 else "MAX"
    return jsonify({
        "bot":"V100001 AUTO",
        "balance":round(get_free_usdt(),4),
        "total_equity":round(auto["TOTAL"],2),
        "auto_mode":auto["MODE"],
        "auto_risk":auto["RISK"],
        "auto_lev":auto["LEV"],
        "auto_tp":auto["TP"],
        "next_to_target":round(auto["NEXT"],2),
        "next_mode":next_mode,
        "btc_trend":state["btc_trend"],
        "btc_vol":f"{state['btc_vol']}%",
        "open_count":cnt,
        "max_positions":auto["MAX"],
        "open_symbols":syms,
        "total_margin":round(total,2),
        "daily_pnl":state["daily_pnl"],
        "daily_limit":-CONFIG["DAILY_LOSS_LIMIT"],
        "consecutive_losses":state["consecutive_losses"],
        "stopped":state["stopped_by_loss"],
        "stopped_reason":state["stopped_reason"],
        "scanned":state["scanned"],
        "loop":state["loop"],
        "last_scan":state["last_scan"],
        "signals":state["signals"],
        "positions":[{"symbol":p["symbol"],"side":p.get("side"),"entry":p.get("entryPrice"),"pnl":round(float(p.get("unrealizedPnl") or 0),4)} for p in pos if float(p.get("contracts") or 0)>0],
        "spot_sold":state["spot_sold"],
        "errors":state["errors"][-3:],
    })

@app.route("/api/spot")
def api_spot():
    try:
        bal=exchange.fetch_balance(); holdings=[]
        for coin, data in bal.get("total",{}).items():
            if coin=="USDT": continue
            total_amt=float(data or 0)
            if total_amt>0:
                try:
                    symbol=f"{coin}/USDT"; ticker=exchange.fetch_ticker(symbol); price=float(ticker["last"]); df=fetch_df(symbol, "1h")
                    if df is None: trend="غير معروف"; advice="انتظر"; rsi_val=None
                    else:
                        curr=df.iloc[-1]; rsi_val=round(float(curr["rsi"]),1)
                        if curr["close"]<curr["ema50"] and curr["rsi"]<40: trend="هابط قرب قاع"; advice="لا تبيع الآن"
                        elif curr["close"]>curr["ema50"] and curr["rsi"]>70: trend="قمة محتملة"; advice="بيع 50% الآن - قمة"
                        elif curr["close"]>curr["ema200"] and curr["rsi"]<65: trend="صاعد قوي"; advice="انتظر - لا تبيع"
                        else: trend="عرضي"; advice="انتظر"
                    value=total_amt*price
                    if value>=0.3: holdings.append({"coin":coin,"amount":total_amt,"price":price,"value_usdt":round(value,2),"trend":trend,"advice":advice,"rsi":rsi_val})
                except: pass
        holdings.sort(key=lambda x:x["value_usdt"], reverse=True)
        total_value=sum([h["value_usdt"] for h in holdings])
        return jsonify({"total_spot_value":round(total_value,2),"holdings":holdings})
    except Exception as e: return jsonify({"error":str(e)})

@app.route("/api/config", methods=["GET","POST"])
def api_config():
    if request.method=="GET": return jsonify(CONFIG)
    else:
        try:
            data=request.get_json(); allowed=["DAILY_LOSS_LIMIT","SPOT_SELL_RSI_PEAK","SPOT_SELL_RSI_TOP","STOP_LOSS","SPOT_WEAK_COINS","SPOT_STRONG_COINS"]
            new_cfg={}
            for k in allowed:
                if k in data: new_cfg[k]=data[k]
            ok=save_config(new_cfg)
            return jsonify({"ok":ok,"saved":new_cfg})
        except Exception as e: return jsonify({"ok":False,"error":str(e)})

@app.route("/ping")
def ping(): return jsonify({"pong":True,"loop":state["loop"]})
@app.route("/trades")
def trades(): return jsonify(load_trades()[-50:])
@app.route("/reset_daily")
def reset_daily():
    state["daily_pnl"]=0.0; state["consecutive_losses"]=0; state["stopped_by_loss"]=False; state["stopped_reason"]=""; state["daily_date"]=str(date.today()); save_state()
    return jsonify({"reset":True})
@app.route("/spot/force_sell_weak")
def force_sell_weak():
    sold=auto_spot_manager()
    return jsonify({"sold_now":sold,"all_sold":state["spot_sold"]})
@app.route("/health")
def health(): return jsonify({"status":"online"})

if __name__=="__main__":
    import threading; threading.Thread(target=run_bot,daemon=True).start()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","5000")),debug=False,use_reloader=False)
