"""Append-only store: immutability is enforced by triggers, and inserts are idempotent."""
import sqlite3

import pytest

from collector import db
from collector.snapshot import make_snapshot, persist_snapshots


def _conn():
    return db.connect(":memory:")


def test_snapshot_insert_is_idempotent():
    conn = _conn()
    assert db.insert_snapshot(conn, "G1", "pinnacle", 104.5, -105, -105, captured_at=1000.0) is True
    # Same natural key -> no-op.
    assert db.insert_snapshot(conn, "G1", "pinnacle", 104.5, -105, -105, captured_at=1000.0) is False
    assert db.snapshot_count(conn) == 1
    # A different captured_at is a genuinely new observation.
    assert db.insert_snapshot(conn, "G1", "pinnacle", 104.5, -105, -105, captured_at=1060.0) is True
    assert db.snapshot_count(conn) == 2


def test_snapshots_are_immutable():
    conn = _conn()
    db.insert_snapshot(conn, "G1", "pinnacle", 104.5, -105, -105, captured_at=1000.0)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE snapshots SET line = 200 WHERE game_id = 'G1'")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM snapshots WHERE game_id = 'G1'")


def test_persist_snapshots_batch_and_replay():
    conn = _conn()
    snaps = [
        make_snapshot("G1", "pinnacle", 104.5, -105, -105, captured_at=1000.0),
        make_snapshot("G1", "draftkings", 105.0, -110, -110, captured_at=1000.0),
    ]
    assert persist_snapshots(conn, snaps) == 2
    # Replaying the identical batch (e.g. after a crash) writes nothing new.
    assert persist_snapshots(conn, snaps) == 0
    assert db.snapshot_count(conn) == 2


def test_grade_records_idempotent():
    conn = _conn()
    assert db.record_grade(conn, "G1", "pinnacle", "under", 104.5, 54.0, "win") is True
    assert db.record_grade(conn, "G1", "pinnacle", "under", 104.5, 54.0, "win") is False
    assert db.graded_count(conn) == 1
