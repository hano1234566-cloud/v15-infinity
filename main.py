# V100 TRAILING 100X - كل ما ارتفعت العملة يرفع الربح معها حتى 100X
import os, json, time, requests
from datetime import datetime

SOUL_FILE = "soul.json"
VERSION = "V100 TRAILING 100X"

def load_soul():
    try:
        if os.path.exists(SOUL_FILE):
            with open(SOUL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return {
        "version": VERSION,
        "active_trade": None, # الصفقة الشغالة
        "blacklist": [],
        "trades": []
    }

def save_soul(s):
    with open(SOUL_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

def get_price(coin="WIF-USDT"):
    try:
        url = f"https://www.okx.com/api/v5/market/ticker?instId={coin}"
        r = requests.get(url, timeout=10).json()
        return float(r["data"][0]["last"])
    except:
        return None

soul = load_soul()
print(f"=== {VERSION} - نظام 100X بدأ ===")

while True:
    try:
        now = datetime.now()

        # اذا ما في صفقة - افحص السوق وادخل افضل عملة
        if not soul.get("active_trade"):
            print(f"[{now}] يفحص افضل عملة للدخول...")
            # مثال يدخل WIF - انت تقدر تغيره لاي عملة يكتشفها
            price = get_price("WIF-USDT")
            soul["active_trade"] = {
                "coin": "WIF-USDT",
                "entry": price,
                "highest": price,
                "stop_loss": price * 0.95, # خسارة 5% فقط بالبداية
                "take_profit": price * 100 # هدف 100X
            }
            print(f"دخل {soul['active_trade']['coin']} بسعر {price} - هدف 100X")
            save_soul(soul)

        else:
            # في صفقة شغالة - نظام رفع الستوب
            trade = soul["active_trade"]
            curr = get_price(trade["coin"])
            if not curr:
                time.sleep(10)
                continue

            # حدث اعلى سعر وصلته
            if curr > trade["highest"]:
                trade["highest"] = curr
            
            profit_pct = ((curr - trade["entry"]) / trade["entry"]) * 100
            highest_profit = ((trade["highest"] - trade["entry"]) / trade["entry"]) * 100

            # نظام رفع الربح التلقائي
            if highest_profit >= 5 and trade["stop_loss"] < trade["entry"]:
                trade["stop_loss"] = trade["entry"] # وصل +5% -> يرفع الستوب لنقطة الدخول (ما عاد يخسر)
                print(f"✅ ارتفع 5% -> رفع الستوب لنقطة الدخول - صار بدون خسارة")

            if highest_profit >= 10:
                trade["stop_loss"] = trade["entry"] * 1.05 # وصل +10% -> يضمن +5% ربح
                print(f"🔥 ارتفع 10% -> ضمن ربح +5%")

            if highest_profit >= 20:
                trade["stop_loss"] = trade["entry"] * 1.15 # وصل +20% -> يضمن +15%
                print(f"🔥🔥 ارتفع 20% -> ضمن ربح +15%")

            if highest_profit >= 50:
                trade["stop_loss"] = trade["entry"] * 1.40 # وصل +50% -> يضمن +40%
                print(f"🚀 ارتفع 50% -> ضمن ربح +40% - مستمر لـ 100X")

            print(f"[{now}] {trade['coin']} | دخول: {trade['entry']:.4f} | الآن: {curr:.4f} | ربح: {profit_pct:.2f}% | اعلى ربح: {highest_profit:.2f}% | ستوب: {trade['stop_loss']:.4f} | هدف: 100X")

            # اذا نزل للستوب -> يبيع ويضمن الربح
            if curr <= trade["stop_loss"]:
                print(f"❌ ضرب الستوب - بيع {trade['coin']} بربح {profit_pct:.2f}%")
                soul["trades"].append({"coin": trade["coin"], "profit": profit_pct, "time": str(now)})
                soul["active_trade"] = None

            save_soul(soul)

        time.sleep(30) # يفحص كل 30 ثانية

    except Exception as e:
        print(f"خطأ - يصلح نفسه: {e}")
        time.sleep(10)
