"""Paper trading engine.

Simulates broker execution for SIGNAL decisions with conservative fills:

- Entry: filled only if the option's ask (falling back to LTP) lies inside
  the decision's entry band; the fill price is ask PLUS slippage. No fill →
  the signal is recorded but no trade opens (that itself is research data).
- Monitoring: every snapshot, open positions are marked against the option's
  bid (falling back to LTP). Exit priority: STOP_LOSS, TARGET, TIME_EXIT,
  EOD square-off. Exits fill at the reference price MINUS slippage.
- Costs: full round-trip transaction costs applied at close.

Slippage always hurts (pay more on entry, receive less on exit), so paper
results can only understate live performance, never flatter it.
"""

import logging
from datetime import datetime, time as dtime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from anode import ids
from anode.models import (
    Decision,
    ExitReason,
    MarketSnapshot,
    PaperTrade,
    TradeStatus,
)
from anode.trading.costs import round_trip_costs

log = logging.getLogger(__name__)


class PaperTradingEngine:
    def __init__(
        self,
        lot_size: int = 75,
        slippage_bps: float = 5.0,
        costs_config: Optional[Dict[str, Any]] = None,
        force_square_off: str = "15:20",
        seq_base_fn: Optional[Callable[[str], int]] = None,
    ) -> None:
        # seq_base_fn("YYYYMMDD") -> already-used trade count for that day,
        # so IDs continue across separate runs instead of colliding.
        self._seq_base_fn = seq_base_fn
        self.lot_size = lot_size
        self.slippage = slippage_bps / 10_000.0
        self.costs_config = costs_config or {}
        h, m = force_square_off.split(":")
        self.square_off_time = dtime(int(h), int(m))

        # open positions: (trade, decision)
        self.open_positions: List[Tuple[PaperTrade, Decision]] = []
        self.closed_trades: List[PaperTrade] = []
        self._day: Optional[str] = None
        self._day_seq = 0

    @property
    def open_count(self) -> int:
        return len(self.open_positions)

    # ----------------------------------------------------------------- entry

    def on_decision(
        self, decision: Decision, snapshot: MarketSnapshot, quantity_lots: int = 1
    ) -> Optional[PaperTrade]:
        """Attempt to fill a SIGNAL decision at the current snapshot."""
        if decision.status != "SIGNAL":
            return None
        contract = snapshot.option(
            decision.strike, decision.option_type, decision.expiry
        )
        if contract is None:
            log.info("%s: contract not in snapshot — no fill", decision.decision_id)
            return None
        ref = contract.ask if contract.ask is not None else contract.ltp
        if ref is None or not (decision.entry_low <= ref <= decision.entry_high):
            log.info(
                "%s: price %s outside entry band %s-%s — no fill",
                decision.decision_id, ref, decision.entry_low, decision.entry_high,
            )
            return None

        fill = round(ref * (1.0 + self.slippage), 2)
        trade = PaperTrade(
            trade_id=self._next_id(snapshot.timestamp),
            decision_id=decision.decision_id,
            status=TradeStatus.OPEN,
            entry_time=snapshot.timestamp,
            entry_price=fill,
            quantity=quantity_lots * self.lot_size,
        )
        self.open_positions.append((trade, decision))
        log.info(
            "OPEN %s %s %s @ %.2f x%d (SL %.2f, target %.2f)",
            trade.trade_id, decision.direction, decision.strike,
            fill, trade.quantity, decision.stop_loss, decision.target,
        )
        return trade

    # ------------------------------------------------------------ monitoring

    def on_snapshot(self, snapshot: MarketSnapshot) -> List[PaperTrade]:
        """Mark open positions against the snapshot; close any that exit."""
        closed: List[PaperTrade] = []
        still_open: List[Tuple[PaperTrade, Decision]] = []

        for trade, decision in self.open_positions:
            contract = snapshot.option(
                decision.strike, decision.option_type, decision.expiry
            )
            if contract is None:
                still_open.append((trade, decision))
                continue
            ref = contract.bid if contract.bid is not None else contract.ltp
            if ref is None:
                still_open.append((trade, decision))
                continue

            reason = self._exit_reason(trade, decision, ref, snapshot.timestamp)
            if reason is None:
                still_open.append((trade, decision))
                continue

            exit_price = round(max(0.05, ref * (1.0 - self.slippage)), 2)
            costs = round_trip_costs(
                trade.entry_price, exit_price, trade.quantity, self.costs_config
            )
            trade.close(snapshot.timestamp, exit_price, reason, costs=costs)
            self.closed_trades.append(trade)
            closed.append(trade)
            log.info(
                "CLOSE %s @ %.2f (%s) net_pnl=%.2f",
                trade.trade_id, exit_price, reason, trade.net_pnl,
            )

        self.open_positions = still_open
        return closed

    def _exit_reason(
        self, trade: PaperTrade, decision: Decision, ref: float, ts: datetime
    ) -> Optional[str]:
        if ref <= decision.stop_loss:
            return ExitReason.STOP_LOSS
        if ref >= decision.target:
            return ExitReason.TARGET
        if decision.max_holding_minutes is not None and ts - trade.entry_time >= timedelta(
            minutes=decision.max_holding_minutes
        ):
            return ExitReason.TIME_EXIT
        if ts.time() >= self.square_off_time:
            return ExitReason.EOD
        return None

    # -------------------------------------------------------------- lifecycle

    def force_close_all(
        self, snapshot: MarketSnapshot, reason: str = ExitReason.EOD
    ) -> List[PaperTrade]:
        """Close every open position at the snapshot's prices (end of data)."""
        closed: List[PaperTrade] = []
        for trade, decision in list(self.open_positions):
            contract = snapshot.option(
                decision.strike, decision.option_type, decision.expiry
            )
            ref = None
            if contract is not None:
                ref = contract.bid if contract.bid is not None else contract.ltp
            if ref is None:
                ref = trade.entry_price  # no quote: flat close, costs still apply
            exit_price = round(max(0.05, ref * (1.0 - self.slippage)), 2)
            costs = round_trip_costs(
                trade.entry_price, exit_price, trade.quantity, self.costs_config
            )
            trade.close(snapshot.timestamp, exit_price, reason, costs=costs)
            self.closed_trades.append(trade)
            closed.append(trade)
        self.open_positions = []
        return closed

    def _next_id(self, ts: datetime) -> str:
        day = ts.strftime("%Y%m%d")
        if day != self._day:
            self._day = day
            self._day_seq = self._seq_base_fn(day) if self._seq_base_fn else 0
        self._day_seq += 1
        return ids.trade_id(ts, self._day_seq)
