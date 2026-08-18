Yes — now I understand your idea better.

You **don't want to build an "AI model" that predicts NIFTY**.

You want to build a **self-improving trading software/system**, where the intelligence is in the *decision-making logic*, and Claude CLI acts as a continuously supervising developer/researcher.

The loop you have in mind is essentially:

```text
LIVE NIFTY MARKET
       ↓
Your Trading Software
       ↓
Technical Analysis
       ↓
Decision
       ↓
BUY / SELL / NO TRADE
       ↓
PAPER TRADE
       ↓
Wait for actual outcome
       ↓
Was decision correct?
       ↓
Analyze WHY
       ↓
Claude CLI observes everything
       ↓
Claude modifies decision logic
       ↓
Run again
       ↓
Repeat for weeks/months
       ↓
Software becomes increasingly selective
       ↓
Eventually target extremely high accuracy
```

**Yes. That architecture makes sense.**

The important correction I'd make is that **Claude is not the trader**. Claude is the **continuous software researcher/debugger**, while your software itself makes every market decision.

---

# What I think you actually want

Imagine your software has a brain like this:

```text
                 NIFTY LIVE DATA
                       │
                       ▼
              ┌─────────────────┐
              │ MARKET ANALYZER │
              └────────┬────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       PRICE          OI           IV
       ACTION       ANALYSIS      ANALYSIS
          │            │            │
          ├────────────┼────────────┤
          ▼            ▼            ▼
       TREND        SUPPORT/       VOLATILITY
                    RESISTANCE
          │            │            │
          └────────────┼────────────┘
                       ▼
               DECISION ENGINE
                       │
             ┌─────────┴─────────┐
             │                   │
             ▼                   ▼
         NO TRADE             TRADE
                                 │
                                 ▼
                         ENTRY / TARGET
                         STOP / EXPIRY
                                 │
                                 ▼
                          PAPER TRADE
                                 │
                                 ▼
                            OUTCOME
```

And **this decision engine is what keeps evolving**.

---

# The key thing: don't make Claude modify it randomly

This is the part I'd design very carefully.

Suppose the software says:

```text
10:32 AM

BUY NIFTY 25,000 CE

Entry: 142
Target: 170
SL: 125
```

The system records the entire state:

```text
timestamp
NIFTY price
option price
strike
expiry
OI
change OI
volume
IV
Greeks
RSI
MACD
VWAP
EMA
ATR
support/resistance
trend
PCR
etc.
```

Then the paper trade finishes.

Suppose:

```text
ENTRY = 142
TARGET = 170
ACTUAL HIGH = 153
SL = 125

Result = LOSS
```

Now **Claude gets the entire event**.

Claude investigates:

> Why did the system believe this was a high-quality setup?

Maybe it discovers:

```text
Failure pattern:

When:
- NIFTY above VWAP
- RSI > 60
- Call OI increasing
- IV rising

BUT

- Bid/ask spread > X
- resistance within 0.3%
- previous 5-minute candle had abnormal volume

the strategy has historically failed 82% of the time.
```

Claude proposes:

```text
NEW RULE:

Do not issue CALL signal when
resistance distance < 0.35%
AND
option spread > threshold.
```

Then the **software tests this rule**.

If it improves performance:

```text
Version 17
        ↓
Version 18
```

If it makes things worse:

```text
Version 18
        ↓
REJECT
        ↓
keep Version 17
```

That's the self-improvement mechanism you're describing.

---

# So your system has TWO brains

### Brain 1 — Trading software

This is responsible for:

> **"What should I do right now?"**

It continuously receives market data and makes decisions.

### Brain 2 — Claude CLI

This is responsible for:

> **"Why did the trading software make that decision, was it correct, and how can its decision logic be improved?"**

Claude should **not directly make the trading decision**.

That separation is extremely important.

---

# And your software doesn't necessarily need ML initially

This is another place where I misunderstood you earlier.

You can start with a **rule/logic-based decision engine**.

For example:

```text
IF

trend == bullish

AND

price > VWAP

AND

EMA20 > EMA50

AND

RSI between 55 and 70

AND

call OI condition favorable

AND

put OI condition favorable

AND

IV condition favorable

AND

resistance distance > X

AND

volume confirmation == true

AND

market regime == suitable

THEN

BUY CALL

ELSE

NO TRADE
```

Then Claude observes thousands of decisions.

It can discover:

```text
Rule A is useful
Rule B is useless
Rule C works only during expiry
Rule D causes false signals
Rule E should have a different threshold
Rule F works only in trending markets
```

And modify the logic.

Over time:

```text
Version 1
   ↓
Version 2
   ↓
Version 3
   ↓
...
Version 87
```

This is much closer to what you're describing.

---

# But there is one huge problem with your "99%" target

If you tell Claude:

> "Keep changing the software until it reaches 99% accuracy."

it can easily produce a **fake 99%**.

For example:

```text
Version 1
1000 trades
52% accuracy

Version 20
500 trades
67%

Version 50
100 trades
83%

Version 100
20 trades
95%

Version 200
3 trades
100%
```

It can eventually make the system so restrictive that it gives almost no signals.

You already said:

> "I don't care if it gives one signal in a month."

That actually makes this problem **more dangerous**, because the system can trivially reach 99% by almost never trading.

So you need another condition:

```text
Accuracy
+
minimum statistical significance
+
minimum number of opportunities
+
out-of-sample validation
+
paper-trading validation
```

For example, you might eventually define:

```text
Target:

≥ 95% paper-trade accuracy
over ≥ 200 qualifying signals

AND

no major degradation across different market regimes.
```

The exact numbers can be decided later.

---

# The really interesting part of your idea

You don't want Claude to "train a model."

You want Claude to perform **continuous strategy evolution**.

Something like:

```text
             SOFTWARE V1
                  │
                  ▼
           10,000 decisions
                  │
                  ▼
          ┌───────────────┐
          │ Failure cases │
          └───────┬───────┘
                  │
                  ▼
              CLAUDE
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
    Analyze    Find       Propose
    patterns   weakness   changes
        │         │         │
        └─────────┼─────────┘
                  ▼
             V2 strategy
                  │
                  ▼
            Backtest V2
                  │
          ┌───────┴───────┐
          ▼               ▼
       WORSE             BETTER
          │               │
        reject          V2
                          │
                          ▼
                     Paper trade
                          │
                          ▼
                     More data
                          │
                          ▼
                       CLAUDE
                          │
                          ▼
                         V3
```

**That is absolutely something you can build.**

---

# I would actually give the project a different name

Not:

> NIFTY AI Predictor

Something like:

> **Autonomous NIFTY Options Decision Engine**

or

> **Self-Evolving NIFTY Options Trading Research System**

Because that's what you're really building.

---

# And Claude CLI becomes the continuous researcher

You could have Claude running against the project repository for months.

It periodically examines:

```text
/data
/decisions
/paper_trades
/failures
/strategies
/experiments
/metrics
/logs
```

and receives commands/tasks such as:

```text
Analyze today's failed signals.

Find common characteristics among the failures.

Determine whether any current decision rules
are responsible.

Propose changes.

Run the complete historical test suite.

Compare the new strategy with the current strategy.

Do not replace the current strategy unless the
new strategy passes all promotion criteria.

Document the experiment.
```

Then the next day it does it again.

---

# I would build the first version WITHOUT Claude

This is important.

First create:

### `Market Feed`

↓

### `Technical Analysis Engine`

↓

### `Decision Engine`

↓

### `Paper Trading Engine`

↓

### `Result Analyzer`

↓

### `Database`

Only after that works should Claude be connected.

Then:

```text
                    ┌───────────────────┐
                    │ Trading Software  │
                    └─────────┬─────────┘
                              │
                       continuously
                              │
                              ▼
                     ┌─────────────────┐
                     │ Paper Trading   │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │ Results DB      │
                     └────────┬────────┘
                              │
                              ▼
                       ┌─────────────┐
                       │ Claude CLI  │
                       └──────┬──────┘
                              │
                     modifies/researches
                              │
                              ▼
                       Strategy V2
                              │
                              ▼
                         Test suite
                              │
                       ┌──────┴──────┐
                       ▼             ▼
                     FAIL          PASS
                       │             │
                       ▼             ▼
                    Reject        Paper
```

---

## And there's one more thing I'd strongly recommend

**Don't let Claude have unrestricted permission to change the running system.**

Give it something like:

```text
production/
    strategy_v17/

research/
    strategy_v18_candidate/

```

Claude can do anything it wants inside:

```text
research/
```

But it cannot directly overwrite:

```text
production/
```

A candidate must pass:

```text
Backtest
   ↓
Historical validation
   ↓
Previous-version comparison
   ↓
Paper trading
   ↓
Promotion
```

before becoming production.

That gives you an **autonomous improvement loop without autonomous destruction of your strategy**.

---

### So yes — I now understand your idea.

You are essentially asking:

> **Can we create a deterministic/algorithmic NIFTY options decision engine, feed it continuous live market data, let it paper-trade every decision, record exactly where it succeeds/fails, and have Claude CLI continuously inspect those failures and evolve the decision logic until the system demonstrates extremely high reliability?**

**Yes. That's the project I'd build.**

And I would start with **NIFTY 50 only, paper trading only, no broker integration, no ML requirement initially, and a version-controlled self-improvement loop**.

The next useful step is to design the **actual software architecture + database schema + decision-engine structure + Claude CLI operating protocol**. That is where we can turn your idea into something you can literally hand to Claude Code and say **"build this from Phase 1 onward."**




Exactly. Let's turn the idea into an actual engineering project.

I would build it in **phases**, and importantly, I would make the system capable of evolving before giving Claude permission to evolve it.

# 1. Final system architecture

The complete system should eventually look like this:

```text
                         ┌──────────────────────┐
                         │   LIVE MARKET FEED   │
                         │ NIFTY + OPTION CHAIN │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   MARKET DATA ENGINE │
                         │ Clean / Validate /   │
                         │ Normalize / Store    │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ TECHNICAL ANALYSIS   │
                         │                      │
                         │ Price Action         │
                         │ Indicators           │
                         │ OI                   │
                         │ IV                   │
                         │ Greeks               │
                         │ Volume               │
                         │ VWAP                 │
                         │ S/R                  │
                         │ Market Regime        │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   DECISION ENGINE    │
                         │                      │
                         │ BUY CALL             │
                         │ BUY PUT              │
                         │ NO TRADE             │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ PAPER TRADE ENGINE   │
                         │ Entry / SL / Target  │
                         │ Exit / P&L / Time    │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   OUTCOME ANALYZER   │
                         │                      │
                         │ Why WIN?             │
                         │ Why LOSS?            │
                         │ What conditions?     │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │    RESEARCH DB      │
                         └──────────┬───────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────┐
                    │        CLAUDE CLI            │
                    │                              │
                    │ Observe → Analyze → Hypothesize│
                    │ → Modify → Test → Evaluate   │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                         ┌──────────────────────┐
                         │ CANDIDATE STRATEGY   │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ VALIDATION GATE      │
                         │                      │
                         │ Backtest             │
                         │ Walk-forward         │
                         │ Paper trading        │
                         │ Regression tests     │
                         └──────────┬───────────┘
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                      REJECT                 PROMOTE
                         │                     │
                         └──────────────┐      │
                                        ▼      ▼
                                   Production Strategy
```

That is the system I would aim for.

---

# 2. Phase 1 — Build the "brainless" trading simulator

Don't start with AI.

Don't even start with Claude.

First create a software framework capable of answering:

> Given market data at time `T`, what decision would the software have made, and what happened afterward?

This is the foundation.

I'd use:

```text
Python
FastAPI
PostgreSQL / DuckDB
Pandas / Polars
NumPy
```

Initially you don't need React either.

A CLI + database + reports is enough.

---

# 3. Market data layer

Create one standard internal market representation.

For example:

```text
MarketSnapshot

timestamp
nifty_spot

atm_strike

expiry

option_chain[]
```

Each option:

```text
OptionSnapshot

timestamp
expiry
strike
option_type

ltp
bid
ask

volume
open_interest
oi_change

iv

delta
gamma
theta
vega
```

Don't let the strategy directly consume raw API responses.

Always go:

```text
External API
     ↓
Adapter
     ↓
Normalized MarketSnapshot
     ↓
Everything else
```

This means you can later replace the market-data provider without rewriting your trading engine.

---

# 4. Record EVERYTHING

This is probably the most important engineering rule.

Every time your software makes a decision, store the **entire state of the world that it saw at that moment**.

For example:

```text
decision_id
timestamp

strategy_version

nifty_price

expiry
strike
option_type

option_ltp
bid
ask
volume
oi
oi_change
iv

rsi
macd
ema20
ema50
vwap
atr

trend
market_regime

support
resistance

decision
entry
stop_loss
target

decision_reason
```

Then:

```text
result
exit_time
exit_price
pnl
success/failure
failure_reason
```

Why?

Because six months later Claude needs to be able to ask:

> "Show me every failed CALL signal where RSI was between 60–70, NIFTY was above VWAP, IV increased >5%, and resistance was within 0.5%."

If you haven't stored the original state, you can't do that.

---

# 5. Create a technical-analysis engine

Don't put indicators directly inside your decision logic.

Separate them.

```text
TechnicalAnalysisEngine
```

produces:

```text
{
    trend: "BULLISH",

    rsi: 63.2,

    macd:
        bullish,

    ema20_above_ema50: true,

    price_above_vwap: true,

    atr: ...,

    volatility_regime: "MEDIUM",

    support_levels: [...],

    resistance_levels: [...],

    volume_confirmation: true,

    option_chain_analysis: {...}
}
```

Then your strategy receives this object.

This separation becomes extremely useful later when Claude experiments with different logic.

---

# 6. Don't start with 100 indicators

This is another trap.

Start with a reasonable set:

### Price

```text
OHLC
returns
VWAP
ATR
```

### Trend

```text
EMA 20
EMA 50
EMA 200
ADX
```

### Momentum

```text
RSI
MACD
```

### Volatility

```text
ATR
realized volatility
IV
IV change
```

### Options

```text
OI
OI change
volume
PCR
IV skew
ATM IV
```

### Market structure

```text
support
resistance
previous day high
previous day low
day high
day low
VWAP
```

That's enough for V1.

---

# 7. Decision engine

Now create:

```text
DecisionEngine
```

It should return a structured object.

Something like:

```text
Decision:

status = SIGNAL / NO_TRADE

direction = CALL / PUT

contract = ...

entry = ...

stop_loss = ...

target = ...

max_holding_time = ...

reason_codes = [...]

strategy_version = ...
```

For example:

```text
SIGNAL

BUY CALL

Entry: 145–148
SL: 128
Target: 175

Reasons:

TREND_BULLISH
ABOVE_VWAP
EMA_CONFIRMATION
OI_CONFIRMATION
VOLUME_CONFIRMATION
RESISTANCE_CLEAR
IV_ACCEPTABLE
```

The reasons are extremely important.

Claude needs to know **why** the software made the decision.

---

# 8. Give every decision a unique fingerprint

For example:

```text
decision_id = DEC-20260819-103201-00042
```

And:

```text
strategy_version = STRAT-001
```

Now you can trace:

```text
DEC-...42
     ↓
STRAT-001
     ↓
signal
     ↓
paper trade
     ↓
LOSS
     ↓
failure analysis
     ↓
Claude experiment EXP-034
     ↓
STRAT-002
```

This is essential for autonomous development.

---

# 9. Paper trading engine

The paper trader should behave as though it were a real broker.

It should simulate:

```text
signal
 ↓
entry
 ↓
position
 ↓
monitor
 ↓
SL / TARGET / TIME EXIT
 ↓
close
```

And account for:

```text
spread
slippage
brokerage
taxes/fees
```

The point is to avoid:

> "The backtest made ₹10 lakh."

when real execution wouldn't have achieved it.

---

# 10. The failure analyzer

This is where your idea becomes powerful.

Suppose:

```text
Signal #143

BUY NIFTY CALL

Result:
LOSS
```

The system should automatically generate:

```text
FAILURE REPORT

Signal:
143

Market regime:
SIDEWAYS

Trend:
BULLISH

RSI:
67

VWAP:
ABOVE

OI:
BULLISH

IV:
HIGH

Resistance:
0.22% away

Volume:
WEAK

Result:
STOP LOSS

Potential failure factors:

1. Resistance too close
2. High IV
3. Weak volume
4. Sideways regime
```

Then Claude can investigate the pattern across **all historical failures**, rather than looking at one trade.

---

# 11. This is where Claude CLI comes in

Now we create an `AGENTS.md` / research protocol.

Claude's job isn't:

> "Make the strategy better."

That's too vague.

Its job is:

> **Find statistically repeatable failure patterns and test whether modifying the decision logic improves out-of-sample performance.**

For every cycle:

```text
1. Read current strategy
2. Read recent decisions
3. Read wins
4. Read losses
5. Analyze failure clusters
6. Form ONE hypothesis
7. Create candidate strategy
8. Run tests
9. Compare against baseline
10. Reject or accept
11. Document result
```

**One hypothesis per experiment** is important.

Otherwise Claude changes 15 things and you don't know what actually improved the system.

---

# 12. Example Claude improvement cycle

Current rule:

```text
BUY CALL if:

bullish trend
AND
above VWAP
AND
RSI > 55
AND
OI bullish
```

After 300 paper trades, Claude notices:

```text
Most losses occur when:
resistance < 0.4%
```

Claude proposes:

```text
NEW RULE:

resistance_distance >= 0.4%
```

Candidate:

```text
STRAT-002
```

Run:

```text
STRAT-001
vs
STRAT-002
```

Suppose:

```text
STRAT-001
Win rate: 81%

STRAT-002
Win rate: 89%
```

But now check:

```text
number of trades
profit factor
drawdown
different market regimes
different months
expiry vs non-expiry
```

If everything improves:

```text
STRAT-002 → candidate for promotion
```

Otherwise:

```text
STRAT-002 → rejected
```

---

# 13. Claude should maintain an experiment journal

Something like:

```text
experiments/
    EXP-001.md
    EXP-002.md
    EXP-003.md
```

Each experiment:

```text
Experiment:
EXP-042

Hypothesis:
Signals near resistance produce excessive failures.

Change:
Require resistance distance > 0.4%.

Baseline:
STRAT-017

Candidate:
STRAT-018

Results:

                    STRAT-017   STRAT-018

Signals             412         291
Win rate            86.2%       92.1%
Profit factor       3.4         4.7
Max DD              7.1%        4.2%

Conclusion:
Candidate improves quality but reduces opportunity.

Status:
PROMOTE TO PAPER
```

This creates an **auditable evolutionary history**.

---

# 14. The system should have strategy versions

Never have:

```text
strategy.py
```

that Claude continuously edits.

Instead:

```text
strategies/

STRAT-001/
STRAT-002/
STRAT-003/
...
```

Each is immutable once evaluated.

You then have:

```text
CURRENT_PRODUCTION = STRAT-017
```

Claude creates:

```text
STRAT-018
```

It cannot destroy STRAT-017.

This is basically **Git for trading strategies**.

---

# 15. The autonomous loop

Once everything works:

```text
Every day
   ↓
Collect market data
   ↓
Generate decisions
   ↓
Paper trade
   ↓
Close positions
   ↓
Analyze outcomes
   ↓
Update research database
   ↓
Claude wakes up
   ↓
Analyze failures
   ↓
Choose research question
   ↓
Create candidate
   ↓
Run experiment
   ↓
Validate
   ↓
If better → candidate
   ↓
Continue paper testing
```

Claude could run once after the trading session rather than continuously.

That's actually better initially.

---

# 16. Don't let Claude change rules every day

This sounds counterintuitive, but it's important.

Suppose:

```text
Monday:
Loss → change rule

Tuesday:
Loss → change rule

Wednesday:
Loss → change rule
```

You're fitting the strategy to recent noise.

Instead:

```text
Collect enough observations
        ↓
Identify statistically meaningful pattern
        ↓
Experiment
        ↓
Validate
```

The agent should be **patient**, just like you want the trading system to be.

---

# 17. Your "99%" target should become a promotion criterion

I'd eventually define something like:

```text
PROMOTION REQUIREMENTS

✓ Minimum number of qualifying signals
✓ High out-of-sample hit rate
✓ Stable performance across months
✓ Stable performance across market regimes
✓ Stable performance around expiry
✓ Positive expectancy
✓ Controlled drawdown
✓ Realistic transaction costs
✓ No look-ahead leakage
✓ No data leakage
✓ No single market period responsible for performance
```

And then:

```text
IF all conditions pass
    → promote
ELSE
    → continue research
```

So Claude isn't chasing a number.

It's trying to satisfy a **quality specification**.

---

# 18. One critical distinction: prediction vs decision

Your software doesn't need to predict:

> "NIFTY will go up."

It needs to decide:

> **"Is there a sufficiently favorable opportunity to buy this specific contract right now?"**

That's a much more useful problem.

For example:

```text
NIFTY:
+0.35%

But:

NIFTY CALL:
poor liquidity
high IV
resistance nearby

=> NO TRADE
```

Or:

```text
NIFTY:
+0.2%

CALL:
strong momentum
OI confirmation
volume expansion
IV reasonable
resistance far away
good liquidity

=> TRADE
```

That is the behavior you're looking for.

---

# 19. Eventually the system can discover its own rules

You don't necessarily have to manually tell it:

```text
RSI > 60
```

You can let Claude investigate:

```text
What RSI ranges produce the highest
conditional success rate under each market regime?
```

It might discover:

```text
Trending bullish:
RSI 58–72 → strong

Sideways:
RSI > 65 → poor

High volatility:
RSI alone → unreliable
```

Then the decision engine becomes:

```text
IF regime == TRENDING_BULLISH:
    use RSI rule A

IF regime == SIDEWAYS:
    use RSI rule B

IF regime == HIGH_VOLATILITY:
    disable RSI rule
```

That's **strategy evolution**, not necessarily ML.

---

# 20. What I would build first

I would make your project roadmap:

### Phase 1 — Infrastructure

```text
[ ] Project structure
[ ] Market-data abstraction
[ ] Database
[ ] Market snapshot schema
[ ] Logging
[ ] Configuration system
```

### Phase 2 — Analysis

```text
[ ] NIFTY price analysis
[ ] Option-chain analysis
[ ] Technical indicators
[ ] OI analysis
[ ] IV analysis
[ ] Market-regime detection
```

### Phase 3 — Decision engine

```text
[ ] CALL decision
[ ] PUT decision
[ ] NO-TRADE decision
[ ] Entry calculation
[ ] SL calculation
[ ] Target calculation
[ ] Decision explanation
```

### Phase 4 — Paper trading

```text
[ ] Position simulator
[ ] Entry simulation
[ ] Exit simulation
[ ] SL/target monitoring
[ ] Costs
[ ] P&L
[ ] Trade history
```

### Phase 5 — Research engine

```text
[ ] Failure analysis
[ ] Win analysis
[ ] Pattern discovery
[ ] Strategy versioning
[ ] Experiment framework
[ ] Backtesting
[ ] Walk-forward testing
```

### Phase 6 — Claude integration

```text
[ ] Claude reads reports
[ ] Claude analyzes failures
[ ] Claude proposes experiments
[ ] Claude modifies candidate code
[ ] Automated testing
[ ] Candidate evaluation
[ ] Strategy promotion
```

### Phase 7 — Long-term autonomous operation

```text
Market
  ↓
Trade
  ↓
Outcome
  ↓
Research
  ↓
Claude
  ↓
Experiment
  ↓
Validation
  ↓
Improvement
  ↓
Repeat
```

---

# 21. And THIS is the prompt I'd eventually give Claude Code

Not the prompt from my previous answer. For your actual idea, I'd start with a project-bootstrap prompt along these lines:

```text
Build a production-quality research and paper-trading platform for NIFTY 50 options.

IMPORTANT:

This is NOT an AI chatbot and it is NOT initially an ML prediction project.

The core product is a continuously running market-analysis and decision-making software.

The software must consume live NIFTY 50 and NIFTY options market data, perform extensive technical and options-market analysis, and decide:

1. BUY CALL
2. BUY PUT
3. NO TRADE

Every trade decision must contain:

- instrument
- expiry
- strike
- option type
- entry price/range
- stop loss
- target
- maximum holding time
- decision timestamp
- strategy version
- complete reasoning/conditions used

The system must initially operate ONLY in paper-trading mode.

No real orders must ever be placed.

Every market snapshot and every decision must be persistently recorded so that the exact information available to the system at decision time can be reconstructed later.

The system must record the complete outcome of every paper trade.

The software must have a strategy-versioning architecture.

Never modify the currently active strategy directly.

All modifications must create a new candidate strategy version.

The project must support:

- historical backtesting
- replay of historical market data
- live paper trading
- strategy comparison
- experiment tracking
- failure analysis
- performance analysis
- strategy promotion/rejection

The decision engine must have a NO-TRADE state and must be designed for selectivity rather than generating frequent signals.

The system must NOT optimize for the number of trades.

The system must NOT optimize solely for historical accuracy.

All experiments must guard against:

- look-ahead bias
- data leakage
- overfitting
- survivorship bias
- unrealistic fills
- transaction-cost omission

The system must model realistic execution conditions including bid/ask spread, slippage and applicable trading costs.

Create a complete experiment framework so that an external autonomous coding/research agent such as Claude CLI can later:

1. inspect historical decisions
2. inspect winning trades
3. inspect losing trades
4. identify recurring failure patterns
5. formulate a hypothesis
6. modify a candidate strategy
7. run historical tests
8. run walk-forward validation
9. compare candidate against current strategy
10. reject or promote the candidate
11. document the experiment

Claude must never directly modify or replace the production strategy.

The project must maintain an immutable history of strategy versions and experiments.

Initially implement the system without machine learning.

Use a modular decision-engine architecture so that additional rules, statistical models and ML components can be added later without rewriting the platform.

Start by implementing Phase 1:

- project architecture
- configuration
- database schema
- market-data abstraction
- normalized market snapshot model
- option-chain model
- decision model
- paper-trade model
- strategy-version model
- experiment model
- logging
- CLI commands
- test framework

Do not attempt to build everything in one file.

Do not create placeholder implementations that pretend to work.

Build the foundation cleanly so that live data, historical replay, technical analysis, decision logic and autonomous research can be added incrementally.

Before writing implementation code, inspect the repository and produce an architecture plan, data model, module boundaries and development roadmap.
```

That's the prompt I would actually start with.

**Don't tell Claude "make it 99% accurate" during the initial build.** Tell it to build the infrastructure that can *measure whether increasing accuracy is real*. Once that infrastructure exists, we can add the self-improvement loop.

And one final reality check: **a claimed 99% paper-trading hit rate does not imply 99% live-trading accuracy**. The system should therefore remain paper-only until it has survived a substantial genuinely unseen live period. No amount of Claude iteration can remove the stochastic nature of markets.

The next step I'd recommend is to design **Phase 1 in exact detail — the folder structure, Python modules, database tables, JSON schemas, CLI commands, and the first `AGENTS.md` that controls Claude's autonomous research behavior.** That would give you something you can paste into Claude CLI and start building immediately.
