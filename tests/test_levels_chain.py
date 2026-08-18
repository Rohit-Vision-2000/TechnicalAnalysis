import unittest
from datetime import datetime, timedelta

from anode.analysis.candles import Candle
from anode.analysis.chain import analyze_chain
from anode.analysis.levels import build_levels, swing_highs, swing_lows
from anode.models import MarketSnapshot, OptionSnapshot


def make_candles(hlc_list):
    start = datetime(2026, 8, 19, 9, 15)
    return [
        Candle(start=start + timedelta(minutes=5 * i),
               open=c, high=h, low=low, close=c)
        for i, (h, low, c) in enumerate(hlc_list)
    ]


class TestSwings(unittest.TestCase):
    def test_pivot_high_detected(self):
        # highs: rise to 110 at index 3, then fall — pivot with window 3
        highs = [100, 102, 105, 110, 106, 103, 101]
        candles = make_candles([(h, h - 2, h - 1) for h in highs])
        self.assertEqual(swing_highs(candles, window=3), [110])

    def test_pivot_low_detected(self):
        highs = [110, 106, 103, 100, 104, 107, 111]
        candles = make_candles([(h, h - 2, h - 1) for h in highs])
        self.assertEqual(swing_lows(candles, window=3), [98])

    def test_no_pivot_in_monotonic(self):
        highs = list(range(100, 120))
        candles = make_candles([(h, h - 2, h - 1) for h in highs])
        self.assertEqual(swing_highs(candles, window=3), [])


class TestBuildLevels(unittest.TestCase):
    def test_split_and_nearest(self):
        ls = build_levels(
            spot=25000.0,
            candles=[],
            day_high=25080.0,
            day_low=24900.0,
            prev_day_high=25150.0,
            prev_day_low=24850.0,
            oi_resistance=25100.0,
            oi_support=24950.0,
        )
        self.assertEqual(ls.nearest_resistance, 25080.0)
        self.assertEqual(ls.nearest_support, 24950.0)
        self.assertAlmostEqual(ls.resistance_distance_pct, 80 / 25000 * 100)
        self.assertAlmostEqual(ls.support_distance_pct, 50 / 25000 * 100)
        self.assertEqual(ls.resistances, [25080.0, 25100.0, 25150.0])
        self.assertEqual(ls.supports, [24950.0, 24900.0, 24850.0])

    def test_dedupe_merges_close_levels(self):
        ls = build_levels(
            spot=25000.0, candles=[],
            day_high=25100.0, prev_day_high=25105.0,  # within 0.05%
        )
        self.assertEqual(len(ls.resistances), 1)
        self.assertAlmostEqual(ls.resistances[0], 25102.5)

    def test_empty(self):
        ls = build_levels(spot=25000.0, candles=[])
        self.assertIsNone(ls.nearest_support)
        self.assertIsNone(ls.nearest_resistance)


def opt(strike, opt_type, ltp=100.0, oi=None, oi_change=None, iv=None,
        volume=None, bid=None, ask=None, expiry="2026-08-27"):
    return OptionSnapshot(
        expiry=expiry, strike=strike, option_type=opt_type, ltp=ltp,
        bid=bid, ask=ask, volume=volume, open_interest=oi,
        oi_change=oi_change, iv=iv,
    )


class TestChainAnalysis(unittest.TestCase):
    def make_snapshot(self):
        options = [
            opt(24800, "CE", oi=1_000_000, oi_change=5_000, iv=13.0, volume=10_000),
            opt(24800, "PE", oi=4_000_000, oi_change=20_000, iv=14.5, volume=30_000),
            opt(25000, "CE", oi=3_000_000, oi_change=15_000, iv=12.0,
                volume=50_000, bid=141.0, ask=142.0, ltp=141.5),
            opt(25000, "PE", oi=3_500_000, oi_change=-10_000, iv=12.4,
                volume=60_000, bid=150.0, ask=151.0, ltp=150.5),
            opt(25200, "CE", oi=5_000_000, oi_change=40_000, iv=12.8, volume=20_000),
            opt(25200, "PE", oi=800_000, oi_change=1_000, iv=13.5, volume=8_000),
        ]
        return MarketSnapshot(
            timestamp=datetime(2026, 8, 19, 10, 30),
            nifty_spot=25010.0,
            options=options,
        )

    def test_atm_and_pcr(self):
        c = analyze_chain(self.make_snapshot())
        self.assertEqual(c.atm_strike, 25000.0)
        total_call = 1_000_000 + 3_000_000 + 5_000_000
        total_put = 4_000_000 + 3_500_000 + 800_000
        self.assertAlmostEqual(c.pcr_oi, total_put / total_call)
        self.assertAlmostEqual(c.pcr_volume, (30 + 60 + 8) / (10 + 50 + 20))

    def test_atm_iv_and_spread(self):
        c = analyze_chain(self.make_snapshot())
        self.assertAlmostEqual(c.atm_iv, (12.0 + 12.4) / 2)
        self.assertIsNotNone(c.atm_spread_pct)
        # ~1.0 spread on ~141.5/150.5 mids -> below 1%
        self.assertLess(c.atm_spread_pct, 0.01)

    def test_iv_skew_uses_otm_wings(self):
        c = analyze_chain(self.make_snapshot(), skew_offset_points=200.0)
        # OTM put at 24800 (iv 14.5) minus OTM call at 25200 (iv 12.8)
        self.assertAlmostEqual(c.iv_skew, 14.5 - 12.8)

    def test_oi_walls(self):
        c = analyze_chain(self.make_snapshot())
        self.assertEqual(c.oi_resistance_strike, 25200.0)  # max call OI
        self.assertEqual(c.oi_support_strike, 24800.0)  # max put OI

    def test_oi_flow_totals(self):
        c = analyze_chain(self.make_snapshot())
        self.assertEqual(c.total_call_oi_change, 5_000 + 15_000 + 40_000)
        self.assertEqual(c.total_put_oi_change, 20_000 - 10_000 + 1_000)

    def test_max_pain_within_strike_range(self):
        c = analyze_chain(self.make_snapshot())
        self.assertIn(c.max_pain_strike, (24800.0, 25000.0, 25200.0))

    def test_empty_chain(self):
        snap = MarketSnapshot(
            timestamp=datetime(2026, 8, 19, 10, 30), nifty_spot=25000.0
        )
        c = analyze_chain(snap)
        self.assertIsNone(c.pcr_oi)
        self.assertIsNone(c.atm_strike)

    def test_restricted_to_one_expiry(self):
        snap = self.make_snapshot()
        snap.options.append(
            opt(25000, "CE", oi=99_000_000, expiry="2026-09-24")
        )
        c = analyze_chain(snap)  # nearest expiry = 2026-08-27
        self.assertEqual(c.oi_resistance_strike, 25200.0)  # far expiry ignored


if __name__ == "__main__":
    unittest.main()
