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


def cmd_analyze(args, cfg) -> int:
    from anode.analysis import TechnicalAnalysisEngine
    from anode.data.synthetic import SyntheticDayProvider

    if args.file:
        provider = CsvReplayProvider(args.file)
        source = args.file
    else:
        provider = SyntheticDayProvider(seed=args.seed)
        source = "synthetic session (seed={}) — demo only, proves nothing".format(
            args.seed
        )

    analysis_cfg = cfg.raw.get("analysis", {})
    engine = TechnicalAnalysisEngine(
        candle_minutes=analysis_cfg.get("candle_minutes", 5),
        iv_change_lookback_minutes=analysis_cfg.get("iv_change_lookback_minutes", 30),
        skew_offset_points=analysis_cfg.get("skew_offset_points", 200.0),
        adx_trend_threshold=analysis_cfg.get("adx_trend_threshold", 25.0),
        high_vol_atr_pct=analysis_cfg.get("high_vol_atr_pct", 0.20),
    )

    print("Analyzing: {}".format(source))
    state = None
    count = 0
    for snap in provider:
        state = engine.update(snap)
        count += 1
        if args.every and count % args.every == 0:
            print(
                "{}  spot={:>9.2f}  trend={:<8} regime={:<16} "
                "rsi={} adx={} atr%={} vwap={} res_dist%={}".format(
                    state.timestamp.strftime("%H:%M"), state.spot, state.trend,
                    state.regime, _fmt(state.rsi14), _fmt(state.adx14),
                    _fmt(state.atr_pct, 3), _fmt(state.vwap),
                    _fmt(state.resistance_distance_pct, 3),
                )
            )
    if state is None:
        print("No snapshots produced.")
        return 1

    print()
    print("Final TechnicalState ({} snapshots, {} candles, warmed_up={}):".format(
        count, state.candles_seen, state.warmed_up))
    for key, value in state.to_dict().items():
        if key == "chain":
            print("  chain:")
            for ck, cv in value.items():
                print("    {:<24} {}".format(ck, cv))
        else:
            print("  {:<26} {}".format(key, value))
    return 0


def _fmt(v, digits: int = 1):
    return "-" if v is None else "{:.{}f}".format(v, digits)


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


def _load_snapshot_list(args):
    """Materialize snapshots from --file / --synthetic-days for reuse."""
    from anode.data.synthetic import SyntheticMultiDayProvider

    if getattr(args, "file", None):
        provider = CsvReplayProvider(args.file)
        label = args.file
    else:
        days = getattr(args, "synthetic_days", 5) or 5
        provider = SyntheticMultiDayProvider(days=days, seed=args.seed)
        label = "synthetic x{} days (seed={}) — demo only, proves nothing".format(
            days, args.seed
        )
    return list(provider), label


def _get_strategy(repo, version_id):
    if version_id == "production":
        s = repo.production()
        if s is None:
            raise ValueError("no PRODUCTION strategy — promote one first")
        return s
    s = repo.get(version_id)
    if s is None:
        raise ValueError("unknown strategy version: {}".format(version_id))
    return s


def _print_metrics(m, indent="  "):
    order = ("signals", "no_trades", "trades", "wins", "losses", "win_rate",
             "gross_pnl", "total_costs", "net_pnl", "profit_factor",
             "expectancy", "avg_win", "avg_loss", "max_drawdown",
             "avg_holding_minutes", "exit_reasons")
    for k in order:
        v = m.get(k)
        if k == "win_rate" and v is not None:
            v = "{:.1%}".format(v)
        print("{}{:<22} {}".format(indent, k, v))
    for group in ("by_direction", "by_regime", "by_day"):
        if m.get(group):
            print("{}{}:".format(indent, group))
            for bucket, s in m[group].items():
                wr = "{:.1%}".format(s["win_rate"]) if s["win_rate"] is not None else "-"
                print("{}  {:<22} trades={:<4} win_rate={:<7} net_pnl={}".format(
                    indent, bucket, s["trades"], wr, s["net_pnl"]))


def cmd_backtest(args, cfg) -> int:
    from anode.research import ListProvider, run_session

    db = _open_db(cfg)
    strategy = _get_strategy(StrategyRepository(db), args.strategy)
    snapshots, label = _load_snapshot_list(args)
    print("Backtest {} over {} ({} snapshots)".format(
        strategy.version_id, label, len(snapshots)))

    store = None
    if args.store:
        store = {
            "snapshots": SnapshotRepository(db),
            "decisions": DecisionRepository(db),
            "trades": TradeRepository(db),
        }
    source = "replay" if getattr(args, "file", None) else "synthetic"
    result = run_session(
        ListProvider(snapshots), strategy, cfg.raw,
        store=store, snapshot_source=source,
    )
    print()
    _print_metrics(result.metrics)
    db.close()
    return 0


def cmd_compare(args, cfg) -> int:
    from anode.research import ListProvider, compare_results, run_session

    db = _open_db(cfg)
    strat_repo = StrategyRepository(db)
    baseline = _get_strategy(strat_repo, args.baseline)
    candidate = _get_strategy(strat_repo, args.candidate)
    snapshots, label = _load_snapshot_list(args)
    print("Comparing {} (baseline) vs {} (candidate) over {}".format(
        baseline.version_id, candidate.version_id, label))

    base_res = run_session(ListProvider(snapshots), baseline, cfg.raw)
    cand_res = run_session(ListProvider(snapshots), candidate, cfg.raw)
    gates = cfg.raw.get("promotion_gates", {})
    report = compare_results(base_res.metrics, cand_res.metrics, gates)

    print()
    print("Verdict: {}".format(report["verdict"]))
    for c in report["checks"]:
        print("  [{}] {:<18} {}".format(c["result"], c["gate"], c["detail"]))
    print()
    print("Baseline metrics:")
    _print_metrics(base_res.metrics)
    print()
    print("Candidate metrics:")
    _print_metrics(cand_res.metrics)

    if args.experiment:
        exp_repo = ExperimentRepository(db)
        exp = exp_repo.get(args.experiment)
        if exp is None:
            print("Unknown experiment: {}".format(args.experiment))
            return 1
        if exp.candidate_version != candidate.version_id:
            print("Experiment {} candidate is {}, not {}".format(
                args.experiment, exp.candidate_version, candidate.version_id))
            return 1
        exp.status = "RUNNING"
        exp.results = {
            "data": label,
            "verdict": report["verdict"],
            "checks": report["checks"],
            "baseline": report["baseline"],
            "candidate": report["candidate"],
        }
        exp_repo.save(exp)
        print()
        print("Results recorded on {} (status RUNNING — conclude it explicitly)".format(
            args.experiment))
    db.close()
    return 0


def cmd_conclude_experiment(args, cfg) -> int:
    db = _open_db(cfg)
    repo = ExperimentRepository(db)
    exp = repo.get(args.id)
    if exp is None:
        print("Unknown experiment: {}".format(args.id))
        return 1
    exp.status = args.status.upper()
    exp.conclusion = args.conclusion
    repo.save(exp)
    print("{} -> {}".format(args.id, exp.status))
    db.close()
    return 0


def cmd_promote(args, cfg) -> int:
    """Promote a candidate to PRODUCTION — only via an ACCEPTED experiment."""
    db = _open_db(cfg)
    strat_repo = StrategyRepository(db)
    exp = ExperimentRepository(db).get(args.experiment)
    if exp is None:
        print("Unknown experiment: {}".format(args.experiment))
        return 1
    if exp.status != "ACCEPTED":
        print("Refusing: experiment {} status is {}, not ACCEPTED".format(
            args.experiment, exp.status))
        return 1
    if exp.candidate_version != args.candidate:
        print("Refusing: experiment {} candidate is {}, not {}".format(
            args.experiment, exp.candidate_version, args.candidate))
        return 1
    verdict = (exp.results or {}).get("verdict")
    if verdict != "PASS":
        print("Refusing: experiment {} recorded verdict is {} (need PASS)".format(
            args.experiment, verdict))
        return 1
    current = strat_repo.production()
    strat_repo.set_status(args.candidate, "PRODUCTION")
    print("{} promoted to PRODUCTION{} (via {})".format(
        args.candidate,
        " (replacing {})".format(current.version_id) if current else "",
        args.experiment,
    ))
    db.close()
    return 0


def cmd_report(args, cfg) -> int:
    db = _open_db(cfg)
    day = args.date  # YYYY-MM-DD
    like = "{}%".format(day)
    conn = db.conn
    # Synthetic rows exercise the pipeline only; they must never blend into
    # research reporting (AGENTS.md rule 6).
    src_cond = "" if args.include_synthetic else " AND m.source != 'synthetic'"
    dec = conn.execute(
        "SELECT d.status, COUNT(*) AS n FROM decisions d "
        "JOIN market_snapshots m ON d.snapshot_id = m.snapshot_id "
        "WHERE d.timestamp LIKE ?" + src_cond + " GROUP BY d.status", (like,),
    ).fetchall()
    dec_counts = {r["status"]: r["n"] for r in dec}
    trades = conn.execute(
        "SELECT t.* FROM paper_trades t "
        "JOIN decisions d ON t.decision_id = d.decision_id "
        "JOIN market_snapshots m ON d.snapshot_id = m.snapshot_id "
        "WHERE t.entry_time LIKE ?" + src_cond + " ORDER BY t.entry_time",
        (like,),
    ).fetchall()
    prod = StrategyRepository(db).production()

    print("ANODE daily report — {}{}".format(
        day, " (synthetic included)" if args.include_synthetic else ""))
    print("Production strategy: {}".format(prod.version_id if prod else "(none)"))
    print("Decisions: {} signals, {} no-trade".format(
        dec_counts.get("SIGNAL", 0), dec_counts.get("NO_TRADE", 0)))
    if not trades:
        print("Trades: none")
    else:
        net = sum(r["net_pnl"] or 0.0 for r in trades if r["status"] == "CLOSED")
        wins = sum(1 for r in trades if (r["net_pnl"] or 0) > 0)
        closed = [r for r in trades if r["status"] == "CLOSED"]
        print("Trades: {} ({} closed, {} wins, net P&L {:.2f})".format(
            len(trades), len(closed), wins, net))
        for r in trades:
            if r["status"] == "CLOSED":
                print("  {}  {} -> {} ({})  net={:.2f} [{}]".format(
                    r["trade_id"], r["entry_price"], r["exit_price"],
                    r["exit_reason"], r["net_pnl"], r["result"]))
            else:
                print("  {}  entry={}  OPEN".format(r["trade_id"], r["entry_price"]))
    db.close()
    return 0


def cmd_failures(args, cfg) -> int:
    from anode.research import failure_analysis

    db = _open_db(cfg)
    trade_repo = TradeRepository(db)
    dec_repo = DecisionRepository(db)
    trades = trade_repo.recent(limit=args.limit)
    if not args.include_synthetic:
        synthetic_ids = {
            r["decision_id"] for r in db.conn.execute(
                "SELECT d.decision_id FROM decisions d "
                "JOIN market_snapshots m ON d.snapshot_id = m.snapshot_id "
                "WHERE m.source = 'synthetic'"
            ).fetchall()
        }
        trades = [t for t in trades if t.decision_id not in synthetic_ids]
    decisions = {}
    for t in trades:
        d = dec_repo.get(t.decision_id)
        if d:
            decisions[d.decision_id] = d
    report = failure_analysis(trades, decisions)

    print("Failure analysis over {} closed trades (overall win rate: {})".format(
        report["trades_analyzed"],
        "{:.1%}".format(report["overall_win_rate"])
        if report["overall_win_rate"] is not None else "-",
    ))
    for dim, stats in report["dimensions"].items():
        print("\n  {}:".format(dim))
        for bucket, s in stats.items():
            wr = "{:.1%}".format(s["win_rate"]) if s["win_rate"] is not None else "-"
            flag = "" if s["significant"] else "  (low sample)"
            print("    {:<14} trades={:<4} win_rate={:<7} net_pnl={}{}".format(
                bucket, s["trades"], wr, s["net_pnl"], flag))
    if report["weak_spots"]:
        print("\n  WEAK SPOTS (significant, >=10pp below overall):")
        for w in report["weak_spots"]:
            print("    {}={}  trades={}  win_rate={:.1%}  ({:+.1%} vs overall)".format(
                w["dimension"], w["bucket"], w["trades"],
                w["win_rate"], w["vs_overall"]))
    db.close()
    return 0


def cmd_run(args, cfg) -> int:
    """Run a full paper-trading session (live NSE, synthetic, or file)."""
    from anode.research import run_session

    db = _open_db(cfg)
    strategy = _get_strategy(StrategyRepository(db), args.strategy)

    if args.source == "nse":
        from anode.data.live import NseLiveProvider

        provider = NseLiveProvider(
            interval_seconds=args.interval,
            duration_minutes=args.duration,
            session_end=cfg.market.get("session_end", "15:30"),
        )
        source = "live"
        print("LIVE PAPER SESSION (NSE feed, poll every {}s) — strategy {}".format(
            args.interval, strategy.version_id))
        print("Paper trading only. No orders are or can be placed.")
    elif args.source == "file":
        if not args.file:
            print("--file is required with --source file")
            return 1
        provider = CsvReplayProvider(args.file)
        source = "replay"
    else:
        from anode.data.synthetic import SyntheticDayProvider

        provider = SyntheticDayProvider(seed=args.seed)
        source = "synthetic"
        print("SYNTHETIC session (seed={}) — demo only, proves nothing".format(args.seed))

    store = None
    if not args.no_store:
        store = {
            "snapshots": SnapshotRepository(db),
            "decisions": DecisionRepository(db),
            "trades": TradeRepository(db),
        }

    # Rebuild indicator state from today's stored snapshots so a restart
    # mid-session does not restart the (candle-based) warmup from zero.
    seeds = None
    if source == "live" and store is not None:
        from datetime import date

        seeds = store["snapshots"].for_day(date.today().isoformat(), "live")
        if seeds:
            print("Seeding warmup from {} stored snapshots (today, source=live)".format(
                len(seeds)))

    result = run_session(provider, strategy, cfg.raw, store=store,
                         snapshot_source=source, seed_snapshots=seeds)
    print()
    print("Session complete: {} snapshots, {} signals, {} trades closed".format(
        result.snapshots_processed, len(result.signals), len(result.trades)))
    _print_metrics(result.metrics)
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

    sp = sub.add_parser(
        "analyze",
        help="run technical analysis over a replay file (or a synthetic demo session)",
    )
    sp.add_argument("--file", default=None, help="replay CSV (omit for synthetic demo data)")
    sp.add_argument("--seed", type=int, default=42, help="synthetic data seed")
    sp.add_argument("--every", type=int, default=30,
                    help="print a progress line every N snapshots (0 = final state only)")

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

    sp = sub.add_parser("backtest", help="backtest a strategy over historical data")
    sp.add_argument("--strategy", required=True, help="STRAT-NNN or 'production'")
    sp.add_argument("--file", default=None, help="replay CSV (omit for synthetic)")
    sp.add_argument("--synthetic-days", type=int, default=5)
    sp.add_argument("--seed", type=int, default=42)
    sp.add_argument("--store", action="store_true",
                    help="persist snapshots/decisions/trades to the database")

    sp = sub.add_parser(
        "compare", help="run baseline vs candidate on identical data with promotion gates"
    )
    sp.add_argument("--baseline", required=True)
    sp.add_argument("--candidate", required=True)
    sp.add_argument("--file", default=None, help="replay CSV (omit for synthetic)")
    sp.add_argument("--synthetic-days", type=int, default=5)
    sp.add_argument("--seed", type=int, default=42)
    sp.add_argument("--experiment", default=None,
                    help="EXP-NNN to record the results on")

    sp = sub.add_parser("conclude-experiment", help="accept or reject an experiment")
    sp.add_argument("--id", required=True)
    sp.add_argument("--status", required=True, choices=["ACCEPTED", "REJECTED",
                                                        "accepted", "rejected"])
    sp.add_argument("--conclusion", required=True)

    sp = sub.add_parser(
        "promote",
        help="promote a candidate to PRODUCTION (requires an ACCEPTED experiment with a PASS verdict)",
    )
    sp.add_argument("--candidate", required=True)
    sp.add_argument("--experiment", required=True)

    sp = sub.add_parser("report", help="daily summary report")
    sp.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                    help="YYYY-MM-DD (default today)")
    sp.add_argument("--include-synthetic", action="store_true",
                    help="include synthetic-sourced rows (pipeline debugging only)")

    sp = sub.add_parser("failures", help="failure analysis over recorded trades")
    sp.add_argument("--limit", type=int, default=500,
                    help="analyze the most recent N trades")
    sp.add_argument("--include-synthetic", action="store_true",
                    help="include synthetic-sourced trades (pipeline debugging only)")

    sp = sub.add_parser(
        "run", help="run a paper-trading session (live NSE / synthetic / file)"
    )
    sp.add_argument("--source", choices=["nse", "synthetic", "file"], required=True)
    sp.add_argument("--strategy", default="production",
                    help="STRAT-NNN or 'production' (default)")
    sp.add_argument("--interval", type=int, default=60,
                    help="live poll interval in seconds")
    sp.add_argument("--duration", type=int, default=None,
                    help="stop after N minutes (live only; default: session end)")
    sp.add_argument("--file", default=None, help="replay CSV for --source file")
    sp.add_argument("--seed", type=int, default=42, help="seed for --source synthetic")
    sp.add_argument("--no-store", action="store_true",
                    help="do not persist to the database (dry run)")
    return p


COMMANDS = {
    "init-db": cmd_init_db,
    "status": cmd_status,
    "replay": cmd_replay,
    "analyze": cmd_analyze,
    "snapshots": cmd_snapshots,
    "decisions": cmd_decisions,
    "trades": cmd_trades,
    "strategies": cmd_strategies,
    "new-strategy": cmd_new_strategy,
    "set-status": cmd_set_status,
    "new-experiment": cmd_new_experiment,
    "experiments": cmd_experiments,
    "backtest": cmd_backtest,
    "compare": cmd_compare,
    "conclude-experiment": cmd_conclude_experiment,
    "promote": cmd_promote,
    "report": cmd_report,
    "failures": cmd_failures,
    "run": cmd_run,
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
