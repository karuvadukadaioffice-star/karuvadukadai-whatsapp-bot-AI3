import os
import hmac
import json
import requests
from hashlib import sha256
from flask import Flask, request, jsonify

app = Flask(__name__)

# =========================================================
# ENV VARIABLES (MATCH RENDER EXACTLY)
# =========================================================
INTERAKT_API_KEY = os.getenv("INTERAKT_API_KEY")
INTERAKT_SECRET = os.getenv("INTERAKT_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PORT = int(os.getenv("PORT", 10000))

# =========================================================
# SAFETY CHECK (LOG ON START)
# =========================================================
print("ENV CHECK:")
print("INTERAKT_API_KEY:", "OK" if INTERAKT_API_KEY else "MISSING")
print("INTERAKT_SECRET:", "OK" if INTERAKT_SECRET else "MISSING")
print("OPENAI_API_KEY:", "OK" if OPENAI_API_KEY else "MISSING")

# =========================================================
# SIGNATURE VERIFICATION (INTERAKT)
# =========================================================
def verify_interakt_signature(secret_key, payload, received_signature):
    if not secret_key or not received_signature:
        return False

    computed = hmac.new(
        secret_key.encode("utf-8"),
        payload,
        sha256
    ).hexdigest()

    return f"sha256={computed}" == received_signature


# =========================================================
# OPENAI CALL
# =========================================================
def get_ai_reply(user_message):
    url = "https://api.openai.com/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are KaruvaduKadai WhatsApp customer support.\n"
                    "Reply in simple Tamil-English mix.\n"
                    "Be polite, short, and helpful.\n"
                    "If order tracking is asked, guide politely."
                )
            },
            {
                "role": "user",
                "content": user_message
            }
        ],
        "temperature": 0.3
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"]


# =========================================================
# SEND MESSAGE VIA INTERAKT
# =========================================================
def send_whatsapp_message(phone, text):
    url = "https://api.interakt.ai/v1/public/message/"

    headers = {
        "Authorization": f"Bearer {INTERAKT_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "receiver": phone,
        "type": "text",
        "message": {"text": text}
    }

    r = requests.post(url, headers=headers, json=payload, timeout=30)
    print("INTERAKT SEND STATUS:", r.status_code)
    print("INTERAKT RESPONSE:", r.text)


# =========================================================
# HOME
# =========================================================
@app.route("/", methods=["GET"])
def home():
    return "Interakt WhatsApp AI Bot is LIVE 🚀", 200


# =========================================================
# WEBHOOK
# =========================================================
@app.route("/webhook", methods=["POST"])
def webhook():
    raw_body = request.get_data()
    signature = request.headers.get("Interakt-Signature")

    # Verify signature
    if not verify_interakt_signature(INTERAKT_SECRET, raw_body, signature):
        print("❌ Invalid Interakt Signature")
        return jsonify({"error": "Invalid signature"}), 403

    data = request.json
    print("WEBHOOK DATA:", json.dumps(data, indent=2))

    message = data.get("message", {})
    phone = message.get("from")
    content_type = message.get("message_content_type")

    if content_type != "text":
        send_whatsapp_message(
            phone,
            "🙏 Please send text message only. Images will be supported soon."
        )
        return jsonify({"status": "ignored"}), 200

    user_text = message.get("message", "")

    if not user_text:
        return jsonify({"status": "empty"}), 200

    try:
        ai_reply = get_ai_reply(user_text)
        send_whatsapp_message(phone, ai_reply)
    except Exception as e:
        print("❌ AI ERROR:", str(e))
        send_whatsapp_message(
            phone,
            "⚠️ Sorry, service is busy. Please try again in few minutes."
        )

    return jsonify({"status": "ok"}), 200


# =========================================================
# START SERVER
# =========================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
