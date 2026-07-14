"""Detect halftime — the ~12-minute window when the 2H bet is live and information is mispriced.

This is an interface, not a scraper. A live feed reports game state; `is_halftime` decides whether
now is the moment to snapshot `totals_h2`. Wire a real `GameState` source (scoreboard API, PBP feed)
and keep this logic here so the "when to snapshot" rule is testable in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GameState:
    game_id: str
    period: int          # 1 = first half/quarter framing; 2 = second; NCAAB is halves
    clock_seconds: float # seconds remaining in the current period (0 at a buzzer)
    status: str          # "in_progress" | "halftime" | "final" | "scheduled"
    league: str = "NCAAB"


def is_halftime(state: GameState) -> bool:
    """True exactly when the game is between halves and the 2H line is (or is about to be) posted.

    We accept an explicit "halftime" status, or the end of regulation's first half with the clock
    at zero, so a feed that only reports period/clock still triggers correctly.
    """
    if state.status == "halftime":
        return True
    # Halves framing: end of period 1 with the clock expired.
    if state.status == "in_progress" and state.period == 1 and state.clock_seconds <= 0.0:
        return True
    return False


def should_snapshot(state: GameState, already_captured: bool) -> bool:
    """Snapshot iff we're at halftime and haven't already captured this game's halftime window."""
    return is_halftime(state) and not already_captured
