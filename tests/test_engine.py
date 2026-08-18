import unittest
from datetime import datetime, timedelta

from anode.analysis import TechnicalAnalysisEngine
from anode.analysis.regime import Regime, classify_regime
from anode.data.synthetic import SyntheticDayProvider
from anode.models import MarketSnapshot, OptionSnapshot


def snap(ts, spot, atm_iv=None):
    options = []
    if atm_iv is not None:
        strike = round(spot / 50) * 50
        options = [
            OptionSnapshot(expiry="2026-08-27", strike=strike,
                           option_type="CE", ltp=100.0, iv=atm_iv),
            OptionSnapshot(expiry="2026-08-27", strike=strike,
                           option_type="PE", ltp=100.0, iv=atm_iv),
        ]
    return MarketSnapshot(timestamp=ts, nifty_spot=spot, options=options)


class TestClassifyRegime(unittest.TestCase):
    def test_unknown_without_emas(self):
        self.assertEqual(
            classify_regime(100.0, None, None, None, None), Regime.UNKNOWN
        )

    def test_trending_bullish(self):
        r = classify_regime(
            close=105.0, ema_fast=103.0, ema_slow=100.0,
            adx_value=30.0, atr_value=0.05,
        )
        self.assertEqual(r, Regime.TRENDING_BULLISH)

    def test_trending_bearish(self):
        r = classify_regime(
            close=95.0, ema_fast=97.0, ema_slow=100.0,
            adx_value=30.0, atr_value=0.05,
        )
        self.assertEqual(r, Regime.TRENDING_BEARISH)

    def test_high_volatility_wins(self):
        r = classify_regime(
            close=100.0, ema_fast=103.0, ema_slow=100.0,
            adx_value=30.0, atr_value=1.0,  # 1% ATR >= 0.20% threshold
        )
        self.assertEqual(r, Regime.HIGH_VOLATILITY)

    def test_sideways_low_adx(self):
        r = classify_regime(
            close=105.0, ema_fast=103.0, ema_slow=100.0,
            adx_value=15.0, atr_value=0.05,
        )
        self.assertEqual(r, Regime.SIDEWAYS)


class TestEngineSessions(unittest.TestCase):
    def test_day_tracking_and_rollover(self):
        eng = TechnicalAnalysisEngine(candle_minutes=5)
        day1 = datetime(2026, 8, 18, 9, 15)
        eng.update(snap(day1, 25000.0))
        eng.update(snap(day1 + timedelta(minutes=1), 25080.0))
        state = eng.update(snap(day1 + timedelta(minutes=2), 24950.0))
        self.assertEqual(state.day_high, 25080.0)
        self.assertEqual(state.day_low, 24950.0)
        self.assertIsNone(state.prev_day_high)

        day2 = datetime(2026, 8, 19, 9, 15)
        state = eng.update(snap(day2, 25010.0))
        self.assertEqual(state.prev_day_high, 25080.0)
        self.assertEqual(state.prev_day_low, 24950.0)
        self.assertEqual(state.day_high, 25010.0)

    def test_vwap_proxy_resets_per_session(self):
        eng = TechnicalAnalysisEngine()
        day1 = datetime(2026, 8, 18, 9, 15)
        eng.update(snap(day1, 100.0))
        eng.update(snap(day1 + timedelta(minutes=1), 200.0))
        day2 = datetime(2026, 8, 19, 9, 15)
        state = eng.update(snap(day2, 300.0))
        self.assertAlmostEqual(state.vwap, 300.0)  # not polluted by day 1
        self.assertTrue(state.vwap_is_proxy)

    def test_out_of_order_rejected(self):
        eng = TechnicalAnalysisEngine()
        t = datetime(2026, 8, 19, 10, 0)
        eng.update(snap(t, 25000.0))
        with self.assertRaises(ValueError):
            eng.update(snap(t - timedelta(minutes=1), 25000.0))

    def test_iv_change_tracked(self):
        eng = TechnicalAnalysisEngine(iv_change_lookback_minutes=10)
        t0 = datetime(2026, 8, 19, 10, 0)
        for i in range(11):
            state = eng.update(
                snap(t0 + timedelta(minutes=i), 25000.0, atm_iv=12.0 + i * 0.1)
            )
        # IV rose 0.1/min for 10 minutes -> change ~= 1.0
        self.assertIsNotNone(state.atm_iv_change)
        self.assertAlmostEqual(state.atm_iv_change, 1.0, places=6)

    def test_iv_change_none_without_history(self):
        eng = TechnicalAnalysisEngine(iv_change_lookback_minutes=30)
        state = eng.update(snap(datetime(2026, 8, 19, 10, 0), 25000.0, atm_iv=12.0))
        self.assertIsNone(state.atm_iv_change)


class TestEngineFullSession(unittest.TestCase):
    def test_synthetic_day_warms_up(self):
        eng = TechnicalAnalysisEngine(candle_minutes=5)
        state = None
        for s in SyntheticDayProvider(seed=7):
            state = eng.update(s)
        self.assertIsNotNone(state)
        # 375 minutes -> 74 completed 5-min candles: enough for all
        # 14/20/26/50-period indicators.
        self.assertGreaterEqual(state.candles_seen, 70)
        self.assertTrue(state.warmed_up)
        self.assertIsNotNone(state.rsi14)
        self.assertTrue(0 <= state.rsi14 <= 100)
        self.assertIsNotNone(state.adx14)
        self.assertIsNotNone(state.atr14)
        self.assertIsNotNone(state.ema20)
        self.assertIsNotNone(state.ema50)
        self.assertIn(state.trend, ("BULLISH", "BEARISH", "NEUTRAL"))
        self.assertNotEqual(state.regime, Regime.UNKNOWN)
        self.assertIsNotNone(state.chain["pcr_oi"])
        self.assertIsNotNone(state.chain["atm_iv"])
        self.assertIsNotNone(state.chain["max_pain_strike"])
        self.assertIsNotNone(state.nearest_resistance)
        self.assertIsNotNone(state.nearest_support)
        # state serializes cleanly for decision features storage
        d = state.to_dict()
        self.assertIsInstance(d["timestamp"], str)
        self.assertIn("chain", d)

    def test_determinism(self):
        def run(seed):
            eng = TechnicalAnalysisEngine()
            state = None
            for s in SyntheticDayProvider(seed=seed, minutes=60):
                state = eng.update(s)
            return state

        a, b = run(3), run(3)
        self.assertEqual(a.to_dict(), b.to_dict())


if __name__ == "__main__":
    unittest.main()
