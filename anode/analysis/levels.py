"""Support / resistance level detection.

Levels come from three sources, merged and deduplicated:
  1. Swing pivots — local highs/lows in the candle series (fractal pivots).
  2. Session levels — current day high/low, previous day high/low.
  3. Option-chain levels — strikes carrying maximum call OI (resistance)
     and maximum put OI (support), supplied by the chain analyzer.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence

from anode.analysis.candles import Candle


@dataclass
class LevelSet:
    supports: List[float]  # sorted descending (nearest first relative to spot)
    resistances: List[float]  # sorted ascending (nearest first)
    nearest_support: Optional[float]
    nearest_resistance: Optional[float]
    support_distance_pct: Optional[float]  # (spot - support) / spot * 100
    resistance_distance_pct: Optional[float]  # (resistance - spot) / spot * 100


def swing_highs(candles: Sequence[Candle], window: int = 3) -> List[float]:
    """Pivot highs: candle high strictly greater than `window` neighbors each side."""
    out: List[float] = []
    for i in range(window, len(candles) - window):
        h = candles[i].high
        if all(h > candles[i - j].high for j in range(1, window + 1)) and all(
            h > candles[i + j].high for j in range(1, window + 1)
        ):
            out.append(h)
    return out


def swing_lows(candles: Sequence[Candle], window: int = 3) -> List[float]:
    out: List[float] = []
    for i in range(window, len(candles) - window):
        low = candles[i].low
        if all(low < candles[i - j].low for j in range(1, window + 1)) and all(
            low < candles[i + j].low for j in range(1, window + 1)
        ):
            out.append(low)
    return out


def _dedupe(levels: List[float], tolerance_pct: float) -> List[float]:
    """Merge levels closer than tolerance_pct of each other (keep the mean)."""
    if not levels:
        return []
    levels = sorted(levels)
    merged: List[List[float]] = [[levels[0]]]
    for lv in levels[1:]:
        cluster = merged[-1]
        if abs(lv - cluster[-1]) / cluster[-1] * 100.0 <= tolerance_pct:
            cluster.append(lv)
        else:
            merged.append([lv])
    return [sum(c) / len(c) for c in merged]


def build_levels(
    spot: float,
    candles: Sequence[Candle],
    day_high: Optional[float] = None,
    day_low: Optional[float] = None,
    prev_day_high: Optional[float] = None,
    prev_day_low: Optional[float] = None,
    oi_resistance: Optional[float] = None,
    oi_support: Optional[float] = None,
    swing_window: int = 3,
    dedupe_tolerance_pct: float = 0.05,
) -> LevelSet:
    raw: List[float] = []
    raw.extend(swing_highs(candles, swing_window))
    raw.extend(swing_lows(candles, swing_window))
    for lv in (day_high, day_low, prev_day_high, prev_day_low,
               oi_resistance, oi_support):
        if lv is not None:
            raw.append(lv)

    levels = _dedupe(raw, dedupe_tolerance_pct)
    supports = sorted([lv for lv in levels if lv < spot], reverse=True)
    resistances = sorted([lv for lv in levels if lv > spot])

    nearest_support = supports[0] if supports else None
    nearest_resistance = resistances[0] if resistances else None
    return LevelSet(
        supports=supports,
        resistances=resistances,
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
        support_distance_pct=(
            (spot - nearest_support) / spot * 100.0 if nearest_support else None
        ),
        resistance_distance_pct=(
            (nearest_resistance - spot) / spot * 100.0 if nearest_resistance else None
        ),
    )
