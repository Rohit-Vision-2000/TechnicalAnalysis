"""TechnicalAnalysisEngine — streaming snapshot → TechnicalState.

Feed snapshots in time order via ``update()``; each call returns the current
TechnicalState. The engine maintains:

- a candle series on the working timeframe (default 5-minute)
- session state (day high/low, previous day high/low, VWAP accumulation)
- an ATM-IV history for IV-change measurement

Indicators are computed on COMPLETED candles only — the forming candle is
excluded, so a value can never quietly change after the fact (no intra-bar
repainting, which would be a form of look-ahead in backtests).
"""

import logging
from collections import deque
from datetime import date, datetime, timedelta
from typing import Deque, Optional, Tuple

from anode.analysis import indicators as ind
from anode.analysis.candles import CandleBuilder
from anode.analysis.chain import analyze_chain
from anode.analysis.levels import build_levels
from anode.analysis.regime import (
    DEFAULT_ADX_TREND_THRESHOLD,
    DEFAULT_HIGH_VOL_ATR_PCT,
    classify_regime,
)
from anode.analysis.state import TechnicalState, Trend
from anode.models import MarketSnapshot

log = logging.getLogger(__name__)


class TechnicalAnalysisEngine:
    def __init__(
        self,
        candle_minutes: int = 5,
        iv_change_lookback_minutes: int = 30,
        skew_offset_points: float = 200.0,
        adx_trend_threshold: float = DEFAULT_ADX_TREND_THRESHOLD,
        high_vol_atr_pct: float = DEFAULT_HIGH_VOL_ATR_PCT,
        swing_window: int = 3,
    ) -> None:
        self.builder = CandleBuilder(candle_minutes)
        self.iv_change_lookback = timedelta(minutes=iv_change_lookback_minutes)
        self.skew_offset_points = skew_offset_points
        self.adx_trend_threshold = adx_trend_threshold
        self.high_vol_atr_pct = high_vol_atr_pct
        self.swing_window = swing_window

        self._session_date: Optional[date] = None
        self._day_high: Optional[float] = None
        self._day_low: Optional[float] = None
        self._prev_day_high: Optional[float] = None
        self._prev_day_low: Optional[float] = None

        # Time-weighted VWAP proxy accumulation (index has no volume).
        self._vwap_sum = 0.0
        self._vwap_n = 0

        # (timestamp, atm_iv) history for IV-change measurement.
        self._iv_history: Deque[Tuple[datetime, float]] = deque()

        self._last_ts: Optional[datetime] = None

    def update(self, snapshot: MarketSnapshot) -> TechnicalState:
        ts = snapshot.timestamp
        if self._last_ts is not None and ts < self._last_ts:
            raise ValueError(
                "snapshot out of order: {} after {}".format(ts, self._last_ts)
            )
        self._last_ts = ts

        self._roll_session(ts.date(), snapshot.nifty_spot)
        self.builder.update(ts, snapshot.nifty_spot)

        # --- session tracking ---
        spot = snapshot.nifty_spot
        self._day_high = spot if self._day_high is None else max(self._day_high, spot)
        self._day_low = spot if self._day_low is None else min(self._day_low, spot)
        self._vwap_sum += spot
        self._vwap_n += 1
        vwap_proxy = self._vwap_sum / self._vwap_n

        # --- indicators on completed candles only ---
        candles = self.builder.all_candles(include_current=False)
        closes = [c.close for c in candles]

        ema20 = ind.last(ind.ema(closes, 20)) if len(closes) >= 20 else None
        ema50 = ind.last(ind.ema(closes, 50)) if len(closes) >= 50 else None
        ema200 = ind.last(ind.ema(closes, 200)) if len(closes) >= 200 else None
        rsi14 = ind.last(ind.rsi(closes, 14))
        macd_res = ind.macd(closes)
        macd_v = ind.last(macd_res.macd)
        macd_sig = ind.last(macd_res.signal)
        macd_hist = ind.last(macd_res.histogram)
        atr14 = ind.last(ind.atr(candles, 14))
        adx_res = ind.adx(candles, 14)
        adx14 = ind.last(adx_res.adx)
        plus_di = ind.last(adx_res.plus_di)
        minus_di = ind.last(adx_res.minus_di)

        # --- option chain ---
        chain = analyze_chain(
            snapshot, skew_offset_points=self.skew_offset_points
        )
        atm_iv_change = self._track_iv(ts, chain.atm_iv)

        # --- levels ---
        levels = build_levels(
            spot=spot,
            candles=candles,
            day_high=self._day_high,
            day_low=self._day_low,
            prev_day_high=self._prev_day_high,
            prev_day_low=self._prev_day_low,
            oi_resistance=chain.oi_resistance_strike,
            oi_support=chain.oi_support_strike,
            swing_window=self.swing_window,
        )

        # --- trend / regime ---
        trend = Trend.UNKNOWN
        if ema20 is not None and ema50 is not None:
            if ema20 > ema50 and spot > ema20:
                trend = Trend.BULLISH
            elif ema20 < ema50 and spot < ema20:
                trend = Trend.BEARISH
            else:
                trend = Trend.NEUTRAL

        regime = classify_regime(
            close=spot,
            ema_fast=ema20,
            ema_slow=ema50,
            adx_value=adx14,
            atr_value=atr14,
            adx_trend_threshold=self.adx_trend_threshold,
            high_vol_atr_pct=self.high_vol_atr_pct,
        )

        core = (ema20, ema50, rsi14, macd_v, atr14, adx14)
        return TechnicalState(
            timestamp=ts,
            spot=spot,
            trend=trend,
            ema20=ema20,
            ema50=ema50,
            ema200=ema200,
            ema20_above_ema50=(
                ema20 > ema50 if ema20 is not None and ema50 is not None else None
            ),
            rsi14=rsi14,
            macd=macd_v,
            macd_signal=macd_sig,
            macd_histogram=macd_hist,
            macd_bullish=(
                macd_v > macd_sig
                if macd_v is not None and macd_sig is not None
                else None
            ),
            adx14=adx14,
            plus_di=plus_di,
            minus_di=minus_di,
            atr14=atr14,
            atr_pct=(atr14 / spot * 100.0 if atr14 is not None else None),
            vwap=vwap_proxy,
            vwap_is_proxy=True,
            price_above_vwap=spot > vwap_proxy,
            day_high=self._day_high,
            day_low=self._day_low,
            prev_day_high=self._prev_day_high,
            prev_day_low=self._prev_day_low,
            supports=levels.supports,
            resistances=levels.resistances,
            nearest_support=levels.nearest_support,
            nearest_resistance=levels.nearest_resistance,
            support_distance_pct=levels.support_distance_pct,
            resistance_distance_pct=levels.resistance_distance_pct,
            regime=regime,
            chain=chain.to_dict(),
            atm_iv_change=atm_iv_change,
            candles_seen=len(candles),
            warmed_up=all(v is not None for v in core),
        )

    def _roll_session(self, day: date, spot: float) -> None:
        if self._session_date is None:
            self._session_date = day
            return
        if day != self._session_date:
            log.info("new session %s (previous %s)", day, self._session_date)
            self._prev_day_high = self._day_high
            self._prev_day_low = self._day_low
            self._day_high = None
            self._day_low = None
            self._vwap_sum = 0.0
            self._vwap_n = 0
            self._iv_history.clear()
            self.builder.flush()
            self._session_date = day

    def _track_iv(self, ts: datetime, atm_iv: Optional[float]) -> Optional[float]:
        """Record ATM IV and return its change vs the lookback window."""
        if atm_iv is None:
            return None
        self._iv_history.append((ts, atm_iv))
        cutoff = ts - self.iv_change_lookback
        # keep one entry at/behind the cutoff as the comparison point
        while len(self._iv_history) >= 2 and self._iv_history[1][0] <= cutoff:
            self._iv_history.popleft()
        base_ts, base_iv = self._iv_history[0]
        if base_ts > cutoff:
            return None  # not enough history yet
        return atm_iv - base_iv
