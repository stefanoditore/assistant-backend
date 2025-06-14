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
    temperature = data.get("temperature", 0.7)
    top_p = data.get("top_p", 1.0)
    thread_id = data.get("thread_id")

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
        "OpenAI-Beta": "assistants=v2"
    }

    # 1. Crea thread se non esiste
    if not thread_id:
        thread_resp = requests.post("https://api.openai.com/v1/threads", headers=headers)
        thread_resp.raise_for_status()
        thread_id = thread_resp.json().get("id")

    # 2. Aggiungi messaggio utente
    msg_resp = requests.post(
        f"https://api.openai.com/v1/threads/{thread_id}/messages",
        headers=headers,
        json={"role": "user", "content": user_message}
    )
    msg_resp.raise_for_status()

    # 3. Polling breve per assicurarsi che il messaggio sia registrato
    for attempt in range(10):  # max 5 secondi
        check = requests.get(f"https://api.openai.com/v1/threads/{thread_id}/messages", headers=headers)
        check.raise_for_status()
        for m in check.json().get("data", []):
            if m.get("role") == "user":
                content = m.get("content", [])
                if content and isinstance(content[0], dict):
                    text = content[0].get("text", {}).get("value", "")
                    if text == user_message:
                        break
        else:
            time.sleep(0.5)
            continue
        break
    else:
        return jsonify({"error": "Timeout waiting for user message"}), 500

    # 4. Avvia la run
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

    # 5. Polling per completamento run
    for _ in range(20):  # max 10 secondi
        status_resp = requests.get(
            f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}",
            headers=headers
        )
        status_resp.raise_for_status()
        if status_resp.json().get("status") == "completed":
            break
        time.sleep(0.5)
    else:
        return jsonify({"error": "Timeout waiting for completion"}), 500

    # 6. Recupera l'ultima risposta dell'assistente
    messages_resp = requests.get(f"https://api.openai.com/v1/threads/{thread_id}/messages", headers=headers)
    messages_resp.raise_for_status()
    messages = messages_resp.json().get("data", [])

    response_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", [])
            if content and isinstance(content[0], dict):
                response_text = content[0].get("text", {}).get("value", "")
            else:
                response_text = content[0]
            break

    return jsonify({"response": response_text, "thread_id": thread_id})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
