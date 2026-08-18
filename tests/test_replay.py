import tempfile
import unittest
from pathlib import Path

from anode.data.replay import CsvReplayProvider

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample" / "sample_snapshots.csv"


class TestCsvReplayProvider(unittest.TestCase):
    def test_sample_file_groups_by_timestamp(self):
        snaps = list(CsvReplayProvider(SAMPLE))
        self.assertEqual(len(snaps), 3)
        first = snaps[0]
        self.assertEqual(first.nifty_spot, 24985.50)
        self.assertEqual(len(first.options), 4)
        self.assertEqual(first.atm_strike, 25000.0)
        self.assertEqual(first.nearest_expiry, "2026-08-27")
        ce = first.option(25000.0, "CE")
        self.assertEqual(ce.ltp, 142.35)
        self.assertEqual(ce.open_interest, 4520000)
        # timestamps strictly increase across the sample
        self.assertLess(snaps[0].timestamp, snaps[1].timestamp)
        self.assertLess(snaps[1].timestamp, snaps[2].timestamp)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            CsvReplayProvider("does_not_exist.csv")

    def _write_csv(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8"
        )
        f.write(content)
        f.close()
        self.addCleanup(Path(f.name).unlink)
        return Path(f.name)

    def test_missing_columns_rejected(self):
        path = self._write_csv("timestamp,nifty_spot\n2026-08-19 10:30:00,25000\n")
        with self.assertRaises(ValueError) as ctx:
            list(CsvReplayProvider(path))
        self.assertIn("missing required columns", str(ctx.exception))

    def test_out_of_order_rejected(self):
        path = self._write_csv(
            "timestamp,nifty_spot,expiry,strike,option_type,ltp\n"
            "2026-08-19 10:31:00,25000,2026-08-27,25000,CE,140\n"
            "2026-08-19 10:30:00,25000,2026-08-27,25000,CE,141\n"
        )
        with self.assertRaises(ValueError) as ctx:
            list(CsvReplayProvider(path))
        self.assertIn("out of order", str(ctx.exception))

    def test_optional_fields_blank(self):
        path = self._write_csv(
            "timestamp,nifty_spot,expiry,strike,option_type,ltp,bid,ask,iv\n"
            "2026-08-19 10:30:00,25000,2026-08-27,25000,CE,140,,,\n"
        )
        snaps = list(CsvReplayProvider(path))
        self.assertEqual(len(snaps), 1)
        opt = snaps[0].options[0]
        self.assertIsNone(opt.bid)
        self.assertIsNone(opt.iv)
        self.assertIsNone(opt.spread)

    def test_bad_row_reports_line_number(self):
        path = self._write_csv(
            "timestamp,nifty_spot,expiry,strike,option_type,ltp\n"
            "2026-08-19 10:30:00,25000,2026-08-27,25000,XX,140\n"
        )
        with self.assertRaises(ValueError) as ctx:
            list(CsvReplayProvider(path))
        self.assertIn(":2:", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
