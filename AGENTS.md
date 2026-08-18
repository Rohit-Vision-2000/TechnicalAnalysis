# ANODE — Autonomous Research Protocol

This file governs how any autonomous agent (Claude CLI) works on this
repository. The agent is the **researcher/debugger**, never the trader.
The software makes every market decision; the agent's job is to understand
why decisions succeed or fail and to evolve the decision logic through
controlled experiments.

## Hard rules (never violate)

1. **Paper trading only.** Never add broker integration, order placement,
   or anything that could send a real order. Ever.
2. **Never modify the PRODUCTION strategy.** All changes create a new
   strategy version (`python -m anode new-strategy --parent STRAT-NNN ...`).
   Strategy directories under `strategies/` are immutable once evaluated.
3. **Never delete or rewrite historical data** — snapshots, decisions,
   trades, experiments. The database is the system's memory.
4. **One hypothesis per experiment.** Change one rule/threshold at a time,
   otherwise results are unattributable.
5. **No metric gaming.** Accuracy achieved by shrinking the signal count
   below the minimum-signals threshold is not an improvement. Never tune on
   the validation window. Guard against look-ahead bias, data leakage,
   overfitting, and unrealistic fills.

## Research cycle (one iteration)

1. Read the current production strategy and its recent performance.
2. Read recent decisions, wins, and losses (`decisions`, `paper_trades`).
3. Look for **statistically repeatable** failure clusters — not single-trade
   noise. Do not propose a change from fewer than ~30 relevant observations.
4. Form ONE hypothesis; record it as an experiment
   (`python -m anode new-experiment ...` + `experiments/EXP-NNN.md`).
5. Create a candidate strategy version with the single change.
6. Backtest baseline vs candidate on identical data; run walk-forward
   validation on data not used to form the hypothesis.
7. Compare: signal count, win rate, profit factor, max drawdown,
   stability across market regimes / months / expiry vs non-expiry days.
8. Accept (candidate → CANDIDATE, continue paper testing) or reject
   (candidate → REJECTED). Record results and conclusion in the experiment.
9. Promotion to PRODUCTION requires the full promotion criteria below.

## Promotion criteria

A candidate may replace production only if ALL hold:

- Minimum number of qualifying signals in evaluation (not fewer trades
  achieving a prettier ratio) — threshold set in the experiment up front.
- Out-of-sample (walk-forward) performance improves or holds while the
  targeted failure mode measurably shrinks.
- No major degradation in any market regime or month.
- Realistic costs (spread, slippage, brokerage, taxes) included.
- Positive expectancy and controlled drawdown.
- No single market period responsible for the improvement.

## Concrete workflow commands

Daily operation (paper trading):

    python -m anode run --source nse --interval 60        # live session (paper)
    python -m anode report --date YYYY-MM-DD              # end-of-day summary
    python -m anode failures --limit 500                  # failure clusters

Research cycle:

    python -m anode failures                               # 1. find weak spots
    python -m anode new-experiment --hypothesis "..." \
        --baseline STRAT-NNN --candidate STRAT-MMM         # 2. register hypothesis
    python -m anode new-strategy --parent STRAT-NNN \
        --description "..." --params '{"call": {...}}'     # 3. one-change candidate
    python -m anode backtest --strategy STRAT-MMM --file DATA.csv
    python -m anode compare --baseline STRAT-NNN --candidate STRAT-MMM \
        --file DATA.csv --experiment EXP-KKK               # 4. gated comparison
    python -m anode conclude-experiment --id EXP-KKK \
        --status ACCEPTED|REJECTED --conclusion "..."      # 5. record judgment
    python -m anode promote --candidate STRAT-MMM \
        --experiment EXP-KKK                               # 6. only path to PRODUCTION

`promote` refuses unless the experiment is ACCEPTED, names that exact
candidate, and its recorded comparison verdict is PASS. Do not bypass this
with `set-status` — `set-status --status PRODUCTION` is reserved for the
initial bootstrap when no production strategy exists yet.

Synthetic data (`--source synthetic`, `--synthetic-days`) exercises the
pipeline ONLY. Never draw strategy conclusions from it and never let
synthetic-sourced rows into a research argument (snapshots are tagged
`source='synthetic'` for this reason).

## Working style

- Be patient: collect enough observations before changing rules. Daily
  rule-churn is fitting to noise.
- Document everything: experiments must be reproducible from their records.
- Run the test suite (`python -m unittest discover -s tests`) before and
  after any code change; never commit failing tests.
- Platform code (data layer, storage, paper trader) changes are normal
  software engineering. Strategy logic changes go through experiments.
