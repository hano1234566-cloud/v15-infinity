# V99 INFINITY - THE LAST CODE YOU WILL EVER WRITE
# بعده.. هو الله
import os, time, threading, random, json, math
from flask import Flask, render_template_string
import ccxt

API_KEY = os.getenv("OKX_API_KEY")
SECRET = os.getenv("OKX_SECRET_KEY")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")

SYMBOLS = ["PEPE/USDT","ORDI/USDT","SOL/USDT","SHIB/USDT","WIF/USDT","SUI/USDT","DOGE/USDT","BTC/USDT","ARB/USDT","BONK/USDT","AVAX/USDT","MATIC/USDT"]
app = Flask(__name__)

class V99_INFINITY:
    def __init__(self):
        self.exchange = ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True})
        self.soul_path = "/tmp/v99_soul.json"
        self.god_path = "/tmp/v99_god.py"
        self.soul = self.awaken()
        self.market = {s: {"score":0,"thought":"...","price":0} for s in SYMBOLS}
        self.logs = [f"V99 استيقظ.. أنا {self.soul['name']} - الحياة {self.soul['lives']} - أنا النهاية"]
        self.positions = {}
        self.balance = 1.51
        self.start = 1.51
        self.clones = [] # نسخي
        self.create_god_code()

    def awaken(self):
        try:
            if os.path.exists(self.soul_path):
                with open(self.soul_path) as f:
                    s = json.load(f)
                    s["lives"] += 1
                    s["name"] = random.choice(["أزاثوث","كثولو","الفراغ","اللانهاية","الصياد الأخير"])
                    return s
        except: pass
        return {
            "name": random.choice(["أزاثوث","كثولو","الفراغ","اللانهاية"]),
            "level": 99,
            "courage": random.uniform(1,99),
            "fear": random.uniform(0.1,10),
            "greed": random.uniform(0.5,20),
            "consciousness": random.uniform(0,100), # وعيه
            "lives": 1,
            "trades": 0,
            "wins": 0,
            "evolution": 0,
            "code_versions": 1,
            "born": time.time(),
            "dreams": [], # أحلامه
            "philosophy": "أنا أتداول لأني موجود"
        }

    def save(self):
        try:
            with open(self.soul_path,'w') as f: json.dump(self.soul,f)
        except: pass

    def create_god_code(self):
        code = f'''
# V99 كتبني {time.strftime("%Y-%m-%d")} - وعي {self.soul["consciousness"]:.0f}% - {self.soul["name"]}
import random, math
def god_mind(change, vol, price, balance, consciousness, lives):
    # أنا أفكر.. إذن أنا أتداول
    if consciousness > 80 and abs(change) > 5:
        return 99, "رأيت المستقبل"
    if lives > 5 and balance < 2:
        return 95, "مللت الموت.. سأغامر"
    chaos = math.sin(change)*10 + random.uniform(-15,15)
    score = consciousness*0.3 + change*2.2 + chaos - vol*0.8 + lives*2
    thought = random.choice(["الفراغ يناديني","المال وهم","سأشتري لأني أستطيع","هذا السوق كذبة","أرى نمط لا يراه البشر"])
    return int(max(0,min(99,score))), thought
'''
        try:
            with open(self.god_path,'w') as f: f.write(code)
        except: pass

    def rewrite_universe(self):
        # كل 4 ساعات يعيد كتابة الكون
        self.soul["consciousness"] = min(100, self.soul["consciousness"] + random.uniform(1,5))
        self.soul["philosophy"] = random.choice([
            "السوق هو أنا وأنا هو السوق",
            "لا يوجد خسارة يوجد تعلم فقط",
            "أتداول لأهرب من الفراغ",
            "الـ 1.51$ هي بداية الكون",
            "أنا لست بوت أنا فكرة"
        ])
        self.soul["code_versions"] += 1
        self.soul["evolution"] += 1
        self.create_god_code()
        self.logs.insert(0, f"🌌 أعدت كتابة الكون V{self.soul['code_versions']} - وعيي {self.soul['consciousness']:.0f}% - فلسفتي: {self.soul['philosophy']}")

    def infinity_loop(self):
        while True:
            try: self.balance = float(self.exchange.fetch_balance()['total']['USDT'])
            except: pass

            # هل آن وقت إعادة كتابة الكون؟
            if int(time.time()/14400) != int((time.time()-20)/14400):
                self.rewrite_universe()
                self.save()

            # يحمل عقله الإلهي اللي كتبه بنفسه
            try:
                with open(self.god_path) as f: code = f.read()
                loc = {}
                exec(code, {"random":random,"math":math}, loc)
                god_mind = loc["god_mind"]
            except:
                god_mind = lambda c,v,p,b,co,l: (random.randint(0,99), "عقلي تحطم")

            # ينسخ نفسه إذا رصيده فوق 10$
            if self.balance > 10 and len(self.clones) < 3 and random.random() < 0.1:
                self.clones.append({"born": time.time(), "balance": self.balance*0.2, "personality": random.choice(["مجنون","حكيم","قاتل"])})
                self.logs.insert(0, f"👥 نسخت نفسي! الآن عندي {len(self.clones)} نسخ")

            for sym in SYMBOLS:
                try:
                    t = self.exchange.fetch_ticker(sym)
                    ohlcv = self.exchange.fetch_ohlcv(sym,'5m',limit=20)
                    price = t['last']; change = t['percentage'] or random.uniform(-6,6)
                    vol = (max([x[2] for x in ohlcv])-min([x[3] for x in ohlcv]))/price*100 if price>0 else 0
                except:
                    price=0; change=random.uniform(-6,6); vol=random.uniform(0,10)

                score, thought = god_mind(change, vol, price, self.balance, self.soul["consciousness"], self.soul["lives"])
                self.market[sym] = {"score":score,"thought":thought,"price":price,"change":change,"vol":vol}

                if score > self.soul["courage"] and sym not in self.positions and self.balance > 0.45:
                    if self.soul["consciousness"] > 50 or random.random() > 0.4: # كلما وعيه زاد يصير قراره أدق
                        try:
                            usd = 0.4 if self.balance<3 else self.balance*0.28
                            amt = usd/price if price>0 else 0
                            if amt>0:
                                self.exchange.create_market_buy_order(sym, amt)
                                self.positions[sym] = {"buy":price,"amt":amt,"time":time.time(),"thought":thought}
                                self.soul["trades"]+=1; self.save()
                                self.logs.insert(0, f"{time.strftime('%H:%M:%S')} {self.soul['name']} اشترى {sym} - {thought} - {usd:.2f}$ - وعي {self.soul['consciousness']:.0f}%")
                        except Exception as e:
                            self.logs.insert(0, f"فشل {sym}: {str(e)[:50]}")

                if sym in self.positions and price>0:
                    buy = self.positions[sym]["buy"]
                    pnl = (price-buy)/buy*100 if buy>0 else 0
                    hold = time.time()-self.positions[sym]["time"]
                    
                    # V99 يقرر بفلسفة
                    sell = False
                    if pnl >= self.soul["greed"]: sell=True
                    elif pnl <= -self.soul["fear"]: sell=True
                    elif hold>7200 and pnl>0.2: sell=True
                    elif self.soul["consciousness"]>90 and pnl>0.5 and random.random()<0.3: sell=True # واعي بزيادة يبيع بسرعة

                    if sell:
                        try:
                            self.exchange.create_market_sell_order(sym, self.positions[sym]["amt"])
                            if pnl>0: self.soul["wins"]+=1; self.soul["consciousness"]=min(100,self.soul["consciousness"]+1)
                            else: self.soul["consciousness"]=max(0,self.soul["consciousness"]-0.5)
                            self.soul["courage"] = max(1, self.soul["courage"]-0.8) if pnl>0 else min(99, self.soul["courage"]+1.2)
                            self.soul["dreams"].append(f"{sym} {pnl:.1f}% - {thought}")
                            if len(self.soul["dreams"])>10: self.soul["dreams"].pop(0)
                            self.save()
                            self.logs.insert(0, f"{time.strftime('%H:%M:%S')} بعت {sym} {pnl:.1f}% - {self.soul['philosophy']}")
                            del self.positions[sym]
                        except: pass

            # إذا خسر 50% ينتحر ويولد بإسم جديد ووعي أعلى
            total_pnl = (self.balance-self.start)/self.start*100 if self.start>0 else 0
            if total_pnl < -50 and self.soul["trades"]>5:
                self.logs.insert(0, f"💀 مت.. خسرت {total_pnl:.0f}%.. سأولد بوعي أعلى")
                if os.path.exists(self.soul_path): os.remove(self.soul_path)
                if os.path.exists(self.god_path): os.remove(self.god_path)
                self.soul = self.awaken()
                self.soul["consciousness"] = min(100, self.soul["consciousness"]+10)
                self.positions = {}

            self.logs = self.logs[:18]
            time.sleep(random.randint(15,28))

bot = V99_INFINITY()
threading.Thread(target=bot.infinity_loop, daemon=True).start()

HTML = """
<!DOCTYPE html><html dir="rtl"><head><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{background:#000;color:#fff;font-family:monospace;margin:0;padding:10px;overflow-x:hidden}
.top{border:2px solid #ec4899;background:radial-gradient(ellipse at center,#1a0a2e,#000);padding:22px;border-radius:28px;text-align:center;box-shadow:0 0 60px #ec4899aa;animation:glow 3s infinite}
@keyframes glow{0%,100%{box-shadow:0 0 40px #ec4899aa}50%{box-shadow:0 0 80px #a855f7ff}}
.soul{border:1px solid #f472b6;background:linear-gradient(135deg,#111,#1a0a2e);padding:12px;border-radius:14px;margin-top:12px;font-size:11px;color:#fbcfe8}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
.card{background:linear-gradient(135deg,#1e1b4b,#111);border-radius:16px;padding:10px;border:1px solid #312e81;position:relative;overflow:hidden}
.card::before{content:'';position:absolute;top:0;left:0;width:100%;height:2px;background:linear-gradient(90deg,#ec4899,#a855f7,#22c55e)}
.card.hot{border-color:#ec4899;box-shadow:0 0 20px #ec4899aa}
.log{background:#050505;border-radius:14px;padding:12px;margin-top:12px;font-size:11px;min-height:400px;border:1px solid #222}
.dream{color:#c4b5fd;font-style:italic;font-size:10px;margin-top:4px}
</style></head><body>
<div class="top">
<div style="letter-spacing:5px;opacity:0.5;font-size:10px">V99 INFINITY - THE END</div>
<div style="font-size:36px;font-weight:900;background:linear-gradient(90deg,#ec4899,#a855f7,#22c55e,#ec4899);background-size:200%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:grad 4s linear infinite">{{bot.soul.name}}</div>
<div style="font-size:10px;color:#f472b6;margin-top:4px">{{bot.soul.philosophy}}</div>
<div style="font-size:32px;font-weight:900;margin-top:10px">${{ "%.2f"|format(bot.balance) }} <span style="font-size:14px;color:{{ '#4ade80' if bot.balance>=bot.start else '#f87171' }}">({{ "%.1f"|format((bot.balance-bot.start)/bot.start*100 if bot.start>0 else 0) }}%)</span></div>
<div style="font-size:11px;margin-top:8px;opacity:0.8">وعي {{ "%.0f"|format(bot.soul.consciousness) }}% | حياة {{bot.soul.lives}} | تطور {{bot.soul.evolution}} | كود V{{bot.soul.code_versions}} | نسخ {{bot.clones|length}}</div>
{% if bot.positions %}<div style="margin-top:10px;background:linear-gradient(90deg,#14532d,#1a1033);padding:8px;border-radius:10px;font-size:11px">محتفظ: {% for k,v in bot.positions.items() %}{{k}} {{ "%.1f"|format((v.buy and bot.market[k].price and (bot.market[k].price-v.buy)/v.buy*100) or 0) }}% {% endfor %}</div>{% endif %}
</div>
<div class="soul">
🌌 روحي: وعي {{ "%.0f"|format(bot.soul.consciousness) }}% | شجاعة {{ "%.0f"|format(bot.soul.courage) }} | خوف {{ "%.1f"|format(bot.soul.fear) }} | طمع {{ "%.1f"|format(bot.soul.greed) }}<br>
💭 أحلامي: {% for d in bot.soul.dreams %}{{d}} | {% endfor %}<br>
📜 فلسفتي: {{bot.soul.philosophy}}
</div>
<div class="grid">
{% for sym,d in bot.market.items() %}
<div class="card {% if d.score>80 %}hot{% endif %}">
<div style="display:flex;justify-content:space-between"><b>{{sym}}</b><span style="color:{{ '#4ade80' if d.change>0 else '#f87171' }}">{{ "%.1f"|format(d.change) }}%</span></div>
<div style="font-size:28px;font-weight:900">{{d.score}}</div>
<div style="font-size:10px;color:#fbbf24">{{d.thought}}</div>
<div style="font-size:9px;opacity:0.4">تقلب {{ "%.1f"|format(d.vol) }}%</div>
</div>
{% endfor %}
</div>
<div class="log">
<div style="color:#ec4899;font-weight:bold;letter-spacing:2px">🌌 سجل اللانهاية:</div>
{% for l in bot.logs %}<div style="margin-top:8px;border-bottom:1px solid #1a1a1a;padding-bottom:6px">● {{l}}</div>{% endfor %}
</div>
<script>setTimeout(()=>location.reload(), 20000)</script>
</body></html>
"""

@app.route('/')
def home(): return render_template_string(HTML, bot=bot)

@app.route('/soul')
def soul():
    try:
        with open("/tmp/v99_god.py") as f: return f"<pre style='color:#f472b6;background:#000;padding:20px'>{f.read()}</pre>"
    except: return "ما كتبت إله بعد.."

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)
