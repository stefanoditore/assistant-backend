from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
import time
import base64
import random

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
    temperature = data.get("temperature", 0.7)
    top_p = data.get("top_p", 1.0)

    thread_id = data.get("thread_id")
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
        "OpenAI-Beta": "assistants=v2"
    }

    # 1. Crea un nuovo thread se non c'è thread_id
    if not thread_id:
        thread_resp = requests.post(
            "https://api.openai.com/v1/threads",
            headers=headers,
            json={}
        )
        thread_resp.raise_for_status()
        thread_id = thread_resp.json().get("id")

    # 2. Aggiungi messaggio utente
    msg_resp = requests.post(
        f"https://api.openai.com/v1/threads/{thread_id}/messages",
        headers=headers,
        json={
            "role": "user",
            "content": user_message
        }
    )
    msg_resp.raise_for_status()

    # 3. ATTENDI CHE IL MESSAGGIO APPPAIA (come prima)
    found = False
    for _ in range(10):  # Max 10 secondi
        messages_check = requests.get(
            f"https://api.openai.com/v1/threads/{thread_id}/messages",
            headers=headers
        )
        messages_check.raise_for_status()
        messages_data = messages_check.json().get("data", [])
        for m in messages_data:
            if m.get("role") == "user":
                content = m.get("content", [])
                if content and isinstance(content, list):
                    if isinstance(content[0], dict):
                        msg_text = content[0].get("text", "")
                        if isinstance(msg_text, dict):
                            msg_text = msg_text.get("value", "")
                        if msg_text == user_message:
                            found = True
                            break
                    else:
                        if content[0] == user_message:
                            found = True
                            break
        if found:
            # DEBUG: stampa tutti i messaggi utente del thread
            print("\n---MESSAGGI UTENTE PRIMA DELLA RUN---")
            for m in messages_data:
                if m.get("role") == "user":
                    print(m)
            print("---FINE---\n")
            # Delay extra per sicurezza
            time.sleep(2 + random.random())
            break
        time.sleep(1)
    else:
        return jsonify({"error": "Timeout waiting for message delivery"}), 500

    # 4. Avvia una run
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

    # 5. Attendi che la run sia completata
    status = ""
    for _ in range(60):  # max 60 secondi
        status_resp = requests.get(
            f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}",
            headers=headers
        )
        status_resp.raise_for_status()
        status = status_resp.json().get("status")
        if status == "completed":
            break
        time.sleep(1)
    else:
        return jsonify({"error": "Timeout during run"}), 500

    # 6. Recupera l’ULTIMA risposta dell’assistente
    messages_resp = requests.get(
        f"https://api.openai.com/v1/threads/{thread_id}/messages",
        headers=headers
    )
    messages_resp.raise_for_status()
    messages = messages_resp.json().get("data", [])
    response_text = ""
    # Prendi sempre l’ULTIMO messaggio assistant!
    assistant_msgs = [msg for msg in messages if msg.get("role") == "assistant"]
    if assistant_msgs:
        last_assistant = assistant_msgs[-1]
        content = last_assistant.get("content", [])
        if content and isinstance(content, list):
            if isinstance(content[0], dict):
                response_text = content[0].get("text", "")
                if isinstance(response_text, dict):
                    response_text = response_text.get("value", "")
            else:
                response_text = content[0]

    return jsonify({"response": response_text, "thread_id": thread_id})

@app.route("/speak", methods=["POST"])
def speak():
    data = request.json
    text = data.get("message", "")
    voice_id = ELEVENLABS_VOICE_ID
    api_key = ELEVENLABS_API_KEY
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=pcm_44100"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "voice_settings": { "stability": 0.5, "similarity_boost": 0.5 }
    }
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code != 200:
        return jsonify({"error": resp.text}), 500
    audio_b64 = base64.b64encode(resp.content).decode("utf-8")
    return jsonify({"audio": audio_b64})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
