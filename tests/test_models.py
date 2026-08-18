import unittest
from datetime import datetime

from anode.models import (
    Decision,
    DecisionStatus,
    Direction,
    ExitReason,
    MarketSnapshot,
    OptionSnapshot,
    PaperTrade,
    TradeResult,
    TradeStatus,
)


def make_option(**overrides):
    base = dict(
        expiry="2026-08-27", strike=25000.0, option_type="CE",
        ltp=142.35, bid=142.05, ask=142.65,
        volume=125000, open_interest=4520000, oi_change=182000, iv=12.4,
    )
    base.update(overrides)
    return OptionSnapshot(**base)


class TestOptionSnapshot(unittest.TestCase):
    def test_valid_option(self):
        o = make_option()
        self.assertEqual(o.contract, "NIFTY 2026-08-27 25000 CE")
        self.assertAlmostEqual(o.spread, 0.60, places=6)
        self.assertAlmostEqual(o.spread_pct, 0.60 / 142.35, places=4)

    def test_invalid_option_type(self):
        with self.assertRaises(ValueError):
            make_option(option_type="CALL")

    def test_negative_strike(self):
        with self.assertRaises(ValueError):
            make_option(strike=-50)

    def test_spread_none_without_quotes(self):
        o = make_option(bid=None, ask=None)
        self.assertIsNone(o.spread)
        self.assertIsNone(o.spread_pct)


class TestMarketSnapshot(unittest.TestCase):
    def test_atm_and_expiry_derived(self):
        snap = MarketSnapshot(
            timestamp=datetime(2026, 8, 19, 10, 30),
            nifty_spot=24985.5,
            options=[
                make_option(strike=25000.0),
                make_option(strike=24950.0),
                make_option(strike=25000.0, option_type="PE"),
            ],
        )
        self.assertEqual(snap.atm_strike, 25000.0)
        self.assertEqual(snap.nearest_expiry, "2026-08-27")

    def test_option_lookup(self):
        snap = MarketSnapshot(
            timestamp=datetime(2026, 8, 19, 10, 30),
            nifty_spot=24985.5,
            options=[make_option(), make_option(option_type="PE", ltp=151.2)],
        )
        found = snap.option(25000.0, "PE")
        self.assertIsNotNone(found)
        self.assertEqual(found.ltp, 151.2)
        self.assertIsNone(snap.option(24800.0, "CE"))

    def test_pcr(self):
        snap = MarketSnapshot(
            timestamp=datetime(2026, 8, 19, 10, 30),
            nifty_spot=24985.5,
            options=[
                make_option(open_interest=1000),
                make_option(option_type="PE", open_interest=1200),
            ],
        )
        self.assertAlmostEqual(snap.pcr_oi(), 1.2)

    def test_invalid_spot(self):
        with self.assertRaises(ValueError):
            MarketSnapshot(timestamp=datetime.now(), nifty_spot=0)


class TestDecision(unittest.TestCase):
    def _signal_kwargs(self, **overrides):
        base = dict(
            decision_id="DEC-20260819-103000-00001",
            timestamp=datetime(2026, 8, 19, 10, 30),
            strategy_version="STRAT-001",
            status=DecisionStatus.SIGNAL,
            direction=Direction.CALL,
            expiry="2026-08-27",
            strike=25000.0,
            entry_low=142.0,
            entry_high=145.0,
            stop_loss=128.0,
            target=170.0,
            reason_codes=["TREND_BULLISH", "ABOVE_VWAP"],
        )
        base.update(overrides)
        return base

    def test_valid_signal(self):
        d = Decision(**self._signal_kwargs())
        self.assertEqual(d.option_type, "CE")  # derived from direction

    def test_put_option_type(self):
        d = Decision(**self._signal_kwargs(direction=Direction.PUT))
        self.assertEqual(d.option_type, "PE")

    def test_no_trade_needs_no_contract(self):
        d = Decision(
            decision_id="DEC-20260819-103000-00002",
            timestamp=datetime(2026, 8, 19, 10, 30),
            strategy_version="STRAT-001",
            status=DecisionStatus.NO_TRADE,
            reason_codes=["RESISTANCE_TOO_CLOSE"],
        )
        self.assertIsNone(d.direction)

    def test_signal_missing_fields_rejected(self):
        with self.assertRaises(ValueError):
            Decision(**self._signal_kwargs(target=None))

    def test_signal_without_direction_rejected(self):
        with self.assertRaises(ValueError):
            Decision(**self._signal_kwargs(direction=None))

    def test_inverted_levels_rejected(self):
        # stop loss above entry makes no sense for a long option
        with self.assertRaises(ValueError):
            Decision(**self._signal_kwargs(stop_loss=150.0))


class TestPaperTrade(unittest.TestCase):
    def _open_trade(self):
        return PaperTrade(
            trade_id="TRD-20260819-00001",
            decision_id="DEC-20260819-103000-00001",
            status=TradeStatus.OPEN,
            entry_time=datetime(2026, 8, 19, 10, 32),
            entry_price=143.0,
            quantity=75,
        )

    def test_close_win(self):
        t = self._open_trade()
        t.close(datetime(2026, 8, 19, 11, 5), 170.0, ExitReason.TARGET, costs=120.0)
        self.assertEqual(t.status, TradeStatus.CLOSED)
        self.assertAlmostEqual(t.gross_pnl, (170.0 - 143.0) * 75)
        self.assertAlmostEqual(t.net_pnl, t.gross_pnl - 120.0)
        self.assertEqual(t.result, TradeResult.WIN)

    def test_close_loss(self):
        t = self._open_trade()
        t.close(datetime(2026, 8, 19, 11, 5), 128.0, ExitReason.STOP_LOSS, costs=120.0)
        self.assertEqual(t.result, TradeResult.LOSS)
        self.assertLess(t.net_pnl, 0)

    def test_double_close_rejected(self):
        t = self._open_trade()
        t.close(datetime(2026, 8, 19, 11, 5), 170.0, ExitReason.TARGET)
        with self.assertRaises(ValueError):
            t.close(datetime(2026, 8, 19, 11, 6), 171.0, ExitReason.MANUAL)

    def test_invalid_exit_reason(self):
        t = self._open_trade()
        with self.assertRaises(ValueError):
            t.close(datetime(2026, 8, 19, 11, 5), 170.0, "WHATEVER")


if __name__ == "__main__":
    unittest.main()
