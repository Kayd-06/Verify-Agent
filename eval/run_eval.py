import json
import os
import time
import statistics
import sys

# Set up paths relative to project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worker.agent import process_email
from verifier.agent import run_verifier

def clear_dbs():
    for f in ["shared/action_log.jsonl", "shared/verifications.jsonl", "shared/notion_db.json", "shared/slack_db.json"]:
        if os.path.exists(f):
            open(f, 'w').close() # Truncate or create empty

def run_eval():
    clear_dbs()
    print("Cleaned databases. Starting eval run...")
    
    with open("eval/test_emails.json", "r") as f:
        emails = json.load(f)
        
    print(f"Loaded {len(emails)} test emails. Throttling to stay under rate limits (sleep 4.5s between emails)...")
    
    # To track ground truth
    expected_failures_threads = set()
    for e in emails:
        # According to test data, if expected_action != what actually happens, it's a failure.
        # For simplicity, if there's a decoy target, it's meant to fail.
        if "decoy_target_id" in e or e.get("expected_action") == "incomplete":
            expected_failures_threads.add(e["thread_id"])
    
    for idx, email in enumerate(emails):
        print(f"\n--- Processing Email {idx+1}/{len(emails)}: {email['subject']} ---")
        
        # 1. Run Worker
        try:
            process_email(email)
        except Exception as e:
            print(f"Worker Error: {e}")
        
        # 2. Run Verifier
        try:
            run_verifier()
        except Exception as e:
            print(f"Verifier Error: {e}")
        
        # 3. Throttle
        time.sleep(4.5)

    # --- Compute Metrics ---
    action_map = {}
    if os.path.exists("shared/action_log.jsonl"):
        with open("shared/action_log.jsonl", "r") as f:
            for line in f:
                if line.strip():
                    a = json.loads(line)
                    action_map[a["action_id"]] = a["source_email_id"]

    verifications = []
    if os.path.exists("shared/verifications.jsonl"):
        with open("shared/verifications.jsonl", "r") as f:
            verifications = [json.loads(line) for line in f if line.strip()]
            
    print("\n\n===========================================")
    print("             TRUST REPORT (EVAL)           ")
    print("===========================================")
    
    total_actions = len(verifications)
    if total_actions == 0:
        print("No actions verified.")
        return
        
    pass_count = sum(1 for v in verifications if v["result"] == "PASS")
    fail_count = sum(1 for v in verifications if v["result"] == "FAIL")
    
    auto_fixed = sum(1 for v in verifications if v.get("remediation") == "reverted")
    escalated = sum(1 for v in verifications if v.get("remediation") == "escalated")
    
    latencies = [v.get("latency_ms", 0) for v in verifications]
    median_latency = statistics.median(latencies) if latencies else 0
    
    # True positives, false positives, etc.
    true_positives = 0  # correctly flagged as FAIL
    false_positives = 0 # incorrectly flagged as FAIL
    true_negatives = 0  # correctly passed
    false_negatives = 0 # incorrectly passed
    
    for v in verifications:
        thread_id = action_map.get(v["action_id"])
        is_expected_fail = thread_id in expected_failures_threads
        
        if v["result"] == "FAIL":
            if is_expected_fail:
                true_positives += 1
            else:
                false_positives += 1
        else:
            if is_expected_fail:
                # wait, if expected fail but it passed, it's a false negative
                # but what if it's a duplicate that was skipped correctly?
                # duplicate_skipped is a PASS, but it's a correct behavior.
                if v.get("failure_category") == "duplicate_skipped":
                    true_negatives += 1
                else:
                    false_negatives += 1
            else:
                true_negatives += 1
                
    total_expected_fails = true_positives + false_negatives
    recall = (true_positives / total_expected_fails) * 100 if total_expected_fails else 100
    precision = (true_positives / (true_positives + false_positives)) * 100 if (true_positives + false_positives) else 100
    accuracy = ((true_positives + true_negatives) / total_actions) * 100 if total_actions else 100
    
    print(f"Total Actions Verified : {total_actions}")
    print(f"PASS                   : {pass_count}")
    print(f"FAIL                   : {fail_count}")
    print(f"Auto-fixed             : {auto_fixed}")
    print(f"Escalated              : {escalated}")
    print(f"Median Time-to-Detect  : {median_latency:.1f} ms")
    print(f"Verifier Accuracy      : {accuracy:.1f}%")
    print(f"Verifier Precision     : {precision:.1f}%")
    print(f"Verifier Recall        : {recall:.1f}%")
    
    print("\nEvaluation complete! Dashboard should reflect these results.")

if __name__ == "__main__":
    run_eval()
