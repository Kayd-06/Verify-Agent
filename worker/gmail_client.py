import json

TEST_EMAILS_FILE = "eval/test_emails.json"

def get_unread_emails():
    """Poll for unread emails from the synthetic inbox."""
    try:
        with open(TEST_EMAILS_FILE, "r") as f:
            emails = json.load(f)
            return emails
    except Exception as e:
        print(f"Error reading emails: {e}")
        return []
