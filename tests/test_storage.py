import sqlite3
import unittest
from datetime import datetime

from anode.models import (
    Decision,
    DecisionStatus,
    Direction,
    Experiment,
    ExitReason,
    MarketSnapshot,
    OptionSnapshot,
    PaperTrade,
    StrategyStatus,
    StrategyVersion,
    TradeStatus,
)
from anode.storage import (
    Database,
    DecisionRepository,
    ExperimentRepository,
    SnapshotRepository,
    StrategyRepository,
    TradeRepository,
)


class StorageTestCase(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.db.init_schema()

    def tearDown(self):
        self.db.close()

    def _make_strategy(self, version_id="STRAT-001", status=StrategyStatus.DRAFT):
        s = StrategyVersion(
            version_id=version_id,
            created_at=datetime(2026, 8, 19, 9, 0),
            status=status,
            description="test strategy",
            config={"rsi_min": 55},
        )
        StrategyRepository(self.db).save(s)
        return s


class TestSnapshotRepository(StorageTestCase):
    def test_roundtrip(self):
        snap = MarketSnapshot(
            timestamp=datetime(2026, 8, 19, 10, 30),
            nifty_spot=24985.5,
            options=[
                OptionSnapshot(
                    expiry="2026-08-27", strike=25000.0, option_type="CE",
                    ltp=142.35, bid=142.05, ask=142.65,
                    volume=125000, open_interest=4520000, oi_change=182000,
                    iv=12.4, delta=0.48, gamma=0.0021, theta=-8.2, vega=14.1,
                ),
                OptionSnapshot(
                    expiry="2026-08-27", strike=25000.0, option_type="PE",
                    ltp=151.20,
                ),
            ],
        )
        repo = SnapshotRepository(self.db)
        sid = repo.save(snap)
        loaded = repo.get(sid)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.timestamp, snap.timestamp)
        self.assertEqual(loaded.nifty_spot, snap.nifty_spot)
        self.assertEqual(loaded.atm_strike, 25000.0)
        self.assertEqual(len(loaded.options), 2)
        ce = loaded.option(25000.0, "CE")
        self.assertEqual(ce.open_interest, 4520000)
        self.assertEqual(ce.delta, 0.48)

    def test_get_missing(self):
        self.assertIsNone(SnapshotRepository(self.db).get(999))


class TestDecisionRepository(StorageTestCase):
    def test_roundtrip_signal(self):
        self._make_strategy()
        d = Decision(
            decision_id="DEC-20260819-103000-00001",
            timestamp=datetime(2026, 8, 19, 10, 30),
            strategy_version="STRAT-001",
            status=DecisionStatus.SIGNAL,
            direction=Direction.CALL,
            expiry="2026-08-27", strike=25000.0,
            entry_low=142.0, entry_high=145.0, stop_loss=128.0, target=170.0,
            max_holding_minutes=120,
            reason_codes=["TREND_BULLISH", "ABOVE_VWAP"],
            features={"rsi": 63.2, "trend": "BULLISH"},
        )
        repo = DecisionRepository(self.db)
        repo.save(d)
        loaded = repo.get(d.decision_id)
        self.assertEqual(loaded.direction, "CALL")
        self.assertEqual(loaded.option_type, "CE")
        self.assertEqual(loaded.reason_codes, ["TREND_BULLISH", "ABOVE_VWAP"])
        self.assertEqual(loaded.features["rsi"], 63.2)

    def test_unknown_strategy_rejected(self):
        d = Decision(
            decision_id="DEC-20260819-103000-00001",
            timestamp=datetime(2026, 8, 19, 10, 30),
            strategy_version="STRAT-999",  # not in strategy_versions
            status=DecisionStatus.NO_TRADE,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            DecisionRepository(self.db).save(d)

    def test_count_for_day(self):
        self._make_strategy()
        repo = DecisionRepository(self.db)
        for i in range(3):
            repo.save(Decision(
                decision_id="DEC-20260819-1030{:02d}-{:05d}".format(i, i + 1),
                timestamp=datetime(2026, 8, 19, 10, 30, i),
                strategy_version="STRAT-001",
                status=DecisionStatus.NO_TRADE,
            ))
        self.assertEqual(repo.count_for_day("20260819"), 3)
        self.assertEqual(repo.count_for_day("20260820"), 0)


class TestTradeRepository(StorageTestCase):
    def test_open_close_roundtrip(self):
        self._make_strategy()
        DecisionRepository(self.db).save(Decision(
            decision_id="DEC-20260819-103000-00001",
            timestamp=datetime(2026, 8, 19, 10, 30),
            strategy_version="STRAT-001",
            status=DecisionStatus.SIGNAL,
            direction=Direction.CALL,
            expiry="2026-08-27", strike=25000.0,
            entry_low=142.0, entry_high=145.0, stop_loss=128.0, target=170.0,
        ))
        t = PaperTrade(
            trade_id="TRD-20260819-00001",
            decision_id="DEC-20260819-103000-00001",
            status=TradeStatus.OPEN,
            entry_time=datetime(2026, 8, 19, 10, 32),
            entry_price=143.0, quantity=75,
        )
        repo = TradeRepository(self.db)
        repo.save(t)
        self.assertEqual(len(repo.open_trades()), 1)

        t.close(datetime(2026, 8, 19, 11, 5), 170.0, ExitReason.TARGET, costs=120.0)
        repo.save(t)  # upsert
        self.assertEqual(len(repo.open_trades()), 0)
        loaded = repo.get(t.trade_id)
        self.assertEqual(loaded.status, TradeStatus.CLOSED)
        self.assertEqual(loaded.result, "WIN")
        self.assertAlmostEqual(loaded.net_pnl, (170.0 - 143.0) * 75 - 120.0)


class TestStrategyRepository(StorageTestCase):
    def test_single_production_enforced(self):
        repo = StrategyRepository(self.db)
        self._make_strategy("STRAT-001", StrategyStatus.PRODUCTION)
        self._make_strategy("STRAT-002", StrategyStatus.CANDIDATE)

        # Direct INSERT of a second production version must fail at DB level.
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.conn.execute(
                "INSERT INTO strategy_versions "
                "(version_id, created_at, status) VALUES ('STRAT-003', '2026-08-19', 'PRODUCTION')"
            )

        # Promotion path retires the old production automatically.
        repo.set_status("STRAT-002", StrategyStatus.PRODUCTION)
        self.assertEqual(repo.production().version_id, "STRAT-002")
        self.assertEqual(repo.get("STRAT-001").status, StrategyStatus.RETIRED)

    def test_set_status_unknown_version(self):
        with self.assertRaises(ValueError):
            StrategyRepository(self.db).set_status("STRAT-042", StrategyStatus.CANDIDATE)

    def test_config_roundtrip(self):
        self._make_strategy()
        loaded = StrategyRepository(self.db).get("STRAT-001")
        self.assertEqual(loaded.config, {"rsi_min": 55})


class TestExperimentRepository(StorageTestCase):
    def test_roundtrip(self):
        self._make_strategy("STRAT-001")
        self._make_strategy("STRAT-002")
        e = Experiment(
            experiment_id="EXP-001",
            created_at=datetime(2026, 8, 19, 16, 0),
            hypothesis="Signals near resistance produce excessive failures.",
            baseline_version="STRAT-001",
            candidate_version="STRAT-002",
        )
        repo = ExperimentRepository(self.db)
        repo.save(e)

        e.status = "ACCEPTED"
        e.results = {"baseline_win_rate": 0.81, "candidate_win_rate": 0.89}
        e.conclusion = "Candidate improves quality; promote to paper."
        repo.save(e)  # upsert

        loaded = repo.get("EXP-001")
        self.assertEqual(loaded.status, "ACCEPTED")
        self.assertEqual(loaded.results["candidate_win_rate"], 0.89)


if __name__ == "__main__":
    unittest.main()
