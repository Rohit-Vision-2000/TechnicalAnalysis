"""Market-regime classification.

Initial rule-based classifier. The thresholds are starting points, expected
to be tuned through the experiment framework — never hand-edited on a hunch.

Regimes:
    TRENDING_BULLISH  strong directional move up (ADX high, EMAs aligned up)
    TRENDING_BEARISH  strong directional move down
    HIGH_VOLATILITY   outsized ATR relative to price — unstable conditions
    SIDEWAYS          everything else
"""

from typing import Optional


class Regime:
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    UNKNOWN = "UNKNOWN"  # insufficient data
    ALL = (TRENDING_BULLISH, TRENDING_BEARISH, SIDEWAYS, HIGH_VOLATILITY, UNKNOWN)


DEFAULT_ADX_TREND_THRESHOLD = 25.0
DEFAULT_HIGH_VOL_ATR_PCT = 0.20  # ATR as % of price on the working timeframe


def classify_regime(
    close: Optional[float],
    ema_fast: Optional[float],
    ema_slow: Optional[float],
    adx_value: Optional[float],
    atr_value: Optional[float],
    adx_trend_threshold: float = DEFAULT_ADX_TREND_THRESHOLD,
    high_vol_atr_pct: float = DEFAULT_HIGH_VOL_ATR_PCT,
) -> str:
    if close is None or ema_fast is None or ema_slow is None:
        return Regime.UNKNOWN

    if atr_value is not None and close > 0:
        atr_pct = atr_value / close * 100.0
        if atr_pct >= high_vol_atr_pct:
            return Regime.HIGH_VOLATILITY

    if adx_value is not None and adx_value >= adx_trend_threshold:
        if ema_fast > ema_slow and close > ema_fast:
            return Regime.TRENDING_BULLISH
        if ema_fast < ema_slow and close < ema_fast:
            return Regime.TRENDING_BEARISH

    return Regime.SIDEWAYS
