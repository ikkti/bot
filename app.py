import os
import json
import requests
from flask import Flask, request, jsonify
from supabase import create_client

app = Flask(__name__)

# نقرأ المتغير الواحد اللي ضفته
try:
    CONFIG = json.loads(os.getenv("APP_CONFIG", "{}"))
except:
    CONFIG = {}

SUPABASE_URL = CONFIG.get("supabase_url")
SUPABASE_KEY = CONFIG.get("supabase_key")
BOT_TOKEN = CONFIG.get("bot_token")
CF_TOKEN = CONFIG.get("cf_token")
API_ID = CONFIG.get("api_id")
API_HASH = CONFIG.get("api_hash")

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else None

@app.route("/")
def home():
    return jsonify({
        "app": "kruri-valverde.com",
        "status": "سيرفر حقيقي شغال ✅",
        "supabase_connected": bool(supabase),
        "telegram_bot": bool(BOT_TOKEN),
        "endpoints": ["/health", "/api/chat", "/webhook"]
    })

@app.route("/health")
def health():
    try:
        if supabase:
            supabase.table("messages").select("id").limit(1).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# هذا هو الـ API الحقيقي اللي يربط تليجرام + ذكاء كلاودفلير + سوبربيس
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    user_msg = data.get("message", "")
    user_id = data.get("user_id", "web_user")

    # 1. نحفظ رسالة المستخدم بـ Supabase
    if supabase:
        supabase.table("messages").insert({"user_id": user_id, "role": "user", "content": user_msg}).execute()

    # 2. ندزها لـ Cloudflare AI
    ai_reply = "ما قدرت اتصل بالذكاء الاصطناعي"
    if CF_TOKEN:
        try:
            r = requests.post(
                "https://api.cloudflare.com/client/v4/accounts/YOUR_ACCOUNT_ID/ai/run/@cf/meta/llama-3-8b-instruct",
                headers={"Authorization": f"Bearer {CF_TOKEN}"},
                json={"prompt": user_msg},
                timeout=20
            )
            ai_reply = r.json().get("result", {}).get("response", ai_reply)
        except Exception as e:
            ai_reply = f"خطأ AI: {e}"

    # 3. نحفظ رد البوت
    if supabase:
        supabase.table("messages").insert({"user_id": user_id, "role": "bot", "content": ai_reply}).execute()

    return jsonify({"reply": ai_reply})

# ويب هوك لتليجرام
@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.json
    if not update or not TELEGRAM_API:
        return jsonify({"ok": True})
    
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if chat_id and text:
        # ترد نفس فكرة /api/chat بس عبر تليجرام
        requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": f"وصلتني: {text} - السيرفر الجديد شغال على kruri-valverde.com"})

    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
