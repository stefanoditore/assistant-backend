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

    # Crea thread se non esiste
    if not thread_id:
        resp = requests.post("https://api.openai.com/v1/threads", headers=headers)
        resp.raise_for_status()
        thread_id = resp.json()["id"]

    # Aggiungi messaggio utente
    msg_resp = requests.post(
        f"https://api.openai.com/v1/threads/{thread_id}/messages",
        headers=headers,
        json={"role": "user", "content": user_message}
    )
    msg_resp.raise_for_status()

    # Poll per verificare presenza messaggio
    found = False
    for _ in range(10):
        messages = requests.get(f"https://api.openai.com/v1/threads/{thread_id}/messages", headers=headers).json()["data"]
        for m in messages:
            if m["role"] == "user":
                content = m["content"]
                if isinstance(content, list) and content:
                    msg_text = content[0].get("text", {}).get("value", "")
                    if msg_text == user_message:
                        found = True
                        break
        if found:
            break
        time.sleep(1)

    if not found:
        return jsonify({"error": "Message not registered in thread"}), 500

    # Avvia run
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
    run_id = run_resp.json()["id"]

    # Poll fino a completamento
    for _ in range(60):
        status_resp = requests.get(f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}", headers=headers)
        status_resp.raise_for_status()
        if status_resp.json()["status"] == "completed":
            break
        time.sleep(1)
    else:
        return jsonify({"error": "Timeout during run"}), 500

    # Recupera ultima risposta dell’assistente
    messages = requests.get(f"https://api.openai.com/v1/threads/{thread_id}/messages", headers=headers).json()["data"]
    response_text = ""
    for msg in reversed(messages):
        if msg["role"] == "assistant":
            content = msg["content"]
            if isinstance(content, list) and content:
                value = content[0].get("text", {}).get("value", "")
                if value:
                    response_text = value
                    break

    return jsonify({
        "response": response_text,
        "thread_id": thread_id
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
