import os, json, asyncio
from flask import Flask, request, session, jsonify, render_template_string, redirect

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "kruri-2026-very-secret")

# تحميل api_id / api_hash من متغير Fly
try:
    CONFIG = json.loads(os.getenv("APP_CONFIG", "{}"))
except:
    CONFIG = {}

API_ID = int(CONFIG.get("api_id", 0) or os.getenv("API_ID", 0))
API_HASH = CONFIG.get("api_hash", "") or os.getenv("API_HASH", "")

# نخزن الجلسات هنا مؤقتاً
from telethon.sessions import StringSession
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

CLIENTS_DATA = {} # phone -> {session_str, phone_code_hash}

def get_loop():
    try:
        loop = asyncio.get_event_loop()
    except:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop

LOGIN_PHONE_PAGE = """
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>دخول تليجرام</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0a0a0f;color:#fff;font-family:system-ui}
.card{background:#1c1c24;padding:35px;border-radius:24px;width:92%;max-width:400px}
h2{text-align:center;color:#2AABEE} input{width:100%;padding:15px;margin:12px 0;border-radius:12px;border:1px solid #333;background:#111;color:#fff;box-sizing:border-box;font-size:16px}
button{width:100%;padding:15px;background:#2AABEE;border:0;border-radius:12px;font-weight:800;cursor:pointer;color:#fff;font-size:16px}
small{display:block;text-align:center;color:#666;margin-top:15px}.err{background:#ff3b3b22;color:#ff8a8a;padding:10px;border-radius:10px;text-align:center}
</style></head><body><div class="card">
<h2>تسجيل دخول تليجرام</h2>
<p style="text-align:center;color:#888">ادخل رقمك مع رمز البلد</p>
%ERROR%
<form method="POST" action="/send-code">
<input name="phone" placeholder="+9647XXXXXXXX" required value="+964">
<button>إرسال كود التحقق</button>
</form>
<small>يستخدم api_id الخاص بك - kruri-valverde.com<br>API_ID: {{api_id}}</small>
</div></body></html>
"""

VERIFY_PAGE = """
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>تأكيد الكود</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0a0a0f;color:#fff;font-family:system-ui}
.card{background:#1c1c24;padding:35px;border-radius:24px;width:92%;max-width:400px}
h2{text-align:center;color:#2AABEE} input{width:100%;padding:15px;margin:12px 0;border-radius:12px;border:1px solid #333;background:#111;color:#fff;box-sizing:border-box;font-size:16px;letter-spacing:5px;text-align:center}
button{width:100%;padding:15px;background:#2AABEE;border:0;border-radius:12px;font-weight:800;cursor:pointer;color:#fff}
.err{background:#ff3b3b22;color:#ff8a8a;padding:10px;border-radius:10px;text-align:center}
</style></head><body><div class="card">
<h2>ادخل الكود</h2>
<p style="text-align:center;color:#888">الكود وصلك على تليجرام: {{phone}}</p>
%ERROR%
<form method="POST" action="/verify-code">
<input name="code" placeholder="12345" required autofocus>
<input name="password" type="password" placeholder="كلمة مرور التحقق بخطوتين (اذا عندك)">
<button>تأكيد الدخول</button>
</form>
<a href="/" style="display:block;text-align:center;color:#666;margin-top:15px">تغيير الرقم</a>
</div></body></html>
"""

@app.route("/")
def home():
    if "user" in session:
        return redirect("/dashboard")
    if not API_ID or not API_HASH:
        return f"<h1 style='color:red'>API_ID / API_HASH ما مربوط - ضبط fly secrets</h1> CONFIG: {CONFIG.keys()}"
    html = LOGIN_PHONE_PAGE.replace("%ERROR%", "")
    return render_template_string(html, api_id=API_ID)

@app.route("/send-code", methods=["POST"])
async def send_code_async():
    phone = request.form.get("phone", "").strip()
    if not phone:
        return redirect("/")

    # نستخدم loop يدوي لان flask sync
    loop = get_loop()
    return await _send_code(phone)

async def _send_code(phone):
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        CLIENTS_DATA[phone] = {
            "session_str": client.session.save(),
            "phone_code_hash": sent.phone_code_hash
        }
        session["phone"] = phone
        html = VERIFY_PAGE.replace("%ERROR%", "")
        return render_template_string(html, phone=phone)
    except Exception as e:
        return render_template_string(LOGIN_PHONE_PAGE.replace("%ERROR%", f'<div class="err">{str(e)}</div>'), api_id=API_ID)
    finally:
        await client.disconnect()

# Wrapper للـ async في Flask العادي
@app.route("/send-code", methods=["POST"])
def send_code():
    phone = request.form.get("phone", "").strip()
    if not phone:
        return redirect("/")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_send_code(phone))
    except Exception as e:
        html = LOGIN_PHONE_PAGE.replace("%ERROR%", f'<div class="err">{e}</div>')
        return render_template_string(html, api_id=API_ID)

@app.route("/verify-code", methods=["POST"])
def verify_code():
    phone = session.get("phone") or request.form.get("phone")
    code = request.form.get("code", "").strip()
    password = request.form.get("password", "").strip()

    data = CLIENTS_DATA.get(phone)
    if not data:
        return redirect("/")

    async def _verify():
        client = TelegramClient(StringSession(data["session_str"]), API_ID, API_HASH)
        await client.connect()
        try:
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=data["phone_code_hash"])
            except SessionPasswordNeededError:
                if not password:
                    raise Exception("هذا الحساب محمي بكلمة مرور بخطوتين - ادخلها")
                await client.sign_in(password=password)

            me = await client.get_me()
            session["user"] = {
                "id": me.id,
                "first_name": me.first_name,
                "username": me.username,
                "phone": me.phone
            }
            # نحفظ الـ session string حتى تبقى مسجل
            session["tg_session"] = client.session.save()
            CLIENTS_DATA.pop(phone, None)
            return redirect("/dashboard")
        except Exception as e:
            html = VERIFY_PAGE.replace("%ERROR%", f'<div class="err">{e}</div>')
            return render_template_string(html, phone=phone)
        finally:
            await client.disconnect()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_verify())

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    u = session["user"]
    return f"""
    <body dir="rtl" style="background:#0a0a0f;color:#fff;font-family:system-ui;padding:25px">
    <h1>تم تسجيل الدخول ✅</h1>
    <div style="background:#1c1c24;padding:20px;border-radius:16px">
    ID: {u['id']}<br>الاسم: {u['first_name']}<br>اليوزر: @{u.get('username','')}<br>الرقم: {u.get('phone','')}<br><br>
    جلسة تليجرام محفوظة عن طريق api_id: {API_ID}<br><br>
    <a href="/logout" style="color:#2AABEE">خروج</a>
    </div></body>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/health")
def health():
    return jsonify(ok=True, api_id=bool(API_ID), api_hash=bool(API_HASH))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
