# Experiment journal

One Markdown file per experiment (`EXP-NNN.md`), mirroring the `experiments`
database table. Every experiment tests exactly **one hypothesis**.

Template:

```markdown
# EXP-NNN

**Hypothesis:** <one sentence — what failure pattern this addresses>

**Change:** <the single rule/threshold change being tested>

**Baseline:** STRAT-NNN
**Candidate:** STRAT-MMM

## Results

|                | Baseline | Candidate |
|----------------|----------|-----------|
| Signals        |          |           |
| Win rate       |          |           |
| Profit factor  |          |           |
| Max drawdown   |          |           |
| Regime breakdown |        |           |

## Conclusion

<accepted / rejected, and why>
```
