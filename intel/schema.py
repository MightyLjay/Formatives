"""The structured field the LLM produces from messy halftime text.

Turning "Smith is heading to the locker room and won't return" into
{player: "Smith", status: OUT, minutes_delta: -20, confidence: 0.9, ts: ...} is the one thing an
LLM is genuinely best at — fast, at scale, across hundreds of simultaneous games. Everything
downstream (impact, sizing) consumes this shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field

STATUSES = ("OUT", "DOUBTFUL", "QUESTIONABLE", "PROBABLE", "RETURNED", "ACTIVE")

# JSON schema handed to the Claude API's structured-output constraint (output_config.format).
DELTA_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "deltas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "player": {"type": "string"},
                    "team": {"type": "string"},
                    "status": {"type": "string", "enum": list(STATUSES)},
                    "minutes_delta": {
                        "type": "number",
                        "description": "Expected change in the player's remaining 2H minutes "
                        "vs. their normal role (negative = fewer minutes; e.g. -20 for out).",
                    },
                    "confidence": {"type": "number"},
                },
                "required": ["player", "team", "status", "minutes_delta", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["deltas"],
    "additionalProperties": False,
}


@dataclass
class AvailabilityDelta:
    player: str
    team: str
    status: str            # one of STATUSES
    minutes_delta: float   # expected change in remaining 2H minutes vs normal role
    confidence: float      # 0..1
    ts: float              # unix seconds — when the source published this (see intel.latency)
    source: str = ""

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}, got {self.status!r}")
        self.confidence = float(min(max(self.confidence, 0.0), 1.0))
