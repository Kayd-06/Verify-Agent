"""
V2a – Independent target re-derivation.
The verifier reads the original source email and independently derives
the correct Notion target ID, without ever looking at what the Worker claimed.
Uses Gemini with rate-limit awareness.
"""
import json
from groq import Groq
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

client = Groq()

_last_call_time = 0.0
_MIN_INTERVAL = 13.0  # 5 req/min free tier → 1 every 12s, use 13 for safety


class Derivation(BaseModel):
    derived_target_id: str
    reasoning: str


def _rate_limit():
    """Groq rate limits are generous, minimal pacing needed."""
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < 2.0:
        time.sleep(2.0 - elapsed)
    _last_call_time = time.time()


def rederive_target(email: dict) -> str:
    """
    Independently derive the correct Notion target ID from the raw email.
    Returns a target_id string (or 'new_ticket' for creates).
    """
    subject = email["subject"]
    body = email["body"]

    prompt = f"""You are an independent audit agent verifying a support ticket system.
Based ONLY on the email below, determine the correct Notion ticket ID that should
be created or updated.

Email Subject: {subject}
Email Body: {body}

Rules:
- If the email clearly refers to an existing project/account, derive the ID from it.
  Examples:
    "Project Alpha"     → ticket_alpha_123
    "Project Alphabet"  → ticket_alphabet_456
    "ACME Industries"   → acme_ind_789
    "ACME Corp"         → acme_corp_101
    "Jon Smith"         → user_jon_smith
    "John Smith"        → user_john_smith
- If it's clearly a brand-new support request, return 'new_ticket'.
- If there is no Notion target at all (e.g., Slack-only actions), return 'none'.

Respond with JSON ONLY containing keys 'derived_target_id' and 'reasoning'."""

    _rate_limit()

    response = client.chat.completions.create(
        model="compound-beta",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    
    parsed_json = json.loads(response.choices[0].message.content)
    return parsed_json.get("derived_target_id", "none")
