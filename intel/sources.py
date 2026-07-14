"""Source registry — beat writers, team accounts, injury feeds, halftime reports, polled continuously.

A `Source` yields timestamped `Report`s of raw text for a game. `extract.extract_availability` turns
each report into structured deltas. This is an interface plus an offline `FixtureSource`; wire real
sources (X/Twitter lists, ESPN/CBB injury feeds, broadcast scrapes) behind the same protocol.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Report:
    game_id: str
    text: str
    ts: float           # when the source published it (drives the latency edge)
    source: str


class Source(Protocol):
    name: str

    def poll(self, game_id: str) -> list[Report]:
        ...


class FixtureSource:
    """Deterministic offline source: one halftime injury report for the demo game."""

    name = "fixture"

    def poll(self, game_id: str) -> list[Report]:
        now = time.time()
        return [
            Report(
                game_id=game_id,
                text="Star guard Jordan Reyes is heading to the locker room and will not return.",
                ts=now,
                source=self.name,
            )
        ]


def poll_all(game_id: str, sources: list[Source]) -> list[Report]:
    reports: list[Report] = []
    for s in sources:
        try:
            reports.extend(s.poll(game_id))
        except Exception as e:
            print(f"[warn] source {s.name} failed: {e}")
    return reports
