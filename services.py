import os
import json
import base64
import requests
from google import genai
from google.genai import types

# DEFAULT FALLBACK CONSTANTS
DEFAULT_LAT = 12.9716
DEFAULT_LON = 77.5946
DEFAULT_STATE = "Karnataka"
DEFAULT_CROP = "Tomato"
DEFAULT_GRADE = "Grade B"

# LAZY CLIENT INITIALIZATION
def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in environment variables.")
    return genai.Client(api_key=api_key)

# ---------------------------------------------------------------------------
# 1. SARVAM AI - TEXT TO SPEECH
# ---------------------------------------------------------------------------
def generate_voice_note(text: str, output_path: str, language_code: str = "hi-IN", speaker: str = "shubh") -> str | None:
    sarvam_url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": os.getenv("SARVAM_API_KEY"),
        "Content-Type": "application/json"
    }
    
    supported_langs = ["hi-IN", "kn-IN", "ta-IN", "te-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN"]
    tts_lang = language_code if language_code in supported_langs else "hi-IN"

    payload = {
        "text": text[:2500],
        "target_language_code": tts_lang,
        "speaker": speaker,
        "pace": 1.0,
        "model": "bulbul:v3",
        "output_audio_codec": "mp3"
    }

    try:
        res = requests.post(sarvam_url, headers=headers, json=payload, timeout=15)
        if res.status_code == 200:
            audio_bytes = base64.b64decode(res.json()["audios"][0])
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
            return output_path
        else:
            print(f"Sarvam TTS Error ({res.status_code}): {res.text}")
    except Exception as e:
        print(f"TTS Exception: {e}")
    return None

# ---------------------------------------------------------------------------
# 2. GOVERNMENT MANDI DATA API WITH FALLBACK
# ---------------------------------------------------------------------------
def fetch_mandi_profit_options(farmer_lat: float, farmer_lon: float, state: str, commodity: str, grade: str, quantity_kg: int = 1000) -> dict:
    api_key = os.getenv("DATA_GOV_IN_API_KEY")
    resource_id = "9ef84268-d588-465a-a308-a864a43d0070"
    url = f"https://api.data.gov.in/resource/{resource_id}?api-key={api_key}&format=json&filters[state]={state}&filters[commodity]={commodity}"
    TRANSPORT_RATE_PER_KM = 12.0

    GRADE_MULTIPLIER = {"Grade A": 1.15, "Grade B": 1.00, "Grade C": 0.80}
    multiplier = GRADE_MULTIPLIER.get(grade, 1.00)

    try:
        res = requests.get(url, timeout=8).json()
        records = res.get("records", [])
        
        if not records:
            base_price = 25.00 * multiplier
            est_distance = 15.0
            trans_cost = est_distance * TRANSPORT_RATE_PER_KM
            net_prof = (base_price * quantity_kg) - trans_cost
            
            return {
                "mandi": f"Nearest APMC Market ({state})",
                "price_per_kg": round(base_price, 2),
                "distance_km": est_distance,
                "transport_cost": round(trans_cost, 2),
                "net_profit": round(net_prof, 2),
                "is_fallback": True
            }

        best_mandi = None
        max_profit = -float("inf")

        for record in records:
            market_name = record.get("market", "Local Mandi")
            base_price = float(record.get("modal_price", 2000)) / 100.0
            adjusted_price = base_price * multiplier

            distance_km = round((((farmer_lat - (farmer_lat + 0.05))**2 + (farmer_lon - (farmer_lon + 0.05))**2)**0.5) * 111.0, 1)
            transport_cost = round(distance_km * TRANSPORT_RATE_PER_KM, 2)
            gross_revenue = round(adjusted_price * quantity_kg, 2)
            net_profit = round(gross_revenue - transport_cost, 2)

            if net_profit > max_profit:
                max_profit = net_profit
                best_mandi = {
                    "mandi": market_name,
                    "price_per_kg": round(adjusted_price, 2),
                    "distance_km": distance_km,
                    "transport_cost": transport_cost,
                    "net_profit": net_profit,
                    "is_fallback": False
                }
        return best_mandi

    except Exception:
        return {
            "mandi": "Regional Mandi (Estimated)",
            "price_per_kg": round(20.0 * multiplier, 2),
            "distance_km": 20.0,
            "transport_cost": 240.0,
            "net_profit": round((20.0 * multiplier * quantity_kg) - 240.0, 2),
            "is_fallback": True
        }

# ---------------------------------------------------------------------------
# 3. VISION & ADVISORY WITH PARSING FALLBACK
# ---------------------------------------------------------------------------
def inspect_crop_and_recommend_mandi(image_bytes: bytes, farmer_lat: float, farmer_lon: float, state: str, lang_code: str) -> str:
    gemini_client = get_gemini_client()

    vision_prompt = """
    Analyze this crop image and output ONLY a raw JSON object with keys:
    {
      "crop": "<Detected Crop Name>",
      "grade": "<Grade A, Grade B, or Grade C>",
      "quality_reason": "<Short 1-sentence explanation>"
    }
    """
    
    try:
        vision_res = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), vision_prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        crop_info = json.loads(vision_res.text)
    except Exception as e:
        print(f"Vision API/Parsing Error: {e}")
        crop_info = {
            "crop": DEFAULT_CROP,
            "grade": DEFAULT_GRADE,
            "quality_reason": "Could not clearly determine crop condition from image; analyzed assuming standard market quality."
        }

    crop = crop_info.get("crop", DEFAULT_CROP)
    grade = crop_info.get("grade", DEFAULT_GRADE)
    reason = crop_info.get("quality_reason", "Standard quality crop.")

    mandi_data = fetch_mandi_profit_options(
        farmer_lat=farmer_lat,
        farmer_lon=farmer_lon,
        state=state,
        commodity=crop,
        grade=grade
    )

    explanation_prompt = f"""
    You are an expert AI agricultural advisor. Generate a simple response for a farmer speaking in language code '{lang_code}'.
    
    Output the explanation entirely in the native script for language '{lang_code}'.
    Information to explain:
    - Crop: {crop}
    - Quality Rating: {grade} ({reason})
    - Recommended Market: {mandi_data['mandi']}
    - Expected Price: ₹{mandi_data['price_per_kg']} per kg
    - Transport Distance: {mandi_data['distance_km']} km (Estimated Cost: ₹{mandi_data['transport_cost']})
    - Estimated Net Profit (1 Ton): ₹{mandi_data['net_profit']}
    
    Keep the explanation practical, clear, conversational, and direct for text-to-speech read-aloud.
    """

    try:
        explanation = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=explanation_prompt
        ).text
    except Exception:
        explanation = f"Crop identified as {crop} ({grade}). Best nearby mandi is {mandi_data['mandi']} with net profit ₹{mandi_data['net_profit']} per ton."

    return explanation
# ---------------------------------------------------------------------------
# 4. GENERAL TEXT ADVISORY PIPELINE
# ---------------------------------------------------------------------------
def answer_general_query(user_query: str, lang_code: str = "en-IN") -> str:
    prompt = f"""
    You are an expert AI agricultural advisor helping Indian farmers.
    Answer the following query concisely, accurately, and practically in simple terms.
    If asked in another language, respond in that language script.
    
    Query: "{user_query}"
    """
    
    try:
        gemini_client = get_gemini_client()
        
        # Try primary model
        try:
            response = gemini_client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            return response.text.strip()
        except Exception as model_err:
            print(f"Gemini 1.5 Flash failed, trying gemini-2.0-flash... Error: {model_err}")
            response = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            return response.text.strip()

    except Exception as e:
        print(f"--- DETAILED GEMINI ERROR LOG ---")
        print(f"Exception Type: {type(e).__name__}")
        print(f"Exception Message: {str(e)}")
        print(f"---------------------------------")
        return f"Error connecting to AI advisor: {str(e)}"
