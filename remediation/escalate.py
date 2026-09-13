from worker.mock_api import SlackAPI

def escalate_failure(action_id, category, confidence, retries, diffs):
    diff_text = "\n- ".join(diffs) if diffs else "N/A"
    msg = (
        f"🚨 *VERITY ESCALATION* 🚨\n"
        f"*Action*: `{action_id}`\n"
        f"*Confidence*: `{confidence.upper()}`\n"
        f"*Category*: `{category}`\n"
        f"*Retries*: `{retries}`\n"
        f"*Diff*:\n- {diff_text}"
    )
    SlackAPI.post_message("#verity-alerts", msg)
    return "escalated"
