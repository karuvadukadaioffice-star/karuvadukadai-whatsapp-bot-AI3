import os
import json
import hmac
from hashlib import sha256
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ===== ENVIRONMENT VARIABLES =====
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
INTERAKT_API_KEY = os.environ.get("INTERAKT_API_KEY")
INTERAKT_WEBHOOK_SECRET = os.environ.get("INTERAKT_WEBHOOK_SECRET")

INTERAKT_SEND_URL = "https://api.interakt.ai/v1/public/message"


# ===== SIGNATURE VERIFICATION =====
def verify_interakt_signature(secret_key, payload, received_signature):
    computed = hmac.new(
        secret_key.encode("utf-8"),
        payload,
        sha256
    ).hexdigest()
    return f"sha256={computed}" == received_signature


# ===== OPENAI CALL =====
def ask_openai(user_text):
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4.1-mini",
        "input": [
            {
                "role": "system",
                "content": (
                    "You are Karuvadukadai customer support assistant. "
                    "Reply politely, shortly, and clearly. "
                    "If order tracking is asked, ask for order number."
                )
            },
            {
                "role": "user",
                "content": user_text
            }
        ]
    }

    r = requests.post(url, headers=headers, json=payload, timeout=20)
    r.raise_for_status()
    data = r.json()

    for output in data.get("output", []):
        if output.get("type") == "message":
            for c in output.get("content", []):
                if c.get("type") == "output_text":
                    return c.get("text")

    return "Sorry, please try again later."


# ===== SEND MESSAGE VIA INTERAKT =====
def send_whatsapp_message(phone, text):
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

    r = requests.post(INTERAKT_SEND_URL, headers=headers, json=payload, timeout=10)
    print("Interakt send response:", r.status_code, r.text)


# ===== ROUTES =====
@app.route("/", methods=["GET"])
def home():
    return "Interakt WhatsApp AI Bot is LIVE 🚀", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    raw_body = request.data
    signature = request.headers.get("Interakt-Signature", "")

    if not verify_interakt_signature(
        INTERAKT_WEBHOOK_SECRET,
        raw_body,
        signature
    ):
        print("❌ Invalid signature")
        return jsonify({"error": "Invalid signature"}), 403

    payload = json.loads(raw_body.decode("utf-8"))
    print("📩 Incoming:", payload)

    try:
        message = payload["data"]["message"]
        if message["type"] != "text":
            return jsonify({"status": "ignored"}), 200

        user_text = message["text"]
        phone = payload["data"]["from"]

        ai_reply = ask_openai(user_text)
        send_whatsapp_message(phone, ai_reply)

    except Exception as e:
        print("⚠️ Error:", e)

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
