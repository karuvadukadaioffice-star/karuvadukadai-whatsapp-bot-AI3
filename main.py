import os
import hmac
import requests
from hashlib import sha256
from flask import Flask, request, jsonify

app = Flask(__name__)

# ===============================
# ENV VARIABLES (Render)
# ===============================
INTERAKT_API_KEY = os.getenv("INTERAKT_API_KEY")
INTERAKT_SECRET = os.getenv("INTERAKT_SECRET")   # ✅ FIXED NAME
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

INTERAKT_SEND_URL = "https://api.interakt.ai/v1/public/message"

# ===============================
# VERIFY INTERAKT SIGNATURE
# ===============================
def verify_interakt_signature(secret_key, payload, received_signature):
    if not secret_key or not received_signature:
        return False

    computed = hmac.new(
        secret_key.encode("utf-8"),
        payload,
        sha256
    ).hexdigest()

    return f"sha256={computed}" == received_signature


# ===============================
# OPENAI CALL
# ===============================
def ask_openai(user_text):
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4.1-mini",
        "input": f"""
You are Karuvadukadai customer support.
Reply shortly, politely, in Tamil-English mix.
If delivery or order related, be helpful and reassuring.

Customer message:
{user_text}
"""
    }

    r = requests.post(url, json=payload, headers=headers, timeout=20)
    r.raise_for_status()

    data = r.json()
    return data["output"][0]["content"][0]["text"]


# ===============================
# SEND WHATSAPP MESSAGE
# ===============================
def send_whatsapp(to, text):
    headers = {
        "Authorization": f"Bearer {INTERAKT_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "receiver": to,
        "type": "text",
        "message": {"text": text}
    }

    requests.post(INTERAKT_SEND_URL, json=payload, headers=headers, timeout=10)


# ===============================
# HEALTH CHECK
# ===============================
@app.route("/", methods=["GET"])
def home():
    return "Interakt WhatsApp AI Bot is LIVE 🚀", 200


# ===============================
# WEBHOOK ENDPOINT
# ===============================
@app.route("/webhook", methods=["POST"])
def webhook():
    raw_body = request.get_data()
    signature = request.headers.get("Interakt-Signature")

    # 🔐 Verify signature
    if not verify_interakt_signature(INTERAKT_SECRET, raw_body, signature):
        return jsonify({"error": "Invalid signature"}), 401

    data = request.json

    try:
        msg = data["data"]["message"]
        sender = data["data"]["from"]

        if msg["type"] != "text":
            return jsonify({"status": "ignored"}), 200

        user_text = msg["text"]

        # 🤖 AI Reply
        ai_reply = ask_openai(user_text)

        # 📲 Send back to WhatsApp
        send_whatsapp(sender, ai_reply)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("Webhook error:", e)
        return jsonify({"error": "server error"}), 200


# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
