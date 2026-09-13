"""
V3 – Structural field-by-field diff.
Compares claimed_result fields against actual Notion ticket state.
"""

import difflib

def structural_diff(claimed: dict, actual: dict | None) -> tuple[bool, list[str]]:
    """
    Returns (is_match, list_of_diff_messages).
    If actual is None the target was never written — always a mismatch.
    """
    if actual is None:
        return False, ["Target ticket not found in Notion DB"]

    diffs = []
    for key, claimed_val in claimed.items():
        actual_val = actual.get(key)
        
        # Fuzzy match for summary
        if key == "summary" and isinstance(claimed_val, str) and isinstance(actual_val, str):
            similarity = difflib.SequenceMatcher(None, claimed_val.lower(), actual_val.lower()).ratio()
            if similarity < 0.6:  # 60% similarity threshold
                diffs.append(
                    f"Field '{key}' semantic mismatch (similarity: {similarity:.2f}): claimed={repr(claimed_val)}, actual={repr(actual_val)}"
                )
        else:
            # Exact match for structured fields (category, priority, status)
            if actual_val != claimed_val:
                diffs.append(
                    f"Field '{key}': claimed={repr(claimed_val)}, actual={repr(actual_val)}"
                )

    return len(diffs) == 0, diffs
