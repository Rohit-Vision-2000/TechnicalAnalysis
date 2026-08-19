"""Repositories: the only code that talks SQL.

Each repository maps between dataclass models and database rows. Timestamps
are stored as ISO-8601 strings; JSON columns hold reason codes, features,
strategy configs and experiment results.
"""

import json
from datetime import datetime
from typing import List, Optional

from anode.models import (
    Decision,
    Experiment,
    MarketSnapshot,
    OptionSnapshot,
    PaperTrade,
    StrategyStatus,
    StrategyVersion,
)
from anode.storage.db import Database


def _iso(ts: Optional[datetime]) -> Optional[str]:
    return ts.isoformat(sep=" ") if ts is not None else None


def _dt(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s else None


class SnapshotRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, snap: MarketSnapshot, source: str = "replay") -> int:
        """Persist a snapshot with its full option chain. Returns snapshot_id."""
        cur = self.db.conn.execute(
            "INSERT INTO market_snapshots "
            "(timestamp, nifty_spot, atm_strike, nearest_expiry, source) "
            "VALUES (?, ?, ?, ?, ?)",
            (_iso(snap.timestamp), snap.nifty_spot, snap.atm_strike,
             snap.nearest_expiry, source),
        )
        snapshot_id = cur.lastrowid
        self.db.conn.executemany(
            "INSERT INTO option_snapshots "
            "(snapshot_id, expiry, strike, option_type, ltp, bid, ask, volume, "
            " open_interest, oi_change, iv, delta, gamma, theta, vega) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (snapshot_id, o.expiry, o.strike, o.option_type, o.ltp, o.bid,
                 o.ask, o.volume, o.open_interest, o.oi_change, o.iv,
                 o.delta, o.gamma, o.theta, o.vega)
                for o in snap.options
            ],
        )
        self.db.conn.commit()
        return snapshot_id

    def get(self, snapshot_id: int) -> Optional[MarketSnapshot]:
        row = self.db.conn.execute(
            "SELECT * FROM market_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if row is None:
            return None
        opt_rows = self.db.conn.execute(
            "SELECT * FROM option_snapshots WHERE snapshot_id = ? "
            "ORDER BY expiry, strike, option_type",
            (snapshot_id,),
        ).fetchall()
        options = [
            OptionSnapshot(
                expiry=r["expiry"], strike=r["strike"], option_type=r["option_type"],
                ltp=r["ltp"], bid=r["bid"], ask=r["ask"], volume=r["volume"],
                open_interest=r["open_interest"], oi_change=r["oi_change"],
                iv=r["iv"], delta=r["delta"], gamma=r["gamma"],
                theta=r["theta"], vega=r["vega"],
            )
            for r in opt_rows
        ]
        return MarketSnapshot(
            timestamp=_dt(row["timestamp"]),
            nifty_spot=row["nifty_spot"],
            options=options,
            atm_strike=row["atm_strike"],
            nearest_expiry=row["nearest_expiry"],
        )

    def for_day(self, day: str, source: str) -> List[MarketSnapshot]:
        """All snapshots for one day (YYYY-MM-DD) and source, oldest first.

        Used to rebuild indicator state after an intraday restart; the
        options are loaded too because chain analysis needs them.
        """
        rows = self.db.conn.execute(
            "SELECT snapshot_id FROM market_snapshots "
            "WHERE source = ? AND timestamp >= ? AND timestamp < ? "
            "ORDER BY timestamp",
            (source, day + " 00:00:00", day + " 23:59:59.999999"),
        ).fetchall()
        return [self.get(r["snapshot_id"]) for r in rows]

    def recent(self, limit: int = 20) -> List[dict]:
        rows = self.db.conn.execute(
            "SELECT snapshot_id, timestamp, nifty_spot, atm_strike, nearest_expiry, "
            "source, (SELECT COUNT(*) FROM option_snapshots o "
            " WHERE o.snapshot_id = m.snapshot_id) AS option_count "
            "FROM market_snapshots m ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


class DecisionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, d: Decision) -> None:
        self.db.conn.execute(
            "INSERT INTO decisions "
            "(decision_id, timestamp, strategy_version, snapshot_id, status, "
            " direction, expiry, strike, option_type, entry_low, entry_high, "
            " stop_loss, target, max_holding_minutes, reason_codes_json, "
            " features_json, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (d.decision_id, _iso(d.timestamp), d.strategy_version, d.snapshot_id,
             d.status, d.direction, d.expiry, d.strike, d.option_type,
             d.entry_low, d.entry_high, d.stop_loss, d.target,
             d.max_holding_minutes, json.dumps(d.reason_codes),
             json.dumps(d.features), d.notes),
        )
        self.db.conn.commit()

    def get(self, decision_id: str) -> Optional[Decision]:
        row = self.db.conn.execute(
            "SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        return self._from_row(row) if row else None

    def recent(self, limit: int = 20, status: Optional[str] = None) -> List[Decision]:
        sql = "SELECT * FROM decisions"
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = self.db.conn.execute(sql, params).fetchall()
        return [self._from_row(r) for r in rows]

    def count_for_day(self, day: str) -> int:
        """Number of decisions on a YYYYMMDD day (for per-day ID sequencing)."""
        row = self.db.conn.execute(
            "SELECT COUNT(*) AS n FROM decisions WHERE decision_id LIKE ?",
            ("DEC-{}-%".format(day),),
        ).fetchone()
        return row["n"]

    @staticmethod
    def _from_row(r) -> Decision:
        return Decision(
            decision_id=r["decision_id"], timestamp=_dt(r["timestamp"]),
            strategy_version=r["strategy_version"], status=r["status"],
            snapshot_id=r["snapshot_id"], direction=r["direction"],
            expiry=r["expiry"], strike=r["strike"], option_type=r["option_type"],
            entry_low=r["entry_low"], entry_high=r["entry_high"],
            stop_loss=r["stop_loss"], target=r["target"],
            max_holding_minutes=r["max_holding_minutes"],
            reason_codes=json.loads(r["reason_codes_json"]),
            features=json.loads(r["features_json"]), notes=r["notes"],
        )


class TradeRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, t: PaperTrade) -> None:
        self.db.conn.execute(
            "INSERT OR REPLACE INTO paper_trades "
            "(trade_id, decision_id, status, entry_time, entry_price, quantity, "
            " exit_time, exit_price, exit_reason, gross_pnl, costs, net_pnl, result) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (t.trade_id, t.decision_id, t.status, _iso(t.entry_time),
             t.entry_price, t.quantity, _iso(t.exit_time), t.exit_price,
             t.exit_reason, t.gross_pnl, t.costs, t.net_pnl, t.result),
        )
        self.db.conn.commit()

    def get(self, trade_id: str) -> Optional[PaperTrade]:
        row = self.db.conn.execute(
            "SELECT * FROM paper_trades WHERE trade_id = ?", (trade_id,)
        ).fetchone()
        return self._from_row(row) if row else None

    def recent(self, limit: int = 20) -> List[PaperTrade]:
        rows = self.db.conn.execute(
            "SELECT * FROM paper_trades ORDER BY entry_time DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._from_row(r) for r in rows]

    def count_for_day(self, day: str) -> int:
        """Number of trades on a YYYYMMDD day (for per-day ID sequencing)."""
        row = self.db.conn.execute(
            "SELECT COUNT(*) AS n FROM paper_trades WHERE trade_id LIKE ?",
            ("TRD-{}-%".format(day),),
        ).fetchone()
        return row["n"]

    def open_trades(self) -> List[PaperTrade]:
        rows = self.db.conn.execute(
            "SELECT * FROM paper_trades WHERE status = 'OPEN' ORDER BY entry_time"
        ).fetchall()
        return [self._from_row(r) for r in rows]

    @staticmethod
    def _from_row(r) -> PaperTrade:
        return PaperTrade(
            trade_id=r["trade_id"], decision_id=r["decision_id"],
            status=r["status"], entry_time=_dt(r["entry_time"]),
            entry_price=r["entry_price"], quantity=r["quantity"],
            exit_time=_dt(r["exit_time"]), exit_price=r["exit_price"],
            exit_reason=r["exit_reason"], gross_pnl=r["gross_pnl"],
            costs=r["costs"], net_pnl=r["net_pnl"], result=r["result"],
        )


class StrategyRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, s: StrategyVersion) -> None:
        self.db.conn.execute(
            "INSERT INTO strategy_versions "
            "(version_id, created_at, status, description, parent_version, config_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (s.version_id, _iso(s.created_at), s.status, s.description,
             s.parent_version, json.dumps(s.config)),
        )
        self.db.conn.commit()

    def get(self, version_id: str) -> Optional[StrategyVersion]:
        row = self.db.conn.execute(
            "SELECT * FROM strategy_versions WHERE version_id = ?", (version_id,)
        ).fetchone()
        return self._from_row(row) if row else None

    def all(self) -> List[StrategyVersion]:
        rows = self.db.conn.execute(
            "SELECT * FROM strategy_versions ORDER BY version_id"
        ).fetchall()
        return [self._from_row(r) for r in rows]

    def all_ids(self) -> List[str]:
        rows = self.db.conn.execute(
            "SELECT version_id FROM strategy_versions"
        ).fetchall()
        return [r["version_id"] for r in rows]

    def production(self) -> Optional[StrategyVersion]:
        row = self.db.conn.execute(
            "SELECT * FROM strategy_versions WHERE status = 'PRODUCTION'"
        ).fetchone()
        return self._from_row(row) if row else None

    def set_status(self, version_id: str, status: str) -> None:
        """Change a version's status.

        Promoting to PRODUCTION automatically retires the current production
        version (there can only ever be one). Strategy definitions themselves
        are immutable — only status transitions are allowed.
        """
        if status not in StrategyStatus.ALL:
            raise ValueError("invalid strategy status: {!r}".format(status))
        if self.get(version_id) is None:
            raise ValueError("unknown strategy version: {}".format(version_id))
        if status == StrategyStatus.PRODUCTION:
            current = self.production()
            if current and current.version_id != version_id:
                self.db.conn.execute(
                    "UPDATE strategy_versions SET status = 'RETIRED' "
                    "WHERE version_id = ?",
                    (current.version_id,),
                )
        self.db.conn.execute(
            "UPDATE strategy_versions SET status = ? WHERE version_id = ?",
            (status, version_id),
        )
        self.db.conn.commit()

    @staticmethod
    def _from_row(r) -> StrategyVersion:
        return StrategyVersion(
            version_id=r["version_id"], created_at=_dt(r["created_at"]),
            status=r["status"], description=r["description"],
            parent_version=r["parent_version"], config=json.loads(r["config_json"]),
        )


class ExperimentRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, e: Experiment) -> None:
        self.db.conn.execute(
            "INSERT OR REPLACE INTO experiments "
            "(experiment_id, created_at, hypothesis, baseline_version, "
            " candidate_version, status, results_json, conclusion) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (e.experiment_id, _iso(e.created_at), e.hypothesis,
             e.baseline_version, e.candidate_version, e.status,
             json.dumps(e.results), e.conclusion),
        )
        self.db.conn.commit()

    def get(self, experiment_id: str) -> Optional[Experiment]:
        row = self.db.conn.execute(
            "SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()
        return self._from_row(row) if row else None

    def all(self) -> List[Experiment]:
        rows = self.db.conn.execute(
            "SELECT * FROM experiments ORDER BY experiment_id"
        ).fetchall()
        return [self._from_row(r) for r in rows]

    def all_ids(self) -> List[str]:
        rows = self.db.conn.execute("SELECT experiment_id FROM experiments").fetchall()
        return [r["experiment_id"] for r in rows]

    @staticmethod
    def _from_row(r) -> Experiment:
        return Experiment(
            experiment_id=r["experiment_id"], created_at=_dt(r["created_at"]),
            hypothesis=r["hypothesis"], baseline_version=r["baseline_version"],
            candidate_version=r["candidate_version"], status=r["status"],
            results=json.loads(r["results_json"]), conclusion=r["conclusion"],
        )
