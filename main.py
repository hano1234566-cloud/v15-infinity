from flask import Flask
import os
app=Flask(__name__)
@app.route("/")
def home():
    k=os.getenv("OKX_API_KEY","NOT FOUND")
    s=os.getenv("OKX_SECRET_KEY","NOT FOUND")
    p=os.getenv("OKX_PASSPHRASE","NOT FOUND")
    return f"<h1>فحص Render</h1><p>API_KEY: {k[:10]}... len={len(k)}</p><p>SECRET: {s[:10] if s!='NOT FOUND' else s} len={len(s) if s!='NOT FOUND' else 0}</p><p>PASSPHRASE: {p} len={len(p) if p!='NOT FOUND' else 0}</p><p><br>اذا طلع NOT FOUND معناه ما حطيته في Render Environment!</p>"
app.run(host="0.0.0.0",port=10000)
