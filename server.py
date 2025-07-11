from flask import Flask, request, jsonify
import time
import requests
import os
import base64
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_ASSISTANT_ID = os.environ.get("OPENAI_ASSISTANT_ID", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_message = data.get("message", "")
    system_message = data.get("system_message", "")
    temperature = data.get("temperature", 0.4)
    top_p = data.get("top_p", 1.0)
    thread_id = data.get("thread_id")

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
        "OpenAI-Beta": "assistants=v2"
    }

    if not thread_id:
        thread_resp = requests.post("https://api.openai.com/v1/threads", headers=headers, json={})
        thread_resp.raise_for_status()
        thread_id = thread_resp.json().get("id")

    msg_resp = requests.post(
        f"https://api.openai.com/v1/threads/{thread_id}/messages",
        headers=headers,
        json={ "role": "user", "content": user_message }
    )
    msg_resp.raise_for_status()

    run_resp = requests.post(
        f"https://api.openai.com/v1/threads/{thread_id}/runs",
        headers=headers,
        json={
            "assistant_id": OPENAI_ASSISTANT_ID,
            "instructions": system_message,
            "temperature": temperature,
            "top_p": top_p
        }
    )
    run_resp.raise_for_status()
    run_id = run_resp.json().get("id")

    # ⏱️ Polling ottimizzato: ogni 0.25s fino a 30s
    for _ in range(120):
        status_resp = requests.get(
            f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}",
            headers=headers
        )
        status_resp.raise_for_status()
        if status_resp.json().get("status") == "completed":
            break
        time.sleep(0.25)
    else:
        return jsonify({"error": "Timeout"}), 500

    messages_resp = requests.get(
        f"https://api.openai.com/v1/threads/{thread_id}/messages",
        headers=headers
    )
    messages_resp.raise_for_status()
    messages = messages_resp.json().get("data", [])
    messages = sorted(messages, key=lambda m: m.get("created_at", 0), reverse=True)

    response_text = ""
    for msg in messages:
        if msg.get("role") == "assistant":
            parts = msg.get("content", [])
            for part in parts:
                if isinstance(part, dict):
                    text = part.get("text", "")
                    if isinstance(text, dict):
                        text = text.get("value", "")
                    response_text += text
            break

    return jsonify({
        "response": response_text.strip(),
        "thread_id": thread_id
    })


@app.route("/speak", methods=["POST"])
def speak():
    data = request.json
    text = data.get("message", "").strip()

    if not text:
        return jsonify({"error": "Messaggio vuoto"}), 400

    def split_into_sentences(text):
        return [s.strip() for s in re.split(r'(?<=[.?!])\s+', text) if s.strip()]

    sentences = split_into_sentences(text)
    audio_data = bytearray()

    for sentence in sentences:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}?output_format=pcm_44100"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "text": sentence,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }

        resp = requests.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            return jsonify({"error": resp.text}), 500

        audio_data.extend(resp.content)

    audio_b64 = base64.b64encode(audio_data).decode("utf-8")
    return jsonify({ "audio": audio_b64 })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
