import os, json
from flask import Flask, request, redirect, session, jsonify, render_template_string

app = Flask(__name__)
app.secret_key = "kruri-2026"

LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>تسجيل الدخول - kruri-valverde.com</title>
<style>
body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;background:#0f0f14;color:#fff;font-family:system-ui}
.card{background:#1c1c24;padding:40px;border-radius:20px;width:92%;max-width:400px;box-shadow:0 20px 50px rgba(0,0,0,.6)}
h2{text-align:center;color:#a78bfa;margin:0 0 25px} 
input{width:100%;padding:14px;margin:8px 0;border-radius:12px;border:1px solid #333;background:#111;color:#fff;box-sizing:border-box}
button{width:100%;padding:14px;margin-top:15px;background:#a78bfa;border:0;border-radius:12px;font-weight:800;cursor:pointer}
.err{background:#ff3b3b20;color:#ff8a8a;padding:10px;border-radius:10px;text-align:center;margin-bottom:10px}
small{display:block;text-align:center;margin-top:18px;color:#666}
</style></head>
<body><div class="card"><h2>تسجيل الدخول</h2>
%ERROR%
<form method="POST" action="/login"><input name="email" type="email" placeholder="البريد" required><input name="password" type="password" placeholder="كلمة المرور" required><button>دخول</button></form>
<small>kruri-valverde.com - السيرفر الحقيقي</small></div></body></html>
"""

@app.route("/")
def home():
    if "user" in session:
        return redirect("/dashboard")
    html = LOGIN_PAGE.replace("%ERROR%", "")
    return render_template_string(html)

@app.route("/login", methods=["POST"])
def do_login():
    email = request.form.get("email","")
    pwd = request.form.get("password","")
    if email and pwd:
        session["user"] = email
        return redirect("/dashboard")
    html = LOGIN_PAGE.replace("%ERROR%", '<div class="err">خطأ بالبريد أو كلمة المرور</div>')
    return render_template_string(html)

@app.route("/dashboard")
def dash():
    if "user" not in session:
        return redirect("/")
    return f"""
    <body style="background:#0f0f14;color:#fff;font-family:system-ui;padding:30px" dir="rtl">
    <h1>أهلاً {session['user']} 👋</h1>
    <div style="background:#1c1c24;padding:20px;border-radius:16px">السيرفر شغال 100% على kruri-valverde.com ✅<br><br>
    <a href="/logout" style="color:#a78bfa">خروج</a></div></body>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/health")
def health():
    return jsonify(ok=True)

# Fly يحتاج هذا المنفذ
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
