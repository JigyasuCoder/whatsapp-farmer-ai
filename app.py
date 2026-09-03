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

    # 1. IMAGE ANALYSIS PIPELINE
    if "image" in request.files:
        try:
            image_file = request.files["image"]
            image_bytes = image_file.read()

            try:
                lat = float(request.form.get("latitude", services.DEFAULT_LAT))
                lon = float(request.form.get("longitude", services.DEFAULT_LON))
                if lat == 0.0 or lon == 0.0:
                    lat, lon = services.DEFAULT_LAT, services.DEFAULT_LON
            except (ValueError, TypeError):
                lat, lon = services.DEFAULT_LAT, services.DEFAULT_LON

            state = request.form.get("state", services.DEFAULT_STATE) or services.DEFAULT_STATE
            lang_code = request.form.get("language_code", "kn-IN") or "kn-IN"

            reply_text = services.inspect_crop_and_recommend_mandi(
                image_bytes=image_bytes,
                farmer_lat=lat,
                farmer_lon=lon,
                state=state,
                lang_code=lang_code
            )

            audio_filename = f"crop_advisory_{uuid.uuid4().hex[:8]}.mp3"
            local_output_path = os.path.join(AUDIO_DIR, audio_filename)
            
            services.generate_voice_note(
                text=reply_text,
                output_path=local_output_path,
                language_code=lang_code
            )

            return jsonify({
                "reply_text": reply_text or "Crop processed successfully.",
                "reply_audio_url": f"{host_url}/static/audio/{audio_filename}"
            })
        except Exception as e:
            print(f"Image API Error: {e}")
            return jsonify({"reply_text": "Image analysis failed due to a processing error."}), 500

    # 2. VOICE NOTE INPUT HANDLING
    if "audio" in request.files:
        try:
            # Voice placeholder until Sarvam STT is attached
            transcript = "Audio received (Voice query processed)"
            reply_text = services.answer_general_query("How to improve crop yield this season?")
            
            audio_filename = f"voice_reply_{uuid.uuid4().hex[:8]}.mp3"
            local_output_path = os.path.join(AUDIO_DIR, audio_filename)
            services.generate_voice_note(text=reply_text, output_path=local_output_path, language_code="hi-IN")

            return jsonify({
                "transcript": transcript,
                "reply_text": reply_text,
                "reply_audio_url": f"{host_url}/static/audio/{audio_filename}"
            })
        except Exception as e:
            print(f"Audio API Error: {e}")
            return jsonify({"transcript": "Voice note failed", "reply_text": "Error processing audio."}), 500

    # 3. GENERAL TEXT MESSAGES
    data = request.get_json(silent=True) or {}
    if "message" in data:
        user_msg = data.get("message", "").strip()
        if not user_msg:
            return jsonify({"error": "Empty message"}), 400

        reply_text = services.answer_general_query(user_msg)
        return jsonify({"reply_text": reply_text})

    return jsonify({"error": "No valid payload received"}), 400

if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 5000)), debug=True)
