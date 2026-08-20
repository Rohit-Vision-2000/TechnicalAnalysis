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

**Run 2 (prev-day seeding + estimated spreads): COMPLETE — first real
baseline.** 88,002 decisions → 173 signals → 173 closed trades.
Win rate 36.4%, net P&L **−31,489** (1 lot, costs+estimated spreads).

Exit decomposition: STOP_LOSS 86 trades −131,532; TARGET 47 trades
+94,662; TIME_EXIT 29 trades +7,663; EOD 11 trades −2,281. Payoff ratio
~1.32 — too small for a 36% win rate.

**Strongest cluster (n=67, well above the 30-obs gate): entries at/after
13:00 IST — 26% win rate, −34,054 net; entries before 13:00 — ~42% win
rate, +2,565 net.** Nearly the entire annual loss comes from afternoon
entries. Weaker clusters (small n, noted only): ADX 50-60 0/5; PUT side
33% wr vs CALL 41%; PCR>1.2 1/6.

**Next step (NOT started — first task for the next session): EXP-001** —
hypothesis: "no new entries at or after 13:00 IST"; candidate = STRAT-001
+ entry cutoff (single change); baseline-vs-candidate on identical 2024
data with walk-forward split (form on H1, validate on H2); check
stability across months before acceptance. Note: the decision engine has
no entry-cutoff config key yet — add engine support (config-driven, with
tests) first, then create the candidate via new-strategy.

## 2026-08-20 — HANDOFF

Research moves to the user's 24/7 server. The laptop session that did all
of the above stops here to avoid two concurrent researchers. Whoever reads
this on the server: you are now the sole researcher. The scratch backtest
DBs were on the laptop and are NOT in the repo — rebuild in minutes with
the driver pattern above (single process + seed each day with the previous
day's snapshots). Backtest baseline to reproduce/verify: 173 trades,
36.4% win rate, net −31,489.

**Operational fixes this cycle:** collection crons moved ~25 min early
(GitHub fires late); leg-A staging bug fixed (git add aborts on missing
pathspec — morning of 2026-08-20 was lost to it).

**Discipline reminders for whoever continues:** one hypothesis per
experiment; no rule changes from backtest alone — walk-forward + live
confirmation required; estimated spreads mean spread-sensitive results
need extra scrutiny; synthetic rows never count.
