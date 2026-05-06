# sarvam.py
import os
import requests
from logger_store import add_log

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY")

def process_audio(audio_file_path):
    """
    Sends the audio file to Sarvam AI speech-to-text API.
    """
    if not SARVAM_API_KEY:
        add_log("error", "SARVAM_API_KEY is not set.")
        return "Error: SARVAM_API_KEY is not set."
        
    url = "https://api.sarvam.ai/speech-to-text"
    headers = {"api-subscription-key": SARVAM_API_KEY}
    
    # Send the audio file to Sarvam AI
    add_log("info", f"Sending audio file {audio_file_path} to Sarvam AI...")
    with open(audio_file_path, "rb") as audio_file:
        files = {"file": ("audio.webm", audio_file, "audio/webm")}
        data = {
            "model": "saaras:v3",
            "mode": "translate" # Translate to english to easily match Swiggy menu
        }
        
        try:
            response = requests.post(url, headers=headers, files=files, data=data)
            response.raise_for_status()
            
            response_json = response.json()
            transcript = response_json.get('transcript') or response_json.get('text', '')
            
            if transcript:
                add_log("success", f"Sarvam transcribed: '{transcript}'")
                return transcript
            else:
                add_log("warning", "Sarvam returned empty transcript.")
                return "Could not understand the audio clearly."
            
        except requests.exceptions.HTTPError as e:
            error_details = e.response.text if e.response else str(e)
            add_log("error", f"Sarvam AI HTTP Error: {error_details}")
            return f"Sarvam AI API Error: {error_details}"
        except Exception as e:
            add_log("error", f"Error communicating with Sarvam AI: {str(e)}")
            return f"Error communicating with Sarvam AI: {str(e)}"