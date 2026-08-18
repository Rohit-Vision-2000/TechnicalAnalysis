import unittest
from datetime import datetime, timedelta

from anode.models import Decision, MarketSnapshot, OptionSnapshot
from anode.trading import PaperTradingEngine, round_trip_costs
from anode.trading.costs import DEFAULT_COSTS


def make_decision(ts, entry_low=140.0, entry_high=145.0,
                  stop_loss=121.0, target=178.0, max_holding=60):
    return Decision(
        decision_id="DEC-20260819-103000-00001",
        timestamp=ts,
        strategy_version="STRAT-001",
        status="SIGNAL",
        direction="CALL",
        expiry="2026-08-27",
        strike=25000.0,
        entry_low=entry_low, entry_high=entry_high,
        stop_loss=stop_loss, target=target,
        max_holding_minutes=max_holding,
    )


def snap(ts, ce_ltp, bid=None, ask=None):
    return MarketSnapshot(
        timestamp=ts, nifty_spot=25000.0,
        options=[OptionSnapshot(
            expiry="2026-08-27", strike=25000.0, option_type="CE",
            ltp=ce_ltp,
            bid=bid if bid is not None else round(ce_ltp - 0.3, 2),
            ask=ask if ask is not None else round(ce_ltp + 0.3, 2),
        )],
    )


class TestCosts(unittest.TestCase):
    def test_components_add_up(self):
        entry, exit_, qty = 100.0, 120.0, 75
        total = round_trip_costs(entry, exit_, qty, {})
        buy_t, sell_t = entry * qty, exit_ * qty
        brokerage = 40.0
        exchange = (buy_t + sell_t) * DEFAULT_COSTS["exchange_txn_charge_pct"] / 100
        sebi = (buy_t + sell_t) / 1e7 * 10.0
        stt = sell_t * 0.1 / 100
        stamp = buy_t * 0.003 / 100
        gst = (brokerage + exchange + sebi) * 0.18
        self.assertAlmostEqual(
            total, round(brokerage + exchange + sebi + stt + stamp + gst, 2)
        )

    def test_costs_nontrivial(self):
        # ~16500 turnover round trip should cost noticeably more than brokerage
        total = round_trip_costs(100.0, 120.0, 75, {})
        self.assertGreater(total, 60.0)


class TestPaperTradingEngine(unittest.TestCase):
    def setUp(self):
        self.t0 = datetime(2026, 8, 19, 10, 30)
        self.engine = PaperTradingEngine(lot_size=75, slippage_bps=5)

    def test_fill_inside_band_with_slippage(self):
        d = make_decision(self.t0)
        trade = self.engine.on_decision(d, snap(self.t0, 142.0, ask=142.3))
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(trade.entry_price, round(142.3 * 1.0005, 2))
        self.assertEqual(trade.quantity, 75)
        self.assertEqual(self.engine.open_count, 1)

    def test_no_fill_outside_band(self):
        d = make_decision(self.t0)
        trade = self.engine.on_decision(d, snap(self.t0, 150.0, ask=150.3))
        self.assertIsNone(trade)
        self.assertEqual(self.engine.open_count, 0)

    def test_target_exit(self):
        d = make_decision(self.t0)
        self.engine.on_decision(d, snap(self.t0, 142.0, ask=142.3))
        t1 = self.t0 + timedelta(minutes=10)
        closed = self.engine.on_snapshot(snap(t1, 180.0, bid=179.0))
        self.assertEqual(len(closed), 1)
        trade = closed[0]
        self.assertEqual(trade.exit_reason, "TARGET")
        self.assertEqual(trade.result, "WIN")
        self.assertAlmostEqual(trade.exit_price, round(179.0 * 0.9995, 2))
        self.assertGreater(trade.costs, 0)
        self.assertEqual(self.engine.open_count, 0)

    def test_stop_loss_exit(self):
        d = make_decision(self.t0)
        self.engine.on_decision(d, snap(self.t0, 142.0, ask=142.3))
        closed = self.engine.on_snapshot(
            snap(self.t0 + timedelta(minutes=5), 120.0, bid=119.5)
        )
        self.assertEqual(closed[0].exit_reason, "STOP_LOSS")
        self.assertEqual(closed[0].result, "LOSS")

    def test_stop_loss_beats_target_priority(self):
        # if bid is somehow below SL, SL fires even on a wild snapshot
        d = make_decision(self.t0, stop_loss=121.0, target=178.0)
        self.engine.on_decision(d, snap(self.t0, 142.0, ask=142.3))
        closed = self.engine.on_snapshot(
            snap(self.t0 + timedelta(minutes=1), 100.0, bid=100.0)
        )
        self.assertEqual(closed[0].exit_reason, "STOP_LOSS")

    def test_time_exit(self):
        d = make_decision(self.t0, max_holding=30)
        self.engine.on_decision(d, snap(self.t0, 142.0, ask=142.3))
        # price meanders inside SL/target for 30+ minutes
        holding = self.engine.on_snapshot(
            snap(self.t0 + timedelta(minutes=29), 145.0, bid=144.5)
        )
        self.assertEqual(holding, [])
        closed = self.engine.on_snapshot(
            snap(self.t0 + timedelta(minutes=30), 145.0, bid=144.5)
        )
        self.assertEqual(closed[0].exit_reason, "TIME_EXIT")

    def test_eod_square_off(self):
        d = make_decision(self.t0, max_holding=600)
        self.engine.on_decision(d, snap(self.t0, 142.0, ask=142.3))
        eod = datetime(2026, 8, 19, 15, 21)
        closed = self.engine.on_snapshot(snap(eod, 145.0, bid=144.5))
        self.assertEqual(closed[0].exit_reason, "EOD")

    def test_force_close_all(self):
        d = make_decision(self.t0, max_holding=600)
        self.engine.on_decision(d, snap(self.t0, 142.0, ask=142.3))
        closed = self.engine.force_close_all(
            snap(self.t0 + timedelta(minutes=5), 143.0, bid=142.5)
        )
        self.assertEqual(len(closed), 1)
        self.assertEqual(self.engine.open_count, 0)

    def test_missing_contract_keeps_position_open(self):
        d = make_decision(self.t0, max_holding=600)
        self.engine.on_decision(d, snap(self.t0, 142.0, ask=142.3))
        bare = MarketSnapshot(
            timestamp=self.t0 + timedelta(minutes=1), nifty_spot=25000.0
        )
        closed = self.engine.on_snapshot(bare)
        self.assertEqual(closed, [])
        self.assertEqual(self.engine.open_count, 1)

    def test_non_signal_ignored(self):
        d = Decision(
            decision_id="DEC-20260819-103000-00002",
            timestamp=self.t0, strategy_version="STRAT-001", status="NO_TRADE",
        )
        self.assertIsNone(self.engine.on_decision(d, snap(self.t0, 142.0)))


if __name__ == "__main__":
    unittest.main()
