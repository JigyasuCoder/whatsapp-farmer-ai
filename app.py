import os
import uuid
from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import services

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

AUDIO_DIR = os.path.join(app.root_path, "static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/static/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_DIR, filename)

@app.route("/api/chat", methods=["POST"])
def chat_api():
    host_url = request.host_url.rstrip('/')

    try:
        # 1. CROP IMAGE ANALYSIS
        if "image" in request.files:
            # ... keep existing image handling code ...
            pass

        # 2. VOICE NOTE QUERY
        if "audio" in request.files:
            # ... keep existing audio handling code ...
            pass

        # 3. JSON PAYLOADS (TEXT & LOCATION)
        data = request.get_json(silent=True) or {}

        # Handle Location Sharing
        if "latitude" in data or "lat" in data or "location" in data:
            lat = data.get("latitude") or data.get("lat")
            lon = data.get("longitude") or data.get("lon") or data.get("lng")
            
            # Formulate query for mandi prices based on coordinates
            loc_query = f"Find nearby Mandi crop prices and agricultural market insights for coordinates: Latitude {lat}, Longitude {lon}."
            reply_text = services.answer_general_query(loc_query)
            return jsonify({"reply_text": reply_text})

        # Handle Text Messages
        if "message" in data or "text" in data:
            user_msg = (data.get("message") or data.get("text") or "").strip()
            
            # Handle placeholder text sent by frontend button
            if "*Sharing current location...*" in user_msg:
                return jsonify({"reply_text": "Location received! Fetching nearest Mandi prices for your area..."})
                
            if not user_msg:
                return jsonify({"reply_text": "Please type a valid question."})

            reply_text = services.answer_general_query(user_msg)
            return jsonify({"reply_text": reply_text})

        return jsonify({"reply_text": "Request not recognized."})

    except Exception as e:
        print(f"API Error: {e}")
        return jsonify({"reply_text": f"Error: {str(e)}"}), 200

if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 5000)), debug=True)
