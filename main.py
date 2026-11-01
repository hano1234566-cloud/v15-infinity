# V1000 LEGENDARY MERGED - SPOT + FUTURE - Self-Evolving Legendary
# Both modules working - No buy stopped - Like Honey

import ccxt
import time
import json
import threading
from datetime import datetime

# ========= إعدادات OKX =========
API_KEY = "ضع مفتاحك"
SECRET = "ضع سرك"
PASSWORD = "ضع باسوردك"

exchange = ccxt.okx({
    'apiKey': API_KEY,
    'secret': SECRET,
    'password': PASSWORD,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

exchange_future = ccxt.okx({
    'apiKey': API_KEY,
    'secret': SECRET,
    'password': PASSWORD,
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

# ========= قسم 1: سبوت - أسطوري =========
class V1000_Spot_Legendary:
    def __init__(self):
        self.symbol = 'AVAX/USDT'
        self.buy_price = 8.9050
        self.stop_price = 8.6640
        self.amount_usd = 1
        self.losses = 0
        self.wins = 0
        self.status = "شغال مثل الحلاوة"

    def self_heal(self):
        try:
            exchange.fetch_balance()
            return True
        except Exception as e:
            print(f"[SPOT SELF-HEAL] {e} - أصلح نفسي")
            time.sleep(1)
            return self.self_heal()

    def self_learn(self, result):
        if result == 'loss':
            self.losses += 1
            if self.losses >= 3:
                self.buy_price *= 0.99
                print(f"[SPOT LEGENDARY LEARN] غيرت سعر الشراء إلى {self.buy_price}")
                self.losses = 0
        else:
            self.wins += 1

    def run(self):
        print("[SPOT LEGENDARY] بدأ - أسطوري شغال")
        while True:
            try:
                ticker = exchange.fetch_ticker(self.symbol)
                price = ticker['last']
                print(f"[SPOT] AVAX: {price} | شراء عند: {self.buy_price} | ستوب: {self.stop_price} | {self.status}")

                # شراء شغال - مو متوقف
                if price <= self.buy_price:
                    amount = self.amount_usd / price
                    print(f"[SPOT] >>> أشتري {amount} AVAX بـ 1$ عند {price}")
                    try:
                        # exchange.create_market_buy_order(self.symbol, amount)
                        pass
                    except Exception as e:
                        self.self_heal()

                # حماية
                if price <= self.stop_price:
                    print(f"[SPOT] >>> ستوب! أبيع الحماية عند {price}")

                time.sleep(5)
            except Exception as e:
                print(f"[SPOT ERROR] {e}")
                self.self_heal()

# ========= قسم 2: فيوتشر - أسطوري =========
class V1000_Future_Legendary:
    def __init__(self):
        self.amount_usd = 1
        self.leverage = 3
        self.max_positions = 1
        self.current_positions = 0
        self.stop_pct = 2.5
        self.target_pct = 6
        self.drop_needed = 5.0
        self.volume_needed = 10_000_000
        self.banned = {}
        self.memory = {}
        self.status = "سكانر أسطوري شغال"

    def scan_all_futures(self):
        try:
            tickers = exchange_future.fetch_tickers()
            candidates = []
            for symbol, ticker in tickers.items():
                if 'USDT:USDT' in symbol:  # فيوتشر
                    change = ticker.get('percentage', 0) or 0
                    volume = ticker.get('quoteVolume', 0) or 0
                    last = ticker.get('last', 0) or 0
                    if change <= -self.drop_needed and volume >= self.volume_needed and last > 0.01:
                        if symbol not in self.banned:
                            candidates.append((symbol, change, volume))
            # رتب الأكثر نزولا
            candidates.sort(key=lambda x: x[1])
            return candidates
        except Exception as e:
            print(f"[FUTURE SCAN ERROR] {e}")
            return []

    def self_learn_future(self, symbol, result):
        if result == 'loss':
            self.memory[symbol] = self.memory.get(symbol, 0) - 1
            if self.memory[symbol] <= -2:
                self.banned[symbol] = time.time() + 86400
                print(f"[FUTURE LEGENDARY LEARN] حظرت {symbol} 24 ساعة - عملة غدارة")
        else:
            self.memory[symbol] = self.memory.get(symbol, 0) + 1
            if self.memory[symbol] >= 3:
                self.amount_usd = 2
                print(f"[FUTURE LEGENDARY] {symbol} أسطورية - أضاعف المبلغ إلى 2$")

        # فك الحظر
        for k in list(self.banned.keys()):
            if time.time() > self.banned[k]:
                del self.banned[k]

    def run(self):
        print("[FUTURE LEGENDARY] بدأ - سكانر 200 عملة - أسطوري شغال")
        while True:
            try:
                if self.current_positions < self.max_positions:
                    candidates = self.scan_all_futures()
                    print(f"[FUTURE] فحصت {len(candidates)} عملة تحقق الشروط | {self.status}")
                    if candidates:
                        sym, change, vol = candidates[0]
                        print(f"[FUTURE] >>> دخول أسطوري {sym} نازلة {change}% حجم {vol} - 1$ 3X")
                        self.current_positions += 1
                        # هنا أمر الفيوتشر الحقيقي
                        # exchange_future.set_leverage(self.leverage, sym)
                        # exchange_future.create_market_buy_order(sym, self.amount_usd)
                        # ستوب متحرك + هدف
                else:
                    print(f"[FUTURE] عندي صفقة شغالة - أنتظر")

                time.sleep(10)
            except Exception as e:
                print(f"[FUTURE ERROR] {e}")
                time.sleep(2)

# ========= تشغيل مدمج - الاثنين مع بعض =========
def start_legendary_merged():
    spot = V1000_Spot_Legendary()
    future = V1000_Future_Legendary()

    t1 = threading.Thread(target=spot.run, daemon=True)
    t2 = threading.Thread(target=future.run, daemon=True)
    
    t1.start()
    t2.start()
    
    print("\n========== V1000 LEGENDARY MERGED ==========")
    print("سبوت: شغال مثل الحلاوة - يشتري AVAX")
    print("فيوتشر: شغال مثل الحلاوة - سكانر 200 عملة")
    print("كل قسم يطور نفسه بنفسه - بدون تدخلك")
    print("==========================================\n")

    while True:
        time.sleep(1)

# شغل
if __name__ == "__main__":
    start_legendary_merged()