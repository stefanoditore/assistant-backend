from flask import Flask, request, jsonify
import time
import requests
import base64
import os

app = Flask(__name__)

# Chiavi API dalle variabili d'ambiente
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
    thread_id = data.get("thread_id")   # Se presente, continuiamo la conversazione

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
        "OpenAI-Beta": "assistants=v2"
    }

    # 1️⃣ Se non ho un thread_id (prima interazione), lo creo
    if not thread_id:
        thread_resp = requests.post(
            "https://api.openai.com/v1/threads",
            headers=headers,
            json={}
        )
        thread_resp.raise_for_status()
        thread_id = thread_resp.json().get("id")

    # 2️⃣ Aggiungo il messaggio utente al thread
    msg_resp = requests.post(
        f"https://api.openai.com/v1/threads/{thread_id}/messages",
        headers=headers,
        json={
            "role": "user",
            "content": user_message
        }
    )
    msg_resp.raise_for_status()

    # 3️⃣ Avvio una run con le istruzioni
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

    # 4️⃣ Polling: aspetta il completamento della run
    status = ""
    for i in range(60):  # Fino a 60 secondi
        status_resp = requests.get(
            f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}",
            headers=headers
        )
        status_resp.raise_for_status()
        status = status_resp.json().get("status")

        if status == "completed":
            break

        time.sleep(0.3 if i < 10 else 1.0)
    else:
        return jsonify({"error": "Timeout durante la run"}), 500

    # 5️⃣ Recupero la risposta dell'assistente (ultima del thread)
    messages_resp = requests.get(
        f"https://api.openai.com/v1/threads/{thread_id}/messages",
        headers=headers
    )
    messages_resp.raise_for_status()
    messages = messages_resp.json().get("data", [])

    response_text = ""
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
