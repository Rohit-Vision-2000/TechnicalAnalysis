"""TechnicalState — the complete analysis output for one moment in time.

This is the object the decision engine (Phase 3) consumes, and — serialized
via ``to_dict()`` — the ``features`` payload stored with every Decision so
that any decision can be reconstructed and re-analyzed later. Fields are None
during indicator warm-up; consumers must treat None as "unknown", never as 0.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


class Trend:
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"
    ALL = (BULLISH, BEARISH, NEUTRAL, UNKNOWN)


@dataclass
class TechnicalState:
    timestamp: datetime
    spot: float

    # Trend / moving averages (on the working candle timeframe)
    trend: str = Trend.UNKNOWN
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    ema20_above_ema50: Optional[bool] = None

    # Momentum
    rsi14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    macd_bullish: Optional[bool] = None  # macd line above signal line
    adx14: Optional[float] = None
    plus_di: Optional[float] = None
    minus_di: Optional[float] = None

    # Volatility
    atr14: Optional[float] = None
    atr_pct: Optional[float] = None  # atr / spot * 100

    # VWAP (true VWAP needs volume; index data falls back to a
    # time-weighted session average and sets vwap_is_proxy)
    vwap: Optional[float] = None
    vwap_is_proxy: bool = True
    price_above_vwap: Optional[bool] = None

    # Session structure
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    prev_day_high: Optional[float] = None
    prev_day_low: Optional[float] = None

    # Support / resistance
    supports: List[float] = field(default_factory=list)
    resistances: List[float] = field(default_factory=list)
    nearest_support: Optional[float] = None
    nearest_resistance: Optional[float] = None
    support_distance_pct: Optional[float] = None
    resistance_distance_pct: Optional[float] = None

    # Regime
    regime: str = "UNKNOWN"

    # Option chain (nearest expiry)
    chain: Dict[str, Any] = field(default_factory=dict)
    atm_iv_change: Optional[float] = None  # vs. lookback window (pct points)

    # Data sufficiency
    candles_seen: int = 0
    warmed_up: bool = False  # all core indicators defined

    def to_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d["timestamp"] = self.timestamp.isoformat(sep=" ")
        return d
