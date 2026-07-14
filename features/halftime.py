"""Halftime state from play-by-play: possessions, pace, eFG%, TOV%, OREB%, FT rate, fouls, bonus,
margin, star foul trouble, lineup on floor.

Possessions use the standard estimate:  poss = FGA - OREB + TOV + 0.44*FTA.

Every function here calls `assert_no_leakage` on the events it consumes, so a feature accidentally
fed a post-buzzer event raises rather than silently biasing the model.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .leakage_guard import HalftimeMarker, PBPEvent, assert_no_leakage

# NCAAB bonus thresholds (team fouls in a half). NBA differs; parameterize if you add it.
BONUS_FOULS = 7          # 1-and-1
DOUBLE_BONUS_FOULS = 10  # two shots
FOUL_TROUBLE = 3         # "in foul trouble" at the half (foul-out at 5 in NCAAB)


@dataclass
class TeamHalftimeState:
    team: str
    points: float = 0.0
    fga: int = 0
    fgm: int = 0
    tpm: int = 0            # made 3s
    fta: int = 0
    ftm: int = 0
    oreb: int = 0
    dreb: int = 0
    turnovers: int = 0
    team_fouls: int = 0
    player_fouls: dict = field(default_factory=dict)

    @property
    def possessions(self) -> float:
        return self.fga - self.oreb + self.turnovers + 0.44 * self.fta

    @property
    def efg(self) -> float:
        return (self.fgm + 0.5 * self.tpm) / self.fga if self.fga else 0.0

    @property
    def tov_rate(self) -> float:
        p = self.possessions
        return self.turnovers / p if p > 0 else 0.0

    @property
    def oreb_rate(self) -> float:
        reb = self.oreb + self.dreb
        return self.oreb / reb if reb else 0.0

    @property
    def ft_rate(self) -> float:
        return self.fta / self.fga if self.fga else 0.0

    @property
    def in_bonus(self) -> bool:
        return self.team_fouls >= BONUS_FOULS

    @property
    def in_double_bonus(self) -> bool:
        return self.team_fouls >= DOUBLE_BONUS_FOULS

    def players_in_foul_trouble(self) -> list[str]:
        return [p for p, n in self.player_fouls.items() if n >= FOUL_TROUBLE]


@dataclass
class HalftimeState:
    home: TeamHalftimeState
    away: TeamHalftimeState
    h1_total: float               # both teams' 1st-half points (the anchor for grading)
    margin: float                 # home - away at the half
    pace: float                   # avg possessions per team in the half

    def feature_row(self) -> dict:
        """Flatten to a model-ready feature dict. No post-half information can be present — the
        constructor guarded against it."""
        return {
            "h1_total": self.h1_total,
            "margin": self.margin,
            "pace": self.pace,
            "home_efg": self.home.efg,
            "away_efg": self.away.efg,
            "home_tov_rate": self.home.tov_rate,
            "away_tov_rate": self.away.tov_rate,
            "home_oreb_rate": self.home.oreb_rate,
            "away_oreb_rate": self.away.oreb_rate,
            "home_ft_rate": self.home.ft_rate,
            "away_ft_rate": self.away.ft_rate,
            "home_fouls": self.home.team_fouls,
            "away_fouls": self.away.team_fouls,
            "home_in_bonus": int(self.home.in_bonus),
            "away_in_bonus": int(self.away.in_bonus),
            "home_foul_trouble": len(self.home.players_in_foul_trouble()),
            "away_foul_trouble": len(self.away.players_in_foul_trouble()),
        }


def compute_halftime_state(
    events: list[PBPEvent],
    home: str,
    away: str,
    marker: HalftimeMarker = HalftimeMarker(),
) -> HalftimeState:
    """Build the halftime state from first-half play-by-play.

    Raises LeakageError if `events` contains any post-halftime event. Pass only first-half events
    (use `leakage_guard.first_half_events` to filter safely) — the guard is the safety net, not the
    intended filter.
    """
    assert_no_leakage(events, marker)  # the contract: no future events, ever.

    teams = {home: TeamHalftimeState(team=home), away: TeamHalftimeState(team=away)}

    for e in events:
        if e.team not in teams:
            continue
        t = teams[e.team]
        if e.event_type == "shot":
            t.fga += 1
            if e.made:
                t.fgm += 1
                if e.is_three:
                    t.tpm += 1
                    t.points += 3
                else:
                    t.points += 2
        elif e.event_type == "free_throw":
            t.fta += 1
            if e.made:
                t.ftm += 1
                t.points += 1
        elif e.event_type == "rebound":
            if e.rebound_kind == "off":
                t.oreb += 1
            else:
                t.dreb += 1
        elif e.event_type == "turnover":
            t.turnovers += 1
        elif e.event_type == "foul":
            t.team_fouls += 1
            if e.player:
                t.player_fouls[e.player] = t.player_fouls.get(e.player, 0) + 1

    h, a = teams[home], teams[away]
    h1_total = h.points + a.points
    pace = (h.possessions + a.possessions) / 2.0
    return HalftimeState(home=h, away=a, h1_total=h1_total, margin=h.points - a.points, pace=pace)
