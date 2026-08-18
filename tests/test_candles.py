import unittest
from datetime import datetime

from anode.analysis.candles import CandleBuilder


def ts(h, m, s=0):
    return datetime(2026, 8, 19, h, m, s)


class TestCandleBuilder(unittest.TestCase):
    def test_aggregation_5min(self):
        b = CandleBuilder(5)
        self.assertIsNone(b.update(ts(9, 15), 100.0))
        self.assertIsNone(b.update(ts(9, 16), 105.0))
        self.assertIsNone(b.update(ts(9, 19), 95.0))
        completed = b.update(ts(9, 20), 102.0)  # crosses into next bucket
        self.assertIsNotNone(completed)
        self.assertEqual(completed.start, ts(9, 15))
        self.assertEqual(completed.open, 100.0)
        self.assertEqual(completed.high, 105.0)
        self.assertEqual(completed.low, 95.0)
        self.assertEqual(completed.close, 95.0)
        self.assertEqual(b.current.open, 102.0)

    def test_bucket_alignment(self):
        b = CandleBuilder(5)
        b.update(ts(9, 17), 100.0)  # first tick mid-bucket
        self.assertEqual(b.current.start, ts(9, 15))

    def test_out_of_order_rejected(self):
        b = CandleBuilder(5)
        b.update(ts(9, 16), 100.0)
        with self.assertRaises(ValueError):
            b.update(ts(9, 15), 99.0)

    def test_flush(self):
        b = CandleBuilder(5)
        b.update(ts(9, 15), 100.0)
        c = b.flush()
        self.assertIsNotNone(c)
        self.assertEqual(len(b.candles), 1)
        self.assertIsNone(b.current)

    def test_gap_skips_buckets(self):
        b = CandleBuilder(5)
        b.update(ts(9, 15), 100.0)
        completed = b.update(ts(10, 0), 110.0)  # 45-minute gap
        self.assertEqual(completed.start, ts(9, 15))
        self.assertEqual(b.current.start, ts(10, 0))

    def test_all_candles_include_current(self):
        b = CandleBuilder(5)
        b.update(ts(9, 15), 100.0)
        b.update(ts(9, 20), 101.0)
        self.assertEqual(len(b.all_candles(include_current=False)), 1)
        self.assertEqual(len(b.all_candles(include_current=True)), 2)

    def test_volume_accumulates(self):
        b = CandleBuilder(5)
        b.update(ts(9, 15), 100.0, volume=10)
        b.update(ts(9, 16), 101.0, volume=15)
        self.assertEqual(b.current.volume, 25)


if __name__ == "__main__":
    unittest.main()
