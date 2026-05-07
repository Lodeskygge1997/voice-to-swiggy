import os
import time
from flask import Flask, request, jsonify, render_template, send_from_directory, g
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
load_dotenv()

from sarvam import process_audio
from swiggy_agent import run_agent_sync
from logger_store import add_log, server_logs
from network_store import record_trace, get_traces, record_user_behavior

app = Flask(__name__, static_folder='static')

@app.before_request
def start_timer():
    g.start_time = time.time()
    try:
        g.req_body = request.get_data(as_text=True)
    except Exception:
        g.req_body = "Binary Data"

@app.after_request
def log_request(response):
    if request.path.startswith('/admin') or request.path.startswith('/api/traces') or request.path.startswith('/static') or request.path == '/':
        return response
        
    duration = int((time.time() - g.start_time) * 1000)
    
    try:
        resp_body = response.get_data(as_text=True) if response.direct_passthrough is False else "Streamed/Binary"
    except Exception:
        resp_body = "Binary Data"
        
    record_trace(
        direction="INBOUND",
        method=request.method,
        url=request.url,
        request_headers=dict(request.headers),
        request_body=g.req_body,
        response_status=response.status_code,
        response_headers=dict(response.headers),
        response_body=resp_body,
        duration_ms=duration
    )
    return response

@app.route('/admin/logs')
def admin_logs():
    """Secured endpoint to view logs"""
    admin_secret = os.environ.get("ADMIN_SECRET", "supersecret123")
    passed_key = request.args.get("key")
    
    if passed_key != admin_secret:
        add_log("warning", f"Unauthorized access attempt to logs with key: {passed_key}")
        return "Unauthorized. Please provide the correct ?key= parameter.", 401
        
    html = "<body style='background:#121212; color:#0f0; font-family:monospace; padding:20px;'>"
    html += "<h1>Admin Dashboard - Production Logs</h1><hr/>"
    for log in server_logs:
        html += f"<div>{log}</div>"
    html += "</body>"
    return html

@app.route('/admin/apigw')
def admin_apigw():
    """Returns the rich API Gateway HTML UI"""
    admin_secret = os.environ.get("ADMIN_SECRET", "supersecret123")
    passed_key = request.args.get("key")
    if passed_key != admin_secret:
        return "Unauthorized. Please provide the correct ?key= parameter.", 401
    return render_template('apigw.html')

@app.route('/api/traces')
def api_traces():
    admin_secret = os.environ.get("ADMIN_SECRET", "supersecret123")
    passed_key = request.args.get("key")
    if passed_key != admin_secret:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_traces())

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/order/web', methods=['POST'])
def order_from_web():
    """Endpoint for the Web Interface to send audio recordings."""
    add_log("info", "Received audio upload from Web Interface")
    
    if 'audio' not in request.files:
        add_log("error", "No audio file provided in web request")
        return jsonify({"error": "No audio file provided"}), 400
        
    audio_file = request.files['audio']
    temp_path = "/tmp/web_audio.wav"
    audio_file.save(temp_path)
    add_log("info", f"Saved audio file to {temp_path}")
    
    record_user_behavior("web_user", "voice_order_received", {"path": temp_path})
    
    # 1. Process with Sarvam
    text = process_audio(temp_path)
    
    # 2. Process with Swiggy MCP Agent
    response_msg = run_agent_sync(text)
    
    return jsonify({
        "transcription": text,
        "message": response_msg,
        "cart": [] # Cart is now managed by the agent internally
    })

@app.route('/api/order/whatsapp', methods=['POST'])
def order_from_whatsapp():
    """Webhook endpoint for Twilio WhatsApp Sandbox."""
    incoming_msg = request.values.get('Body', '')
    media_url = request.values.get('MediaUrl0')
    sender = request.values.get('From', 'Unknown')
    
    add_log("info", f"Received WhatsApp message from {sender}. MediaURL: {media_url}")
    record_user_behavior(sender, "whatsapp_message_received", {"media_url": media_url, "body": incoming_msg})
    
    response = MessagingResponse()
    msg = response.message()
    
    # Check if a voice note was sent
    if media_url:
        import requests
        # Download the audio file from Twilio
        add_log("info", f"Downloading audio from Twilio: {media_url}")
        audio_data = requests.get(media_url).content
        temp_path = "/tmp/whatsapp_audio.ogg"
        with open(temp_path, "wb") as f:
            f.write(audio_data)
            
        # 1. Process with Sarvam
        text = process_audio(temp_path)
        
        # 2. Process with Swiggy MCP Agent
        reply_text = run_agent_sync(text)
        
        # 3. Add transcription so the user knows what we heard
        final_reply = f"🎙️ *I heard:* '{text}'\n\n🛍️ *Swiggy:* {reply_text}"
        msg.body(final_reply)
    else:
        msg.body("Please send a voice note with your Swiggy order! For example: 'I want paneer tikka and garlic naan'.")
        
    return str(response)

if __name__ == '__main__':
    app.run(port=3000, debug=True)