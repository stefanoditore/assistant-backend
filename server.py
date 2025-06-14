from flask import Flask, request, jsonify
import requests
import os
import time

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

    # 1. Crea thread se non presente
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

    # 3. Avvia la run
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

    # 4. Attendi completamento run (polling)
    for _ in range(60):
        run_status_resp = requests.get(
            f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}",
            headers=headers
        )
        run_status_resp.raise_for_status()
        status = run_status_resp.json().get("status")
        if status == "completed":
            break
        time.sleep(1)
    else:
        return jsonify({"error": "Run timeout"}), 500

    # 5. Recupera la risposta direttamente dal run
    run_result_resp = requests.get(
        f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}",
        headers=headers
    )
    run_result_resp.raise_for_status()
    response_text = run_result_resp.json().get("last_response", {}).get("message", {}).get("content", "")

    return jsonify({"response": response_text, "thread_id": thread_id})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
