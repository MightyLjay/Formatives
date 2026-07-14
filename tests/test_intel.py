"""Intel layer: LLM extraction (via an injected stub — no key needed), impact, and latency."""
from intel.extract import _stub_completer, extract_availability
from intel.impact import PlayerProfile, aggregate_delta, expected_points_delta
from intel.latency import LatencyLog
from intel.schema import AvailabilityDelta


def test_extract_parses_deltas_with_injected_completer():
    text = "Star guard is heading to the locker room and will not return."
    deltas = extract_availability(text, ts=1000.0, source="test", complete=_stub_completer)
    assert len(deltas) == 1
    d = deltas[0]
    assert d.status == "OUT"
    assert d.minutes_delta < 0
    assert d.ts == 1000.0


def test_extract_no_change_returns_empty():
    deltas = extract_availability("Both teams look healthy at the half.", complete=_stub_completer)
    assert deltas == []


def test_impact_of_star_out_lowers_total():
    delta = AvailabilityDelta("Star", "HOME", "OUT", minutes_delta=-20.0, confidence=1.0, ts=0.0)
    star = PlayerProfile("Star", "HOME", usage=0.30, points_per_poss=1.15, on_off_net=8.0)
    pts = expected_points_delta(delta, star)
    assert pts < 0  # losing an above-replacement star lowers expected 2H points


def test_aggregate_delta_sums_players():
    deltas = [
        AvailabilityDelta("A", "HOME", "OUT", -20.0, 1.0, 0.0),
        AvailabilityDelta("B", "AWAY", "QUESTIONABLE", -8.0, 0.5, 0.0),
    ]
    profiles = {
        "A": PlayerProfile("A", "HOME", 0.28, 1.10, 5.0),
        "B": PlayerProfile("B", "AWAY", 0.22, 1.05, 2.0),
    }
    total = aggregate_delta(deltas, profiles)
    assert total < 0


def test_latency_edge_positive_when_we_know_first():
    log = LatencyLog()
    log.record("G1", "info", ts=100.0, detail="beat writer: star out")
    log.record("G1", "line_move", ts=140.0, detail="book dropped 2H total")
    assert log.edge_seconds("G1") == 40.0
    assert log.won_race("G1") is True

    log.record("G2", "line_move", ts=100.0)
    log.record("G2", "info", ts=130.0)  # we learned AFTER the book moved
    assert log.won_race("G2") is False
