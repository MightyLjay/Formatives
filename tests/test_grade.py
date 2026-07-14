"""The single most important grading rule: TARGET = final_total - h1_total, OT included."""
import pytest

from collector.grade import grade, h2_actual_points


def test_target_is_final_minus_first_half():
    # 1st half 52, final 106 (no OT) -> 2H actual = 54.
    assert h2_actual_points(52.0, 106.0) == 54.0


def test_overtime_settles_into_the_2h_bet():
    # Regulation ends 100, then two OTs push the final to 118. 1st half was 48.
    # H2 (incl. OT) = 118 - 48 = 70. Using the H2 *box score* (which excludes OT) would wrongly
    # give 100 - 48 = 52 and bias every OT game UNDER.
    assert h2_actual_points(48.0, 118.0) == 70.0


def test_grade_over_under_and_push():
    # h2_actual = 106 - 52 = 54.
    assert grade("over", 53.5, 52.0, 106.0).result == "win"
    assert grade("under", 53.5, 52.0, 106.0).result == "loss"
    assert grade("over", 54.5, 52.0, 106.0).result == "loss"
    assert grade("under", 54.5, 52.0, 106.0).result == "win"
    assert grade("over", 54.0, 52.0, 106.0).result == "push"


def test_final_below_first_half_is_an_error():
    # A common data bug: final_total accidentally holds a half's points, not the whole game.
    with pytest.raises(ValueError):
        h2_actual_points(52.0, 40.0)


def test_bad_side_rejected():
    with pytest.raises(ValueError):
        grade("middle", 54.0, 52.0, 106.0)
