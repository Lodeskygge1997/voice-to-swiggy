# sarvam.py
import os
import requests
from logger_store import add_log
from network_store import record_trace

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY")

import time

def process_audio(audio_file_path):
    """
    Sends the audio file to Sarvam AI speech-to-text API with retries for 429 limits.
    """
    if not SARVAM_API_KEY:
        add_log("error", "SARVAM_API_KEY is not set.")
        return "Error: SARVAM_API_KEY is not set."
        
    url = "https://api.sarvam.ai/speech-to-text"
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "User-Agent": "VoiceToSwiggy/1.0"
    }
    
    # Dynamically extract correct file extension to prevent gateway corruption
    filename = os.path.basename(audio_file_path)
    extension = os.path.splitext(filename)[1].lower().replace(".", "")
    mime_type = f"audio/{extension}" if extension else "audio/wav"
    
    data = {
        "model": "saaras:v3"
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        add_log("info", f"Sending audio {audio_file_path} to Sarvam AI (Attempt {attempt+1}/{max_retries})...")
        try:
            start_time = time.time()
            with open(audio_file_path, "rb") as audio_file:
                files = {"file": (filename, audio_file, mime_type)}
                response = requests.post(url, headers=headers, files=files, data=data)
                duration_ms = int((time.time() - start_time) * 1000)
                
                # Record outbound trace to APIGW
                record_trace(
                    direction="OUTBOUND",
                    method="POST",
                    url=url,
                    request_headers=headers,
                    request_body={"model": data.get("model"), "file": filename},
                    response_status=response.status_code,
                    response_headers=dict(response.headers),
                    response_body=response.text,
                    duration_ms=duration_ms
                )
                
                response.raise_for_status()
                
                response_json = response.json()
                add_log("info", f"Sarvam Full Response Body: {response.text}")
                
                transcript = response_json.get('transcript') or response_json.get('text', '')
                
                if transcript:
                    add_log("success", f"Sarvam transcribed: '{transcript}'")
                    return transcript
                else:
                    add_log("warning", "Sarvam returned empty transcript.")
                    return "Could not understand the audio clearly."
                
        except requests.exceptions.HTTPError as e:
            error_details = e.response.text if e.response else str(e)
            status_code = e.response.status_code if e.response else None
            
            # Try to extract the specific internal error code (e.g., 'insufficient_quota_error')
            internal_code = "unknown_code"
            try:
                if e.response:
                    err_json = e.response.json()
                    if "error" in err_json and "code" in err_json["error"]:
                        internal_code = err_json["error"]["code"]
            except Exception:
                pass
            
            if status_code == 429:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s
                    add_log("warning", f"Sarvam Rate Limit (429) hit. Internal Code: [{internal_code}]. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    add_log("error", f"Sarvam 429 Exhausted. Code: [{internal_code}]. Details: {error_details}")
                    return f"Sarvam AI Exact Error [{internal_code}]: {error_details}"
            else:
                add_log("error", f"Sarvam AI HTTP Error {status_code} [{internal_code}]: {error_details}")
                return f"Sarvam AI API Error [{internal_code}]: {error_details}"
                
        except Exception as e:
            add_log("error", f"Error communicating with Sarvam AI: {str(e)}")
            return f"Error communicating with Sarvam AI: {str(e)}"