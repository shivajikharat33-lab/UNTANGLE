"""Shared settings that every part of UNTANGLE must agree on.

Confidence cutoffs live here. A score is turned into high, medium, or low
with these two numbers only. The API database URL and upload limits are
added when the server is built.
"""

HIGH_CONFIDENCE_MIN = 0.85
MEDIUM_CONFIDENCE_MIN = 0.60


def level_for_score(score: float) -> str:
    """Return the confidence level for a score between 0 and 1."""
    if score >= HIGH_CONFIDENCE_MIN:
        return "high"
    if score >= MEDIUM_CONFIDENCE_MIN:
        return "medium"
    return "low"
