"""Decision model.

Every evaluation of the market by a strategy produces a Decision — including
NO_TRADE decisions. The ``features`` dict must capture the complete state the
strategy saw (indicator values, option-chain metrics, regime, levels, ...) so
any decision can be reconstructed and re-analyzed months later.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


class DecisionStatus:
    SIGNAL = "SIGNAL"
    NO_TRADE = "NO_TRADE"
    ALL = (SIGNAL, NO_TRADE)


class Direction:
    CALL = "CALL"
    PUT = "PUT"
    ALL = (CALL, PUT)


@dataclass
class Decision:
    decision_id: str
    timestamp: datetime
    strategy_version: str
    status: str  # DecisionStatus

    snapshot_id: Optional[int] = None  # FK to stored market snapshot

    # Contract (required when status == SIGNAL)
    direction: Optional[str] = None  # Direction
    expiry: Optional[str] = None
    strike: Optional[float] = None
    option_type: Optional[str] = None  # "CE"/"PE", derived from direction

    # Trade plan (required when status == SIGNAL)
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    max_holding_minutes: Optional[int] = None

    # Why the decision was made
    reason_codes: List[str] = field(default_factory=list)
    features: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        if self.status not in DecisionStatus.ALL:
            raise ValueError("invalid decision status: {!r}".format(self.status))

        if self.status == DecisionStatus.SIGNAL:
            if self.direction not in Direction.ALL:
                raise ValueError(
                    "SIGNAL requires direction CALL or PUT, got {!r}".format(
                        self.direction
                    )
                )
            missing = [
                name
                for name, value in (
                    ("expiry", self.expiry),
                    ("strike", self.strike),
                    ("entry_low", self.entry_low),
                    ("entry_high", self.entry_high),
                    ("stop_loss", self.stop_loss),
                    ("target", self.target),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    "SIGNAL decision missing required fields: {}".format(
                        ", ".join(missing)
                    )
                )
            if self.option_type is None:
                self.option_type = "CE" if self.direction == Direction.CALL else "PE"
            if self.entry_low > self.entry_high:
                raise ValueError("entry_low cannot exceed entry_high")
            # Long-options-only platform: SL below entry, target above.
            if not (self.stop_loss < self.entry_low <= self.entry_high < self.target):
                raise ValueError(
                    "expected stop_loss < entry range < target "
                    "(got SL={}, entry={}-{}, target={})".format(
                        self.stop_loss, self.entry_low, self.entry_high, self.target
                    )
                )
