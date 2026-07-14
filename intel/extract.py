"""Claude API: unstructured halftime text -> structured availability delta.

This is the edge, if one exists: messy human text ("X is limping to the locker room, doubtful to
return") into {player, status, minutes_delta, confidence, ts}, fast, across hundreds of games.

The API call is behind an injectable `complete` callable so the extraction logic is unit-testable
with a stub (no key, no network). The default `complete` uses the Anthropic SDK with structured
outputs (`output_config.format`) for schema-valid JSON. Model defaults to claude-opus-4-8.
"""
from __future__ import annotations

import argparse
import json
import time
from typing import Callable

from .schema import DELTA_JSON_SCHEMA, AvailabilityDelta

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = (
    "You extract basketball player-availability changes from halftime reports, beat-writer posts, "
    "and injury feeds. Return ONLY players whose availability or role for the 2nd half changed. "
    "minutes_delta is the expected change in that player's remaining 2H minutes versus their normal "
    "role: roughly -20 for a starter ruled out, -10 for 'doubtful', small negatives for foul "
    "trouble or a minutes restriction, positive when a player is cleared to return. Set confidence "
    "to how firmly the text supports the change. If nothing changed, return an empty list."
)

# A `complete` takes the report text and returns a dict matching DELTA_JSON_SCHEMA.
Completer = Callable[[str], dict]


def extract_availability(
    text: str,
    ts: float | None = None,
    source: str = "",
    complete: Completer | None = None,
    model: str = MODEL,
) -> list[AvailabilityDelta]:
    """Extract availability deltas from one piece of text. `ts` is when the source published it."""
    ts = time.time() if ts is None else ts
    complete = complete or _make_anthropic_completer(model)
    payload = complete(text)
    deltas = []
    for d in payload.get("deltas", []):
        deltas.append(
            AvailabilityDelta(
                player=d["player"],
                team=d.get("team", ""),
                status=d["status"],
                minutes_delta=float(d["minutes_delta"]),
                confidence=float(d["confidence"]),
                ts=ts,
                source=source,
            )
        )
    return deltas


def _make_anthropic_completer(model: str) -> Completer:
    """Build the real Claude-backed completer. Imports `anthropic` lazily so the module loads (and
    tests run) without the SDK or a key installed."""

    def _complete(text: str) -> dict:
        import anthropic  # lazy: only needed for live extraction

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
            output_config={"format": {"type": "json_schema", "schema": DELTA_JSON_SCHEMA}},
        )
        raw = next((b.text for b in response.content if b.type == "text"), "{}")
        return json.loads(raw)

    return _complete


def _stub_completer(text: str) -> dict:
    """Offline stand-in for the demo/tests: a crude keyword rule, NOT the real extractor.

    The real path is the Claude API; this only exists so the pipeline is runnable without a key.
    """
    low = text.lower()
    deltas = []
    if "locker room" in low or "will not return" in low or "won't return" in low or "ruled out" in low:
        deltas.append(
            {"player": "Unknown Starter", "team": "", "status": "OUT",
             "minutes_delta": -20.0, "confidence": 0.8}
        )
    elif "questionable" in low or "doubtful" in low:
        deltas.append(
            {"player": "Unknown Starter", "team": "", "status": "QUESTIONABLE",
             "minutes_delta": -8.0, "confidence": 0.5}
        )
    return {"deltas": deltas}


def _demo() -> None:
    import os

    reports = [
        "Star guard Jordan Reyes is heading to the locker room and will not return in the 2nd half.",
        "Center is questionable to return with an ankle issue; team says he's day-to-day.",
        "No injury news at the half; both teams look healthy.",
    ]
    live = bool(os.environ.get("ANTHROPIC_API_KEY"))
    complete = None if live else _stub_completer
    print(f"intel.extract demo  (mode: {'LIVE Claude API' if live else 'offline stub'})\n")
    for r in reports:
        deltas = extract_availability(r, source="demo", complete=complete)
        print(f"text: {r}")
        if not deltas:
            print("  -> (no availability change)\n")
        for d in deltas:
            print(f"  -> {d.player} [{d.team or '?'}] {d.status} "
                  f"min_delta={d.minutes_delta:+.0f} conf={d.confidence:.2f}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="extract availability deltas from halftime text")
    ap.add_argument("--demo", action="store_true", help="run the offline demo (or LIVE if ANTHROPIC_API_KEY is set)")
    args = ap.parse_args()
    if args.demo:
        _demo()
    else:
        print("Pass text on the command line via your own driver, or run --demo.")


if __name__ == "__main__":
    main()
