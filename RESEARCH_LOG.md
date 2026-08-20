# ANODE Research Log

Running log of research state so any Claude session (any machine, or
claude.ai/code) can continue the work. Read CLAUDE.md and AGENTS.md first.
Append; never rewrite history.

## 2026-08-20 — First full-year backtest of STRAT-001 (2024 data)

**Setup:** 245 converted days in `data/historical/2024/*.csv.gz` (1-min
snapshots, nearest expiry, Kaggle-sourced, Apache 2.0). Replay driver:
single process, WAL pragmas, one `run_session` per day into a scratch DB.

**Run 1 result (no seeding, no spreads): 0 signals in 91,874 decisions.**
Root causes, from reason-code aggregation — NOT strategy weaknesses:

1. `FAIL_WARMUP` on 61,249 decisions (67%): each day starts a cold TA
   engine; EMA50 needs 250 of the day's 375 minutes. Fixed in backtests by
   seeding each day with the previous day's snapshots (`seed_snapshots`).
   TODO: live sessions/EOD replay should also seed from the previous day.
2. `FAIL_LIQUIDITY_OK` on 100% of post-warmup decisions: the gate reads
   ATM bid/ask spread; the dataset has no bid/ask. Fixed by writing a
   deliberately conservative estimate into the data (0.15%/side, 5-paise
   floor — wider than real NIFTY weekly ATM spreads, so backtest costs
   are harsher than live). Commit b90ca30.

**Run 2 (prev-day seeding + estimated spreads): in progress.**
Results to be appended below when available.

**Operational fixes this cycle:** collection crons moved ~25 min early
(GitHub fires late); leg-A staging bug fixed (git add aborts on missing
pathspec — morning of 2026-08-20 was lost to it).

**Discipline reminders for whoever continues:** one hypothesis per
experiment; no rule changes from backtest alone — walk-forward + live
confirmation required; estimated spreads mean spread-sensitive results
need extra scrutiny; synthetic rows never count.
