"""Parse and format free-roam action strings for the game engine."""

from __future__ import annotations


def extract_say_clause(response: str) -> str | None:
    """Extract a free-roam say(...) clause from a model response.

    Returns normalized ``say(message)`` for the game engine, or None.
    """
    response = response.strip()
    if not response:
        return None

    candidates: list[str] = []
    if "|" in response:
        candidates.extend(part.strip() for part in response.split("|"))
    candidates.append(response)

    for part in candidates:
        if not part:
            continue
        lower = part.lower()
        if lower.startswith("say(") and part.endswith(")"):
            message = part[part.index("(") + 1 : -1]
            return f"say({message})"
    return None


def combine_action_and_say(action: str, response: str) -> str:
    """Attach free-roam chat to the parsed action for GameEngine."""
    say_clause = extract_say_clause(response)
    if say_clause:
        return f"{action} | {say_clause}"
    return action
