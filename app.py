import os
from flask import Flask, request, jsonify, render_template, send_from_directory
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv

from mock_swiggy import MockSwiggyMCP
from sarvam import process_audio

load_dotenv()

app = Flask(__name__, static_folder='static')
swiggy_mcp = MockSwiggyMCP()

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/order/web', methods=['POST'])
def order_from_web():
    """Endpoint for the Web Interface to send audio recordings."""
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
        
    audio_file = request.files['audio']
    temp_path = "/tmp/web_audio.wav"
    audio_file.save(temp_path)
    
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
    
    response = MessagingResponse()
    msg = response.message()
    
    # Check if a voice note was sent
    if media_url:
        import requests
        # Download the audio file from Twilio
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