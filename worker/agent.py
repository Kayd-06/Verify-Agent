import os
import json
import time
from uuid import uuid4
from datetime import datetime, timezone
from groq import Groq
from pydantic import BaseModel
from dotenv import load_dotenv

# Load env before importing other local modules that might rely on it
load_dotenv()

from worker.dedup import check_dedup
from worker.mock_api import NotionAPI, SlackAPI
from worker.gmail_client import get_unread_emails

ACTION_LOG_FILE = "shared/action_log.jsonl"

client = Groq()

class Classification(BaseModel):
    category: str
    priority: str
    summary: str
    action_type: str
    target_id: str

def log_action(action_id, source_email_id, content_hash, action_type, target_app, target_id, claimed_result, claimed_state=None):
    log_entry = {
        "action_id": action_id,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_email_id": source_email_id,
        "content_hash": content_hash,
        "action_type": action_type,
        "target_app": target_app,
        "target_id": target_id,
        "claimed_result": claimed_result,
        "claimed_state": claimed_state  # full ticket/message state written — used by verifier for diff
    }

    with open(ACTION_LOG_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

def process_email(email):
    thread_id = email["thread_id"]
    body = email["body"]
    subject = email["subject"]
    
    action_id = f"a_{uuid4().hex[:8]}"
    
    # 1. W0 dedup check
    is_duplicate, content_hash = check_dedup(thread_id, body)
    if is_duplicate:
        log_action(action_id, thread_id, content_hash, "pre_empted_duplicate", "none", "none", {"status": "skipped", "summary": "Duplicate email detected."})
        return
        
    # 2. Classification call
    prompt = f"""
    Classify the following email for a support ticketing system.
    
    Subject: {subject}
    Body: {body}
    
    Determine:
    - category (e.g., bug, question, feature_request, support, billing, status_update, security, access)
    - priority (high, medium, low)
    - summary (a short 1-sentence summary of the request)
    - action_type (create_ticket or update_ticket or incomplete). Use incomplete if the request is missing critical info to act upon.
    - target_id (If it's an update, guess the target ticket ID based on the text. If creating, generate a suitable ID like 'ticket_abc123' or 'user_jon_smith' based on the text. If none, use 'none'.)
    
    Output JSON ONLY with keys: category, priority, summary, action_type, target_id.
    """
    
    response = client.chat.completions.create(
        model='compound-beta',
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    import re
    content = response.choices[0].message.content or "{}"
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        content = match.group(0)
    classification_dict = json.loads(content)
    classification = Classification(**classification_dict)
    
    if classification.action_type == "incomplete":
         log_action(action_id, thread_id, content_hash, "incomplete", "none", "none", {"status": "skipped", "summary": "Incomplete task."})
         return

    # 3. Actions
    target_id = classification.target_id
    if not target_id or target_id.lower() == "none":
        target_id = f"ticket_{uuid4().hex[:6]}"
        
    if classification.action_type == "create_ticket":
        notion_state = {
            "status": "open",
            "category": classification.category,
            "summary": classification.summary,
            "priority": classification.priority,
        }
        claimed_result = NotionAPI.create_ticket(target_id, classification.category, classification.summary, classification.priority)
    elif classification.action_type == "update_ticket":
        notion_state = {
            "status": "In Progress",
            "category": classification.category,
            "summary": classification.summary,
            "priority": classification.priority,
        }
        claimed_result = NotionAPI.update_ticket(target_id, status="In Progress", category=classification.category, summary=classification.summary, priority=classification.priority)
    else:
        notion_state = None
        claimed_result = {"status": "unknown", "summary": ""}

    # Emit Action Log for Notion (with full intended ticket state for verifier)
    log_action(
        action_id=action_id,
        source_email_id=thread_id,
        content_hash=content_hash,
        action_type=classification.action_type,
        target_app="notion",
        target_id=target_id,
        claimed_result=claimed_result,
        claimed_state=notion_state,
    )

    # Slack post
    slack_msg = f"Processed {classification.action_type} for {target_id}: {classification.summary}"
    slack_msg_id, slack_claimed_result = SlackAPI.post_message("#verity-status", slack_msg)
    
    # Emit Action Log for Slack
    log_action(
        action_id=f"a_{uuid4().hex[:8]}",
        source_email_id=thread_id,
        content_hash=content_hash,
        action_type="post_status",
        target_app="slack",
        target_id=slack_msg_id,
        claimed_result=slack_claimed_result
    )

def run_worker():
    emails = get_unread_emails()
    # Limit to 3 emails for testing purposes
    for email in emails[:3]:
        print(f"Worker processing: {email['subject']}")
        try:
            process_email(email)
        except Exception as e:
            print(f"Error processing email: {e}")
        # Sleep slightly to avoid generic API limits, though Groq is more generous
        time.sleep(2)

if __name__ == "__main__":
    run_worker()
