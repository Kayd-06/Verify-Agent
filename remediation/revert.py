from worker.mock_api import NotionAPI, SlackAPI

def auto_revert(target_app, target_id):
    if target_app == "notion":
        NotionAPI.update_ticket(target_id, status="open", summary="[REVERTED BY VERITY]")
    elif target_app == "slack":
        SlackAPI.delete_message("#verity-status", target_id)
    return "reverted"

def re_trigger_step(action_id):
    SlackAPI.post_message("#verity-alerts", f"🔄 RE-TRIGGERED missing step for action {action_id}")
    return "reverted"
