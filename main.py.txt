from flask import Flask, request, jsonify
import os
import hmac
from hashlib import sha256
import requests
import json

app = Flask(__name__)

# 🔑 ENV VARS (set these on Render/Railway/Heroku etc.)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
INTERAKT_API_KEY = os.environ.get("INTERAKT_API_KEY")
INTERAKT_SECRET = os.environ.get("INTERAKT_SECRET")  # from Interakt webhook settings
INTERAKT_BASE_URL = "https://api.interakt.ai/v1/public"  # adjust if your docs say different


# ---------- 1) Verify Interakt Webhook Signature ----------

def generate_signature(secret_key: str, payload: bytes) -> str:
    """Return HMAC-SHA256 signature prefixed with 'sha256='."""
    if payload is None:
        payload = b""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    hash_value = hmac.new(secret_key.encode("utf-8"), payload, sha256).hexdigest()
    return "sha256=" + hash_value


def verify_signature(secret_key: str, payload: bytes, signature: str) -> bool:
    """Compare received signature with freshly generated one."""
    if not signature:
        return False
    expected = generate_signature(secret_key, payload)
    # use hmac.compare_digest to avoid timing attacks
    return hmac.compare_digest(expected, signature)


# ---------- 2) OpenAI call (Customer support brain) ----------

def ask_openai(user_message: str, user_phone: str) -> str:
    """
    Call OpenAI Responses API and return AI reply.
    You can customize system prompt for your brand.
    """
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "You are a polite customer support agent for karuvadukadai.com, a dry fish and ready-to-eat store. "
        "Language: understand both Tamil and English, and reply in the same language style as the customer. "
        "Be short and clear. If the user asks for order status, politely ask for order ID or registered phone number. "
        "Do NOT make up fake tracking numbers."
    )

    payload = {
        "model": "gpt-4.1-mini",
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Extract text from Responses API
    text = ""
    for item in data.get("output", []):
        # handle message-style output
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    text += c.get("text", "")
        elif item.get("type") == "output_text":
            text += item.get("text", "")

    if not text:
        text = "Sorry, I am not able to respond right now. Please try again."
    return text.strip()


# ---------- 3) Send reply to customer via Interakt ----------

def send_whatsapp_reply(to_number: str, message: str):
    url = f"{INTERAKT_BASE_URL}/message"
    headers = {
        "Authorization": f"Bearer {INTERAKT_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "receiver": to_number,      # e.g. "9198xxxxxxxx"
        "type": "text",
        "message": {"text": message},
    }

    r = requests.post(url, headers=headers, json=payload, timeout=30)
    try:
        r.raise_for_status()
    except Exception as e:
        print("Error sending message to Interakt:", e, r.text)


# ---------- 4) Routes ----------

@app.route("/", methods=["GET"])
def home():
    return "Customer Support AI is running", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    # raw bytes for signature verification
    raw_body = request.data
    received_sig = request.headers.get("Interakt-Signature", "")

    # 1) Verify signature
    if not verify_signature(INTERAKT_SECRET, raw_body, received_sig):
        print("Invalid Interakt signature")
        return jsonify({"status": "invalid_signature"}), 401

    # Parse JSON body
    data = request.get_json(force=True, silent=True) or {}
    print("Incoming webhook:", json.dumps(data, indent=2, ensure_ascii=False))

    # ⚠ Adjust according to actual Interakt webhook structure
    # Example expected:
    # {
    #   "event": "message",
    #   "data": {
    #       "from": "9198xxxxxxx",
    #       "message": {
    #           "type": "text",
    #           "text": "Hi"
    #       }
    #   }
    # }
    try:
        event = data.get("event")
        if event != "message":
            return jsonify({"status": "ignored_non_message_event"}), 200

        msg_data = data.get("data", {})
        from_number = msg_data.get("from")  # customer phone
        msg_obj = msg_data.get("message", {})
        msg_type = msg_obj.get("type")

        # ignore non-text messages for now
        if msg_type != "text":
            return jsonify({"status": "ignored_non_text"}), 200

        user_text = msg_obj.get("text", "")

        if not from_number or not user_text:
            return jsonify({"status": "missing_from_or_text"}), 200

        # 2) Get AI reply
        ai_reply = ask_openai(user_text, from_number)

        # 3) Send reply via Interakt
        send_whatsapp_reply(from_number, ai_reply)

        # Interakt expects 200 OK quickly
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("Error in webhook processing:", e)
        return jsonify({"status": "error", "detail": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
