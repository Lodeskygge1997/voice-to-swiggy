import os
from flask import Flask, request, jsonify, render_template, send_from_directory
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
load_dotenv()

from mock_swiggy import MockSwiggyMCP
from sarvam import process_audio
from logger_store import add_log, server_logs

app = Flask(__name__, static_folder='static')
swiggy_mcp = MockSwiggyMCP()

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
    
    # 1. Process with Sarvam
    text = process_audio(temp_path)
    
    # 2. Process with Swiggy MCP
    response_msg = swiggy_mcp.process_order(text)
    
    return jsonify({
        "transcription": text,
        "message": response_msg,
        "cart": swiggy_mcp.cart
    })

@app.route('/api/order/whatsapp', methods=['POST'])
def order_from_whatsapp():
    """Webhook endpoint for Twilio WhatsApp Sandbox."""
    incoming_msg = request.values.get('Body', '')
    media_url = request.values.get('MediaUrl0')
    sender = request.values.get('From', 'Unknown')
    
    add_log("info", f"Received WhatsApp message from {sender}. MediaURL: {media_url}")
    
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
        
        # 2. Process with Swiggy MCP
        reply_text = swiggy_mcp.process_order(text)
        
        # 3. Add transcription so the user knows what we heard
        final_reply = f"🎙️ *I heard:* '{text}'\n\n🛍️ *Swiggy:* {reply_text}"
        msg.body(final_reply)
    else:
        msg.body("Please send a voice note with your Swiggy order! For example: 'I want paneer tikka and garlic naan'.")
        
    return str(response)

if __name__ == '__main__':
    app.run(port=3000, debug=True)