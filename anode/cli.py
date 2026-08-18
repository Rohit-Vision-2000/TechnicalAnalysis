"""ANODE command-line interface.

Run from the repository root:  python -m anode <command> [options]
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from anode import __version__, ids
from anode.config import REPO_ROOT, load_config
from anode.data.replay import CsvReplayProvider
from anode.logging_setup import setup_logging
from anode.models import Experiment, StrategyStatus, StrategyVersion
from anode.storage import (
    Database,
    DecisionRepository,
    ExperimentRepository,
    SnapshotRepository,
    StrategyRepository,
    TradeRepository,
)

log = logging.getLogger("anode.cli")


def _open_db(cfg, must_exist: bool = True) -> Database:
    path = cfg.db_path
    if must_exist and not Path(path).exists():
        print("Database not found at {} — run: python -m anode init-db".format(path))
        raise SystemExit(1)
    return Database(path)


def cmd_init_db(args, cfg) -> int:
    db = Database(cfg.db_path)
    db.init_schema()
    print("Database initialized at {}".format(cfg.db_path))
    db.close()
    return 0


def cmd_status(args, cfg) -> int:
    db = _open_db(cfg)
    counts = db.table_counts()
    print("ANODE v{}".format(__version__))
    print("Database: {}".format(cfg.db_path))
    print()
    for table, n in counts.items():
        print("  {:<20} {}".format(table, "NOT INITIALIZED" if n is None else n))
    prod = StrategyRepository(db).production()
    print()
    print("Production strategy: {}".format(prod.version_id if prod else "(none)"))
    db.close()
    return 0


def cmd_replay(args, cfg) -> int:
    provider = CsvReplayProvider(args.file)
    db = _open_db(cfg) if args.store else None
    repo = SnapshotRepository(db) if db else None

    count = 0
    for snap in provider:
        count += 1
        if repo:
            sid = repo.save(snap, source="replay")
            log.info(
                "stored snapshot %s: %s spot=%.2f options=%d",
                sid, snap.timestamp, snap.nifty_spot, len(snap.options),
            )
        else:
            print(
                "{}  spot={:.2f}  atm={}  expiry={}  options={}".format(
                    snap.timestamp, snap.nifty_spot, snap.atm_strike,
                    snap.nearest_expiry, len(snap.options),
                )
            )
    print(
        "Replayed {} snapshot(s) from {}{}".format(
            count, args.file, " (stored)" if args.store else ""
        )
    )
    if db:
        db.close()
    return 0


def cmd_snapshots(args, cfg) -> int:
    db = _open_db(cfg)
    rows = SnapshotRepository(db).recent(limit=args.limit)
    if not rows:
        print("No snapshots stored.")
    for r in rows:
        print(
            "#{:<6} {}  spot={:<10} atm={:<8} expiry={}  options={}  [{}]".format(
                r["snapshot_id"], r["timestamp"], r["nifty_spot"],
                r["atm_strike"], r["nearest_expiry"], r["option_count"], r["source"],
            )
        )
    db.close()
    return 0


def cmd_decisions(args, cfg) -> int:
    db = _open_db(cfg)
    decisions = DecisionRepository(db).recent(limit=args.limit, status=args.status)
    if not decisions:
        print("No decisions recorded.")
    for d in decisions:
        if d.status == "SIGNAL":
            print(
                "{}  {}  {} {} {} {}  entry={}-{} SL={} target={}  [{}]".format(
                    d.decision_id, d.timestamp, d.status, d.direction,
                    d.strike, d.expiry, d.entry_low, d.entry_high,
                    d.stop_loss, d.target, d.strategy_version,
                )
            )
        else:
            print(
                "{}  {}  NO_TRADE  reasons={}  [{}]".format(
                    d.decision_id, d.timestamp,
                    ",".join(d.reason_codes) or "-", d.strategy_version,
                )
            )
    db.close()
    return 0


def cmd_trades(args, cfg) -> int:
    db = _open_db(cfg)
    trades = TradeRepository(db).recent(limit=args.limit)
    if not trades:
        print("No paper trades recorded.")
    for t in trades:
        if t.status == "CLOSED":
            print(
                "{}  {}  entry={} exit={} ({})  net_pnl={:.2f}  {}".format(
                    t.trade_id, t.entry_time, t.entry_price, t.exit_price,
                    t.exit_reason, t.net_pnl, t.result,
                )
            )
        else:
            print(
                "{}  {}  entry={} qty={}  OPEN".format(
                    t.trade_id, t.entry_time, t.entry_price, t.quantity,
                )
            )
    db.close()
    return 0


def cmd_strategies(args, cfg) -> int:
    db = _open_db(cfg)
    versions = StrategyRepository(db).all()
    if not versions:
        print("No strategy versions. Create one: python -m anode new-strategy --description ...")
    for s in versions:
        parent = " parent={}".format(s.parent_version) if s.parent_version else ""
        print(
            "{}  {:<10} {}{}  — {}".format(
                s.version_id, s.status, s.created_at, parent, s.description,
            )
        )
    db.close()
    return 0


def cmd_new_strategy(args, cfg) -> int:
    db = _open_db(cfg)
    repo = StrategyRepository(db)
    version_id = ids.next_strategy_id(repo.all_ids())
    config = json.loads(args.params) if args.params else {}
    strategy = StrategyVersion(
        version_id=version_id,
        created_at=datetime.now(),
        status=StrategyStatus.DRAFT,
        description=args.description,
        parent_version=args.parent,
        config=config,
    )
    repo.save(strategy)

    # Mirror the version on disk for auditability.
    sdir = REPO_ROOT / "strategies" / version_id
    sdir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version_id": version_id,
        "created_at": strategy.created_at.isoformat(sep=" "),
        "status": strategy.status,
        "description": strategy.description,
        "parent_version": strategy.parent_version,
        "config": config,
    }
    (sdir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print("Created {} (DRAFT) at strategies/{}/".format(version_id, version_id))
    db.close()
    return 0


def cmd_set_status(args, cfg) -> int:
    db = _open_db(cfg)
    StrategyRepository(db).set_status(args.version, args.status.upper())
    print("{} -> {}".format(args.version, args.status.upper()))
    db.close()
    return 0


def cmd_new_experiment(args, cfg) -> int:
    db = _open_db(cfg)
    strat_repo = StrategyRepository(db)
    if strat_repo.get(args.baseline) is None:
        print("Unknown baseline strategy: {}".format(args.baseline))
        return 1
    if args.candidate and strat_repo.get(args.candidate) is None:
        print("Unknown candidate strategy: {}".format(args.candidate))
        return 1
    repo = ExperimentRepository(db)
    experiment = Experiment(
        experiment_id=ids.next_experiment_id(repo.all_ids()),
        created_at=datetime.now(),
        hypothesis=args.hypothesis,
        baseline_version=args.baseline,
        candidate_version=args.candidate,
    )
    repo.save(experiment)
    print("Created {} (PLANNED)".format(experiment.experiment_id))
    db.close()
    return 0


def cmd_experiments(args, cfg) -> int:
    db = _open_db(cfg)
    experiments = ExperimentRepository(db).all()
    if not experiments:
        print("No experiments recorded.")
    for e in experiments:
        print(
            "{}  {:<9} baseline={} candidate={}  — {}".format(
                e.experiment_id, e.status, e.baseline_version,
                e.candidate_version or "-", e.hypothesis,
            )
        )
    db.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="anode",
        description="ANODE — Autonomous NIFTY Options Decision Engine (paper trading only)",
    )
    p.add_argument("--config", help="path to config.json", default=None)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create the database schema")
    sub.add_parser("status", help="show system status")

    sp = sub.add_parser("replay", help="replay market data from a CSV file")
    sp.add_argument("--file", required=True, help="path to replay CSV")
    sp.add_argument("--store", action="store_true", help="store snapshots in the database")

    sp = sub.add_parser("snapshots", help="list stored market snapshots")
    sp.add_argument("--limit", type=int, default=20)

    sp = sub.add_parser("decisions", help="list recorded decisions")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--status", choices=["SIGNAL", "NO_TRADE"], default=None)

    sp = sub.add_parser("trades", help="list paper trades")
    sp.add_argument("--limit", type=int, default=20)

    sub.add_parser("strategies", help="list strategy versions")

    sp = sub.add_parser("new-strategy", help="create a new strategy version (DRAFT)")
    sp.add_argument("--description", required=True)
    sp.add_argument("--parent", default=None, help="parent strategy version id")
    sp.add_argument("--params", default=None, help="strategy parameters as a JSON string")

    sp = sub.add_parser("set-status", help="change a strategy version's status")
    sp.add_argument("--version", required=True)
    sp.add_argument(
        "--status", required=True,
        choices=[s.lower() for s in StrategyStatus.ALL] + list(StrategyStatus.ALL),
    )

    sp = sub.add_parser("new-experiment", help="create a new experiment (PLANNED)")
    sp.add_argument("--hypothesis", required=True)
    sp.add_argument("--baseline", required=True)
    sp.add_argument("--candidate", default=None)

    sub.add_parser("experiments", help="list experiments")
    return p


COMMANDS = {
    "init-db": cmd_init_db,
    "status": cmd_status,
    "replay": cmd_replay,
    "snapshots": cmd_snapshots,
    "decisions": cmd_decisions,
    "trades": cmd_trades,
    "strategies": cmd_strategies,
    "new-strategy": cmd_new_strategy,
    "set-status": cmd_set_status,
    "new-experiment": cmd_new_experiment,
    "experiments": cmd_experiments,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config)
    setup_logging(cfg.log_level, cfg.log_file)
    try:
        return COMMANDS[args.command](args, cfg)
    except (ValueError, FileNotFoundError) as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
