import os
import json
import uuid
import threading
from datetime import datetime
from logger_store import add_log

# Attempt to initialize Supabase client
supabase = None
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        add_log("info", "Supabase APIGW Backend Initialized Successfully.")
    except Exception as e:
        add_log("error", f"Failed to initialize Supabase: {str(e)}")

# Fallback in-memory storage
_traces = []
_user_behavior = []
_store_lock = threading.Lock()

def record_trace(direction, method, url, request_headers, request_body, response_status, response_headers, response_body, duration_ms):
    """
    Records an HTTP network trace to Supabase, falling back to memory.
    """
    safe_req_headers = dict(request_headers) if request_headers else {}
    if "api-subscription-key" in safe_req_headers:
        safe_req_headers["api-subscription-key"] = "REDACTED"
    if "Authorization" in safe_req_headers:
        safe_req_headers["Authorization"] = "REDACTED"
        
    trace = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now().isoformat(),
        "direction": direction,
        "method": method,
        "url": url,
        "request_headers": safe_req_headers,
        "request_body": request_body if isinstance(request_body, str) else json.dumps(request_body, default=str),
        "response_status": response_status,
        "response_headers": dict(response_headers) if response_headers else {},
        "response_body": response_body if isinstance(response_body, str) else json.dumps(response_body, default=str),
        "duration_ms": duration_ms
    }
    
    # Try Supabase first
    if supabase:
        try:
            # We must not block the main thread for too long in a real prod app, 
            # but for this trace we do a synchronous insert
            supabase.table('apigw_traces').insert(trace).execute()
            return trace
        except Exception as e:
            add_log("error", f"Supabase Trace Insert Failed: {str(e)}")
            # Fall through to memory
            
    # Fallback Memory
    with _store_lock:
        trace["timestamp"] = trace["created_at"] # mapping for memory UI
        _traces.append(trace)
        if len(_traces) > 200:
            _traces.pop(0)
            
    return trace

def record_user_behavior(user_id, action, details):
    """
    Records centralized user behavior events.
    """
    event = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now().isoformat(),
        "user_id": str(user_id),
        "action": action,
        "details": details if isinstance(details, dict) else {"info": str(details)}
    }
    
    if supabase:
        try:
            supabase.table('user_behavior').insert(event).execute()
            return event
        except Exception as e:
            add_log("error", f"Supabase Behavior Insert Failed: {str(e)}")
            
    # Fallback Memory
    with _store_lock:
        _user_behavior.append(event)
        if len(_user_behavior) > 500:
            _user_behavior.pop(0)
    return event

def get_traces():
    """
    Fetch traces for the dashboard.
    """
    if supabase:
        try:
            response = supabase.table('apigw_traces').select('*').order('created_at', desc=True).limit(100).execute()
            # Map created_at to timestamp for the UI
            traces = response.data
            for t in traces:
                t['timestamp'] = t['created_at'].split('T')[1][:12] if 'T' in t['created_at'] else t['created_at']
            return traces
        except Exception as e:
            add_log("error", f"Supabase Trace Fetch Failed: {str(e)}")
            
    with _store_lock:
        return list(reversed(_traces))