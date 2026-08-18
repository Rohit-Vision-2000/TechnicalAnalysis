"""Candle aggregation.

The engine receives market snapshots (typically one per minute) and
aggregates the NIFTY spot price into fixed-interval OHLC candles. The index
itself has no traded volume; ``volume`` is optional and only populated when a
data source provides one (e.g. futures volume mapped in by an adapter).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional


@dataclass
class Candle:
    start: datetime  # open time of the interval
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None

    @property
    def typical_price(self) -> float:
        return (self.high + self.low + self.close) / 3.0

    @property
    def range(self) -> float:
        return self.high - self.low


class CandleBuilder:
    """Aggregates a stream of (timestamp, price[, volume]) into candles.

    A candle covers [start, start + interval). ``update`` returns the just-
    completed candle whenever a tick crosses into a new interval, else None.
    Completed candles accumulate in ``candles``.
    """

    def __init__(self, interval_minutes: int = 5) -> None:
        if interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive")
        self.interval = timedelta(minutes=interval_minutes)
        self.interval_minutes = interval_minutes
        self.candles: List[Candle] = []
        self._current: Optional[Candle] = None
        self._last_ts: Optional[datetime] = None

    def _bucket_start(self, ts: datetime) -> datetime:
        minutes = (ts.minute // self.interval_minutes) * self.interval_minutes
        return ts.replace(minute=minutes, second=0, microsecond=0)

    def update(
        self, ts: datetime, price: float, volume: Optional[float] = None
    ) -> Optional[Candle]:
        if self._last_ts is not None and ts < self._last_ts:
            raise ValueError(
                "tick out of order: {} after {}".format(ts, self._last_ts)
            )
        self._last_ts = ts

        bucket = self._bucket_start(ts)
        completed: Optional[Candle] = None

        if self._current is not None and bucket > self._current.start:
            completed = self._current
            self.candles.append(completed)
            self._current = None

        if self._current is None:
            self._current = Candle(
                start=bucket, open=price, high=price, low=price,
                close=price, volume=volume,
            )
        else:
            c = self._current
            c.high = max(c.high, price)
            c.low = min(c.low, price)
            c.close = price
            if volume is not None:
                c.volume = (c.volume or 0.0) + volume

        return completed

    def flush(self) -> Optional[Candle]:
        """Force-complete the in-progress candle (end of session)."""
        completed = self._current
        if completed is not None:
            self.candles.append(completed)
            self._current = None
        return completed

    @property
    def current(self) -> Optional[Candle]:
        return self._current

    def all_candles(self, include_current: bool = True) -> List[Candle]:
        """Completed candles, optionally with the still-forming one appended."""
        if include_current and self._current is not None:
            return self.candles + [self._current]
        return list(self.candles)
