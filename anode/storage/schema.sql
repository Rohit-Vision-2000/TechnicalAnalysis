-- ANODE research database schema (SQLite)
-- Rule: never delete or rewrite historical rows. This database is the
-- system's memory; research depends on it being complete and immutable.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS market_snapshots (
    snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,           -- ISO-8601
    nifty_spot      REAL    NOT NULL,
    atm_strike      REAL,
    nearest_expiry  TEXT,
    source          TEXT    NOT NULL DEFAULT 'replay',  -- replay | live
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON market_snapshots (timestamp);

CREATE TABLE IF NOT EXISTS option_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL REFERENCES market_snapshots (snapshot_id),
    expiry          TEXT    NOT NULL,
    strike          REAL    NOT NULL,
    option_type     TEXT    NOT NULL CHECK (option_type IN ('CE', 'PE')),
    ltp             REAL    NOT NULL,
    bid             REAL,
    ask             REAL,
    volume          INTEGER,
    open_interest   INTEGER,
    oi_change       INTEGER,
    iv              REAL,
    delta           REAL,
    gamma           REAL,
    theta           REAL,
    vega            REAL
);
CREATE INDEX IF NOT EXISTS idx_options_snapshot ON option_snapshots (snapshot_id);
CREATE INDEX IF NOT EXISTS idx_options_contract
    ON option_snapshots (expiry, strike, option_type);

CREATE TABLE IF NOT EXISTS strategy_versions (
    version_id      TEXT PRIMARY KEY,           -- STRAT-NNN
    created_at      TEXT NOT NULL,
    status          TEXT NOT NULL CHECK
        (status IN ('DRAFT','CANDIDATE','PRODUCTION','REJECTED','RETIRED')),
    description     TEXT NOT NULL DEFAULT '',
    parent_version  TEXT REFERENCES strategy_versions (version_id),
    config_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id     TEXT PRIMARY KEY,           -- DEC-YYYYMMDD-HHMMSS-NNNNN
    timestamp       TEXT NOT NULL,
    strategy_version TEXT NOT NULL REFERENCES strategy_versions (version_id),
    snapshot_id     INTEGER REFERENCES market_snapshots (snapshot_id),
    status          TEXT NOT NULL CHECK (status IN ('SIGNAL','NO_TRADE')),
    direction       TEXT CHECK (direction IN ('CALL','PUT')),
    expiry          TEXT,
    strike          REAL,
    option_type     TEXT CHECK (option_type IN ('CE','PE')),
    entry_low       REAL,
    entry_high      REAL,
    stop_loss       REAL,
    target          REAL,
    max_holding_minutes INTEGER,
    reason_codes_json TEXT NOT NULL DEFAULT '[]',
    features_json   TEXT NOT NULL DEFAULT '{}',
    notes           TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions (timestamp);
CREATE INDEX IF NOT EXISTS idx_decisions_strategy ON decisions (strategy_version);
CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions (status);

CREATE TABLE IF NOT EXISTS paper_trades (
    trade_id        TEXT PRIMARY KEY,           -- TRD-YYYYMMDD-NNNNN
    decision_id     TEXT NOT NULL REFERENCES decisions (decision_id),
    status          TEXT NOT NULL CHECK (status IN ('OPEN','CLOSED')),
    entry_time      TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    quantity        INTEGER NOT NULL,
    exit_time       TEXT,
    exit_price      REAL,
    exit_reason     TEXT CHECK
        (exit_reason IN ('TARGET','STOP_LOSS','TIME_EXIT','EOD','MANUAL')),
    gross_pnl       REAL,
    costs           REAL,
    net_pnl         REAL,
    result          TEXT CHECK (result IN ('WIN','LOSS','BREAKEVEN'))
);
CREATE INDEX IF NOT EXISTS idx_trades_decision ON paper_trades (decision_id);
CREATE INDEX IF NOT EXISTS idx_trades_result ON paper_trades (result);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id     TEXT PRIMARY KEY,         -- EXP-NNN
    created_at        TEXT NOT NULL,
    hypothesis        TEXT NOT NULL,
    baseline_version  TEXT NOT NULL REFERENCES strategy_versions (version_id),
    candidate_version TEXT REFERENCES strategy_versions (version_id),
    status            TEXT NOT NULL CHECK
        (status IN ('PLANNED','RUNNING','ACCEPTED','REJECTED')),
    results_json      TEXT NOT NULL DEFAULT '{}',
    conclusion        TEXT NOT NULL DEFAULT ''
);

-- Only one strategy may be PRODUCTION at any time.
CREATE UNIQUE INDEX IF NOT EXISTS idx_single_production
    ON strategy_versions (status) WHERE status = 'PRODUCTION';
