"""Paper-trading ledger. PAPER ONLY — this records intended bets and simulates a bankroll.

There is deliberately NO code here that talks to a sportsbook, moves money, or places a wager, and
there never will be. This exists so a strategy can be run forward and scored (CLV first, then ROI)
without risking a cent. If you find yourself wanting to add a `place_bet()` that hits an external
API, stop: that is not this project.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from eval.metrics import american_to_decimal


@dataclass
class PaperBet:
    game_id: str
    side: str            # over | under
    line: float
    odds: float          # American
    stake: float         # fraction of bankroll (or units)
    ts: float
    result: str = "pending"   # pending | win | loss | push

    def profit_units(self) -> float:
        if self.result == "win":
            return self.stake * (american_to_decimal(self.odds) - 1.0)
        if self.result == "loss":
            return -self.stake
        return 0.0  # push or pending


@dataclass
class PaperBook:
    bankroll: float = 1.0
    bets: list[PaperBet] = field(default_factory=list)

    def place(self, bet: PaperBet) -> None:
        """Record an intended paper bet. No money moves."""
        self.bets.append(bet)

    def settle(self, game_id: str, side: str, result: str) -> None:
        for b in self.bets:
            if b.game_id == game_id and b.side == side and b.result == "pending":
                b.result = result
                self.bankroll += b.profit_units()

    def stats(self) -> dict:
        graded = [b for b in self.bets if b.result in ("win", "loss", "push")]
        if not graded:
            return {"n": 0, "bankroll": self.bankroll, "roi": 0.0, "win_rate": None}
        staked = sum(b.stake for b in graded if b.result != "push")
        profit = sum(b.profit_units() for b in graded)
        decided = [b for b in graded if b.result in ("win", "loss")]
        win_rate = np.mean([b.result == "win" for b in decided]) if decided else None
        return {
            "n": len(graded),
            "bankroll": self.bankroll,
            "roi": (profit / staked) if staked else 0.0,
            "win_rate": None if win_rate is None else float(win_rate),
        }
