"""Immutable snapshot record + the write path into the append-only store.

A `Snapshot` is a frozen value object: once observed it never changes. `persist_snapshots` writes a
batch idempotently, so a crashed poll that replays the same window inserts nothing new.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from . import db


@dataclass(frozen=True)
class Snapshot:
    game_id: str
    book: str
    line: float
    over_odds: float
    under_odds: float
    captured_at: float
    market: str = "totals_h2"
    phase: str = "halftime"
    source: str = "unknown"


def make_snapshot(game_id: str, book: str, line: float, over_odds: float, under_odds: float,
                  source: str = "unknown", captured_at: float | None = None) -> Snapshot:
    return Snapshot(
        game_id=game_id, book=book, line=line, over_odds=over_odds, under_odds=under_odds,
        captured_at=time.time() if captured_at is None else captured_at, source=source,
    )


def persist_snapshots(conn: sqlite3.Connection, snaps: list[Snapshot]) -> int:
    """Append a batch of immutable snapshots. Returns the number of NEW rows written."""
    written = 0
    for s in snaps:
        if db.insert_snapshot(
            conn, s.game_id, s.book, s.line, s.over_odds, s.under_odds,
            market=s.market, phase=s.phase, source=s.source, captured_at=s.captured_at,
        ):
            written += 1
    return written
