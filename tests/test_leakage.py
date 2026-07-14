"""BUILD GATE: this test FAILS THE BUILD if any feature can touch a post-halftime PBP event.

The whole feature layer's integrity rests on `assert_no_leakage`. If that guard ever lets a
post-buzzer event through, halftime features silently peek at the future — so we assert, hard, that
it raises. We also assert the safe path computes correctly.
"""
import pytest

from features.halftime import compute_halftime_state
from features.leakage_guard import (
    HalftimeMarker,
    LeakageError,
    PBPEvent,
    assert_no_leakage,
    first_half_events,
    is_post_halftime,
)

NCAAB = HalftimeMarker(last_period_before_half=1)


def _first_half_stream():
    return [
        PBPEvent(1, 600, "HOME", "shot", made=True, is_three=False),
        PBPEvent(1, 590, "AWAY", "shot", made=False),
        PBPEvent(1, 585, "AWAY", "rebound", rebound_kind="off"),
        PBPEvent(1, 500, "HOME", "turnover"),
        PBPEvent(1, 480, "AWAY", "foul", player="A. Guard"),
        PBPEvent(1, 300, "HOME", "free_throw", made=True),
    ]


def _post_half_event():
    return PBPEvent(2, 1180, "HOME", "shot", made=True, is_three=True)  # 2nd half -> leakage


def test_post_halftime_event_is_detected():
    assert is_post_halftime(_post_half_event(), NCAAB) is True
    assert is_post_halftime(_first_half_stream()[0], NCAAB) is False
    # Overtime is also post-halftime.
    assert is_post_halftime(PBPEvent(3, 300, "HOME", "shot"), NCAAB) is True


def test_guard_raises_on_any_post_half_event():
    events = _first_half_stream() + [_post_half_event()]
    with pytest.raises(LeakageError):
        assert_no_leakage(events, NCAAB)


def test_feature_computation_refuses_leaky_input():
    """A feature fed even one post-buzzer event must raise, not silently compute."""
    leaky = _first_half_stream() + [_post_half_event()]
    with pytest.raises(LeakageError):
        compute_halftime_state(leaky, "HOME", "AWAY", NCAAB)


def test_safe_path_computes():
    events = _first_half_stream()
    state = compute_halftime_state(events, "HOME", "AWAY", NCAAB)
    # HOME: one made 2 + one made FT = 3 pts; AWAY: 0 pts.
    assert state.home.points == 3
    assert state.away.points == 0
    assert state.h1_total == 3
    assert state.margin == 3
    row = state.feature_row()
    assert set(row) >= {"h1_total", "margin", "pace", "home_efg", "away_tov_rate"}


def test_first_half_filter_removes_future():
    mixed = _first_half_stream() + [_post_half_event(), PBPEvent(2, 10, "AWAY", "turnover")]
    safe = first_half_events(mixed, NCAAB)
    assert all(not is_post_halftime(e, NCAAB) for e in safe)
    # And the filtered stream is now safe to compute on.
    compute_halftime_state(safe, "HOME", "AWAY", NCAAB)  # must not raise
