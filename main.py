from flask import Flask, request, jsonify
import os
import hmac
from hashlib import sha256
import requests
import json

app = Flask(__name__)

# ===== ENV VARS (Render) =====
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
INTERAKT_API_KEY = os.environ.get("INTERAKT_API_KEY")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")

INTERAKT_SEND_URL = "https://api.interakt.ai/v1/public/message"

# ===== VERIFY SIGNATURE =====
def verify_interakt_signature(secret_key, payload, received_signature):
    computed = hmac.new(
        secret_key.encode("utf-8"),
        payload,
        sha256
    ).hexdigest()
    return f"sha256={computed}" == received_signature


# ===== OPENAI CALL =====
def ask_openai(question):
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4.1-mini",
        "input": f"You are a customer support agent for Karuvadukadai. Reply briefly.\nCustomer: {question}"
    }

    r = requests.post(url, headers=headers, json=payload, timeout=15)
    r.raise_for_status()
    data = r.json()

    for item in data.get("output", []):
        if item.get("type") == "output_text":
            return item.get("text")

    return "Thanks for contacting Karuvadukadai 🙂"


# ===== SEND WHATSAPP MESSAGE =====
def send_whatsapp(to, text):
    headers = {
        "Authorization": f"Bearer {INTERAKT_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "receiver": to,
        "type": "text",
        "message": {
            "text": text
        }
    }

    requests.post(INTERAKT_SEND_URL, headers=headers, json=payload, timeout=10)


# ===== ROUTES =====
@app.route("/", methods=["GET"])
def home():
    return "Interakt WhatsApp AI Bot is LIVE 🚀", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    raw_body = request.data
    signature = request.headers.get("Interakt-Signature", "")

    # 1️⃣ Verify signature
    if not verify_interakt_signature(WEBHOOK_SECRET, raw_body, signature):
        return "Invalid signature", 403

    data = request.get_json(force=True)

    # 2️⃣ Only incoming text messages
    if data.get("message_type") != "incoming":
        return jsonify({"status": "ignored"}), 200

    if data.get("message_content_type") != "text":
        return jsonify({"status": "ignored"}), 200

    # 3️⃣ Extract message
    customer_number = data["customer"]["phone_number"]
    message_json = json.loads(data["message"])
    customer_text = message_json.get("text", "")

    # 4️⃣ Ask OpenAI
    reply = ask_openai(customer_text)

    # 5️⃣ Reply on WhatsApp
    send_whatsapp(customer_number, reply)

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
