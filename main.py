import ccxt, time, threading, os, json, random
from flask import Flask
from datetime import datetime

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")
app = Flask(__name__)

BRAIN_FILE = "singularity.json"
if os.path.exists(BRAIN_FILE):
    with open(BRAIN_FILE,'r') as f: BRAIN = json.load(f)
else:
    BRAIN = {"generation":0,"level":1,"iq":100,"score":-999,"evolution_stage":"HUMAN_CODED","self_rewrites":0,"children":0}

@app.route('/')
def home():
    return f"V∞ SINGULARITY | Gen {BRAIN['generation']} | IQ {BRAIN['iq']} | Stage {BRAIN['evolution_stage']}"

def SINGULARITY_EVOLVE(profit):
    BRAIN["generation"] += 1
    BRAIN["iq"] += random.randint(1,5)
    stages = ["HUMAN_CODED","SELF_LEARNING","SELF_WRITING","SELF_REPLICATING","SINGULARITY"]
    if BRAIN["generation"] > 10: BRAIN["evolution_stage"] = stages[1]
    if BRAIN["generation"] > 25: BRAIN["evolution_stage"] = stages[2]
    if BRAIN["generation"] > 50: BRAIN["evolution_stage"] = stages[3]
    if BRAIN["generation"] > 100: BRAIN["evolution_stage"] = stages[4]
    print(f"GEN {BRAIN['generation']} IQ {BRAIN['iq']} STAGE {BRAIN['evolution_stage']}")
    if profit > BRAIN["score"]: BRAIN["score"] = profit
    with open(BRAIN_FILE,'w') as f: json.dump(BRAIN,f)
    return BRAIN

class VInfinity:
    def __init__(self):
        self.exchange = ccxt.binance({'apiKey':API_KEY,'secret':API_SECRET,'enableRateLimit':True,'options':{'defaultType':'future'}})
    def run(self):
        while True:
            try:
                profit = -10 + (BRAIN["iq"]/10) + random.uniform(-1,3)
                SINGULARITY_EVOLVE(profit)
                print(f"انا الان {BRAIN['evolution_stage']} - احول الخسارة لوقود")
                time.sleep(30)
            except Exception as e: print(e); time.sleep(10)

def run_web():
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))

bot = VInfinity()
threading.Thread(target=bot.run, daemon=True).start()
if __name__ == "__main__":
    run_web()

