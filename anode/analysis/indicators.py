"""Technical indicators.

Pure functions over price/candle series. Each returns a list aligned to its
input with ``None`` where the indicator is not yet defined (warm-up period),
so callers can never accidentally consume look-ahead or unseeded values.

Conventions:
- EMA is seeded with the SMA of the first ``period`` values (standard).
- RSI, ATR, ADX use Wilder smoothing (standard).
- MACD is EMA(12) - EMA(26) with an EMA(9) signal line.
"""

from typing import List, NamedTuple, Optional, Sequence

from anode.analysis.candles import Candle

Series = List[Optional[float]]


def sma(values: Sequence[float], period: int) -> Series:
    out: Series = [None] * len(values)
    if period <= 0:
        raise ValueError("period must be positive")
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def ema(values: Sequence[float], period: int) -> Series:
    out: Series = [None] * len(values)
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    k = 2.0 / (period + 1)
    prev = seed
    for i in range(period, len(values)):
        prev = (values[i] - prev) * k + prev
        out[i] = prev
    return out


def rsi(closes: Sequence[float], period: int = 14) -> Series:
    out: Series = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_value(avg_gain, avg_loss)
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


class MacdResult(NamedTuple):
    macd: Series
    signal: Series
    histogram: Series


def macd(
    closes: Sequence[float], fast: int = 12, slow: int = 26, signal_period: int = 9
) -> MacdResult:
    n = len(closes)
    macd_line: Series = [None] * n
    signal_line: Series = [None] * n
    histogram: Series = [None] * n

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    for i in range(n):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]

    valid = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    if len(valid) >= signal_period:
        idxs = [i for i, _ in valid]
        vals = [v for _, v in valid]
        sig = ema(vals, signal_period)
        for j, i in enumerate(idxs):
            if sig[j] is not None:
                signal_line[i] = sig[j]
                histogram[i] = macd_line[i] - sig[j]
    return MacdResult(macd_line, signal_line, histogram)


def true_ranges(candles: Sequence[Candle]) -> List[float]:
    out: List[float] = []
    for i, c in enumerate(candles):
        if i == 0:
            out.append(c.high - c.low)
        else:
            pc = candles[i - 1].close
            out.append(max(c.high - c.low, abs(c.high - pc), abs(c.low - pc)))
    return out


def atr(candles: Sequence[Candle], period: int = 14) -> Series:
    trs = true_ranges(candles)
    out: Series = [None] * len(candles)
    if len(candles) < period:
        return out
    prev = sum(trs[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(candles)):
        prev = (prev * (period - 1) + trs[i]) / period
        out[i] = prev
    return out


class AdxResult(NamedTuple):
    adx: Series
    plus_di: Series
    minus_di: Series


def adx(candles: Sequence[Candle], period: int = 14) -> AdxResult:
    n = len(candles)
    adx_out: Series = [None] * n
    pdi_out: Series = [None] * n
    mdi_out: Series = [None] * n
    if n < 2 * period:
        return AdxResult(adx_out, pdi_out, mdi_out)

    trs = true_ranges(candles)
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    for i in range(1, n):
        up = candles[i].high - candles[i - 1].high
        down = candles[i - 1].low - candles[i].low
        if up > down and up > 0:
            plus_dm[i] = up
        if down > up and down > 0:
            minus_dm[i] = down

    # Wilder smoothed sums, seeded over bars 1..period.
    sm_tr = sum(trs[1 : period + 1])
    sm_pdm = sum(plus_dm[1 : period + 1])
    sm_mdm = sum(minus_dm[1 : period + 1])

    dx_values: Series = [None] * n
    for i in range(period, n):
        if i > period:
            sm_tr = sm_tr - sm_tr / period + trs[i]
            sm_pdm = sm_pdm - sm_pdm / period + plus_dm[i]
            sm_mdm = sm_mdm - sm_mdm / period + minus_dm[i]
        if sm_tr == 0:
            continue
        pdi = 100.0 * sm_pdm / sm_tr
        mdi = 100.0 * sm_mdm / sm_tr
        pdi_out[i] = pdi
        mdi_out[i] = mdi
        di_sum = pdi + mdi
        if di_sum > 0:
            dx_values[i] = 100.0 * abs(pdi - mdi) / di_sum

    # ADX = Wilder average of DX, seeded with the mean of the first
    # `period` defined DX values.
    dx_defined = [(i, v) for i, v in enumerate(dx_values) if v is not None]
    if len(dx_defined) >= period:
        seed_idx = dx_defined[period - 1][0]
        prev = sum(v for _, v in dx_defined[:period]) / period
        adx_out[seed_idx] = prev
        for i, v in dx_defined[period:]:
            prev = (prev * (period - 1) + v) / period
            adx_out[i] = prev
    return AdxResult(adx_out, pdi_out, mdi_out)


def rolling_vwap(candles: Sequence[Candle]) -> Optional[float]:
    """Volume-weighted average price over the given candles.

    Returns None unless every candle carries volume — a partial-volume VWAP
    would be silently wrong. (The engine falls back to a time-weighted proxy
    and flags it as such.)
    """
    if not candles:
        return None
    if any(c.volume is None or c.volume <= 0 for c in candles):
        return None
    pv = sum(c.typical_price * c.volume for c in candles)
    v = sum(c.volume for c in candles)
    return pv / v if v > 0 else None


def last(series: Series) -> Optional[float]:
    """Latest value of an indicator series (None if never defined)."""
    for v in reversed(series):
        if v is not None:
            return v
    return None
