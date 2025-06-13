@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_message = data.get("message", "")
    system_message = data.get("system_message", "")
    temperature = data.get("temperature", 0.7)
    top_p = data.get("top_p", 1.0)

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
        "OpenAI-Beta": "assistants=v2"
    }

    # 1. SEMPRE crea nuovo thread!
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

    # 4. Attendi che la run sia completata
    status = ""
    for _ in range(60):
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

    # 5. Recupera l’ULTIMA risposta dell’assistente
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
