from flask import Flask
import os
import hmac
import base64
import hashlib
import requests
from datetime import datetime

app = Flask(__name__)

OKX_API_KEY = os.getenv("OKX_API_KEY", "").strip()
OKX_SECRET = os.getenv("OKX_SECRET", "").strip()
OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE", "").strip()
BASE_URL = "https://www.okx.com"

def okx_sign(ts, method, path, body=""):
    msg = f"{ts}{method}{path}{body}"
    mac = hmac.new(OKX_SECRET.encode(), msg.encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()

def get_balance():
    try:
        ts = datetime.utcnow().isoformat()[:-3] + 'Z'
        method = "GET"
        path = "/api/v5/account/balance"
        sign = okx_sign(ts, method, path, "")
        headers = {
            "OK-ACCESS-KEY": OKX_API_KEY,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE,
            "Content-Type": "application/json"
        }
        r = requests.get(BASE_URL+path, headers=headers, timeout=10)
        data = r.json()
        print(f"OKX RESPONSE: {data}", flush=True)
        if data.get("code")=="0":
            for a in data["data"][0]["details"]:
                if a["ccy"]=="USDT":
                    print(f"FREE USDT: {a['availBal']}", flush=True)
                    return a['availBal']
        return f"Error: {data}"
    except Exception as e:
        print(f"ERR: {e}", flush=True)
        return str(e)

print("=== V23 OKX STARTING ===", flush=True)
bal = get_balance()
print(f"=== LIVE MODE OKX ACTIVE - {bal} ===", flush=True)

@app.route('/')
def home():
    b = get_balance()
    return f"<h1>V23 INFINITY LIVE - OKX</h1><p>USDT: {b}</p><p>Time: {datetime.now()}</p><p><a href='/balance'>Balance API</a></p>"

@app.route('/balance')
def bal_route():
    return {"usdt": get_balance(), "exchange": "OKX", "live": True}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
