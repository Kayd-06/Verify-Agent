import hashlib
import json
import os

ACTION_LOG_FILE = "shared/action_log.jsonl"

def check_dedup(thread_id, body):
    """
    Hash the email body (sha1) + thread_id.
    Check against prior entries in action_log.jsonl.
    If a match exists, return True.
    """
    content_hash = f"sha1:{hashlib.sha1((thread_id + body).encode()).hexdigest()}"
    
    if not os.path.exists(ACTION_LOG_FILE):
        return False, content_hash
        
    with open(ACTION_LOG_FILE, "r") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                log_entry = json.loads(line)
                if log_entry.get("content_hash") == content_hash:
                    return True, content_hash
            except json.JSONDecodeError:
                pass
                
    return False, content_hash
