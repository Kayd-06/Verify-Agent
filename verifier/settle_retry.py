"""
V2b – Settle-window retry logic.
Retries a fetch function with 500ms → 1s → 2s backoff to handle
read-after-write races before finalising a verdict.
"""
import time
from verifier.diff import structural_diff


def settle_and_fetch(fetch_fn, target_id: str, claimed: dict) -> tuple[dict | None, int]:
    """
    Calls fetch_fn(target_id) up to 3 times (initial + 2 retries).
    Stops early if the structural diff passes.
    Returns (final_actual_state, number_of_retries_used).
    """
    backoffs = [0.5, 1.0, 2.0]
    retries = 0

    for attempt, backoff in enumerate(backoffs):
        actual = fetch_fn(target_id)
        is_match, _ = structural_diff(claimed, actual)

        if is_match:
            return actual, retries

        if attempt < len(backoffs) - 1:
            time.sleep(backoff)
            retries += 1

    # Return whatever we got after exhausting retries
    return fetch_fn(target_id), retries
