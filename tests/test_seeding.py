import unittest
from datetime import datetime

from anode.models import MarketSnapshot, OptionSnapshot, StrategyVersion
from anode.research.backtest import ListProvider, run_session
from anode.data.synthetic import SyntheticDayProvider
from anode.storage import Database, SnapshotRepository


def make_strategy():
    return StrategyVersion(
        version_id="STRAT-001",
        created_at=datetime(2026, 8, 1, 9, 0),
        status="CANDIDATE",
        config={},
    )


class TestSeedSnapshots(unittest.TestCase):
    """Indicator warmup must survive an intraday restart via seeding."""

    @classmethod
    def setUpClass(cls):
        cls.day = list(SyntheticDayProvider(seed=7))
        # enough history for every core indicator (50 five-minute candles)
        cls.split = 300
        cls.seeds = cls.day[: cls.split]
        cls.rest = cls.day[cls.split :]

    def test_without_seeds_restart_is_cold(self):
        result = run_session(ListProvider(self.rest), make_strategy(), {})
        self.assertIn("FAIL_WARMUP", result.decisions[0].reason_codes)

    def test_with_seeds_restart_is_warm(self):
        result = run_session(
            ListProvider(self.rest), make_strategy(), {},
            seed_snapshots=self.seeds,
        )
        self.assertNotIn("FAIL_WARMUP", result.decisions[0].reason_codes)

    def test_seeds_produce_no_output(self):
        result = run_session(
            ListProvider([]), make_strategy(), {}, seed_snapshots=self.seeds
        )
        self.assertEqual(result.snapshots_processed, 0)
        self.assertEqual(result.decisions, [])
        self.assertEqual(result.trades, [])


class TestForDay(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.db.init_schema()
        self.repo = SnapshotRepository(self.db)

    def tearDown(self):
        self.db.close()

    def _snap(self, ts):
        return MarketSnapshot(
            timestamp=ts,
            nifty_spot=24000.0,
            options=[
                OptionSnapshot(expiry="2026-08-25", strike=24000.0,
                               option_type="CE", ltp=100.0)
            ],
        )

    def test_filters_by_day_and_source_in_order(self):
        self.repo.save(self._snap(datetime(2026, 8, 19, 10, 1)), source="live")
        self.repo.save(self._snap(datetime(2026, 8, 19, 9, 30)), source="live")
        self.repo.save(self._snap(datetime(2026, 8, 19, 11, 0)), source="synthetic")
        self.repo.save(self._snap(datetime(2026, 8, 18, 10, 0)), source="live")

        got = self.repo.for_day("2026-08-19", "live")
        self.assertEqual(len(got), 2)
        self.assertEqual(
            [s.timestamp for s in got],
            [datetime(2026, 8, 19, 9, 30), datetime(2026, 8, 19, 10, 1)],
        )
        # options travel with the snapshot (chain analysis needs them)
        self.assertEqual(len(got[0].options), 1)

    def test_empty_day(self):
        self.assertEqual(self.repo.for_day("2026-08-20", "live"), [])
