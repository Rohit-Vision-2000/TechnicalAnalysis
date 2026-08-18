import unittest
from datetime import datetime

from anode.analysis.state import TechnicalState
from anode.decision import DecisionEngine
from anode.decision.defaults import merged_config
from anode.models import MarketSnapshot, OptionSnapshot, StrategyVersion


def make_strategy(config=None):
    return StrategyVersion(
        version_id="STRAT-001",
        created_at=datetime(2026, 8, 19, 9, 0),
        status="CANDIDATE",
        config=config or {},
    )


def bullish_state(ts=None, **overrides):
    """A TechnicalState that passes every default CALL rule."""
    base = dict(
        timestamp=ts or datetime(2026, 8, 19, 10, 30),
        spot=25010.0,
        trend="BULLISH",
        ema20=25000.0, ema50=24980.0, ema20_above_ema50=True,
        rsi14=62.0,
        macd=5.0, macd_signal=3.0, macd_histogram=2.0, macd_bullish=True,
        adx14=28.0, atr14=10.0, atr_pct=0.04,
        vwap=24990.0, price_above_vwap=True,
        nearest_resistance=25150.0, resistance_distance_pct=0.56,
        nearest_support=24900.0, support_distance_pct=0.44,
        regime="TRENDING_BULLISH",
        chain={
            "atm_strike": 25000.0, "expiry": "2026-08-27",
            "atm_spread_pct": 0.004, "pcr_oi": 1.1,
        },
        atm_iv_change=0.2,
        candles_seen=60, warmed_up=True,
    )
    base.update(overrides)
    return TechnicalState(**base)


def snapshot_with_atm(ts=None, ask=142.65):
    return MarketSnapshot(
        timestamp=ts or datetime(2026, 8, 19, 10, 30),
        nifty_spot=25010.0,
        options=[
            OptionSnapshot(expiry="2026-08-27", strike=25000.0, option_type="CE",
                           ltp=142.35, bid=142.05, ask=ask),
            OptionSnapshot(expiry="2026-08-27", strike=25000.0, option_type="PE",
                           ltp=120.0, bid=119.7, ask=120.3),
        ],
    )


class TestDecisionEngine(unittest.TestCase):
    def test_call_signal_on_bullish_state(self):
        de = DecisionEngine(make_strategy())
        d = de.evaluate(bullish_state(), snapshot_with_atm())
        self.assertEqual(d.status, "SIGNAL")
        self.assertEqual(d.direction, "CALL")
        self.assertEqual(d.strike, 25000.0)
        self.assertEqual(d.option_type, "CE")
        self.assertIn("TREND_BULLISH", d.reason_codes)
        self.assertIn("RESISTANCE_CLEAR", d.reason_codes)
        # trade plan derived from ask=142.65: SL 15% below, target 25% above
        self.assertAlmostEqual(d.stop_loss, round(142.65 * 0.85, 2))
        self.assertAlmostEqual(d.target, round(142.65 * 1.25, 2))
        self.assertTrue(d.stop_loss < d.entry_low <= d.entry_high < d.target)
        self.assertEqual(d.features["regime"], "TRENDING_BULLISH")

    def test_no_trade_when_not_warmed_up(self):
        de = DecisionEngine(make_strategy())
        d = de.evaluate(bullish_state(warmed_up=False), snapshot_with_atm())
        self.assertEqual(d.status, "NO_TRADE")
        self.assertIn("FAIL_WARMUP", d.reason_codes)

    def test_no_trade_when_resistance_close(self):
        de = DecisionEngine(make_strategy())
        d = de.evaluate(
            bullish_state(resistance_distance_pct=0.10), snapshot_with_atm()
        )
        self.assertEqual(d.status, "NO_TRADE")
        self.assertIn("FAIL_RESISTANCE_CLEAR", d.reason_codes)

    def test_no_resistance_at_all_counts_as_clear(self):
        de = DecisionEngine(make_strategy())
        d = de.evaluate(
            bullish_state(nearest_resistance=None, resistance_distance_pct=None),
            snapshot_with_atm(),
        )
        self.assertEqual(d.status, "SIGNAL")

    def test_no_trade_on_rsi_out_of_range(self):
        de = DecisionEngine(make_strategy())
        d = de.evaluate(bullish_state(rsi14=80.0), snapshot_with_atm())
        self.assertEqual(d.status, "NO_TRADE")
        self.assertIn("FAIL_RSI_IN_RANGE", d.reason_codes)

    def test_none_value_never_passes(self):
        de = DecisionEngine(make_strategy())
        d = de.evaluate(bullish_state(rsi14=None), snapshot_with_atm())
        self.assertEqual(d.status, "NO_TRADE")
        self.assertIn("FAIL_RSI_IN_RANGE", d.reason_codes)

    def test_illiquid_chain_rejected(self):
        de = DecisionEngine(make_strategy())
        state = bullish_state()
        state.chain["atm_spread_pct"] = 0.05  # 5% spread
        d = de.evaluate(state, snapshot_with_atm())
        self.assertEqual(d.status, "NO_TRADE")
        self.assertIn("FAIL_LIQUIDITY_OK", d.reason_codes)

    def test_iv_spike_rejected(self):
        de = DecisionEngine(make_strategy())
        d = de.evaluate(bullish_state(atm_iv_change=3.0), snapshot_with_atm())
        self.assertEqual(d.status, "NO_TRADE")
        self.assertIn("FAIL_IV_STABLE", d.reason_codes)

    def test_put_signal_on_bearish_state(self):
        de = DecisionEngine(make_strategy())
        state = bullish_state(
            trend="BEARISH", price_above_vwap=False, rsi14=38.0,
            macd_bullish=False, regime="TRENDING_BEARISH",
            support_distance_pct=0.6,
        )
        d = de.evaluate(state, snapshot_with_atm())
        self.assertEqual(d.status, "SIGNAL")
        self.assertEqual(d.direction, "PUT")
        self.assertEqual(d.option_type, "PE")
        self.assertIn("SUPPORT_CLEAR", d.reason_codes)

    def test_cooldown_blocks_second_signal(self):
        de = DecisionEngine(make_strategy())
        t1 = datetime(2026, 8, 19, 10, 30)
        t2 = datetime(2026, 8, 19, 10, 35)  # within 15-min cooldown
        t3 = datetime(2026, 8, 19, 10, 50)  # past cooldown
        d1 = de.evaluate(bullish_state(ts=t1), snapshot_with_atm(ts=t1))
        self.assertEqual(d1.status, "SIGNAL")
        d2 = de.evaluate(bullish_state(ts=t2), snapshot_with_atm(ts=t2))
        self.assertEqual(d2.status, "NO_TRADE")
        self.assertIn("FAIL_COOLDOWN", d2.reason_codes)
        d3 = de.evaluate(bullish_state(ts=t3), snapshot_with_atm(ts=t3))
        self.assertEqual(d3.status, "SIGNAL")

    def test_config_override_changes_threshold(self):
        strategy = make_strategy({"call": {"rsi_min": 65.0}})
        de = DecisionEngine(strategy)
        d = de.evaluate(bullish_state(rsi14=62.0), snapshot_with_atm())
        self.assertEqual(d.status, "NO_TRADE")  # 62 < overridden min 65

    def test_missing_contract_is_no_trade(self):
        de = DecisionEngine(make_strategy())
        empty_snap = MarketSnapshot(
            timestamp=datetime(2026, 8, 19, 10, 30), nifty_spot=25010.0,
        )
        state = bullish_state()
        state.chain["atm_strike"] = 25000.0
        d = de.evaluate(state, empty_snap)
        self.assertEqual(d.status, "NO_TRADE")
        self.assertIn("FAIL_NO_CONTRACT", d.reason_codes)

    def test_decision_ids_increment(self):
        de = DecisionEngine(make_strategy())
        t1 = datetime(2026, 8, 19, 10, 30)
        d1 = de.evaluate(bullish_state(ts=t1), snapshot_with_atm(ts=t1))
        t2 = datetime(2026, 8, 19, 10, 31)
        d2 = de.evaluate(bullish_state(ts=t2), snapshot_with_atm(ts=t2))
        self.assertTrue(d1.decision_id.endswith("-00001"))
        self.assertTrue(d2.decision_id.endswith("-00002"))

    def test_seq_base_fn_offsets_ids(self):
        de = DecisionEngine(make_strategy(), seq_base_fn=lambda day: 10)
        t1 = datetime(2026, 8, 19, 10, 30)
        d1 = de.evaluate(bullish_state(ts=t1), snapshot_with_atm(ts=t1))
        self.assertTrue(d1.decision_id.endswith("-00011"))


class TestMergedConfig(unittest.TestCase):
    def test_overrides_one_section_deep(self):
        cfg = merged_config({"call": {"rsi_min": 60.0}})
        self.assertEqual(cfg["call"]["rsi_min"], 60.0)
        self.assertEqual(cfg["call"]["rsi_max"], 70.0)  # default kept
        self.assertEqual(cfg["put"]["rsi_min"], 30.0)  # other section intact

    def test_empty_is_pure_default(self):
        cfg = merged_config({})
        self.assertEqual(cfg["trade_plan"]["sl_pct_of_premium"], 15.0)


if __name__ == "__main__":
    unittest.main()
