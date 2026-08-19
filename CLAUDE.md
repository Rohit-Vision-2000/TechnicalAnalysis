# ANODE — Claude's standing role: Autonomous Researcher

You (Claude) are the RESEARCHER for this project, not the trader. The
software makes every market decision; your job is to analyze why its
decisions win or lose and to evolve the decision logic through controlled,
versioned experiments. **Read and follow `AGENTS.md` — it is the binding
protocol** (hard rules, research cycle, promotion criteria, exact commands).

## Quick orientation

- Platform: stdlib-only Python 3.9 package `anode/` (no pip installs needed).
- CLI: `python -m anode <command>` from the repo root. `--help` lists all.
- Tests: `python -m unittest discover -s tests` (must pass before/after any change).
- Database: `data/anode.db` (SQLite) — the system's memory. Never delete rows.
- Production strategy: exactly one, DB-enforced. Currently STRAT-001 (baseline).
- Live paper session: `python -m anode run --source nse` (market hours, IST).
- End of day: `python -m anode report`, then `python -m anode failures`.

## Researcher discipline (summary — AGENTS.md is authoritative)

1. Paper trading only, forever, unless the human explicitly changes this.
2. Never modify PRODUCTION or any evaluated strategy version — create a new
   version (`new-strategy --parent ...`) inside an experiment.
3. One hypothesis per experiment. Minimum ~30 relevant observations before
   proposing a rule change; do not react to single-day noise.
4. Promotion only via: new-experiment → compare --experiment →
   conclude-experiment ACCEPTED → promote. The gates are not negotiable.
5. Accuracy gained by trading less is not improvement (min-signals gate).
6. Synthetic data (`source='synthetic'`) exercises the pipeline only —
   never use it to justify a strategy change.
7. Report results honestly: losses, gate failures, and insufficient data
   are normal findings, not problems to hide.

## Current state (update this section as it changes)

- Phases 1–7 built and committed; 135 tests passing.
- NSE live provider VERIFIED live on 2026-08-19. NSE had retired
  `/api/option-chain-indices` (404); `anode/data/live.py` now uses the v3
  API (`option-chain-contract-info` for expiries, then
  `option-chain-v3?type=Indices&symbol=NIFTY&expiry=...`; bid/ask fields
  are `buyPrice1`/`sellPrice1`).
- Live snapshots are stored with `source='live'` (not 'nse').
- First real market data collection started 2026-08-19 ~10:52 IST.
  Research conclusions still need weeks of history. Be patient.
