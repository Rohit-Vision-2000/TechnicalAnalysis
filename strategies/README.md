# Strategy versions

Each subdirectory is one **immutable** strategy version:

```
strategies/
    STRAT-001/
        manifest.json    version metadata + parameters
        (later: rules.py or rules.json — the decision logic)
```

Rules:

1. A version is **never edited** after it has been evaluated. To change
   anything, create a new version with `python -m anode new-strategy
   --parent STRAT-NNN --description "..."`.
2. Exactly one version has status `PRODUCTION` (enforced by the database).
3. Promotion to PRODUCTION happens only through the validation gate defined
   in `AGENTS.md`, never by directly editing status outside an accepted
   experiment.
4. The database (`strategy_versions` table) is the source of truth for
   status; the directory mirrors the definition for auditability.
