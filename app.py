import os
import uuid
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import services

app = Flask(__name__, static_folder="static")
CORS(app)

AUDIO_DIR = os.path.join(app.root_path, "static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

@app.route("/static/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_DIR, filename)

@app.route("/api/chat", methods=["POST"])
def chat_api():
    host_url = request.host_url.rstrip('/')

    if "image" in request.files:
        image_file = request.files["image"]
        image_bytes = image_file.read()

        # GPS & Form Parameter Fallback Handler
        try:
            lat = float(request.form.get("latitude", services.DEFAULT_LAT))
            lon = float(request.form.get("longitude", services.DEFAULT_LON))
            if lat == 0.0 or lon == 0.0:
                lat, lon = services.DEFAULT_LAT, services.DEFAULT_LON
        except (ValueError, TypeError):
            lat, lon = services.DEFAULT_LAT, services.DEFAULT_LON

        state = request.form.get("state", services.DEFAULT_STATE) or services.DEFAULT_STATE
        lang_code = request.form.get("language_code", "kn-IN") or "kn-IN"

        # Run pipeline with fallbacks
        reply_text = services.inspect_crop_and_recommend_mandi(
            image_bytes=image_bytes,
            farmer_lat=lat,
            farmer_lon=lon,
            state=state,
            lang_code=lang_code
        )

        # Generate output audio
        audio_filename = f"crop_advisory_{uuid.uuid4().hex[:8]}.mp3"
        local_output_path = os.path.join(AUDIO_DIR, audio_filename)
        
        services.generate_voice_note(
            text=reply_text,
            output_path=local_output_path,
            language_code=lang_code
        )

        return jsonify({
            "reply_text": reply_text,
            "reply_audio_url": f"{host_url}/static/audio/{audio_filename}",
            "applied_coordinates": {"latitude": lat, "longitude": lon}
        })

    return jsonify({"error": "No image provided"}), 400

if __name__ == "__main__":
    app.run(port=5000, debug=True)