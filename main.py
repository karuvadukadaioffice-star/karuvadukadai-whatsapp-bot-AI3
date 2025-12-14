import os
import json
import hmac
import time
import requests
from hashlib import sha256
from flask import Flask, request, jsonify

app = Flask(__name__)

# ================== ENV VARS ==================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
INTERAKT_API_KEY = os.environ.get("INTERAKT_API_KEY")
INTERAKT_WEBHOOK_SECRET = os.environ.get("INTERAKT_WEBHOOK_SECRET")

INTERAKT_SEND_URL = "https://api.interakt.ai/v1/public/message"

# ================== SIGNATURE VERIFY ==================
def verify_interakt_signature(secret_key, payload, received_signature):
    computed = hmac.new(
        secret_key.encode("utf-8"),
        payload,
        sha256
    ).hexdigest()
    return f"sha256={computed}" == received_signature


# ================== OPENAI ==================
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
                    "You are a customer support agent for Karuvadukadai. "
                    "Reply politely, shortly, and clearly. "
                    "Use simple English or Tamil-English mix. "
                    "Do NOT mention AI."
                )
            },
            {
                "role": "user",
                "content": user_text
            }
        ]
    }

    r = requests.post(url, json=payload, headers=headers, timeout=8)
    r.raise_for_status()

    data = r.json()
    text = ""

    for out in data.get("output", []):
        for c in out.get("content", []):
            if c.get("type") == "output_text":
                text += c.get("text", "")

    return text.strip() or "Please wait, our team will help you shortly."


# ================== SEND WHATSAPP ==================
def send_whatsapp(to, message):
    headers = {
        "Authorization": f"Bearer {INTERAKT_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "receiver": to,
        "type": "text",
        "message": {
            "text": message
        }
    }

    r = requests.post(INTERAKT_SEND_URL, json=payload, headers=headers, timeout=8)
    print("Interakt send:", r.status_code, r.text)


# ================== ROUTES ==================
@app.route("/", methods=["GET"])
def home():
    return "Interakt WhatsApp AI Bot is LIVE 🚀", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    raw_payload = request.get_data()
    signature = request.headers.get("Interakt-Signature", "")

    # 🔐 Verify webhook
    if not verify_interakt_signature(
        INTERAKT_WEBHOOK_SECRET,
        raw_payload,
        signature
    ):
        print("❌ Invalid signature")
        return jsonify({"error": "invalid signature"}), 401

    data = json.loads(raw_payload.decode("utf-8"))
    print("Webhook data:", data)

    # ⏱️ Immediate 200 OK (Interakt needs <3 sec)
    response = jsonify({"status": "ok"})
    
    try:
        if data.get("event") != "message":
            return response, 200

        msg = data.get("data", {})
        from_number = msg.get("from")
        message_obj = msg.get("message", {})

        if message_obj.get("type") != "text":
            return response, 200

        user_text = message_obj.get("text", "").strip()
        if not user_text:
            return response, 200

        # 🤖 AI reply
        ai_reply = ask_openai(user_text)

        # 📤 Send WhatsApp reply
        send_whatsapp(from_number, ai_reply)

    except Exception as e:
        print("Webhook error:", e)

    return response, 200


# ================== MAIN ==================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
