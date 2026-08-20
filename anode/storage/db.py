"""SQLite database connection and schema management."""

import sqlite3
from pathlib import Path
from typing import Optional, Union

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


class Database:
    """Thin wrapper around a sqlite3 connection.

    Usage:
        db = Database(path)
        db.init_schema()
        ... repositories use db.conn ...
        db.close()
    """

    def __init__(self, path: Union[str, Path] = ":memory:") -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            # WAL + NORMAL keeps commits durable at the application level
            # while avoiding a full fsync per snapshot — the write pattern
            # is thousands of tiny commits (one per snapshot/decision).
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = NORMAL")

    def init_schema(self) -> None:
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        self.conn.executescript(sql)
        self.conn.commit()

    def table_counts(self) -> dict:
        tables = (
            "market_snapshots",
            "option_snapshots",
            "strategy_versions",
            "decisions",
            "paper_trades",
            "experiments",
        )
        counts = {}
        for t in tables:
            try:
                row = self.conn.execute("SELECT COUNT(*) AS n FROM {}".format(t)).fetchone()
                counts[t] = row["n"]
            except sqlite3.OperationalError:
                counts[t] = None  # table missing — schema not initialized
        return counts

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
