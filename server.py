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
    thread_id = data.get("thread_id")   # <-- se già presente, mantieni il contesto

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
        "OpenAI-Beta": "assistants=v2"
    }

    # 1. Se non ho thread_id, lo creo (prima chiamata della chat)
    if not thread_id:
        thread_resp = requests.post(
            "https://api.openai.com/v1/threads",
            headers=headers,
            json={}
        )
        thread_resp.raise_for_status()
        thread_id = thread_resp.json().get("id")

    # 2. Aggiungi messaggio utente (stesso thread se esiste già)
    msg_resp = requests.post(
        f"https://api.openai.com/v1/threads/{thread_id}/messages",
        headers=headers,
        json={
            "role": "user",
            "content": user_message
        }
    )
    msg_resp.raise_for_status()

    # 3. **POLLING**: aspetta che il messaggio utente sia presente nel thread
    found = False
    for attempt in range(12):  # Max 12 secondi
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
            print(f"Messaggio utente trovato dopo {attempt+1} secondi.")
            break
        time.sleep(1)
    else:
        print("Timeout polling: il messaggio utente non appare nel thread.")
        return jsonify({"error": "Timeout waiting for message delivery"}), 500

    # 4. Avvia la run SOLO ora che il messaggio è presente!
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
