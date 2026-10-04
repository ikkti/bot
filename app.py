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

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot

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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# Configuration
# ============================================================
TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")).strip()

raw_admin = os.environ.get("ADMIN_ID", "0").strip()
ADMIN = int(raw_admin) if raw_admin.isdigit() else 0

CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
CLOUDFLARE_MODEL = os.environ.get("CLOUDFLARE_MODEL", "@cf/meta/llama-3-8b-instruct").strip()
CLOUDFLARE_VISION_MODEL = os.environ.get(
    "CLOUDFLARE_VISION_MODEL", "@cf/meta/llama-3.2-11b-vision-instruct"
).strip()

SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()

APP_NAME = os.environ.get("FLY_APP_NAME", "")
DEFAULT_HOST = f"https://{APP_NAME}.fly.dev" if APP_NAME else "http://localhost:8080"
WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", DEFAULT_HOST).rstrip("/")
WEBHOOK_PATH = f"/webhook/{TOKEN}" if TOKEN else "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

BOT_NAME = os.environ.get("BOT_NAME", "مريم محمد جاسم الياسري💙🎀")
ENDPOINT_PATH = "/api/bot"

DB_DIR = os.environ.get("DB_DIR", os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(DB_DIR, "bot_data.json")

MAX_DOWNLOAD_MB = int(os.environ.get("MAX_DOWNLOAD_MB", "15"))
MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "60000"))

os.makedirs(DB_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = SECRET_KEY or os.urandom(32)
CORS(app)

bot = telebot.TeleBot(TOKEN, threaded=False) if TOKEN else None

DEFAULT_DB = {
    "users": [],
    "notify": True,
}

conversations = {}

# ============================================================
# Database Functions
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
                data[key] = value.copy() if isinstance(value, list) else value
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


def remember_user(user):
    data = load_db()
    if user.id not in data["users"]:
        data["users"].append(user.id)
        save_db(data)
        if data.get("notify", True) and ADMIN:
            try:
                bot.send_message(
                    ADMIN,
                    f"🆕 مستخدم جديد: {user.first_name}\n🆔: `{user.id}`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

# ============================================================
# AI Functions
# ============================================================
def cloudflare_url(model):
    if not CLOUDFLARE_ACCOUNT_ID or not model:
        return None
    return f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{model}"


def ask_ai(text, system_prompt=None, conversation_id=None, model=None):
    api_url = cloudflare_url(model or CLOUDFLARE_MODEL)
    if not api_url or not CLOUDFLARE_API_TOKEN:
        return "⚠️ الذكاء الاصطناعي غير مضبوط حالياً."

    system_prompt = system_prompt or (
        f"اسمك {BOT_NAME}. أنت مساعد ذكاء اصطناعي ذكي، ودود، ومتعاون. أجب دائماً بالعربية بدقة وبأسلوب طبيعي ولبق."
    )
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    messages = [{"role": "system", "content": system_prompt}]
    if conversation_id and conversation_id in conversations:
        messages.extend(conversations[conversation_id][-20:])
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
            {"role": "system", "content": f"أنت مساعد رؤية اسمه {BOT_NAME}. حلل الصور بالعربية بدقة."},
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
            return None
        result = data.get("result") or {}
        return result.get("response") or (result.get("choices", [{}])[0].get("message", {}).get("content"))
    except Exception as exc:
        logger.exception("Vision ERROR: %s", exc)
        return None

# ============================================================
# File Helpers
# ============================================================
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".htm", ".css", ".scss",
    ".json", ".xml", ".yaml", ".yml", ".md", ".txt", ".sql", ".php", ".java",
    ".kt", ".c", ".h", ".cpp", ".cs", ".go", ".rs", ".rb", ".dart", ".sh",
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
            return "\n\n".join([(p.extract_text() or "") for p in reader.pages[:30]]), "PDF"
        except Exception as e:
            return f"تعذر قراءة PDF: {e}", "PDF"
    if ext == ".docx" and DocxDocument:
        try:
            doc = DocxDocument(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs), "DOCX"
        except Exception as e:
            return f"تعذر قراءة DOCX: {e}", "DOCX"
    if ext == ".xlsx" and openpyxl:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            parts = []
            for ws in wb.worksheets[:5]:
                for row in ws.iter_rows(max_row=100, values_only=True):
                    parts.append(" | ".join("" if v is None else str(v) for v in row))
            return "\n".join(parts), "XLSX"
        except Exception as e:
            return f"تعذر قراءة XLSX: {e}", "XLSX"
    return None, "unsupported"


def download_telegram_file(file_id):
    if not bot:
        raise RuntimeError("Bot not configured")
    info = bot.get_file(file_id)
    size = getattr(info, "file_size", 0) or 0
    if size > MAX_DOWNLOAD_MB * 1024 * 1024:
        raise ValueError(f"حجم الملف أكبر من الحد المسموح ({MAX_DOWNLOAD_MB}MB).")
    return bot.download_file(info.file_path), info.file_path


def send_long(chat_id, text):
    text = text or "لا يوجد رد."
    for i in range(0, len(text), 4000):
        bot.send_message(chat_id, text[i:i + 4000])

# ============================================================
# Flask Endpoints
# ============================================================
@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    if not bot:
        return "Bot disabled", 503
    try:
        raw = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(raw)
        if update:
            bot.process_new_updates([update])
        return "OK", 200
    except Exception as exc:
        logger.exception("Webhook error: %s", exc)
        return "Error", 500


@app.route("/")
def index():
    return jsonify({
        "status": "online",
        "bot": BOT_NAME,
        "webhook": WEBHOOK_URL
    })


@app.route("/setwebhook")
def set_webhook():
    if not bot:
        return jsonify({"ok": False, "error": "Token missing"}), 503
    try:
        bot.remove_webhook()
        time.sleep(0.5)
        res = bot.set_webhook(url=WEBHOOK_URL)
        return jsonify({"ok": True, "webhook_url": WEBHOOK_URL, "result": bool(res)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

# ============================================================
# Telegram Handlers (Pure Conversational Bot)
# ============================================================
if bot:
    @bot.message_handler(commands=["start"])
    def cmd_start(message):
        remember_user(message.from_user)
        try:
            bot.send_chat_action(message.chat.id, "typing")
        except Exception:
            pass

        # رسالة ترحيبية يولدها الذكاء الاصطناعي مباشرة
        prompt = (
            f"مستخدم جديد بدأ المحادثة معك. اسمه: {message.from_user.first_name}.\n"
            f"رحب به ترحيباً مميزاً ودافئاً باسمك ({BOT_NAME})، وأخبره باختصار أنك جاهز لمساعدته "
            "في أي استفسار، وتحليل الكود، وقراءة الملفات البرمجية والمستندات (PDF/DOCX) وتحليل الصور عند إرسالها."
        )
        reply = ask_ai(prompt, conversation_id=f"tg-{message.from_user.id}")
        send_long(message.chat.id, reply or f"أهلاً بك يا {message.from_user.first_name} في {BOT_NAME}! كيف يمكنني مساعدتك اليوم؟")

    @bot.message_handler(content_types=["photo"])
    def handle_photo(message):
        remember_user(message.from_user)
        try:
            bot.send_chat_action(message.chat.id, "typing")
            photo = message.photo[-1]
            raw, _ = download_telegram_file(photo.file_id)
            prompt = message.caption or "صف الصورة بدقة وحلل محتواها وما يظهر فيها بالعربية."
            reply = ask_vision(prompt, raw, "image/jpeg")
            send_long(message.chat.id, reply or "⚠️ لم أتمكن من استخراج تفاصيل الصورة.")
        except Exception as exc:
            bot.reply_to(message, f"⚠️ خطأ أثناء تحليل الصورة: {exc}")

    @bot.message_handler(content_types=["document"])
    def handle_document(message):
        remember_user(message.from_user)
        try:
            bot.send_chat_action(message.chat.id, "typing")
            filename = safe_filename(message.document.file_name or "file")
            raw, _ = download_telegram_file(message.document.file_id)
            bot.send_message(message.chat.id, f"📎 جاري تحليل `{filename}`...", parse_mode="Markdown")
            text, kind = extract_text_from_file(filename, raw)
            if not text:
                bot.send_message(message.chat.id, "⚠️ نوع الملف غير مدعوم للتحليل النصي.")
                return
            prompt = f"حلل الملف التالي ({filename}) واشرح محتواه وأهم النقاط فيه:\n\n{text[:MAX_TEXT_CHARS]}"
            reply = ask_ai(prompt)
            send_long(message.chat.id, reply or "⚠️ تعذر التحليل.")
        except Exception as exc:
            bot.reply_to(message, f"⚠️ حدث خطأ: {exc}")

    @bot.message_handler(content_types=["text"])
    def handle_text(message):
        if message.text.startswith("/"):
            return
        remember_user(message.from_user)
        try:
            bot.send_chat_action(message.chat.id, "typing")
        except Exception:
            pass
        reply = ask_ai(message.text, conversation_id=f"tg-{message.from_user.id}")
        send_long(message.chat.id, reply or "⚠️ تعذر الحصول على رد من الذكاء الاصطناعي حالياً.")

# ============================================================
# Entry Point
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
