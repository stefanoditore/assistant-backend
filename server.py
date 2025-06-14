from flask import Flask, request, jsonify
import time
import requests
import os

app = Flask(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_ASSISTANT_ID = os.environ.get("OPENAI_ASSISTANT_ID", "")

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

    # 1. Crea nuovo thread se necessario
    if not thread_id:
        thread_resp = requests.post("https://api.openai.com/v1/threads", headers=headers, json={})
        thread_resp.raise_for_status()
        thread_id = thread_resp.json().get("id")

    # 2. Invia messaggio utente
    msg_resp = requests.post(
        f"https://api.openai.com/v1/threads/{thread_id}/messages",
        headers=headers,
        json={ "role": "user", "content": user_message }
    )
    msg_resp.raise_for_status()

    # 3. Avvia una run
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

    # 4. Attendi completamento della run (polling ogni 0.5s per max 30s)
    for _ in range(60):  # 60 × 0.5s = 30s timeout
        status_resp = requests.get(
            f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}",
            headers=headers
        )
        status_resp.raise_for_status()
        if status_resp.json().get("status") == "completed":
            break
        time.sleep(0.5)
    else:
        return jsonify({"error": "Timeout"}), 500

    # 5. Recupera l’ULTIMA risposta dell’assistente
    messages_resp = requests.get(
        f"https://api.openai.com/v1/threads/{thread_id}/messages",
        headers=headers
    )
    messages_resp.raise_for_status()
    messages = messages_resp.json().get("data", [])

    # Ordina per sicurezza in ordine cronologico inverso
    messages = sorted(messages, key=lambda m: m.get("created_at", 0), reverse=True)

    # 6. Estrai risposta come stringa piatta (compatibile con Unity WebGL)
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

    # 7. Risposta finale compatibile Unity WebGL
    return jsonify({
        "response": response_text.strip(),
        "thread_id": thread_id
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
