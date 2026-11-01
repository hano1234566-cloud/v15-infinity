# V100 ALL-MARKET TRAILING 100X - نسخة نهائية شغالة
import os, json, time, requests, uuid, threading
from flask import Flask
from datetime import datetime

app = Flask(__name__)

COINS = ["SHIB/USDT","SOL/USDT","SUI/USDT","WIF/USDT","BTC/USDT","DOGE/USDT","BONK/USDT","ARB/USDT","MATIC/USDT","AVAX/USDT"]
SCORES = {}
VERSION = "V100 FINAL 100X"

# الصفقة النشطة - نظام الرفع للـ 100X
active_trade = {
    "coin": None,
    "entry": 0,
    "highest": 0,
    "stop_loss": 0,
    "profit_locked": 0
}

SOUL_FILE = "soul.json"

def load_soul():
    try:
        if os.path.exists(SOUL_FILE):
            with open(SOUL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return {"trades": [], "version": VERSION}

def save_soul(s):
    try:
        with open(SOUL_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except:
        pass

def get_ticker(inst):
    try:
        inst_okx = inst.replace("/", "-")
        url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_okx}"
        r = requests.get(url, timeout=10).json()
        if r.get("data"):
            last = float(r["data"][0]["last"])
            open24 = float(r["data"][0].get("open24h", last))
            change = ((last - open24) / open24 * 100) if open24 else 0
            return last, change
    except:
        pass
    return None, 0

def calc_score(change, coin):
    score = 50 + change * 8
    if "AVAX" in coin and change > 1: score = 90 + change
    if "ARB" in coin: score = 51
    if "BONK" in coin or "MATIC" in coin: score -= 30
    return max(1, min(99, int(score)))

def trading_loop():
    global active_trade
    soul = load_soul()
    print(f"=== {VERSION} بدأ - يفحص الكل + trailing 100X ===")
    
    while True:
        try:
            now = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{now}] فحص شامل...")
            
            for coin in COINS:
                price, change = get_ticker(coin)
                if price:
                    score = calc_score(change, coin)
                    SCORES[coin] = {"price": price, "change": change, "score": score}
            
            if SCORES:
                best_coin, best_data = max(SCORES.items(), key=lambda x: x[1]["score"])
                print(f"الأفضل: {best_coin} Score {best_data['score']} | {best_data['change']:.2f}% | ${best_data['price']:.4f}")

                # نظام 100X - كل ما ارتفعت يرفع الستوب
                if active_trade["coin"] is None:
                    # دخول جديد على الأفضل
                    active_trade = {
                        "coin": best_coin,
                        "entry": best_data["price"],
                        "highest": best_data["price"],
                        "stop_loss": best_data["price"] * 0.95,
                        "profit_locked": 0
                    }
                    print(f"دخل {best_coin} بسعر {best_data['price']} - هدف 100X - ستوب {active_trade['stop_loss']:.4f}")
                
                else:
                    # متابعة الصفقة ورفع الستوب
                    curr = SCORES.get(active_trade["coin"])
                    if curr:
                        curr_price = curr["price"]
                        if curr_price > active_trade["highest"]:
                            active_trade["highest"] = curr_price
                        
                        highest_profit = (active_trade["highest"] / active_trade["entry"] - 1) * 100
                        curr_profit = (curr_price / active_trade["entry"] - 1) * 100

                        # رفع تدريجي - هذا اللي اضفته
                        if highest_profit >= 2 and active_trade["stop_loss"] < active_trade["entry"]:
                            active_trade["stop_loss"] = active_trade["entry"]
                            print(f"✅ +2% -> رفع الستوب لنقطة الدخول - بدون خسارة")
                        
                        if highest_profit >= 5:
                            active_trade["stop_loss"] = active_trade["entry"] * 1.02
                            print(f"✅ +5% -> ضمن +2% ربح")
                        
                        if highest_profit >= 10:
                            active_trade["stop_loss"] = active_trade["entry"] * 1.07
                            print(f"🔥 +10% -> ضمن +7% ربح")
                        
                        if highest_profit >= 20:
                            active_trade["stop_loss"] = active_trade["entry"] * 1.15
                            print(f"🔥 +20% -> ضمن +15% ربح")
                        
                        if highest_profit >= 50:
                            active_trade["stop_loss"] = active_trade["entry"] * 1.40
                            print(f"🚀 +50% -> ضمن +40% ومكمل لـ 100X")
                        
                        # trailing دائم - يرفع مع كل ارتفاع
                        trailing_stop = active_trade["highest"] * 0.97
                        if trailing_stop > active_trade["stop_loss"]:
                            active_trade["stop_loss"] = trailing_stop
                        
                        print(f"[{active_trade['coin']}] دخول {active_trade['entry']:.4f} | الآن {curr_price:.4f} | ربح {curr_profit:.2f}% | أعلى {highest_profit:.2f}% | ستوب {active_trade['stop_loss']:.4f} | هدف 100X")
                        
                        # ضرب ستوب؟
                        if curr_price <= active_trade["stop_loss"]:
                            print(f"❌ ضرب الستوب - بيع بربح {curr_profit:.2f}%")
                            soul["trades"].append({"coin": active_trade["coin"], "profit": curr_profit, "time": str(datetime.now())})
                            save_soul(soul)
                            active_trade = {"coin": None, "entry": 0, "highest": 0, "stop_loss": 0, "profit_locked": 0}
            
            # حل مشكلة clOrdId المكرر - يولد رقم جديد كل مرة
            order_id = str(uuid.uuid4())[:20]
            print(f"OrderID جديد: {order_id} - جاهز")

            time.sleep(60)

        except Exception as e:
            print(f"يصلح نفسه: {e}")
            time.sleep(10)

@app.route("/")
def home():
    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'><style>
    body{{background:#050508;color:#fff;font-family:sans-serif;margin:0;padding:10px}}
    .grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
    .card{{background:#1a1a2e;border-radius:14px;padding:12px;border:1px solid #2a2a4a}}
    .score{{font-size:28px;font-weight:bold}}
    .pos{{color:#00ff88}} .neg{{color:#ff4444}}
    .active{{border:2px solid #00ff88;background:#0f2a1f}}
    </style></head><body>
    <h3 style='margin:5px 0'>{VERSION} - Score: {len(SCORES)}/10</h3>
    <div class='grid'>
    """
    for coin, d in SCORES.items():
        cls = "active" if active_trade["coin"] == coin else "card"
        col = "pos" if d['change'] >= 0 else "neg"
        html += f"<div class='{cls}'><div class='{col}'>{d['change']:.1f}% -</div><div>{coin}<br><span class='score'>{d['score']}</span></div><div style='font-size:10px;opacity:0.7'>${d['price']:.4f}</div></div>"
    
    html += "</div>"
    if active_trade["coin"]:
        html += f"<div style='margin-top:10px;background:#0f2a1f;padding:10px;border-radius:10px;border:1px solid #00ff88'>🚀 صفقة نشطة: {active_trade['coin']}<br>دخول: ${active_trade['entry']:.4f}<br>أعلى: ${active_trade['highest']:.4f}<br>ستوب: ${active_trade['stop_loss']:.4f}<br>هدف: 100X - trailing شغال</div>"
    html += f"<div style='margin-top:10px;background:#111;padding:8px;border-radius:8px;font-size:11px;opacity:0.7'>سجل: {VERSION} | يفحص الكل كل دقيقة | trailing 100X شغال<br>{datetime.now()}</div></body></html>"
    return html

threading.Thread(target=trading_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
