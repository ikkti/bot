import os, json
from flask import Flask, render_template, request, redirect, session, jsonify
from supabase import create_client

app = Flask(__name__)
app.secret_key = "kruri-secret-2026" # تكدر تغيره

try:
    CONFIG = json.loads(os.getenv("APP_CONFIG", "{}"))
except:
    CONFIG = {}

supabase = create_client(CONFIG.get("supabase_url"), CONFIG.get("supabase_key")) if CONFIG.get("supabase_url") else None

@app.route("/")
def index():
    if "user" in session:
        return redirect("/dashboard")
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email")
    password = request.form.get("password")

    # نفحص من Supabase Auth
    try:
        if supabase:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            if res.user:
                session["user"] = res.user.email
                # نحفظ تسجيل الدخول
                supabase.table("logins").insert({"email": email}).execute()
                return redirect("/dashboard")
    except Exception as e:
        print(e)

    # اذا ما عندك جدول users بعد، هذا دخول مؤقت للتجربة
    if email and password:
        session["user"] = email
        return redirect("/dashboard")

    return render_template("login.html", error="البريد أو كلمة المرور خطأ")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    return render_template("dashboard.html", user=session["user"], config=CONFIG)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/health")
def health():
    return jsonify({"status": "ok", "domain": "kruri-valverde.com"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
