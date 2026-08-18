"""Normalized market data models.

Everything downstream of the data layer (analysis, decisions, paper trading,
research) consumes these models — never raw provider responses. A provider
adapter's only job is to produce valid ``MarketSnapshot`` objects.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

VALID_OPTION_TYPES = ("CE", "PE")


@dataclass
class OptionSnapshot:
    """State of a single option contract at one moment in time."""

    expiry: str  # ISO date, e.g. "2026-08-27"
    strike: float
    option_type: str  # "CE" or "PE"

    ltp: float
    bid: Optional[float] = None
    ask: Optional[float] = None

    volume: Optional[int] = None
    open_interest: Optional[int] = None
    oi_change: Optional[int] = None

    iv: Optional[float] = None

    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None

    def __post_init__(self) -> None:
        if self.option_type not in VALID_OPTION_TYPES:
            raise ValueError(
                "option_type must be one of {}, got {!r}".format(
                    VALID_OPTION_TYPES, self.option_type
                )
            )
        if self.strike <= 0:
            raise ValueError("strike must be positive, got {}".format(self.strike))
        if self.ltp < 0:
            raise ValueError("ltp cannot be negative, got {}".format(self.ltp))

    @property
    def spread(self) -> Optional[float]:
        if self.bid is None or self.ask is None:
            return None
        return self.ask - self.bid

    @property
    def spread_pct(self) -> Optional[float]:
        """Spread as a fraction of the mid price (None if not computable)."""
        if self.bid is None or self.ask is None:
            return None
        mid = (self.bid + self.ask) / 2.0
        if mid <= 0:
            return None
        return (self.ask - self.bid) / mid

    @property
    def contract(self) -> str:
        """Human-readable contract identifier, e.g. 'NIFTY 2026-08-27 25000 CE'."""
        strike = int(self.strike) if float(self.strike).is_integer() else self.strike
        return "NIFTY {} {} {}".format(self.expiry, strike, self.option_type)


@dataclass
class MarketSnapshot:
    """Complete normalized view of the market at one moment in time."""

    timestamp: datetime
    nifty_spot: float
    options: List[OptionSnapshot] = field(default_factory=list)

    # Populated by the data layer when known; derivable otherwise.
    atm_strike: Optional[float] = None
    nearest_expiry: Optional[str] = None

    def __post_init__(self) -> None:
        if self.nifty_spot <= 0:
            raise ValueError(
                "nifty_spot must be positive, got {}".format(self.nifty_spot)
            )
        if self.atm_strike is None and self.options:
            self.atm_strike = self.compute_atm_strike()
        if self.nearest_expiry is None and self.options:
            self.nearest_expiry = min(o.expiry for o in self.options)

    def compute_atm_strike(self, strike_step: int = 50) -> float:
        """Nearest listed strike to spot; falls back to rounding by step."""
        strikes = sorted({o.strike for o in self.options})
        if strikes:
            return min(strikes, key=lambda s: abs(s - self.nifty_spot))
        return round(self.nifty_spot / strike_step) * strike_step

    def option(
        self, strike: float, option_type: str, expiry: Optional[str] = None
    ) -> Optional[OptionSnapshot]:
        expiry = expiry or self.nearest_expiry
        for o in self.options:
            if o.strike == strike and o.option_type == option_type and o.expiry == expiry:
                return o
        return None

    def pcr_oi(self, expiry: Optional[str] = None) -> Optional[float]:
        """Put/Call ratio by open interest for one expiry (None if unavailable)."""
        expiry = expiry or self.nearest_expiry
        call_oi = sum(
            o.open_interest or 0
            for o in self.options
            if o.option_type == "CE" and o.expiry == expiry
        )
        put_oi = sum(
            o.open_interest or 0
            for o in self.options
            if o.option_type == "PE" and o.expiry == expiry
        )
        if call_oi <= 0:
            return None
        return put_oi / call_oi
