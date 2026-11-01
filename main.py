# LEGENDARY DEATH HUNTER V20001 - UI UPGRADE
import os, time, ccxt, threading
from flask import Flask

API_KEY = os.getenv("OKX_API_KEY")
SECRET = os.getenv("OKX_SECRET")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")

SPOT_BUY = 10.0
FUT_MAX = 5.0
HUNTS = 0; KILLS = 0; POS = 0; BAL = 40.08; LIQ = 0.0
HOLDINGS = "DOGE:$5.99 | TRX:$4.49 | CORE:$1.00 | MEME:$0.81"
LAST = "[DEATH BUY] LSK -23.6% $4.22"
CRON = "OK"

app = Flask(__name__)
ex = ccxt.okx({'apiKey':API_KEY,'secret':SECRET,'password':PASSPHRASE,'enableRateLimit':True})

def get_free():
    try: return float(ex.fetch_balance().get('USDT',{}).get('free',0) or 0)
    except: return BAL

def loop():
    global BAL
    while True:
        BAL = get_free()
        time.sleep(10)
threading.Thread(target=loop, daemon=True).start()

@app.route('/')
def home():
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="12">
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@700&display=swap');
body{{margin:0;background:#050507;color:#fff;font-family:'JetBrains Mono',monospace;overflow-x:hidden}}
.bg{{position:fixed;top:0;left:0;width:100%;height:100%;background:radial-gradient(ellipse at top, #1a0b2e 0%, #050507 60%);z-index:-1}}
.header{{padding:20px 16px 10px;display:flex;justify-content:space-between;align-items:center}}
.live{{background:#ff003c;color:#fff;padding:4px 10px;border-radius:20px;font-size:11px;animation:pulse 1.5s infinite;box-shadow:0 0 15px #ff003c}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.6}}}}
.title{{font-size:22px;font-weight:900;letter-spacing:2px;background:linear-gradient(90deg,#fff,#a855f7,#ff003c);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:0 12px}}
.card{{background:linear-gradient(135deg,rgba(255,255,255,0.08),rgba(255,255,255,0.02));backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:12px;position:relative;overflow:hidden}}
.card::before{{content:'';position:absolute;top:0;left:0;width:100%;height:2px;background:linear-gradient(90deg,#a855f7,#ff003c)}}
.label{{font-size:9px;color:#888;letter-spacing:1px}}
.value{{font-size:20px;font-weight:900;margin-top:4px}}
.green{{color:#00ff88;text-shadow:0 0 10px #00ff88}}
.purple{{color:#a855f7}} .red{{color:#ff003c}} .yellow{{color:#facc15}}
.main-hunt{{margin:12px;background:linear-gradient(135deg,#1a0b2e,#0f0f0f);border:1px solid #a855f7;border-radius:20px;padding:16px;box-shadow:0 0 30px rgba(168,85,247,0.3)}}
.kill-bar{{height:6px;background:#111;border-radius:10px;margin-top:8px;overflow:hidden}}
.kill-fill{{height:100%;background:linear-gradient(90deg,#00ff88,#a855f7);width:40%;box-shadow:0 0 10px #00ff88}}
.death{{font-size:12px;background:#000;border-left:3px solid #ff003c;padding:10px;border-radius:0 10px 10px 0;margin-top:10px;color:#ff5a5a;animation:glow 2s infinite}}
@keyframes glow{{0%,100%{{box-shadow:0 0 5px #ff003c33}}50%{{box-shadow:0 0 20px #ff003c77}}}}
.hold{{font-size:10px;color:#666;margin:12px;line-height:1.6;word-break:break-all}}
</style>
</head>
<body>
<div class="bg"></div>
<div class="header">
<div class="title">DEATH HUNTER</div>
<div class="live">● LIVE V20001</div>
</div>

<div class="main-hunt">
<div style="display:flex;justify-content:space-between">
<div><div class="label">CRON STATUS</div><div class="value green">{CRON} ●</div></div>
<div style="text-align:right"><div class="label">BALANCE</div><div class="value yellow">${BAL:.2f}</div></div>
</div>
<div style="display:flex;gap:20px;margin-top:14px">
<div><div class="label">HUNTS</div><div class="value">{HUNTS}</div></div>
<div><div class="label">KILLS</div><div class="value green">{KILLS}</div></div>
<div><div class="label">POSITIONS</div><div class="value purple">{POS}</div></div>
</div>
<div class="kill-bar"><div class="kill-fill"></div></div>
<div class="death">{LAST}</div>
</div>

<div class="grid">
<div class="card"><div class="label">SPOT FIX</div><div class="value green">${SPOT_BUY}</div></div>
<div class="card"><div class="label">FUTURES LIQ</div><div class="value red">{LIQ}/{FUT_MAX}</div></div>
<div class="card"><div class="label">FU MAX</div><div class="value purple">${FUT_MAX}</div></div>
<div class="card"><div class="label">MODE</div><div class="value">FAST ⚡</div></div>
</div>

<div class="hold">{HOLDINGS}</div>

<div style="text-align:center;padding:20px;color:#333;font-size:9px;letter-spacing:3px">OKX REQUIRES 'SECRET' CREDENTIAL • LEGENDARY EDITION</div>
</body>
</html>
"""
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT",10000)))
