"""Experimental symbol suggestions. Off by default. Nothing is written to the graph."""


def symbol_suggestions(enabled: bool, crop_supplied: bool = False) -> dict:
    """Return suggestions only when the flag is on and a crop was supplied."""
    if not enabled:
        return {
            "available": False,
            "suggestions": [],
            "note": "Few-shot symbol suggestions are off. This is not a trained model.",
        }
    if not crop_supplied:
        return {
            "available": True,
            "suggestions": [],
            "note": "No example crop was supplied. Nothing was added to the graph.",
        }
    return {
        "available": True,
        "suggestions": [],
        "note": "Suggestions require confirmation. Nothing was added to the graph.",
    }
