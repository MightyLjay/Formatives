"""Probe a live odds provider for 2nd-half totals — and STOP to report, before trusting anything.

Same discipline as PLAN_V2.md Step 0: hit the endpoint, print the raw schema, and answer the only
question that matters first — does a live `totals_h2` market actually come back, and which books
carry it? For many leagues it doesn't exist or isn't liquid; find that out for $0 of modelling.

    export ODDS_API_KEY=...            # from the-odds-api.com (free tier is fine to probe)
    python -m market.probe                                   # defaults to NCAAB, totals_h2
    python -m market.probe --sport basketball_nba --market totals_h2
    python -m market.probe --event <event_id>                # probe one specific game

Nothing here runs from the build sandbox (blocked egress, no key). Run it where the network is open
— your own machine or a VPS.
"""
from __future__ import annotations

import argparse
import json
import sys

from .fair import fair_line
from .outliers import find_outliers
from .providers import TheOddsAPIProvider


def probe(sport: str, market: str, event_id: str | None, raw: bool) -> int:
    prov = TheOddsAPIProvider(sport=sport, market=market)
    if not prov.api_key:
        print("ERROR: set ODDS_API_KEY (get one free at https://the-odds-api.com/).", file=sys.stderr)
        return 2

    # 1) What games are on the board?
    try:
        events = prov.list_events()
    except Exception as e:
        print(f"ERROR listing events for {sport!r}: {e}", file=sys.stderr)
        return 2
    print(f"sport={sport}  events on the board: {len(events)}  "
          f"(quota remaining: {prov.requests_remaining})")
    if not events:
        print("No events. Wrong sport key, off-season, or nothing scheduled.")
        return 1

    # 2) Pick an event and pull the 2H-total market.
    ev = next((e for e in events if e.get("id") == event_id), events[0]) if event_id else events[0]
    print(f"\nprobing event {ev.get('id')}: {ev.get('away_team')} @ {ev.get('home_team')} "
          f"(tip {ev.get('commence_time')})")
    try:
        quotes = prov.fetch(ev["id"])
    except Exception as e:
        print(f"ERROR fetching {market!r} for event: {e}", file=sys.stderr)
        return 2

    # 3) The verdict: does the 2H total exist, and where?
    print(f"\n=== VERDICT for market {market!r} ===")
    if not quotes:
        print(f"NO {market} quotes returned for this event.")
        print("This is the expected outcome pre-game (2H totals are an IN-PLAY line) or for a")
        print("league where the 2H market doesn't exist. Re-run at halftime of a live game, and")
        print("try other regions (--regions us,us2,uk,eu,au) before concluding it's unavailable.")
        return 1

    print(f"{market} IS available. {len(quotes)} book(s) posting it:")
    for q in quotes:
        tag = "sharp" if q.is_sharp else "soft "
        print(f"  {tag} {q.book:16s} line={q.line:6.1f}  over={q.over_odds:+.0f} under={q.under_odds:+.0f}")

    # 4) If we have quotes, the whole downstream pipeline just works — show it.
    try:
        fl = fair_line(quotes)
        print(f"\nfair line (anchor={fl.anchor}): {fl.line:.1f}  P(over)={fl.p_over:.3f}")
        opps = find_outliers(quotes, fl, min_gap=1.0)
        if opps:
            print("live outliers vs the sharp consensus:")
            for o in opps:
                print(f"  {o.book:16s} bet {o.side.upper():5s} @ {o.soft_line:6.1f} "
                      f"(gap {o.gap_points:+.1f} pts, est. edge {o.prob_edge:+.3f})")
        else:
            print("no soft book is meaningfully off the sharp consensus right now.")
    except Exception as e:
        print(f"(fair-line/outlier step skipped: {e})")

    if raw:
        print("\n=== RAW quotes (JSON) ===")
        print(json.dumps([q.__dict__ for q in quotes], indent=2))
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="probe a live odds provider for 2H totals, then report")
    ap.add_argument("--sport", default="basketball_ncaab")
    ap.add_argument("--market", default="totals_h2")
    ap.add_argument("--event", default=None, help="probe a specific event id (else the first on the board)")
    ap.add_argument("--raw", action="store_true", help="also dump the parsed quotes as JSON")
    args = ap.parse_args()
    sys.exit(probe(args.sport, args.market, args.event, args.raw))


if __name__ == "__main__":
    main()
