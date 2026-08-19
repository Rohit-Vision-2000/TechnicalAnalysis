import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from anode.data.collect import append_snapshot
from anode.data.replay import CsvReplayProvider
from anode.models import MarketSnapshot, OptionSnapshot


def snap(ts, spot):
    return MarketSnapshot(
        timestamp=ts,
        nifty_spot=spot,
        options=[
            OptionSnapshot(expiry="2026-08-25", strike=24000.0,
                           option_type="CE", ltp=120.5, bid=120.0, ask=121.0,
                           volume=500, open_interest=1000, oi_change=50,
                           iv=11.2),
            OptionSnapshot(expiry="2026-08-25", strike=24000.0,
                           option_type="PE", ltp=98.0, bid=None, ask=None,
                           volume=None, open_interest=None, oi_change=None,
                           iv=None),
        ],
    )


class TestCollectRoundTrip(unittest.TestCase):
    def test_appended_csv_replays_identically(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "day.csv"
            s1 = snap(datetime(2026, 8, 20, 9, 15, 8), 24050.0)
            s2 = snap(datetime(2026, 8, 20, 9, 16, 9), 24061.5)
            append_snapshot(path, s1)
            append_snapshot(path, s2)

            got = list(CsvReplayProvider(path).snapshots())
            self.assertEqual(len(got), 2)
            self.assertEqual(got[0].timestamp, s1.timestamp)
            self.assertEqual(got[1].nifty_spot, 24061.5)
            ce = got[0].options[0]
            self.assertEqual((ce.option_type, ce.ltp, ce.bid, ce.ask), ("CE", 120.5, 120.0, 121.0))
            self.assertEqual((ce.volume, ce.open_interest, ce.oi_change, ce.iv), (500, 1000, 50, 11.2))
            pe = got[0].options[1]
            self.assertIsNone(pe.bid)
            self.assertIsNone(pe.iv)
            # volume defaults: OptionSnapshot may normalize missing ints
            self.assertEqual(pe.ltp, 98.0)
