"""Session runner / backtester.

``run_session`` drives the complete pipeline over any MarketDataProvider:

    snapshot -> TechnicalAnalysisEngine -> DecisionEngine -> PaperTradingEngine

The same function serves historical backtesting (CSV replay, synthetic data)
and live paper trading (a polling provider) — the only difference is where
snapshots come from and whether results are persisted to the database.

Chronological integrity: exits are processed BEFORE new entries on each
snapshot, and the decision engine only consults completed candles, so no
step can ever see the future.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Optional

from anode.analysis import TechnicalAnalysisEngine
from anode.data.provider import MarketDataProvider
from anode.decision import DecisionEngine
from anode.models import Decision, MarketSnapshot, PaperTrade, StrategyVersion
from anode.research.metrics import compute_metrics
from anode.trading import PaperTradingEngine

log = logging.getLogger(__name__)


class ListProvider(MarketDataProvider):
    """Provider over an in-memory snapshot list (for reusing loaded data)."""

    def __init__(self, snapshots: List[MarketSnapshot]) -> None:
        self._snapshots = snapshots

    def snapshots(self) -> Iterator[MarketSnapshot]:
        return iter(self._snapshots)


@dataclass
class BacktestResult:
    strategy_version: str
    snapshots_processed: int = 0
    decisions: List[Decision] = field(default_factory=list)
    trades: List[PaperTrade] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def signals(self) -> List[Decision]:
        return [d for d in self.decisions if d.status == "SIGNAL"]


def run_session(
    provider: Iterable[MarketSnapshot],
    strategy: StrategyVersion,
    app_config: Optional[Dict[str, Any]] = None,
    store: Optional[Dict[str, Any]] = None,
    snapshot_source: str = "replay",
    seed_snapshots: Optional[Iterable[MarketSnapshot]] = None,
) -> BacktestResult:
    """Run the full pipeline over a snapshot stream.

    app_config: the raw config dict (config/config.json contents).
    store: optional dict of repositories to persist everything:
        {"snapshots": SnapshotRepository, "decisions": DecisionRepository,
         "trades": TradeRepository}
    seed_snapshots: already-stored snapshots replayed through the technical
        analysis engine ONLY, so indicator warmup survives an intraday
        restart. Seeds are never stored, never produce decisions or trades.
    """
    app_config = app_config or {}
    analysis_cfg = app_config.get("analysis", {})
    market_cfg = app_config.get("market", {})
    paper_cfg = app_config.get("paper_trading", {})
    costs_cfg = app_config.get("costs", {})

    ta = TechnicalAnalysisEngine(
        candle_minutes=analysis_cfg.get("candle_minutes", 5),
        iv_change_lookback_minutes=analysis_cfg.get("iv_change_lookback_minutes", 30),
        skew_offset_points=analysis_cfg.get("skew_offset_points", 200.0),
        adx_trend_threshold=analysis_cfg.get("adx_trend_threshold", 25.0),
        high_vol_atr_pct=analysis_cfg.get("high_vol_atr_pct", 0.20),
    )
    de = DecisionEngine(
        strategy,
        seq_base_fn=(store["decisions"].count_for_day if store else None),
    )
    pt = PaperTradingEngine(
        lot_size=market_cfg.get("lot_size", 75),
        slippage_bps=costs_cfg.get("slippage_bps", 5),
        costs_config=costs_cfg,
        force_square_off=paper_cfg.get("force_square_off", "15:20"),
        seq_base_fn=(store["trades"].count_for_day if store else None),
    )
    quantity_lots = de.config["trade_plan"].get(
        "quantity_lots", paper_cfg.get("default_quantity_lots", 1)
    )
    max_open = de.config["engine"].get("max_open_positions", 1)

    seeded = 0
    for seed in seed_snapshots or []:
        ta.update(seed)
        seeded += 1
    if seeded:
        log.info("seeded technical state from %d stored snapshots", seeded)

    result = BacktestResult(strategy_version=strategy.version_id)
    last_snapshot: Optional[MarketSnapshot] = None

    for snap in provider:
        last_snapshot = snap
        result.snapshots_processed += 1

        snapshot_id = None
        if store:
            snapshot_id = store["snapshots"].save(snap, source=snapshot_source)

        state = ta.update(snap)

        # 1) manage exits first — an exit and an entry never share a tick
        closed = pt.on_snapshot(snap)
        if store:
            for t in closed:
                store["trades"].save(t)

        # 2) consult the strategy only when a new position could be taken
        if pt.open_count >= max_open:
            continue
        decision = de.evaluate(state, snap, snapshot_id=snapshot_id)
        result.decisions.append(decision)
        if store:
            store["decisions"].save(decision)

        # 3) attempt the fill on the same snapshot's quotes
        if decision.status == "SIGNAL":
            trade = pt.on_decision(decision, snap, quantity_lots=quantity_lots)
            if trade is not None and store:
                store["trades"].save(trade)

    # end of data: square off anything still open at the last known prices
    if last_snapshot is not None and pt.open_count:
        for t in pt.force_close_all(last_snapshot):
            if store:
                store["trades"].save(t)

    result.trades = list(pt.closed_trades)
    decisions_by_id = {d.decision_id: d for d in result.decisions}
    n_signals = len(result.signals)
    result.metrics = compute_metrics(
        result.trades,
        decisions=decisions_by_id,
        signals=n_signals,
        no_trades=len(result.decisions) - n_signals,
    )
    log.info(
        "session complete: strategy=%s snapshots=%d signals=%d trades=%d net_pnl=%s",
        strategy.version_id, result.snapshots_processed,
        n_signals, len(result.trades), result.metrics.get("net_pnl"),
    )
    return result
