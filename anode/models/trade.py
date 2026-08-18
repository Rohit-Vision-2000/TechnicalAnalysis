"""Paper trade model.

A PaperTrade is the simulated execution of a SIGNAL decision: entry fill,
monitoring, and exit via stop loss / target / time limit / end of day.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class TradeStatus:
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    ALL = (OPEN, CLOSED)


class ExitReason:
    TARGET = "TARGET"
    STOP_LOSS = "STOP_LOSS"
    TIME_EXIT = "TIME_EXIT"
    EOD = "EOD"
    MANUAL = "MANUAL"
    ALL = (TARGET, STOP_LOSS, TIME_EXIT, EOD, MANUAL)


class TradeResult:
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    ALL = (WIN, LOSS, BREAKEVEN)


@dataclass
class PaperTrade:
    trade_id: str
    decision_id: str
    status: str  # TradeStatus

    entry_time: datetime
    entry_price: float
    quantity: int  # units (lots * lot_size)

    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # ExitReason

    gross_pnl: Optional[float] = None
    costs: Optional[float] = None
    net_pnl: Optional[float] = None
    result: Optional[str] = None  # TradeResult

    def __post_init__(self) -> None:
        if self.status not in TradeStatus.ALL:
            raise ValueError("invalid trade status: {!r}".format(self.status))
        if self.entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.status == TradeStatus.CLOSED:
            missing = [
                name
                for name, value in (
                    ("exit_time", self.exit_time),
                    ("exit_price", self.exit_price),
                    ("exit_reason", self.exit_reason),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    "CLOSED trade missing: {}".format(", ".join(missing))
                )
            if self.exit_reason not in ExitReason.ALL:
                raise ValueError("invalid exit reason: {!r}".format(self.exit_reason))

    def close(
        self,
        exit_time: datetime,
        exit_price: float,
        exit_reason: str,
        costs: float = 0.0,
    ) -> None:
        """Close the trade and compute P&L (long options only)."""
        if self.status == TradeStatus.CLOSED:
            raise ValueError("trade {} already closed".format(self.trade_id))
        if exit_reason not in ExitReason.ALL:
            raise ValueError("invalid exit reason: {!r}".format(exit_reason))
        self.exit_time = exit_time
        self.exit_price = exit_price
        self.exit_reason = exit_reason
        self.gross_pnl = (exit_price - self.entry_price) * self.quantity
        self.costs = costs
        self.net_pnl = self.gross_pnl - costs
        if self.net_pnl > 0:
            self.result = TradeResult.WIN
        elif self.net_pnl < 0:
            self.result = TradeResult.LOSS
        else:
            self.result = TradeResult.BREAKEVEN
        self.status = TradeStatus.CLOSED
