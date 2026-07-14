"""Map a player-availability delta to an expected 2H points delta.

From a player's per-possession scoring, usage, and on/off net rating, estimate how many 2H points
the *game total* moves when that player's minutes change. This is deliberately simple and explicit:
the point of the project is that being right about the game is not the same as being right about the
price — so we keep this transparent and let CLV tell us whether the market had already moved.
"""
from __future__ import annotations

from dataclasses import dataclass

from .schema import AvailabilityDelta

# Points a replacement-level player produces per possession used (league-ish baseline).
REPLACEMENT_PPP = 0.90
# Typical 2H possessions per team (both halves are ~ symmetric); calibrate from the collector.
TEAM_2H_POSSESSIONS = 33.0
# Fraction of a half a full role represents, in minutes.
HALF_MINUTES = 20.0


@dataclass
class PlayerProfile:
    player: str
    team: str
    usage: float          # share of team possessions the player uses when on the floor (0..1)
    points_per_poss: float  # the player's own scoring efficiency on used possessions
    on_off_net: float = 0.0  # team net-rating swing per 100 poss when on vs off (points)


def expected_points_delta(
    delta: AvailabilityDelta,
    profile: PlayerProfile,
    team_2h_possessions: float = TEAM_2H_POSSESSIONS,
) -> float:
    """Expected change in the GAME's 2H total attributable to this availability change.

    Two channels:
      1. Scoring channel: the minutes lost shift `usage`-weighted possessions from the player
         (points_per_poss) to a replacement (REPLACEMENT_PPP).
      2. On/off channel: the player's net-rating swing applied over the affected possessions,
         split half to offense (affects the total in the same direction).
    Signs follow `minutes_delta`: negative minutes (player out) usually lowers the total.
    """
    minute_fraction = delta.minutes_delta / HALF_MINUTES  # e.g. -1.0 for a starter out the half
    affected_poss = team_2h_possessions * minute_fraction * profile.usage

    scoring_delta = affected_poss * (profile.points_per_poss - REPLACEMENT_PPP)

    # on/off net is per-100-poss, total impact; ~half of it shows up as the team's own points.
    onoff_poss = team_2h_possessions * minute_fraction
    onoff_delta = (profile.on_off_net / 100.0) * onoff_poss * 0.5

    raw = scoring_delta + onoff_delta
    return float(raw * delta.confidence)  # discount by how sure we are the change is real


def aggregate_delta(
    deltas: list[AvailabilityDelta],
    profiles: dict[str, PlayerProfile],
    team_2h_possessions: float = TEAM_2H_POSSESSIONS,
) -> float:
    """Sum expected 2H total impact across every availability change we know about for a game."""
    total = 0.0
    for d in deltas:
        prof = profiles.get(d.player)
        if prof is None:
            continue
        total += expected_points_delta(d, prof, team_2h_possessions)
    return total
