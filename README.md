# h2-totals-lab

A research harness for **2nd-half (H2) basketball totals** betting — built on one hard-won
lesson: **the edge is not in a better model, it's in better information and a worse market.**

> This repo is the sibling of an NBA control experiment (`src/` + `data/games.csv`) in which a
> model *tied* the closing 2H line (MAE 10.23 vs 10.23) and could not beat the vig. Stripped of the
> line, box-score features left the model ~0.45 pts/game behind the market. That gap is
> information, not modeling. See `FINDINGS.md` / `PLAN_V2.md` for the full write-up.
>
> **Status:** the NBA control is *not* in this repo yet (see "What's here" below). This lab is the
> v2 build described in `PLAN_V2.md`, scaffolded offline. The market/collector/intel layers have
> clean interfaces and are tested against fixtures; wiring them to live feeds needs network access
> and API keys that this environment does not currently have.

## The principle

Power spent on the **model** is wasted. Power spent on **information** and **market coverage** is not.

1. **Beat the market to news.** Halftime injury/rotation reports, before the book adjusts. A
   latency problem, not an ML problem. → `intel/`
2. **Find a lazier book.** A soft book 4 points off the sharp consensus is an edge that needs no
   model at all. → `market/`
3. **Measure closing line value, not win rate.** CLV tells you in ~200 bets what win rate needs
   ~2,000 to confirm. → `market/clv.py`, the primary metric of the whole project.

And, above all: **the falsification harness must get stronger as the model gets more powerful.**
Testing hundreds of strategies makes a spurious "edge" nearly certain. `eval/` is built to catch
that — purged/embargoed walk-forward CV, Benjamini–Hochberg, White's Reality Check / Hansen SPA,
Deflated Sharpe. Every result carries a p-value. A backtest without one is a story, not a finding.

## Layout

```
market/     Poll every book, de-vig the sharp consensus, rank soft-book outliers, grade CLV.
collector/  Build the 2H-total dataset nobody archives: snapshot totals_h2 at halftime, grade next day.
intel/      LLM layer (Claude API): messy halftime text -> structured availability delta; impact; latency.
features/   Halftime state from play-by-play, with a leakage guard that FAILS THE BUILD on post-buzzer events.
eval/       The falsification harness. Built BEFORE the model, non-negotiable.
model/      P(2H > line), distributional — only after eval exists. Benchmarked against the closing line.
exec/       Quarter-Kelly max, correlation-aware, PAPER-TRADE ONLY. No bet-placement code, ever.
```

## What's here (this offline build)

Fully implemented and tested against synthetic/fixture data (no network needed):

- `eval/` — the complete falsification harness (Step 5 / Tier 4).
- `market/fair.py`, `market/outliers.py`, `market/clv.py` — de-vig, outlier ranking, CLV.
- `collector/db.py`, `collector/grade.py` — append-only SQLite schema; **target = `final_total - h1_total`**,
  with overtime settling into the 2H bet.
- `features/halftime.py`, `features/leakage_guard.py` — halftime state + the build-failing leakage test.
- `exec/kelly.py` — fractional Kelly + correlation-aware sizing.
- `model/distributional.py`, `model/montecarlo.py` — `P(2H > line)` baselines.

Interfaces ready, need a live feed + credentials to run:

- `market/poll.py` — polls a provider; ships with a fixture provider so it runs offline.
- `collector/detect.py`, `collector/snapshot.py` — halftime detection + immutable snapshots.
- `intel/sources.py`, `intel/extract.py`, `intel/impact.py`, `intel/latency.py` — the Claude-backed
  information layer. `extract.py` takes an injectable client so it's unit-testable without a key.

## Quick start

```bash
python -m pip install -r requirements.txt      # core: numpy, pandas, scipy, pytest
make eval                                       # run the falsification harness on synthetic data
make test                                       # run the full test suite (leakage guard included)
```

Optional live-feed / model / LLM extras are in `requirements-extra.txt` and are imported lazily —
the tested core does not need them.

## Monitoring live odds

The market/collector layers run against a real odds feed once you have (a) a provider key and (b)
network egress. Run the monitor on your own machine or a small always-on VPS — it's cron/supervisor
friendly and the append-only store is crash-safe, which is the whole point.

```bash
make install-live                       # adds requests, anthropic, etc.
export ODDS_API_KEY=...                 # free tier at https://the-odds-api.com/

# 1) PROBE FIRST — does a live 2H total even exist for this sport? (Step-0 discipline)
python -m market.probe --sport basketball_ncaab --market totals_h2

# 2) If it does, monitor it — append every quote as an immutable, timestamped snapshot:
python -m collector.monitor --sport basketball_ncaab --interval 60 \
       --events <eventId> <eventId> --db data/odds.sqlite
```

**The 2H total is an in-play line** — it typically only appears once a game is live (often at
halftime), and for many leagues it doesn't exist or isn't liquid. The probe tells you before you
spend anything. **Quota**: each polled event costs ~1 credit; poll only the games you care about
(`--events`) at a sane `--interval`, or the free tier is gone in an afternoon. The monitor stops
itself when the real `x-requests-remaining` counter hits zero and warns at 80%.

Swap providers without touching the pipeline: `market/providers.py` has `TheOddsAPIProvider` (wired)
and a `SportsGameOddsProvider` stub (80+ books) — both map to the same `BookQuote`.

## Kill criteria (executable, exit non-zero)

- 500 graded snapshots, CLV not positive → `KILL: no CLV`
- Best strategy fails Hansen SPA at p < 0.05 → `KILL: not significant`

"But it was profitable in the backtest" is exactly what noise looks like. The check does not care.
See `eval/kill.py`.

## Non-negotiables

- **Paper-trade only.** There is no bet-placement code in this repo and there never will be.
- **The control is sacred.** If/when `src/` + `data/games.csv` land here, they are the benchmark —
  do not modify them.
- **Every printed result carries a p-value.**
