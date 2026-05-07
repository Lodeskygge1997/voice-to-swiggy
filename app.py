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

def telegram_api_request(method, endpoint, **kwargs):
    import requests
    import time
    import json
    
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_BOT_TOKEN:
        return None
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{endpoint}"
    if endpoint.startswith("http"):
        url = endpoint
        
    start_time = time.time()
    try:
        if method.upper() == "POST":
            response = requests.post(url, **kwargs)
        else:
            response = requests.get(url, **kwargs)
            
        duration = int((time.time() - start_time) * 1000)
        
        # Redact token from logged URL
        log_url = url.replace(TELEGRAM_BOT_TOKEN, "***")
        
        req_body = kwargs.get("json", kwargs.get("data", ""))
        if isinstance(req_body, dict):
            req_body = json.dumps(req_body)
            
        content_type = response.headers.get("Content-Type", "")
        # Don't save huge binary blobs in the DB
        resp_body = response.text[:1000] if "audio" not in content_type and "octet-stream" not in content_type else "Binary File"
            
        try:
            record_trace(
                direction="OUTBOUND",
                method=method.upper(),
                url=log_url,
                request_headers=dict(response.request.headers),
                request_body=str(req_body),
                response_status=response.status_code,
                response_headers=dict(response.headers),
                response_body=resp_body,
                duration_ms=duration
            )
        except Exception as trace_e:
            add_log("error", f"Failed to record outbound trace: {trace_e}")
            
        return response
    except Exception as e:
        duration = int((time.time() - start_time) * 1000)
        log_url = url.replace(TELEGRAM_BOT_TOKEN, "***") if TELEGRAM_BOT_TOKEN else url
        req_body = kwargs.get("json", kwargs.get("data", ""))
        try:
            record_trace(
                direction="OUTBOUND",
                method=method.upper(),
                url=log_url,
                request_headers={},
                request_body=str(req_body),
                response_status=500,
                response_headers={},
                response_body=str(e),
                duration_ms=duration
            )
        except:
            pass
        add_log("error", f"Telegram API error: {e}")
        return None

def send_telegram_msg_global(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    telegram_api_request("POST", "sendMessage", json=payload)

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
        
    try:
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
    except Exception as e:
        add_log("error", f"Failed to record inbound trace: {e}")
        
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
    
    user_id = request.form.get("user_id", "web_user")
    record_user_behavior(user_id, "web_voice_order_received", {"path": temp_path})
    
    # 1. Process with Sarvam
    text = process_audio(temp_path)
    
    # 2. Process with Swiggy MCP Agent
    response_msg = run_agent_sync(text, session_id=user_id)
    
    # Send confirmation to Telegram
    if user_id and user_id != "anonymous_web_user":
        try:
            import json
            clean_json = response_msg.strip()
            if clean_json.startswith("```json"): clean_json = clean_json[7:]
            if clean_json.endswith("```"): clean_json = clean_json[:-3]
            parsed = json.loads(clean_json.strip())
            swiggy_text = parsed.get("text", response_msg)
        except:
            swiggy_text = response_msg
            
        send_telegram_msg_global(
            chat_id=user_id,
            text=f"✅ Voice Order Processed\nI heard: _{text}_\n\n🛍️ Swiggy: {swiggy_text}"
        )
    
    return jsonify({
        "transcription": text,
        "message": swiggy_text,
        "cart": []
    })

@app.route('/api/order/chat', methods=['POST'])
def order_from_chat():
    """Endpoint for the Web Interface to send text."""
    data = request.json
    if not data or 'text' not in data:
        return jsonify({"error": "No text provided"}), 400
        
    text = data['text']
    user_id = data.get('user_id', 'web_user')
    
    add_log("info", f"Received text from Web Interface: {text}")
    record_user_behavior(user_id, "web_chat_received", {"text": text})
    
    # Process with Swiggy MCP Agent
    response_msg = run_agent_sync(text, session_id=user_id)
    
    # Parse agent response
    try:
        import json
        clean_json = response_msg.strip()
        if clean_json.startswith("```json"): clean_json = clean_json[7:]
        if clean_json.endswith("```"): clean_json = clean_json[:-3]
        parsed = json.loads(clean_json.strip())
        swiggy_text = parsed.get("text", response_msg)
    except:
        swiggy_text = response_msg

    # Send confirmation to Telegram
    if user_id and user_id != "anonymous_web_user":
        send_telegram_msg_global(
            chat_id=user_id,
            text=f"💬 Web Chat Processed\nYou said: _{text}_\n\n🛍️ Swiggy: {swiggy_text}"
        )
            
    return jsonify({
        "transcription": text,
        "message": swiggy_text,
        "cart": []
    })

@app.route('/api/telegram/webhook', methods=['POST'])
def telegram_webhook():
    """Webhook endpoint for Telegram Bot."""
    data = request.json
    if not data:
        return "OK", 200
        
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_BOT_TOKEN:
        add_log("error", "TELEGRAM_BOT_TOKEN not set!")
        return "Error", 500
        
    import requests
    import json
    base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    
    def send_telegram_msg(chat_id, text, reply_markup=None):
        send_telegram_msg_global(chat_id, text, reply_markup)
        
    def process_and_reply(chat_id, sender_name, user_input):
        send_telegram_msg(chat_id, "🤖 Thinking...")
        reply_text = run_agent_sync(user_input, session_id=str(chat_id))
        
        try:
            # Parse the LLM's JSON response for the menu flow
            clean_json = reply_text.strip()
            if clean_json.startswith("```json"):
                clean_json = clean_json[7:]
            if clean_json.endswith("```"):
                clean_json = clean_json[:-3]
                
            reply_json = json.loads(clean_json.strip())
            out_text = reply_json.get("text", reply_text)
            options = reply_json.get("options", [])
        except Exception:
            out_text = reply_text
            options = []
        
        inline_keyboard = []
        for opt in options:
            if "label" in opt and "action" in opt:
                inline_keyboard.append([{"text": opt["label"], "callback_data": opt["action"][:64]}])
        
        # We bypass the web app "Live Voice Call" button for purely interactive chat
        # User will only see Swiggy's options
        
        reply_markup = {"inline_keyboard": inline_keyboard} if inline_keyboard else None
        send_telegram_msg(chat_id, f"🛍️ Swiggy: {out_text}", reply_markup=reply_markup)

    # 1. Handle Callback Queries (Button Clicks)
    if "callback_query" in data:
        cb = data["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        action = cb["data"]
        
        # Acknowledge the callback so the button stops loading
        telegram_api_request("POST", "answerCallbackQuery", json={"callback_query_id": cb["id"]})
        
        add_log("info", f"Telegram Button Clicked: {action}")
        record_user_behavior(chat_id, "telegram_button_click", {"action": action})
        
        if action == "start_chat":
            send_telegram_msg(chat_id, "Great! 💬 What are you craving today?\n\n_(You can order food, groceries via Instamart, or book a Dineout table!)_")
            return "OK", 200
            
        if action == "reset_session":
            from swiggy_agent import CONVERSATIONS
            if str(chat_id) in CONVERSATIONS:
                del CONVERSATIONS[str(chat_id)]
            send_telegram_msg(chat_id, "🔄 Session Killed. Memory wiped!\n\nSend /start to begin a new order.")
            return "OK", 200
            
        process_and_reply(chat_id, cb["from"].get("first_name", "User"), action)
        return "OK", 200

    # 2. Handle Standard Messages
    if "message" not in data:
        return "OK", 200
        
    message = data["message"]
    chat_id = message.get("chat", {}).get("id")
    sender_name = message.get("from", {}).get("first_name", "Unknown")

    # If it's a voice note
    if "voice" in message:
        file_id = message["voice"]["file_id"]
        add_log("info", f"Received Telegram Voice Note from {sender_name}. File ID: {file_id}")
        record_user_behavior(chat_id, "telegram_voice_received", {"file_id": file_id})
        
        file_info_resp = telegram_api_request("GET", f"getFile?file_id={file_id}")
        if not file_info_resp:
            send_telegram_msg(chat_id, "Sorry, I couldn't process your voice note.")
            return "OK", 200
            
        file_info = file_info_resp.json()
        if not file_info.get("ok"):
            send_telegram_msg(chat_id, "Sorry, I couldn't download your voice note.")
            return "OK", 200
            
        file_path = file_info["result"]["file_path"]
        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        
        audio_resp = telegram_api_request("GET", download_url)
        if not audio_resp:
            return "OK", 200
            
        audio_data = audio_resp.content
        temp_path = "/tmp/telegram_audio.ogg"
        with open(temp_path, "wb") as f:
            f.write(audio_data)
            
        send_telegram_msg(chat_id, "🎧 Listening to your order...")
        text = process_audio(temp_path)
        send_telegram_msg(chat_id, f"🎙️ I heard: '{text}'")
        
        process_and_reply(chat_id, sender_name, text)
        
    # If it's a text message
    elif "text" in message:
        text = message["text"]
        add_log("info", f"Received Telegram Text from {sender_name}: {text}")
        record_user_behavior(chat_id, "telegram_text_received", {"text": text})
        
        if text in ["/start", "/reset", "/cancel"]:
            if text in ["/reset", "/cancel"]:
                from swiggy_agent import CONVERSATIONS
                if str(chat_id) in CONVERSATIONS:
                    del CONVERSATIONS[str(chat_id)]
                send_telegram_msg(chat_id, "🔄 Session Killed. Memory wiped!")
                
            host = request.host_url.rstrip('/')
            web_app_url = f"{host}/?uid={chat_id}"
            kb = {
                "inline_keyboard": [
                    [{"text": "📞 Live Call", "web_app": {"url": web_app_url}}],
                    [{"text": "💬 Interactive Chat", "callback_data": "start_chat"}],
                    [{"text": "🔄 Kill Session", "callback_data": "reset_session"}]
                ]
            }
            send_telegram_msg(chat_id, f"Hello {sender_name}! 🍔 Welcome to Voice-to-Swiggy.\n\nChoose an option below to begin:", reply_markup=kb)
            return "OK", 200
            
        process_and_reply(chat_id, sender_name, text)

    return "OK", 200

if __name__ == '__main__':
    app.run(port=3000, debug=True)