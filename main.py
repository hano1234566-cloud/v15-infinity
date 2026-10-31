from flask import Flask
import os, hmac, base64, hashlib, requests
from datetime import datetime
app=Flask(__name__)
K=os.getenv("OKX_API_KEY","").strip()
S=os.getenv("OKX_SECRET","").strip()
P=os.getenv("OKX_PASSPHRASE","").strip()
U="https://www.okx.com"
def sign(t,m,p,b=""):
    msg=f"{t}{m}{p}{b}"
    return base64.b64encode(hmac.new(S.encode(),msg.encode(),hashlib.sha256).digest()).decode()
def bal():
    try:
        ts=datetime.utcnow().isoformat()[:-3]+'Z'
        path="/api/v5/account/balance"
        sg=sign(ts,"GET",path,"")
        h={"OK-ACCESS-KEY":K,"OK-ACCESS-SIGN":sg,"OK-ACCESS-TIMESTAMP":ts,"OK-ACCESS-PASSPHRASE":P,"Content-Type":"application/json"}
        r=requests.get(U+path,headers=h,timeout=10).json()
        print(r,flush=True)
        if r.get("code")=="0":
            for a in r["data"][0]["details"]:
                if a["ccy"]=="USDT": return a["availBal"]
        return str(r)
    except Exception as e: return str(e)
@app.route('/')
def home(): return f"<h1>V23 LIVE OKX - USDT {bal()}</h1><p>{datetime.now()}</p>"
@app.route('/balance')
def b2(): return {"usdt":bal()}
if __name__=='__main__': app.run(host='0.0.0.0',port=10000)
