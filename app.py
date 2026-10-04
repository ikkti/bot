import os
import io
import json
import time
import random
import string
import logging
import base64
import mimetypes
import re
from functools import wraps

import requests
from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from flask_cors import CORS
import telebot
from telebot import types

# Optional document readers
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    from docx import Document as DocxDocument
except Exception:
    DocxDocument = None

try:
    import openpyxl
except Exception:
    openpyxl = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    from captcha.image import ImageCaptcha
except Exception:
    ImageCaptcha = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# Configuration (متوافق مع Fly.io)
# ============================================================
# دعم كلا الاسمين للمتغير
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "").strip()
ADMIN = int(os.environ.get("ADMIN_ID", "0") or "0")

# Cloudflare AI
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
CLOUDFLARE_MODEL = os.environ.get("CLOUDFLARE_MODEL", "@cf/meta/llama-3-8b-instruct").strip()
CLOUDFLARE_VISION_MODEL = os.environ.get(
    "CLOUDFLARE_VISION_MODEL", "@cf/meta/llama-3.2-11b-vision-instruct"
).strip()

DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "admin123").strip()
SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()

# استخراج رابط التطبيق تلقائياً على Fly.io أو استخدام المخصص
APP_NAME = os.environ.get("FLY_APP_NAME", "")
DEFAULT_HOST = f"https://{APP_NAME}.fly.dev" if APP_NAME else "http://localhost:8080"
WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", DEFAULT_HOST).rstrip("/")
WEBHOOK_PATH = f"/webhook/{TOKEN}" if TOKEN else "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

BOT_NAME = os.environ.get("BOT_NAME", "مريم محمد جاسم الياسري💙🎀")
ENDPOINT_PATH = "/api/bot"

# مسار قاعدة البيانات
DB_DIR = os.environ.get("DB_DIR", os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(DB_DIR, "bot_data.json")

MAX_DOWNLOAD_MB = int(os.environ.get("MAX_DOWNLOAD_MB", "15"))
MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "60000"))

if not TOKEN:
    logger.warning("TELEGRAM_BOT_TOKEN is missing. Bot will not function.")

os.makedirs(DB_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = SECRET_KEY or os.urandom(32)
CORS(app)

bot = telebot.TeleBot(TOKEN, threaded=False) if TOKEN else None

DEFAULT_DB = {
    "users": [],
    "notify": True,
    "superadmins": [ADMIN] if ADMIN else [],
    "api_keys": {},
    "pending_admins": [],
    "approved_admins": [ADMIN] if ADMIN else [],
    "verify_enabled": False,
}

conversations = {}
pending_verifications = {}

# ============================================================
# Database
# ============================================================
def load_db():
    try:
        if not os.path.exists(DB):
            save_db(DEFAULT_DB.copy())
            return DEFAULT_DB.copy()
        with open(DB, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, value in DEFAULT_DB.items():
            if key not in data:
                data[key] = value.copy() if isinstance(value, list) else value.copy() if isinstance(value, dict) else value
        return data
    except Exception as exc:
        logger.exception("DB LOAD ERROR: %s", exc)
        return DEFAULT_DB.copy()

def save_db(data):
    try:
        tmp = DB + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DB)
    except Exception as exc:
        logger.exception("DB SAVE ERROR: %s", exc)

def is_superadmin(uid):
    data = load_db()
    return uid in data.get("superadmins", []) or (ADMIN and uid == ADMIN)

def is_approved_admin(uid):
    data = load_db()
    return uid in data.get("approved_admins", []) or is_superadmin(uid)

def generate_api_key():
    chars = string.ascii_letters + string.digits
    return "FM.AI_" + "".join(random.choice(chars) for _ in range(30))

def get_dashboard_api_key():
    data = load_db()
    keys = list(data.get("api_keys", {}).keys())
    if keys:
        return keys[0]
    key = generate_api_key()
    data.setdefault("api_keys", {})[key] = ADMIN or 0
    save_db(data)
    return key

# ============================================================
# AI
# ============================================================
def cloudflare_url(model):
    if not CLOUDFLARE_ACCOUNT_ID or not model:
        return None
    return f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{model}"

def ask_ai(text, system_prompt=None, conversation_id=None, model=None, extra_messages=None):
    api_url = cloudflare_url(model or CLOUDFLARE_MODEL)
    if not api_url or not CLOUDFLARE_API_TOKEN:
        return "⚠️ لم يتم ضبط مفاتيح Cloudflare بنجاح."

    system_prompt = system_prompt or (
        f"اسمك {BOT_NAME}. أجب بالعربية غالباً، ويمكنك استخدام الإنجليزية داخل الكود عند الحاجة. "
        "كن دقيقاً وودوداً."
    )
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    messages = [{"role": "system", "content": system_prompt}]
    if conversation_id and conversation_id in conversations:
        messages.extend(conversations[conversation_id][-20:])
    if extra_messages:
        messages.extend(extra_messages)
    messages.append({"role": "user", "content": text})
    payload = {"messages": messages, "max_tokens": 1800}

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=90)
        data = response.json()
        if not data.get("success"):
            logger.error("Cloudflare error: %s", data.get("errors"))
            return None
        result = data.get("result") or {}
        reply = result.get("response")
        if not reply and result.get("choices"):
            reply = result["choices"][0].get("message", {}).get("content")
        if reply and conversation_id:
            conversations.setdefault(conversation_id, [])
            conversations[conversation_id].extend([
                {"role": "user", "content": text},
                {"role": "assistant", "content": reply},
            ])
            conversations[conversation_id] = conversations[conversation_id][-20:]
        return reply
    except Exception as exc:
        logger.exception("Cloudflare AI ERROR: %s", exc)
        return None

def ask_vision(prompt, image_bytes, mime_type="image/jpeg"):
    api_url = cloudflare_url(CLOUDFLARE_VISION_MODEL)
    if not api_url or not CLOUDFLARE_API_TOKEN:
        return None
    b64 = base64.b64encode(image_bytes).decode("ascii")
    image_url = f"data:{mime_type};base64,{b64}"
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [
            {"role": "system", "content": f"أنت مساعد رؤية اسمه {BOT_NAME}. حلل الصور بدقة وأجب بالعربية."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]},
        ],
        "max_tokens": 1800,
    }
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=90)
        data = response.json()
        if not data.get("success"):
            logger.error("Vision error: %s", data.get("errors"))
            return None
        result = data.get("result") or {}
        if result.get("response"):
            return result["response"]
        if result.get("choices"):
            return result["choices"][0].get("message", {}).get("content")
    except Exception as exc:
        logger.exception("Vision ERROR: %s", exc)
    return None

# ============================================================
# File / Image analysis
# ============================================================
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".htm", ".css", ".scss", ".sass",
    ".json", ".xml", ".yaml", ".yml", ".md", ".txt", ".sql", ".php", ".java", ".kt",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb", ".swift", ".dart", ".lua",
    ".sh", ".bash", ".bat", ".ps1", ".vue", ".svelte", ".env", ".ini", ".toml", ".conf",
}

def safe_filename(name):
    name = os.path.basename(name or "file")
    return re.sub(r"[^\w.\- ()\[\]]", "_", name, flags=re.UNICODE)

def extract_text_from_file(filename, raw):
    ext = os.path.splitext(filename.lower())[1]
    if ext in CODE_EXTENSIONS or (not ext and len(raw) < 2_000_000):
        for encoding in ("utf-8", "utf-8-sig", "cp1256", "latin-1"):
            try:
                return raw.decode(encoding), "text/code"
            except Exception:
                pass

    if ext == ".pdf" and PdfReader:
        try:
            reader = PdfReader(io.BytesIO(raw))
            parts = [(page.extract_text() or "") for page in reader.pages[:30]]
            return "\n\n".join(parts), "PDF"
        except Exception as exc:
            return f"تعذر قراءة PDF: {exc}", "PDF"

    if ext == ".docx" and DocxDocument:
        try:
            doc = DocxDocument(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs), "DOCX"
        except Exception as exc:
            return f"تعذر قراءة DOCX: {exc}", "DOCX"

    if ext == ".xlsx" and openpyxl:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            parts = []
            for ws in wb.worksheets[:10]:
                parts.append(f"[Sheet: {ws.title}]")
                for row in ws.iter_rows(max_row=200, values_only=True):
                    parts.append(" | ".join("" if v is None else str(v) for v in row))
            return "\n".join(parts), "XLSX"
        except Exception as exc:
            return f"تعذر قراءة XLSX: {exc}", "XLSX"

    return None, "unsupported"

def download_telegram_file(file_id):
    if not bot:
        raise RuntimeError("Telegram bot is not configured")
    info = bot.get_file(file_id)
    size = getattr(info, "file_size", 0) or 0
    if size > MAX_DOWNLOAD_MB * 1024 * 1024:
        raise ValueError(f"حجم الملف أكبر من الحد المسموح ({MAX_DOWNLOAD_MB}MB).")
    return bot.download_file(info.file_path), info.file_path

def analyze_document(filename, raw, caption=""):
    text, kind = extract_text_from_file(filename, raw)
    if text is None:
        return f"⚠️ لا أستطيع قراءة نوع الملف `{filename}` حالياً."
    text = text[:MAX_TEXT_CHARS]
    prompt = (
        f"حلل الملف التالي: {filename}\nنوع المحتوى: {kind}\n"
        f"طلب المستخدم: {caption or 'حلل الملف واشرح أهم ما فيه والمشاكل والاقتراحات.'}\n\n"
        f"محتوى الملف:\n```\n{text}\n```"
    )
    return ask_ai(prompt)

# ============================================================
# Bot Keyboards
# ============================================================
def main_menu(is_super=False):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("💬 محادثة", callback_data="chat"),
           types.InlineKeyboardButton("❓ مساعدة", callback_data="help"))
    kb.add(types.InlineKeyboardButton("👨‍💻 المطورين", callback_data="dev"))
    if is_super:
        kb.add(types.InlineKeyboardButton("👑 المشرفين", callback_data="superadmin"))
    return kb

def back_button():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back"))
    return kb

def dev_menu():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("🔑 إنشاء رمز API", callback_data="gen_api"),
           types.InlineKeyboardButton("📖 دليل المطورين", callback_data="dev_guide"),
           types.InlineKeyboardButton("🔙 رجوع", callback_data="back"))
    return kb

def superadmin_menu():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("📢 إذاعة", callback_data="broadcast_menu"),
           types.InlineKeyboardButton("👥 المستخدمين", callback_data="users_count"),
           types.InlineKeyboardButton("🔙 رجوع", callback_data="back"))
    return kb

def broadcast_type_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    for label, key in [("📝 نص", "text"), ("🖼️ صورة", "photo"), ("🎥 فيديو", "video")]:
        kb.add(types.InlineKeyboardButton(label, callback_data=f"bcast_{key}"))
    kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="superadmin"))
    return kb

def approval_buttons(uid):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("✅ موافقة", callback_data=f"approve_{uid}"),
           types.InlineKeyboardButton("❌ رفض", callback_data=f"reject_{uid}"))
    return kb

# ============================================================
# Webhook Route & Server Endpoints
# ============================================================
@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    if not bot:
        return "BOT_TOKEN missing", 503
    try:
        update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
        bot.process_new_updates([update])
        return "OK", 200
    except Exception as exc:
        logger.exception("Webhook error: %s", exc)
        return "Error", 500

@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "bot": BOT_NAME,
        "webhook_url": WEBHOOK_URL,
        "ai_connected": bool(CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID)
    })

@app.route("/setwebhook")
def set_webhook_route():
    if not bot:
        return jsonify({"ok": False, "error": "Token missing"}), 503
    try:
        bot.remove_webhook()
        time.sleep(0.5)
        res = bot.set_webhook(url=WEBHOOK_URL)
        return jsonify({"ok": True, "webhook_url": WEBHOOK_URL, "result": bool(res)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

@app.route("/ping")
def ping():
    return jsonify({"status": "ok", "bot": BOT_NAME}), 200

# ============================================================
# Telegram Handlers
# ============================================================
def remember_user(user):
    data = load_db()
    if user.id not in data["users"]:
        data["users"].append(user.id)
        save_db(data)
        if data.get("notify", True):
            for aid in data.get("superadmins", []):
                try:
                    bot.send_message(aid, f"🆕 مستخدم جديد: {user.first_name}\n🆔: `{user.id}`", parse_mode="Markdown")
                except Exception:
                    pass

def send_long(chat_id, text):
    text = text or "لا يوجد رد."
    for i in range(0, len(text), 4000):
        bot.send_message(chat_id, text[i:i + 4000])

if bot:
    @bot.message_handler(commands=["start"])
    def start(message):
        remember_user(message.from_user)
        welcome = (
            f"🌟 أهلاً بك {message.from_user.first_name} في {BOT_NAME}!\n\n"
            "🤖 أستطيع مساعدتك في الإجابة عن الأسئلة، وتحليل الكود والملفات والصور."
        )
        bot.send_message(message.chat.id, welcome, reply_markup=main_menu(is_super=is_superadmin(message.from_user.id)))

    @bot.callback_query_handler(func=lambda c: True)
    def callbacks(call):
        cid, mid, data_cb = call.message.chat.id, call.message.message_id, call.data
        d = load_db()
        is_super = is_superadmin(cid)
        try:
            if data_cb == "chat":
                bot.edit_message_text("💬 أرسل استفسارك الآن مباشرة وسأجيبك فوراً.", cid, mid, reply_markup=back_button())
            elif data_cb == "help":
                bot.edit_message_text("📖 أرسل سؤالاً، صورة، أو ملف كود/مستند وسأقوم بتحليله.", cid, mid, reply_markup=back_button())
            elif data_cb == "dev":
                if not is_approved_admin(cid):
                    if cid not in d.get("pending_admins", []):
                        d.setdefault("pending_admins", []).append(cid); save_db(d)
                        for aid in d.get("superadmins", []):
                            try: bot.send_message(aid, f"📩 طلب صلاحية مطور\n🆔 `{cid}`", parse_mode="Markdown", reply_markup=approval_buttons(cid))
                            except Exception: pass
                    bot.edit_message_text("📩 تم إرسال طلبك للإدارة.", cid, mid, reply_markup=back_button())
                else:
                    bot.edit_message_text("👨‍💻 لوحة المطورين", cid, mid, reply_markup=dev_menu())
            elif data_cb == "gen_api":
                if not is_approved_admin(cid): return bot.answer_callback_query(call.id, "⛔ غير مصرح")
                key = generate_api_key(); d.setdefault("api_keys", {})[key] = cid; save_db(d)
                bot.edit_message_text(f"🔑 مفتاح API الخاص بك:\n\n`{key}`", cid, mid, parse_mode="Markdown", reply_markup=dev_menu())
            elif data_cb == "superadmin":
                if not is_super: return bot.answer_callback_query(call.id, "⛔ غير مصرح")
                bot.edit_message_text("👑 لوحة تحكم الإدارة", cid, mid, reply_markup=superadmin_menu())
            elif data_cb == "users_count":
                if is_super:
                    bot.edit_message_text(f"👥 عدد المستخدمين: {len(d['users'])}", cid, mid, reply_markup=superadmin_menu())
            elif data_cb == "broadcast_menu":
                if is_super: bot.edit_message_text("📢 اختر نوع الإذاعة:", cid, mid, reply_markup=broadcast_type_menu())
            elif data_cb.startswith("bcast_"):
                if not is_super: return
                btype = data_cb[6:]
                msg = bot.edit_message_text(f"📝 أرسل {btype} الإذاعة:", cid, mid)
                bot.register_next_step_handler(msg, lambda m: broadcast(m, btype))
            elif data_cb.startswith("approve_"):
                uid = int(data_cb[8:])
                if not is_super: return
                d.setdefault("approved_admins", []).append(uid)
                if uid in d.get("pending_admins", []): d["pending_admins"].remove(uid)
                save_db(d); bot.edit_message_text("✅ تمت الموافقة.", cid, mid)
                try: bot.send_message(uid, "✅ تمت ترقيتك لمطور!")
                except Exception: pass
            elif data_cb.startswith("reject_"):
                uid = int(data_cb[7:])
                if not is_super: return
                if uid in d.get("pending_admins", []): d["pending_admins"].remove(uid)
                save_db(d); bot.edit_message_text("❌ تم الرفض.", cid, mid)
            elif data_cb == "back":
                bot.edit_message_text("🌟 القائمة الرئيسية:", cid, mid, reply_markup=main_menu(is_super=is_super))
        finally:
            try: bot.answer_callback_query(call.id)
            except Exception: pass

    def broadcast(msg, btype):
        d = load_db(); ok = 0
        for uid in d.get("users", []):
            try:
                if btype == "text": bot.send_message(uid, f"📢 {msg.text}")
                elif btype == "photo" and msg.photo: bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption or "📢")
                elif btype == "video" and msg.video: bot.send_video(uid, msg.video.file_id, caption=msg.caption or "📢")
                ok += 1
            except Exception:
                pass
        bot.reply_to(msg, f"✅ تم الإرسال إلى {ok} مستخدم.")

    @bot.message_handler(content_types=["photo"])
    def handle_photo(message):
        remember_user(message.from_user)
        try:
            bot.send_chat_action(message.chat.id, "typing")
            photo = message.photo[-1]
            raw, _ = download_telegram_file(photo.file_id)
            prompt = message.caption or "صف الصورة بدقة وحلل التفاصيل."
            reply = ask_vision(prompt, raw, "image/jpeg")
            send_long(message.chat.id, reply or "⚠️ لم أتمكن من استخراج تفاصيل الصورة.")
        except Exception as exc:
            bot.reply_to(message, f"⚠️ حدث خطأ أثناء المعالجة: {exc}")

    @bot.message_handler(content_types=["document"])
    def handle_document(message):
        remember_user(message.from_user)
        try:
            bot.send_chat_action(message.chat.id, "typing")
            filename = safe_filename(message.document.file_name or "file")
            raw, _ = download_telegram_file(message.document.file_id)
            bot.send_message(message.chat.id, f"📎 جاري قراءة وتحليل `{filename}`...", parse_mode="Markdown")
            reply = analyze_document(filename, raw, message.caption or "")
            send_long(message.chat.id, reply)
        except Exception as exc:
            bot.reply_to(message, f"⚠️ خطأ: {exc}")

    @bot.message_handler(content_types=["text"])
    def handle_text(message):
        if message.text.startswith("/"): return
        remember_user(message.from_user)
        try: bot.send_chat_action(message.chat.id, "typing")
        except Exception: pass
        reply = ask_ai(message.text, conversation_id=f"tg-{message.from_user.id}")
        send_long(message.chat.id, reply or "⚠️ حدث خطأ مؤقت في الاتصال بالذكاء الاصطناعي.")

# ============================================================
# التشغيل التلقائي عند بدء السيرفر
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    # محاولة ربط الويب هوك تلقائياً إذا كان النطاق متوفراً
    if bot and "fly.dev" in WEBHOOK_URL:
        try:
            bot.remove_webhook()
            bot.set_webhook(url=WEBHOOK_URL)
            logger.info("Webhook linked to: %s", WEBHOOK_URL)
        except Exception as e:
            logger.warning("Could not set webhook automatically: %s", e)
    app.run(host="0.0.0.0", port=port)
