"""Live odds providers. Poll every book you can reach, continuously, timestamped.

These adapters implement the `market.poll.Provider` protocol (`fetch(game_id) -> list[BookQuote]`)
so they drop straight into the existing pipeline (fair line -> outliers -> CLV -> collector).

`requests` is imported lazily so the tested core never depends on it. Nothing here has been run
against a live endpoint from the build sandbox (egress is blocked there) — run `market/probe.py`
first to confirm the 2H market actually comes back for your sport before trusting the feed.

The Odds API (the-odds-api.com), v4:
  - Period markets like `totals_h2` live on the PER-EVENT endpoint, not the bulk odds endpoint.
  - Each response carries quota headers (x-requests-remaining / x-requests-used) — we surface them
    so the collector's QuotaBudget can enforce the 80% warning against the real counter.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from .fair import BookQuote

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Books we treat as sharp for the fair-line anchor (lowercased contains-match on the book title).
SHARP_TITLES = ("pinnacle", "circa", "bookmaker", "betcris")


@dataclass
class TheOddsAPIProvider:
    """Adapter for The Odds API v4.

    api_key : your key (defaults to the ODDS_API_KEY env var).
    sport   : e.g. 'basketball_ncaab', 'basketball_nba', 'basketball_wncaab'.
    market  : the 2H total market key. 'totals_h2' is the standard; some feeds use 'totals_h1'
              for the 1st half — we want the 2nd.
    regions : comma-separated region codes (us,us2,uk,eu,au) — more regions = more books = more credits.
    """

    api_key: str = field(default_factory=lambda: os.environ.get("ODDS_API_KEY", ""))
    sport: str = "basketball_ncaab"
    market: str = "totals_h2"
    regions: str = "us,us2"
    odds_format: str = "american"
    timeout: float = 15.0
    name: str = "the-odds-api"
    requests_remaining: int | None = None  # updated from response headers after each call

    def _get(self, path: str, **params):
        import requests  # lazy: only needed for live polling

        if not self.api_key:
            raise RuntimeError("no API key: set ODDS_API_KEY or pass api_key=")
        params = {"apiKey": self.api_key, **params}
        resp = requests.get(f"{ODDS_API_BASE}{path}", params=params, timeout=self.timeout)
        rem = resp.headers.get("x-requests-remaining")
        if rem is not None:
            self.requests_remaining = int(rem)
        resp.raise_for_status()
        return resp.json()

    def list_events(self) -> list[dict]:
        """Upcoming/live events for the sport: [{id, commence_time, home_team, away_team}, ...]."""
        return self._get(f"/sports/{self.sport}/events")

    def fetch(self, game_id: str) -> list[BookQuote]:
        """Return every book's 2H-total two-way price for one event id, at this instant.

        Books that don't currently post the 2H total (common — it's an in-play line) are simply
        absent from the result, which is itself a signal worth recording.
        """
        data = self._get(
            f"/sports/{self.sport}/events/{game_id}/odds",
            regions=self.regions,
            markets=self.market,
            oddsFormat=self.odds_format,
        )
        return _quotes_from_event(data, self.market)


def _quotes_from_event(event: dict, market_key: str) -> list[BookQuote]:
    now = time.time()
    quotes: list[BookQuote] = []
    for bm in event.get("bookmakers", []):
        title = bm.get("title", bm.get("key", "unknown"))
        for mk in bm.get("markets", []):
            if mk.get("key") != market_key:
                continue
            over = under = None
            line = None
            for oc in mk.get("outcomes", []):
                name = (oc.get("name") or "").lower()
                if name == "over":
                    over, line = oc.get("price"), oc.get("point")
                elif name == "under":
                    under, line = oc.get("price"), oc.get("point")
            if over is None or under is None or line is None:
                continue  # incomplete two-way quote — skip rather than guess
            quotes.append(
                BookQuote(
                    book=title,
                    line=float(line),
                    over_odds=float(over),
                    under_odds=float(under),
                    ts=now,
                    is_sharp=any(s in title.lower() for s in SHARP_TITLES),
                )
            )
    return quotes


@dataclass
class SportsGameOddsProvider:
    """Placeholder adapter for SportsGameOdds (claims 80+ books, has period markets).

    Left as a thin stub with the same protocol so you can swap providers without touching the rest
    of the pipeline. Fill in `fetch` from their docs (schema differs from The Odds API); the mapping
    target is always the same: one `BookQuote` per book with line + two-way American odds + ts.
    """

    api_key: str = field(default_factory=lambda: os.environ.get("SGO_API_KEY", ""))
    sport: str = "BASKETBALL"
    name: str = "sportsgameodds"

    def fetch(self, game_id: str) -> list[BookQuote]:  # pragma: no cover - not wired
        raise NotImplementedError(
            "SportsGameOdds adapter not implemented — map their per-book period-total response to "
            "BookQuote(book, line, over_odds, under_odds, ts, is_sharp). See TheOddsAPIProvider."
        )
