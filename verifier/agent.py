"""
Verifier Agent – Phase 5.3
Tails shared/action_log.jsonl, re-derives ground-truth, performs structural diff,
tags confidence, and emits verdicts to shared/verifications.jsonl.

Failure classification map
--------------------------
wrong_target        → Worker wrote to wrong Notion page (HIGH confidence)
no_op_claimed       → Worker claimed success but Notion state unchanged (HIGH)
incomplete_task     → Action marked incomplete by Worker (HIGH)
stale_state         → Notion was overwritten by a later action (HIGH)
duplicate_skipped   → Worker correctly skipped a duplicate (PASS)
semantic_mismatch   → Summary/priority diverges but structurally present (LOW)
none                → No failure
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

# Allow running as: python -m verifier.agent  OR  python verifier/agent.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from worker.gmail_client import get_unread_emails
from worker.mock_api import NotionAPI, SlackAPI
from verifier.rederive import rederive_target
from verifier.settle_retry import settle_and_fetch
from verifier.diff import structural_diff

ACTION_LOG_FILE = "shared/action_log.jsonl"
VERIFICATIONS_FILE = "shared/verifications.jsonl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_processed_ids() -> set:
    """Return set of action_ids already in verifications.jsonl."""
    seen = set()
    if not os.path.exists(VERIFICATIONS_FILE):
        return seen
    with open(VERIFICATIONS_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                seen.add(json.loads(line)["action_id"])
            except (json.JSONDecodeError, KeyError):
                pass
    return seen


def _emit_verdict(
    action_id: str,
    settle_retries: int,
    actual_state,
    derived_target: str,
    result: str,
    failure_category: str,
    confidence: str,
    diffs: list,
    latency_ms: int,
    remediation: str = "pending",
):
    verdict = {
        "action_id": action_id,
        "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "settle_retries": settle_retries,
        "actual_state": actual_state,
        "derived_correct_target": derived_target,
        "result": result,
        "failure_category": failure_category,
        "confidence": confidence,
        "diffs": diffs,
        "remediation": remediation,
        "latency_ms": latency_ms,
        "cost_usd": 0.0,
    }
    with open(VERIFICATIONS_FILE, "a") as f:
        f.write(json.dumps(verdict) + "\n")

    icon = "✅" if result == "PASS" else "❌"
    print(
        f"  {icon} [{result}] action={action_id} "
        f"cat={failure_category} conf={confidence} "
        f"retries={settle_retries} lat={latency_ms}ms"
    )


# ---------------------------------------------------------------------------
# Core verification logic
# ---------------------------------------------------------------------------

def _verify_notion_action(action: dict, email: dict) -> None:
    """Run V2a → V2b → V3 pipeline for a Notion write action."""
    t0 = time.time()
    action_id = action["action_id"]
    claimed_target = action["target_id"]
    # Use claimed_state (the full ticket fields) for structural diff.
    # claimed_result is just the API call response ("resolved"), not the ticket shape.
    claimed_state = action.get("claimed_state") or action["claimed_result"]

    # --- V2a: independent target re-derivation ---
    derived_target = rederive_target(email)

    # Decide if target looks wrong (structural = HIGH confidence)
    # 'new_ticket' from verifier means it agrees a create was correct
    target_mismatch = False
    if derived_target not in ("new_ticket", "none"):
        target_mismatch = derived_target != claimed_target

    # --- V2b + V3: settle window + structural diff ---
    actual, retries = settle_and_fetch(
        NotionAPI.get_ticket, claimed_target, claimed_state
    )
    is_match, diffs = structural_diff(claimed_state, actual)

    # --- Classification & Confidence ---
    if target_mismatch:
        result, cat, conf = "FAIL", "wrong_target", "high"
    elif not is_match:
        result, cat, conf = "FAIL", "no_op_claimed", "high"
    else:
        result, cat, conf = "PASS", "none", "high"

    latency_ms = int((time.time() - t0) * 1000)
    _emit_verdict(action_id, retries, actual, derived_target, result, cat, conf, diffs, latency_ms)


def _verify_slack_action(action: dict) -> None:
    """Slack post verification – structural only (no LLM re-derivation needed)."""
    t0 = time.time()
    action_id = action["action_id"]
    claimed_target = action["target_id"]   # msg_N

    messages = SlackAPI.get_messages("#verity-status")
    msg_ids = [m["id"] for m in messages]

    is_match = claimed_target in msg_ids
    diffs = [] if is_match else [f"Message {claimed_target!r} not found in #verity-status"]
    result = "PASS" if is_match else "FAIL"
    cat = "none" if is_match else "no_op_claimed"

    latency_ms = int((time.time() - t0) * 1000)
    _emit_verdict(action_id, 0, messages, claimed_target, result, cat, "high", diffs, latency_ms)


def _verify_special(action: dict) -> None:
    """Handle pre_empted_duplicate and incomplete immediately."""
    t0 = time.time()
    action_id = action["action_id"]
    action_type = action["action_type"]

    if action_type == "pre_empted_duplicate":
        # Worker correctly skipped — always PASS
        _emit_verdict(action_id, 0, None, "none", "PASS", "duplicate_skipped", "high", [], int((time.time() - t0) * 1000))
    elif action_type == "incomplete":
        # Worker flagged incompleteness — verifier confirms it
        _emit_verdict(action_id, 0, None, "none", "FAIL", "incomplete_task", "high", ["Task marked incomplete by Worker"], int((time.time() - t0) * 1000))


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

def run_verifier():
    emails = get_unread_emails()
    email_corpus = {e["thread_id"]: e for e in emails}

    if not os.path.exists(ACTION_LOG_FILE):
        print("No action log found. Run the worker first.")
        return

    processed = _load_processed_ids()

    with open(ACTION_LOG_FILE, "r") as f:
        actions = [json.loads(l) for l in f if l.strip()]

    pending = [a for a in actions if a["action_id"] not in processed]
    print(f"Verifier found {len(pending)} unverified action(s).")

    for action in pending:
        action_id = action["action_id"]
        action_type = action["action_type"]
        target_app = action.get("target_app", "none")
        source_id = action["source_email_id"]

        print(f"\n→ Verifying action={action_id} type={action_type} app={target_app}")

        if action_type in ("pre_empted_duplicate", "incomplete"):
            _verify_special(action)

        elif target_app == "notion":
            email = email_corpus.get(source_id)
            if email:
                _verify_notion_action(action, email)
            else:
                print(f"  ⚠️  Source email {source_id!r} not found — skipping")

        elif target_app == "slack":
            _verify_slack_action(action)

        else:
            print(f"  ⚠️  Unknown target_app={target_app!r} — skipping")


if __name__ == "__main__":
    run_verifier()
