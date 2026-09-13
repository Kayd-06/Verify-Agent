"""
V3 – Structural field-by-field diff.
Compares claimed_result fields against actual Notion ticket state.
"""

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
        if actual_val != claimed_val:
            diffs.append(
                f"Field '{key}': claimed={repr(claimed_val)}, actual={repr(actual_val)}"
            )

    return len(diffs) == 0, diffs
