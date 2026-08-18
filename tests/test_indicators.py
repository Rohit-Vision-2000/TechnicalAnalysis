import math
import unittest
from datetime import datetime, timedelta

from anode.analysis import indicators as ind
from anode.analysis.candles import Candle


def make_candles(closes, spread=1.0):
    """Candles with high/low bracketing close by `spread`."""
    start = datetime(2026, 8, 19, 9, 15)
    out = []
    for i, c in enumerate(closes):
        out.append(Candle(
            start=start + timedelta(minutes=5 * i),
            open=c, high=c + spread, low=c - spread, close=c,
        ))
    return out


class TestSmaEma(unittest.TestCase):
    def test_sma_known_values(self):
        s = ind.sma([1, 2, 3, 4, 5], 3)
        self.assertEqual(s[:2], [None, None])
        self.assertAlmostEqual(s[2], 2.0)
        self.assertAlmostEqual(s[3], 3.0)
        self.assertAlmostEqual(s[4], 4.0)

    def test_ema_seeded_with_sma(self):
        e = ind.ema([2, 4, 6, 8], 3)
        self.assertIsNone(e[0])
        self.assertIsNone(e[1])
        self.assertAlmostEqual(e[2], 4.0)  # SMA seed
        # k = 2/(3+1) = 0.5 -> (8-4)*0.5 + 4 = 6
        self.assertAlmostEqual(e[3], 6.0)

    def test_ema_insufficient_data(self):
        self.assertEqual(ind.ema([1, 2], 5), [None, None])

    def test_constant_series(self):
        e = ind.ema([10.0] * 30, 20)
        self.assertAlmostEqual(e[-1], 10.0)


class TestRsi(unittest.TestCase):
    def test_all_gains_is_100(self):
        closes = list(range(1, 40))
        r = ind.rsi(closes, 14)
        self.assertAlmostEqual(r[-1], 100.0)

    def test_all_losses_is_0(self):
        closes = list(range(100, 60, -1))
        r = ind.rsi(closes, 14)
        self.assertAlmostEqual(r[-1], 0.0)

    def test_flat_is_50(self):
        r = ind.rsi([100.0] * 30, 14)
        self.assertAlmostEqual(r[-1], 50.0)

    def test_warmup_none(self):
        r = ind.rsi([1, 2, 3], 14)
        self.assertTrue(all(v is None for v in r))

    def test_alternating_moves_bounded(self):
        closes = [100 + (2 if i % 2 == 0 else -2) for i in range(60)]
        r = ind.rsi(closes, 14)
        self.assertIsNotNone(r[-1])
        self.assertTrue(0 < r[-1] < 100)


class TestMacd(unittest.TestCase):
    def test_uptrend_positive_macd(self):
        closes = [100 + i * 0.5 for i in range(80)]
        m = ind.macd(closes)
        self.assertGreater(m.macd[-1], 0)
        self.assertIsNotNone(m.signal[-1])
        self.assertAlmostEqual(
            m.histogram[-1], m.macd[-1] - m.signal[-1], places=9
        )

    def test_flat_macd_zero(self):
        m = ind.macd([100.0] * 80)
        self.assertAlmostEqual(m.macd[-1], 0.0)
        self.assertAlmostEqual(m.signal[-1], 0.0)

    def test_insufficient_data(self):
        m = ind.macd([100.0] * 10)
        self.assertTrue(all(v is None for v in m.macd))


class TestAtr(unittest.TestCase):
    def test_constant_range(self):
        candles = make_candles([100.0] * 30, spread=1.0)
        a = ind.atr(candles, 14)
        # every TR = high-low = 2.0
        self.assertAlmostEqual(a[-1], 2.0)

    def test_gap_included_via_true_range(self):
        candles = make_candles([100.0, 110.0], spread=1.0)
        trs = ind.true_ranges(candles)
        # second bar: max(2, |111-100|, |109-100|) = 11
        self.assertAlmostEqual(trs[1], 11.0)

    def test_warmup(self):
        a = ind.atr(make_candles([100.0] * 5), 14)
        self.assertTrue(all(v is None for v in a))


class TestAdx(unittest.TestCase):
    def test_strong_trend_high_adx(self):
        closes = [100 + i * 2.0 for i in range(60)]
        res = ind.adx(make_candles(closes), 14)
        self.assertIsNotNone(res.adx[-1])
        self.assertGreater(res.adx[-1], 25)
        self.assertGreater(res.plus_di[-1], res.minus_di[-1])

    def test_downtrend_minus_di_dominates(self):
        closes = [200 - i * 2.0 for i in range(60)]
        res = ind.adx(make_candles(closes), 14)
        self.assertGreater(res.minus_di[-1], res.plus_di[-1])

    def test_choppy_low_adx(self):
        closes = [100 + (3 if i % 2 == 0 else -3) for i in range(80)]
        res = ind.adx(make_candles(closes), 14)
        self.assertIsNotNone(res.adx[-1])
        self.assertLess(res.adx[-1], 25)

    def test_insufficient_data(self):
        res = ind.adx(make_candles([100.0] * 10), 14)
        self.assertTrue(all(v is None for v in res.adx))


class TestVwap(unittest.TestCase):
    def test_requires_volume(self):
        self.assertIsNone(ind.rolling_vwap(make_candles([100.0] * 5)))

    def test_weighted(self):
        candles = make_candles([100.0, 200.0], spread=0.0)
        candles[0].volume = 1.0
        candles[1].volume = 3.0
        v = ind.rolling_vwap(candles)
        self.assertAlmostEqual(v, (100.0 * 1 + 200.0 * 3) / 4)


if __name__ == "__main__":
    unittest.main()
