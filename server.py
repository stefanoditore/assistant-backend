from flask import Flask, request, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)  # Abilita tutte le origini (per test/demo)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    system_message = data.get("system_message", "")
    temperature = data.get("temperature", 0.7)
    top_p = data.get("top_p", 1.0)
    
    # SOSTITUISCI QUESTA LOGICA CON LA TUA
    response_text = f"Hai scritto: {message}\n(system: {system_message}, temp: {temperature}, top_p: {top_p})"
    return jsonify({"response": response_text})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
