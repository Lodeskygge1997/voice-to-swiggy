# logger_store.py
import datetime

server_logs = []

def add_log(level, message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level.upper()}] {message}"
    print(log_entry) # Also print to console for Render logs
    server_logs.insert(0, log_entry)
    if len(server_logs) > 200:
        server_logs.pop()