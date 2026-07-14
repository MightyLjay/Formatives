"""The Odds API response -> BookQuote mapping, and the monitor's offline dry-run.

The network call itself can't run here (no key, blocked egress), but the parsing — the part that
actually turns a provider's JSON into the pipeline's BookQuote — is pure and fully testable.
"""
from collector import db
from collector.monitor import run_monitor
from collector.run import QuotaBudget
from market.fair import fair_line
from market.outliers import find_outliers
from market.poll import FixtureProvider
from market.providers import _quotes_from_event

# A realistic slice of a The Odds API v4 per-event `totals_h2` response.
SAMPLE_EVENT = {
    "id": "abc123",
    "home_team": "Duke",
    "away_team": "UNC",
    "bookmakers": [
        {
            "key": "pinnacle",
            "title": "Pinnacle",
            "markets": [
                {
                    "key": "totals_h2",
                    "outcomes": [
                        {"name": "Over", "price": -105, "point": 68.5},
                        {"name": "Under", "price": -105, "point": 68.5},
                    ],
                }
            ],
        },
        {
            "key": "lazybook",
            "title": "LazyBook",
            "markets": [
                {
                    "key": "totals_h2",
                    "outcomes": [
                        {"name": "Over", "price": -110, "point": 72.5},
                        {"name": "Under", "price": -110, "point": 72.5},
                    ],
                }
            ],
        },
        {
            "key": "noh2",
            "title": "NoH2Book",
            "markets": [  # only full-game total -> correctly ignored for totals_h2
                {"key": "totals", "outcomes": [{"name": "Over", "price": -110, "point": 140.5}]}
            ],
        },
    ],
}


def test_parse_maps_books_and_flags_sharp():
    quotes = _quotes_from_event(SAMPLE_EVENT, "totals_h2")
    assert len(quotes) == 2  # noh2book has no totals_h2 -> excluded
    by_book = {q.book: q for q in quotes}
    assert by_book["Pinnacle"].is_sharp is True
    assert by_book["Pinnacle"].line == 68.5
    assert by_book["LazyBook"].is_sharp is False
    assert by_book["LazyBook"].over_odds == -110


def test_parsed_quotes_flow_through_pipeline():
    quotes = _quotes_from_event(SAMPLE_EVENT, "totals_h2")
    fl = fair_line(quotes)
    assert fl.anchor.lower() == "pinnacle"
    assert fl.line == 68.5
    opps = find_outliers(quotes, fl, min_gap=1.0)
    assert opps and opps[0].book == "LazyBook" and opps[0].side == "under"


def test_incomplete_two_way_quote_is_skipped():
    ev = {
        "bookmakers": [
            {"title": "OneSided", "markets": [
                {"key": "totals_h2", "outcomes": [{"name": "Over", "price": -110, "point": 70.5}]}
            ]}
        ]
    }
    assert _quotes_from_event(ev, "totals_h2") == []


def test_monitor_dry_run_persists_and_is_idempotent():
    from market.fair import BookQuote

    class _FixedTimeProvider:
        """Returns the same quotes at a FIXED capture time, so re-polling replays an identical
        batch — which is exactly the crash-replay case the append-only store must dedupe."""

        name = "fixture"

        def list_events(self):
            return [{"id": "DEMO-EVENT-1"}]

        def fetch(self, event_id):
            return [
                BookQuote("pinnacle", 68.5, -105, -105, ts=1000.0, is_sharp=True),
                BookQuote("lazybook", 72.5, -110, -110, ts=1000.0),
            ]

    conn = db.connect(":memory:")
    run_monitor(_FixedTimeProvider(), conn, interval=0.0, max_cycles=3, budget=QuotaBudget(total=50))
    # 2 books, same captured_at across all 3 cycles -> the last two cycles are pure no-ops.
    assert db.snapshot_count(conn) == 2


def test_monitor_distinct_polls_build_a_time_series():
    """Two polls at DIFFERENT instants are two observations, not duplicates — the point of the
    monitor is to accumulate the line's movement over time."""
    from market.fair import BookQuote

    class _MovingProvider:
        name = "fixture"
        t = 1000.0

        def list_events(self):
            return [{"id": "G1"}]

        def fetch(self, event_id):
            self.t += 60.0
            return [BookQuote("pinnacle", 68.5, -105, -105, ts=self.t, is_sharp=True)]

    conn = db.connect(":memory:")
    run_monitor(_MovingProvider(), conn, interval=0.0, max_cycles=3, budget=QuotaBudget(total=50))
    assert db.snapshot_count(conn) == 3  # one row per distinct capture time
