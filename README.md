# ANODE — Autonomous NIFTY Options Decision Engine

A research and paper-trading platform for NIFTY 50 options. The system consumes
market snapshots (live or replayed), performs technical and options-market
analysis, and decides **BUY CALL / BUY PUT / NO TRADE**. Every decision and the
complete market state behind it is recorded so that outcomes can be analyzed
and the decision logic can be evolved through controlled, versioned experiments.

**This system is paper-trading only. It never places real orders.**

See `readme.txt` for the original idea and design discussion, and `AGENTS.md`
for the autonomous-research protocol that governs how strategies may evolve.

## Current status

**Phase 1 — Infrastructure** (done):

- Project structure and configuration system
- Normalized market data models (`MarketSnapshot`, `OptionSnapshot`)
- Decision / paper-trade / strategy-version / experiment models
- SQLite research database with full schema
- Market-data provider abstraction + CSV replay provider
- Deterministic ID and strategy-versioning scheme
- Logging, CLI, and test suite

**Phase 2 — Technical Analysis Engine** (done):

- Candle aggregation (`CandleBuilder`, default 5-minute, no intra-bar repainting)
- Indicators: SMA, EMA 20/50/200, RSI(14), MACD(12/26/9), ATR(14),
  ADX(14) with +DI/−DI, VWAP (true VWAP with volume, time-weighted proxy
  without — flagged via `vwap_is_proxy`)
- Support/resistance: swing pivots, day/prev-day levels, OI walls — merged
  and deduplicated with nearest-level distances
- Option-chain analysis: PCR (OI/volume), ATM IV + IV change, IV skew,
  max pain, OI support/resistance strikes, OI flow, ATM liquidity (spread%)
- Market-regime classifier: TRENDING_BULLISH / TRENDING_BEARISH /
  SIDEWAYS / HIGH_VOLATILITY (thresholds tunable via experiments)
- `TechnicalAnalysisEngine`: streaming snapshot → `TechnicalState`, the
  object the decision engine will consume and that gets stored as decision
  `features`
- Synthetic session generator (demo/testing only) + `analyze` CLI command

Next: the decision engine (Phase 3), the paper-trading engine (Phase 4),
the research/backtest engine (Phase 5), and Claude CLI autonomous research
integration (Phase 6).

## Requirements

Python 3.9+ — **standard library only**, no third-party packages required.

## Quick start

From the repository root:

```powershell
# create the database
python -m anode init-db

# see system status
python -m anode status

# replay a CSV of market data and store snapshots
python -m anode replay --file data\sample\sample_snapshots.csv --store

# run technical analysis over a replay file, or a synthetic demo session
python -m anode analyze --file data\my_day.csv
python -m anode analyze --seed 7 --every 30

# list stored data
python -m anode snapshots
python -m anode decisions
python -m anode trades

# strategy version management
python -m anode strategies
python -m anode new-strategy --description "Baseline rule set"
python -m anode set-status --version STRAT-001 --status CANDIDATE

# experiments
python -m anode new-experiment --hypothesis "..." --baseline STRAT-001 --candidate STRAT-002
python -m anode experiments

# run tests
python -m unittest discover -s tests -v
```

## Project layout

```
anode/                  Python package (the platform)
  config.py             configuration loading (config/config.json)
  ids.py                decision / strategy / experiment ID generation
  logging_setup.py      logging configuration
  models/               dataclass models (market, decision, trade, strategy)
  storage/              SQLite schema + repositories
  data/                 market-data provider abstraction + replay provider
  cli.py                command-line interface

config/config.json      runtime configuration
data/                   runtime data (database, sample/replay files)
strategies/             immutable strategy versions (STRAT-NNN/)
experiments/            experiment journal (EXP-NNN.md)
tests/                  unit tests (stdlib unittest)
```

## Core design rules

1. **Record everything.** Every decision stores the complete market state and
   indicator values seen at decision time (`decisions.features` JSON).
2. **Normalized data.** Strategies never consume raw provider responses; all
   data flows through the `MarketSnapshot` model via a provider adapter.
3. **Immutable strategy versions.** `strategies/STRAT-NNN/` is never edited
   once evaluated. Changes create a new version. Exactly one version is
   `PRODUCTION` at a time.
4. **Paper only.** There is no broker integration and none may be added
   without explicit human decision.
5. **Experiments are auditable.** One hypothesis per experiment; results and
   conclusions recorded in the database and `experiments/`.
