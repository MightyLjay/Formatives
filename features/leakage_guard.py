"""Make leakage impossible, not merely unlikely.

Every feature is computed from play-by-play. If any feature touches an event that happened AFTER
the halftime buzzer, the model is peeking at the future and every downstream number is a lie. This
module defines the event schema and a guard that RAISES on any post-halftime event. `compute_*`
functions route the events they use through the guard, and `tests/test_leakage.py` fails the build
if the guard ever lets a post-buzzer event through.
"""
from __future__ import annotations

from dataclasses import dataclass


class LeakageError(AssertionError):
    """Raised when a feature computation is handed a play-by-play event from after halftime."""


@dataclass(frozen=True)
class PBPEvent:
    """One play-by-play event.

    `period` uses the feed's native framing: NCAAB has 2 halves (period 1, 2; OT = 3+); NBA has
    4 quarters (halftime after period 2). `seconds_remaining` is seconds left in that period.
    """

    period: int
    seconds_remaining: float
    team: str
    event_type: str          # see EVENT_TYPES
    made: bool = False        # for 'shot'
    is_three: bool = False    # for 'shot'
    rebound_kind: str = ""    # 'off' | 'def' for 'rebound'
    player: str = ""          # for 'foul' and lineup tracking


EVENT_TYPES = {"shot", "free_throw", "rebound", "turnover", "foul"}


@dataclass(frozen=True)
class HalftimeMarker:
    """Defines where halftime sits in the feed's period framing.

    last_period_before_half = 1 for NCAAB (halves), 2 for NBA (quarters). Any event with
    period > last_period_before_half occurred after the halftime buzzer and is leakage.
    """

    last_period_before_half: int = 1


def is_post_halftime(event: PBPEvent, marker: HalftimeMarker) -> bool:
    return event.period > marker.last_period_before_half


def assert_no_leakage(events: list[PBPEvent], marker: HalftimeMarker) -> None:
    """Raise LeakageError if ANY event used occurred after the halftime buzzer.

    This is the contract the whole feature layer relies on. Call it at the top of every feature
    function with the exact events that function consumes.
    """
    offenders = [e for e in events if is_post_halftime(e, marker)]
    if offenders:
        first = offenders[0]
        raise LeakageError(
            f"{len(offenders)} play-by-play event(s) from AFTER the halftime buzzer reached a "
            f"feature (e.g. period={first.period} {first.event_type} by {first.team!r}). "
            f"Halftime is after period {marker.last_period_before_half}; using later events leaks "
            "the future into the halftime state."
        )


def first_half_events(events: list[PBPEvent], marker: HalftimeMarker) -> list[PBPEvent]:
    """Correctly restrict a stream to pre-halftime events (the safe way to prepare input)."""
    return [e for e in events if not is_post_halftime(e, marker)]
