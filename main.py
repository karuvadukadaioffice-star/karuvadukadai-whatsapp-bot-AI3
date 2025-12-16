import os
import hmac
import json
import requests
from hashlib import sha256
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==============================
# ENVIRONMENT VARIABLES
# ==============================
INTERAKT_API_KEY = os.getenv("INTERAKT_API_KEY")
INTERAKT_SECRET = os.getenv("INTERAKT_SECRET")  # ✅ FIXED NAME
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ==============================
# BASIC HEALTH CHECK
# ==============================
@app.route("/", methods=["GET"])
def home():
    return "Interakt WhatsApp AI Bot is LIVE 🚀", 200


# ==============================
# VERIFY INTERAKT SIGNATURE
# ==============================
def verify_interakt_signature(secret_key, payload, received_signature):
    if not secret_key:
        print("❌ INTERAKT_SECRET is missing")
        return False

    computed = hmac.new(
        secret_key.encode("utf-8"),
        payload,
        sha256
    ).hexdigest()

    expected_signature = f"sha256={computed}"
    return hmac.compare_digest(expected_signature, received_signature)


# ==============================
# CALL OPENAI
# ==============================
def ask_openai(user_message):
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
                    "You are a customer support assistant for Karuvadukadai.com. "
                    "Reply politely, briefly, and clearly. "
                    "If question is about orders, shipping, fish, dry fish, or delivery, "
                    "answer like a real support agent."
                )
            },
            {
                "role": "user",
                "content": user_message
            }
        ],
        "temperature": 0.4
    }

    response = requests.post(url, headers=headers, json=payload, timeout=20)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


# ==============================
# SEND MESSAGE TO INTERAKT
# ==============================
def send_whatsapp_message(phone, text):
    url = "https://api.interakt.ai/v1/public/message"

    headers = {
        "Authorization": f"Bearer {INTERAKT_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "receiver": phone,
        "type": "text",
        "message": {
            "text": text
        }
    }

    requests.post(url, headers=headers, json=payload, timeout=10)


# ==============================
# WEBHOOK ENDPOINT
# ==============================
@app.route("/webhook", methods=["POST"])
def webhook():
    raw_body = request.data
    signature = request.headers.get("Interakt-Signature", "")

    # 🔐 VERIFY SIGNATURE
    if not verify_interakt_signature(INTERAKT_SECRET, raw_body, signature):
        print("❌ Invalid Interakt Signature")
        return jsonify({"error": "Invalid signature"}), 401

    data = request.json
    print("📩 Incoming:", json.dumps(data, indent=2))

    try:
        message = data["data"]["message"]
        sender = data["data"]["from"]

        if message["type"] != "text":
            return jsonify({"status": "ignored"}), 200

        user_text = message["text"]

        ai_reply = ask_openai(user_text)
        send_whatsapp_message(sender, ai_reply)

    except Exception as e:
        print("❌ Processing error:", str(e))

    return jsonify({"status": "ok"}), 200


# ==============================
# START SERVER
# ==============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
