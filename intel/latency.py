"""Timestamp everything. Our entire edge is "did we know before the line moved."

If we can't measure the gap between when information appeared and when the book moved its 2H line,
we have nothing. This module records those timestamps and computes the signed latency edge.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LatencyEvent:
    game_id: str
    kind: str          # 'info' (we learned something) | 'line_move' (book moved) | 'bet' (we acted)
    ts: float          # unix seconds
    detail: str = ""


@dataclass
class LatencyLog:
    events: list[LatencyEvent] = field(default_factory=list)

    def record(self, game_id: str, kind: str, ts: float, detail: str = "") -> None:
        self.events.append(LatencyEvent(game_id, kind, ts, detail))

    def edge_seconds(self, game_id: str) -> float | None:
        """Seconds between the first info event and the first subsequent line move for a game.

        Positive = we knew BEFORE the line moved (an exploitable head start). Negative = the book
        moved first (we lost the race). None if we can't pair the two.
        """
        infos = sorted(e.ts for e in self.events if e.game_id == game_id and e.kind == "info")
        moves = sorted(e.ts for e in self.events if e.game_id == game_id and e.kind == "line_move")
        if not infos or not moves:
            return None
        first_info = infos[0]
        later_moves = [m for m in moves if m >= first_info]
        move = later_moves[0] if later_moves else moves[0]
        return float(move - first_info)

    def won_race(self, game_id: str) -> bool | None:
        edge = self.edge_seconds(game_id)
        return None if edge is None else edge > 0

    def summary(self) -> dict:
        games = {e.game_id for e in self.events}
        edges = [self.edge_seconds(g) for g in games]
        edges = [e for e in edges if e is not None]
        if not edges:
            return {"games": len(games), "measured": 0, "win_race_rate": None, "median_edge_s": None}
        wins = sum(1 for e in edges if e > 0)
        return {
            "games": len(games),
            "measured": len(edges),
            "win_race_rate": wins / len(edges),
            "median_edge_s": float(sorted(edges)[len(edges) // 2]),
        }
