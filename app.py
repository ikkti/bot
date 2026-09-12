import os
import json
import asyncio
from flask import Flask, request, session, redirect, render_template_string

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "kruri-secret-2026")

try:
    CFG = json.loads(os.getenv("APP_CONFIG", "{}"))
except:
    CFG = {}

API_ID = int(CFG.get("api_id") or os.getenv("API_ID") or 0)
API_HASH = CFG.get("api_hash") or os.getenv("API_HASH") or ""

from telethon.sessions import StringSession
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

CLIENTS = {}

def run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

LOGIN_HTML = """
<!doctype html><html dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>دخول</title>
<style>body{background:#0a0a0f;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.card{background:#1c1c24;padding:30px;border-radius:20px;width:90%;max-width:380px}input{width:100%;padding:14px;margin:10px 0;border-radius:10px;border:1px solid #333;background:#111;color:#fff;box-sizing:border-box}
button{width:100%;padding:14px;background:#2AABEE;border:0;border-radius:10px;color:#fff;font-weight:bold}
.err{background:#ff000022;color:#ff8a8a;padding:10px;border-radius:8px;margin-bottom:10px;text-align:center}
</style></head><body><div class="card">
<h2 style="text-align:center;color:#2AABEE">تسجيل الدخول</h2>
{{err}}
<form method="post" action="/send-code">
<input name="phone" placeholder="+9647XXXXXXXX" required value="+964">
<button>ارسال الكود</button>
</form>
</div></body></html>
"""

CODE_HTML = """
<!doctype html><html dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>كود</title>
<style>body{background:#0a0a0f;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.card{background:#1c1c24;padding:30px;border-radius:20px;width:90%;max-width:380px}input{width:100%;padding:14px;margin:10px 0;border-radius:10px;border:1px solid #333;background:#111;color:#fff;box-sizing:border-box;text-align:center}
button{width:100%;padding:14px;background:#2AABEE;border:0;border-radius:10px;color:#fff;font-weight:bold}
.err{background:#ff000022;color:#ff8a8a;padding:10px;border-radius:8px;margin-bottom:10px;text-align:center}
</style></head><body><div class="card">
<h2 style="text-align:center">ادخل الكود</h2>
<p style="text-align:center;color:#888">{{phone}}</p>
{{err}}
<form method="post" action="/verify-code">
<input name="code" placeholder="12345" required>
<input name="password" type="password" placeholder="باسورد التحقق بخطوتين (اذا موجود)">
<button>تأكيد</button>
</form>
<a href="/" style="color:#666;display:block;text-align:center;margin-top:15px">تغيير الرقم</a>
</div></body></html>
"""

@app.route("/")
def home():
    if "user" in session:
        return redirect("/dashboard")
    if not API_ID or not API_HASH:
        return "<h1>خطأ في النظام: لم يتم ضبط بيانات الاعتماد.</h1>"
    return render_template_string(LOGIN_HTML, err="")

@app.route("/send-code", methods=["POST"])
def send_code():
    phone = request.form.get("phone","").strip()
    session["phone"] = phone

    async def _do():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            CLIENTS[phone] = {"sess": client.session.save(), "hash": sent.phone_code_hash}
            return render_template_string(CODE_HTML, phone=phone, err="")
        except Exception as e:
            return render_template_string(LOGIN_HTML, err=f"<div class='err'>{e}</div>")
        finally:
            await client.disconnect()
    return run(_do())

@app.route("/verify-code", methods=["POST"])
def verify_code():
    phone = session.get("phone")
    code = request.form.get("code","").strip()
    pwd = request.form.get("password","").strip()
    data = CLIENTS.get(phone)
    if not data:
        return redirect("/")

    async def _do():
        client = TelegramClient(StringSession(data["sess"]), API_ID, API_HASH)
        await client.connect()
        try:
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=data["hash"])
            except SessionPasswordNeededError:
                if not pwd:
                    raise Exception("الحساب بيه تحقق بخطوتين - اكتب الباسورد")
                await client.sign_in(password=pwd)

            me = await client.get_me()
            session["user"] = {"id": me.id, "name": me.first_name, "username": me.username or "", "phone": me.phone or phone}
            session["tg_session"] = client.session.save()
            CLIENTS.pop(phone, None)
            return redirect("/dashboard")
        except Exception as e:
            return render_template_string(CODE_HTML, phone=phone, err=f"<div class='err'>{e}</div>")
        finally:
            await client.disconnect()
    return run(_do())

@app.route("/dashboard")
def dash():
    if "user" not in session:
        return redirect("/")
    u = session["user"]
    tg_sess = session.get("tg_session", "")
    
    return f"""
    <body dir=rtl style='background:#0a0a0f;color:#fff;font-family:sans-serif;padding:20px;display:flex;justify-content:center;'>
    <div style='background:#1c1c24;padding:25px;border-radius:16px;width:100%;max-width:500px;'>
        <h1 style='color:#2AABEE;margin-top:0;'>تم تسجيل الدخول بنجاح ✅</h1>
        <p><b>ID:</b> {u['id']}</p>
        <p><b>الاسم:</b> {u['name']}</p>
        <p><b>اليوزر:</b> @{u['username']}</p>
        <p><b>الرقم:</b> {u['phone']}</p>
        <hr style='border: 0.5px solid #333; margin: 15px 0;'>
        <p style='color:#2AABEE;font-weight:bold;margin-bottom:5px;'>السيشن (String Session):</p>
        <textarea readonly style='width:100%;height:100px;background:#111;color:#00ff66;border:1px solid #333;border-radius:8px;padding:10px;box-sizing:border-radius;font-family:monospace;font-size:12px;resize:none;'>{tg_sess}</textarea>
        <br><br>
        <a href='/logout' style='color:#ff5555;text-decoration:none;'>تسجيل الخروج</a>
    </div>
    </body>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/health")
def health():
    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
