"""Continuous odds monitor — the live path of the collector.

Polls a provider on an interval, appends every 2H-total quote as an immutable snapshot, and honours
an API quota with an 80% warning. Append-only + idempotent means a crash-and-restart never
double-counts, so this is safe to run under a process supervisor for months.

    export ODDS_API_KEY=...
    python -m collector.monitor --sport basketball_ncaab --interval 60 --db data/odds.sqlite
    python -m collector.monitor --dry-run          # offline: fixture provider, in-memory DB

QUOTA WARNING: each cycle costs ~1 credit per event fetched (per region set) on The Odds API. The
free tier is ~500/month. Poll only the games you care about (--events) and a sane --interval, or
you will burn the month's quota in an afternoon. The monitor stops itself when the real
`x-requests-remaining` counter hits zero.
"""
from __future__ import annotations

import argparse
import signal
import time

from market.providers import TheOddsAPIProvider

from . import db
from .run import QuotaBudget
from .snapshot import Snapshot, persist_snapshots

_STOP = False


def _handle_sigint(signum, frame):
    global _STOP
    _STOP = True
    print("\n[monitor] stop requested — finishing the current cycle and exiting cleanly.")


def run_monitor(
    provider,
    conn,
    interval: float = 60.0,
    event_ids: list[str] | None = None,
    max_events: int = 20,
    max_cycles: int | None = None,
    budget: QuotaBudget | None = None,
) -> None:
    """Poll `provider` every `interval` seconds, persisting 2H-total snapshots into `conn`.

    event_ids : restrict polling to these games (recommended — quota control). If None, the first
                `max_events` events on the board are polled.
    """
    signal.signal(signal.SIGINT, _handle_sigint)
    cycle = 0
    while not _STOP:
        cycle += 1
        t0 = time.time()
        try:
            targets = event_ids or [e["id"] for e in provider.list_events()[:max_events]]
        except Exception as e:
            print(f"[monitor] cycle {cycle}: list_events failed: {e}; retrying next interval")
            targets = []

        written = 0
        for eid in targets:
            if budget is not None:
                budget.consume(1)
            try:
                quotes = provider.fetch(eid)
            except Exception as e:
                print(f"[monitor]   event {eid}: fetch failed: {e}")
                continue
            snaps = [
                Snapshot(eid, q.book, q.line, q.over_odds, q.under_odds, q.ts, source=provider.name)
                for q in quotes
            ]
            written += persist_snapshots(conn, snaps)

        remaining = getattr(provider, "requests_remaining", None)
        print(f"[monitor] cycle {cycle}: {len(targets)} events, {written} new snapshots "
              f"(db total {db.snapshot_count(conn)}"
              + (f", quota remaining {remaining}" if remaining is not None else "") + ")")

        if remaining is not None and remaining <= 0:
            print("[monitor] API quota exhausted — stopping.")
            break
        if max_cycles is not None and cycle >= max_cycles:
            break
        if _STOP:
            break

        # Sleep the remainder of the interval (interruptibly).
        elapsed = time.time() - t0
        for _ in range(int(max(interval - elapsed, 0))):
            if _STOP:
                break
            time.sleep(1)


def _dry_run() -> None:
    """Offline demo: fixture provider, one synthetic event, in-memory DB, two quick cycles."""
    from market.poll import FixtureProvider

    class _FixtureEventProvider(FixtureProvider):
        def list_events(self):
            return [{"id": "DEMO-EVENT-1"}]

    conn = db.connect(":memory:")
    run_monitor(_FixtureEventProvider(), conn, interval=1.0, max_cycles=2, budget=QuotaBudget(total=50))
    print("\n[monitor] dry-run complete. Wire a real provider + ODDS_API_KEY to monitor live odds.")


def main() -> None:
    ap = argparse.ArgumentParser(description="continuously monitor 2H-total odds")
    ap.add_argument("--dry-run", action="store_true", help="offline demo (fixture provider)")
    ap.add_argument("--sport", default="basketball_ncaab")
    ap.add_argument("--market", default="totals_h2")
    ap.add_argument("--regions", default="us,us2")
    ap.add_argument("--interval", type=float, default=60.0, help="seconds between polls")
    ap.add_argument("--events", nargs="*", default=None, help="specific event ids to poll (quota control)")
    ap.add_argument("--max-events", type=int, default=20)
    ap.add_argument("--db", default="data/odds.sqlite")
    ap.add_argument("--quota", type=int, default=500, help="soft budget for the 80% warning")
    args = ap.parse_args()

    if args.dry_run:
        _dry_run()
        return

    provider = TheOddsAPIProvider(sport=args.sport, market=args.market, regions=args.regions)
    if not provider.api_key:
        raise SystemExit("set ODDS_API_KEY (https://the-odds-api.com/) or use --dry-run")
    conn = db.connect(args.db)
    print(f"[monitor] {args.sport} {args.market}; polling every {args.interval}s into {args.db}. Ctrl-C to stop.")
    run_monitor(provider, conn, interval=args.interval, event_ids=args.events,
                max_events=args.max_events, budget=QuotaBudget(total=args.quota))


if __name__ == "__main__":
    main()
