import os
import hmac
import json
import requests
from hashlib import sha256
from flask import Flask, request, jsonify

app = Flask(__name__)

# ================== ENV ==================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
INTERAKT_API_KEY = os.getenv("INTERAKT_API_KEY")
INTERAKT_WEBHOOK_SECRET = os.getenv("INTERAKT_WEBHOOK_SECRET")

INTERAKT_SEND_URL = "https://api.interakt.ai/v1/public/message"

# ================== HMAC VERIFY ==================
def verify_interakt_signature(secret_key, payload, received_signature):
    computed = hmac.new(
        secret_key.encode("utf-8"),
        payload,
        sha256
    ).hexdigest()
    return f"sha256={computed}" == received_signature

# ================== OPENAI ==================
def get_ai_reply(user_message):
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
                    "You are a professional WhatsApp customer support agent "
                    "for Karuvadukadai.com (dry fish & seafood store). "
                    "Reply politely, briefly, and clearly. "
                    "If order related, ask for order ID."
                )
            },
            {
                "role": "user",
                "content": user_message
            }
        ]
    }

    r = requests.post(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()

    # Extract text safely
    for output in data.get("output", []):
        if output.get("type") == "message":
            for c in output.get("content", []):
                if c.get("type") == "output_text":
                    return c.get("text")

    return "Sorry, I’m unable to respond right now."

# ================== SEND WHATSAPP ==================
def send_whatsapp_message(phone, text):
    headers = {
        "Authorization": f"Bearer {INTERAKT_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "receiver": phone,
        "type": "text",
        "message": {"text": text}
    }

    r = requests.post(INTERAKT_SEND_URL, headers=headers, json=payload, timeout=30)
    print("Interakt send status:", r.status_code, r.text)

# ================== ROUTES ==================
@app.route("/", methods=["GET"])
def health():
    return "Interakt WhatsApp AI Bot is LIVE 🚀", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    raw_payload = request.get_data()
    received_signature = request.headers.get("Interakt-Signature")

    # 🔐 Verify webhook
    if not received_signature or not verify_interakt_signature(
        INTERAKT_WEBHOOK_SECRET, raw_payload, received_signature
    ):
        return jsonify({"error": "Invalid signature"}), 401

    data = json.loads(raw_payload)
    print("Webhook received:", data)

    # 🧠 Process message
    try:
        msg = data["data"]["message"]
        if msg["type"] != "text":
            return jsonify({"status": "ignored"}), 200

        customer_text = msg["text"]
        customer_phone = data["data"]["from"]

        ai_reply = get_ai_reply(customer_text)
        send_whatsapp_message(customer_phone, ai_reply)

    except Exception as e:
        print("Processing error:", str(e))

    # ✅ Always respond fast
    return jsonify({"status": "ok"}), 200

# ================== RUN ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
