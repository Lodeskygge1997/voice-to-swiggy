# sarvam.py
import os
import requests

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY")

def process_audio(audio_file_path):
    """
    Sends the audio file to Sarvam AI speech-to-text API.
    """
    if not SARVAM_API_KEY:
        return "Error: SARVAM_API_KEY is not set."
        
    url = "https://api.sarvam.ai/speech-to-text"
    headers = {"api-subscription-key": SARVAM_API_KEY}
    
    # Send the audio file to Sarvam AI
    with open(audio_file_path, "rb") as audio_file:
        files = {"file": audio_file}
        data = {
            "model": "saaras:v3",
            "mode": "translate" # Translate to english to easily match Swiggy menu
        }
        
        try:
            response = requests.post(url, headers=headers, files=files, data=data)
            response.raise_for_status()
            
            # The API returns JSON with a 'transcript' or 'text' key.
            # Typically it returns a 'transcript' string. 
            response_json = response.json()
            
            # Trying standard keys, fallback if empty
            transcript = response_json.get('transcript') or response_json.get('text', '')
            return transcript if transcript else "Could not understand the audio clearly."
            
        except Exception as e:
            return f"Error communicating with Sarvam AI: {str(e)}"
