"""One collector cycle, plus quota budgeting. Cron-driven, idempotent, resumable, crash-safe.

Real operation: a cron job calls `run_cycle` every minute. For each in-progress game it checks
`detect.should_snapshot`; at halftime it polls all books and appends immutable snapshots. The next
morning a settle job grades every snapshotted game with `collector.grade`.

`python -m collector.run` runs an OFFLINE demo end-to-end (fixture books, in-memory DB, a synthetic
settled game) so the wiring is exercisable without a feed or network.
"""
from __future__ import annotations

from dataclasses import dataclass

from market.poll import FixtureProvider, poll_once

from . import db
from .detect import GameState, should_snapshot
from .grade import grade
from .snapshot import Snapshot, make_snapshot, persist_snapshots


@dataclass
class QuotaBudget:
    """API-call budget with an 80% warning. Never let a runaway poll burn the month's quota."""

    total: int
    used: int = 0
    warn_at: float = 0.80
    _warned: bool = False

    def consume(self, n: int = 1) -> None:
        self.used += n
        frac = self.used / self.total if self.total else 1.0
        if frac >= self.warn_at and not self._warned:
            self._warned = True
            print(f"[quota] WARNING: {self.used}/{self.total} calls used ({frac:.0%}) — over {self.warn_at:.0%}.")
        if self.used > self.total:
            raise RuntimeError(f"[quota] budget exhausted: {self.used}/{self.total}")

    @property
    def remaining(self) -> int:
        return max(self.total - self.used, 0)


def run_cycle(conn, game_states, providers, budget: QuotaBudget, captured: set[str]) -> int:
    """Snapshot every game currently at halftime that we haven't captured yet. Returns rows written."""
    written = 0
    for state in game_states:
        if not should_snapshot(state, already_captured=state.game_id in captured):
            continue
        budget.consume(1)
        quotes = poll_once(state.game_id, providers)
        snaps = [
            make_snapshot(state.game_id, q.book, q.line, q.over_odds, q.under_odds,
                          source="poll", captured_at=q.ts)
            for q in quotes
        ]
        written += persist_snapshots(conn, snaps)
        captured.add(state.game_id)
    return written


def demo() -> None:
    conn = db.connect(":memory:")
    budget = QuotaBudget(total=100)
    captured: set[str] = set()

    game_id = "DEMO-2026-07-14-NCAAB-0001"
    at_half = GameState(game_id=game_id, period=1, clock_seconds=0.0, status="halftime")

    written = run_cycle(conn, [at_half], [FixtureProvider()], budget, captured)
    print(f"snapshots written: {written} (total in db: {db.snapshot_count(conn)})")

    # Crash-replay idempotency: re-persisting the EXACT SAME snapshots (same captured_at) is a
    # no-op. This is the guarantee that matters after a crash — a re-run never double-counts.
    quotes = poll_once(game_id, [FixtureProvider()])
    snaps = [
        Snapshot(game_id, q.book, q.line, q.over_odds, q.under_odds, q.ts, source="poll")
        for q in quotes
    ]
    first = persist_snapshots(conn, snaps)
    replay = persist_snapshots(conn, snaps)  # identical batch, replayed
    print(f"idempotency check — persist same batch twice: {first} then {replay} new rows "
          "(the replay is a no-op)")

    # Settle the game the next morning. Suppose the 1st half was 52, the game finished 106 (no OT).
    h1_total, final_total, went_ot = 52.0, 106.0, False
    db.upsert_game_result(conn, game_id, h1_total=h1_total, final_total=final_total, went_ot=went_ot)

    # Grade the sharp book's snapshot as an example (bet the UNDER at the fair 104.5 line).
    g = grade("under", entry_line=104.5, h1_total=h1_total, final_total_incl_ot=final_total)
    db.record_grade(conn, game_id, "pinnacle", "under", 104.5, g.h2_actual, g.result)
    print(f"\ngraded: h2_actual = {final_total} - {h1_total} = {g.h2_actual}  -> UNDER 104.5 = {g.result}")
    print(f"graded rows in db: {db.graded_count(conn)}")
    print("\nNote: OT (if any) settles INTO the 2H bet — final_total includes it; the H2 box score does not.")


if __name__ == "__main__":
    demo()
