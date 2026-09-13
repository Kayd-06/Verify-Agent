import json
import os

NOTION_DB_FILE = "shared/notion_db.json"
SLACK_DB_FILE = "shared/slack_db.json"

def _load_db(file_path):
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def _save_db(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

class NotionAPI:
    @staticmethod
    def create_ticket(target_id, category, summary, priority):
        db = _load_db(NOTION_DB_FILE)
        db[target_id] = {
            "status": "open",
            "category": category,
            "summary": summary,
            "priority": priority
        }
        _save_db(NOTION_DB_FILE, db)
        return {"status": "resolved", "summary": summary}
        
    @staticmethod
    def update_ticket(target_id, status=None, category=None, summary=None, priority=None):
        db = _load_db(NOTION_DB_FILE)
        if target_id not in db:
            db[target_id] = {"status": "open", "category": "unknown", "summary": "", "priority": "low"}
        
        if status: db[target_id]["status"] = status
        if category: db[target_id]["category"] = category
        if summary: db[target_id]["summary"] = summary
        if priority: db[target_id]["priority"] = priority
        
        _save_db(NOTION_DB_FILE, db)
        return {"status": "resolved", "summary": db[target_id]["summary"]}

    @staticmethod
    def get_ticket(target_id):
        db = _load_db(NOTION_DB_FILE)
        return db.get(target_id, None)

class SlackAPI:
    @staticmethod
    def post_message(channel, message):
        db = _load_db(SLACK_DB_FILE)
        if channel not in db:
            db[channel] = []
        msg_id = f"msg_{len(db[channel]) + 1}"
        db[channel].append({"id": msg_id, "text": message})
        _save_db(SLACK_DB_FILE, db)
        return msg_id, {"status": "resolved", "summary": f"Posted to {channel}"}
        
    @staticmethod
    def delete_message(channel, msg_id):
        db = _load_db(SLACK_DB_FILE)
        if channel in db:
            db[channel] = [m for m in db[channel] if m["id"] != msg_id]
            _save_db(SLACK_DB_FILE, db)

    @staticmethod
    def get_messages(channel):
        db = _load_db(SLACK_DB_FILE)
        return db.get(channel, [])
