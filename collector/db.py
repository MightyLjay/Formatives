"""Append-only SQLite store for immutable 2H-total snapshots.

Design constraints (from PLAN_V2.md Step 2):
  - Append-only. Snapshots are immutable — triggers reject UPDATE/DELETE on the snapshot table.
  - Idempotent & resumable. Re-inserting an identical snapshot is a no-op (INSERT OR IGNORE on a
    natural-key UNIQUE index), so a crashed-and-restarted poll never double-counts or corrupts.
  - Crash-safe. WAL journaling + synchronous=NORMAL.

If this doesn't run unattended for four months, nothing else matters — so the schema is boring on
purpose.
"""
from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id           INTEGER PRIMARY KEY,
    game_id      TEXT    NOT NULL,
    book         TEXT    NOT NULL,
    market       TEXT    NOT NULL DEFAULT 'totals_h2',
    line         REAL    NOT NULL,
    over_odds    REAL    NOT NULL,
    under_odds   REAL    NOT NULL,
    phase        TEXT    NOT NULL DEFAULT 'halftime',   -- pregame | halftime | live
    source       TEXT    NOT NULL DEFAULT 'unknown',
    captured_at  REAL    NOT NULL,                       -- unix seconds, when WE observed it
    UNIQUE (game_id, book, market, line, over_odds, under_odds, captured_at)
);
CREATE INDEX IF NOT EXISTS ix_snap_game ON snapshots (game_id, captured_at);

-- Immutability: snapshots may only be inserted, never changed or removed.
CREATE TRIGGER IF NOT EXISTS snapshots_no_update
BEFORE UPDATE ON snapshots
BEGIN SELECT RAISE(ABORT, 'snapshots are append-only: UPDATE forbidden'); END;
CREATE TRIGGER IF NOT EXISTS snapshots_no_delete
BEFORE DELETE ON snapshots
BEGIN SELECT RAISE(ABORT, 'snapshots are append-only: DELETE forbidden'); END;

CREATE TABLE IF NOT EXISTS games (
    game_id      TEXT PRIMARY KEY,
    league       TEXT,
    home         TEXT,
    away         TEXT,
    scheduled_at REAL,
    h1_total     REAL,     -- points scored in the 1st half (both teams)
    final_total  REAL,     -- FINAL points including any overtime
    went_ot      INTEGER,  -- 0/1
    graded_at    REAL
);

CREATE TABLE IF NOT EXISTS grades (
    id          INTEGER PRIMARY KEY,
    game_id     TEXT NOT NULL,
    book        TEXT NOT NULL,
    bet_side    TEXT NOT NULL,     -- over | under
    entry_line  REAL NOT NULL,
    h2_actual   REAL NOT NULL,     -- final_total - h1_total (OT included)
    result      TEXT NOT NULL,     -- win | loss | push
    graded_at   REAL NOT NULL,
    UNIQUE (game_id, book, bet_side, entry_line)
);

-- Paper bets you log from the edge checker (e.g. a line you saw on 1xbet vs our fair line).
-- Mutable: closing_line/final_total/result/pnl are filled in later when you settle. PAPER ONLY.
CREATE TABLE IF NOT EXISTS paper_bets (
    id           INTEGER PRIMARY KEY,
    game_id      TEXT,
    matchup      TEXT,
    market       TEXT,
    book         TEXT,             -- where you'd bet it (e.g. '1xbet')
    side         TEXT,             -- over | under
    your_line    REAL,             -- the number YOU saw at your book
    your_odds    REAL,             -- American price at your book
    fair_line    REAL,             -- our fair/consensus line at entry
    edge_points  REAL,             -- |your_line - fair_line|
    prob_edge    REAL,             -- estimated win prob - implied price
    placed_at    REAL,
    closing_line REAL,             -- filled in later to compute CLV
    final_total  REAL,             -- filled in later to grade
    result       TEXT DEFAULT 'pending',   -- pending | win | loss | push
    pnl          REAL
);
"""


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)  # so --db data/odds.sqlite works on a fresh clone
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def insert_snapshot(
    conn: sqlite3.Connection,
    game_id: str,
    book: str,
    line: float,
    over_odds: float,
    under_odds: float,
    *,
    market: str = "totals_h2",
    phase: str = "halftime",
    source: str = "unknown",
    captured_at: float | None = None,
) -> bool:
    """Append one immutable snapshot. Returns True if a new row was written, False if it already
    existed (idempotent — safe to replay after a crash)."""
    captured_at = time.time() if captured_at is None else captured_at
    cur = conn.execute(
        """INSERT OR IGNORE INTO snapshots
           (game_id, book, market, line, over_odds, under_odds, phase, source, captured_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (game_id, book, market, line, over_odds, under_odds, phase, source, captured_at),
    )
    conn.commit()
    return cur.rowcount > 0


def upsert_game_result(
    conn: sqlite3.Connection,
    game_id: str,
    h1_total: float,
    final_total: float,
    went_ot: bool,
    **meta,
) -> None:
    """Record the settled game result used for grading. Games (results) are mutable metadata;
    snapshots are not."""
    conn.execute(
        """INSERT INTO games (game_id, league, home, away, scheduled_at, h1_total, final_total, went_ot, graded_at)
           VALUES (:game_id, :league, :home, :away, :scheduled_at, :h1_total, :final_total, :went_ot, :graded_at)
           ON CONFLICT(game_id) DO UPDATE SET
             h1_total=excluded.h1_total, final_total=excluded.final_total,
             went_ot=excluded.went_ot, graded_at=excluded.graded_at""",
        {
            "game_id": game_id,
            "league": meta.get("league"),
            "home": meta.get("home"),
            "away": meta.get("away"),
            "scheduled_at": meta.get("scheduled_at"),
            "h1_total": h1_total,
            "final_total": final_total,
            "went_ot": int(went_ot),
            "graded_at": time.time(),
        },
    )
    conn.commit()


def record_grade(
    conn: sqlite3.Connection,
    game_id: str,
    book: str,
    bet_side: str,
    entry_line: float,
    h2_actual: float,
    result: str,
) -> bool:
    """Idempotently store a graded bet. Returns True if newly written."""
    cur = conn.execute(
        """INSERT OR IGNORE INTO grades
           (game_id, book, bet_side, entry_line, h2_actual, result, graded_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (game_id, book, bet_side, entry_line, h2_actual, result, time.time()),
    )
    conn.commit()
    return cur.rowcount > 0


def insert_paper_bet(conn: sqlite3.Connection, **f) -> int:
    """Log a paper bet. Returns its row id. PAPER ONLY — nothing is placed anywhere."""
    cur = conn.execute(
        """INSERT INTO paper_bets
           (game_id, matchup, market, book, side, your_line, your_odds, fair_line,
            edge_points, prob_edge, placed_at, result)
           VALUES (:game_id, :matchup, :market, :book, :side, :your_line, :your_odds,
                   :fair_line, :edge_points, :prob_edge, :placed_at, 'pending')""",
        {
            "game_id": f.get("game_id"), "matchup": f.get("matchup"), "market": f.get("market"),
            "book": f.get("book", "1xbet"), "side": f["side"], "your_line": f["your_line"],
            "your_odds": f.get("your_odds", -110.0), "fair_line": f["fair_line"],
            "edge_points": f["edge_points"], "prob_edge": f.get("prob_edge"),
            "placed_at": f.get("placed_at", time.time()),
        },
    )
    conn.commit()
    return cur.lastrowid


def snapshot_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]


def graded_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM grades").fetchone()[0]
