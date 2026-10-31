from flask import Flask
import os
import okx.Account as Account

app = Flask(__name__)

api_key = (os.getenv("OKX_API_KEY") or "").strip()
api_secret = (os.getenv("OKX_SECRET") or "").strip()
passphrase = (os.getenv("OKX_PASSPHRASE") or "").strip()

@app.route('/')
def home():
    if not api_key or not api_secret or not passphrase:
        return f"<h1>V23 ERROR KEYS EMPTY</h1> API len={len(api_key)} Secret len={len(api_secret)} Pass len={len(passphrase)} <br> روح Render > Environment وتأكد انك حفظت المفاتيح وضغطت Save", 500
    try:
        account = Account.AccountAPI(api_key, api_secret, passphrase, False, "0")
        result = account.get_account_balance()
        if result.get("code") == "0":
            total = result["data"][0].get("totalEq", "0")
            return f"<h1>V23 LIVE OKX - USDT {total} - SUCCESS!</h1> {result}"
        else:
            return f"<h1>V23 LIVE - OKX Error: {result}</h1>"
    except Exception as e:
        return f"<h1>V23 Error: {str(e)}</h1>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
