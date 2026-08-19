import csv
import gzip
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from anode.data.historical import (
    convert_day,
    load_spot_minutes,
    nearest_expiry_files,
    parse_ddmmmyy,
)
from anode.data.replay import CsvReplayProvider


class TestParsing(unittest.TestCase):
    def test_parse_ddmmmyy(self):
        self.assertEqual(parse_ddmmmyy("02MAY24"), date(2024, 5, 2))
        self.assertEqual(parse_ddmmmyy("29dec24"), date(2024, 12, 29))

    def test_nearest_expiry_picks_soonest_future(self):
        got = nearest_expiry_files([
            "2024/2024APR/NIFTY-02MAY24-01APR24.csv",
            "2024/2024APR/NIFTY-04APR24-01APR24.csv",
            "2024/2024APR/NIFTY-25APR24-01APR24.csv",
            "garbage.txt",
        ])
        self.assertEqual(got[date(2024, 4, 1)][1], date(2024, 4, 4))

    def test_expired_contracts_ignored(self):
        got = nearest_expiry_files(["NIFTY-04APR24-05APR24.csv"])
        self.assertEqual(got, {})


class TestConvertDay(unittest.TestCase):
    def _write_options(self, path, rows):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["datetime", "strike_price", "right", "open", "high",
                        "low", "close", "open_interest", "volume"])
            w.writerows(rows)

    def test_convert_and_replay_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            opts = tmp / "opts.csv"
            self._write_options(opts, [
                ["09:15", "22450", "CE", "1", "1", "1", "100.5", "1000", "10"],
                ["09:15", "22450", "PE", "1", "1", "1", "90.0", "2000", "5"],
                ["09:16", "22450", "CE", "1", "1", "1", "101.0", "1100", "12"],
                ["09:16", "22450", "PE", "1", "1", "1", "89.0", "2000", "0"],
                # far strike outside +/-10*50 window around 22450 spot
                ["09:15", "30000", "CE", "1", "1", "1", "0.5", "10", "0"],
            ])
            spot = {"09:15": 22450.0, "09:16": 22452.5}
            out = tmp / "day.csv"
            n = convert_day(opts, spot, date(2024, 4, 4), date(2024, 4, 1), out)
            self.assertEqual(n, 2)

            snaps = list(CsvReplayProvider(out).snapshots())
            self.assertEqual(len(snaps), 2)
            self.assertEqual(len(snaps[0].options), 2)  # far strike excluded
            ce_16 = [o for o in snaps[1].options if o.option_type == "CE"][0]
            self.assertEqual(ce_16.oi_change, 100)  # 1100 - 1000
            self.assertEqual(snaps[0].options[0].expiry, "2024-04-04")
            self.assertIsNone(snaps[0].options[0].bid)

    def test_minute_without_spot_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            opts = tmp / "opts.csv"
            self._write_options(opts, [
                ["09:15", "22450", "CE", "1", "1", "1", "100.5", "1000", "10"],
                ["09:16", "22450", "CE", "1", "1", "1", "101.0", "1100", "12"],
            ])
            out = tmp / "day.csv"
            n = convert_day(opts, {"09:16": 22450.0}, date(2024, 4, 4),
                            date(2024, 4, 1), out)
            self.assertEqual(n, 1)


class TestGzipReplay(unittest.TestCase):
    def test_provider_reads_gz(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plain = tmp / "day.csv"
            with open(plain, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["timestamp", "nifty_spot", "expiry", "strike",
                            "option_type", "ltp"])
                w.writerow(["2024-04-01 09:15:00", "22450.0", "2024-04-04",
                            "22450", "CE", "100.5"])
            gz = tmp / "day.csv.gz"
            with open(plain, "rb") as src, gzip.open(gz, "wb") as dst:
                shutil.copyfileobj(src, dst)
            snaps = list(CsvReplayProvider(gz).snapshots())
            self.assertEqual(len(snaps), 1)
            self.assertEqual(snaps[0].options[0].ltp, 100.5)


class TestLoadSpot(unittest.TestCase):
    def test_filters_by_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "spot.csv"
            with open(p, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["datetime", "open", "high", "low", "close", "volume"])
                w.writerow(["2024-04-01 09:15", "1", "1", "1", "22479.4", "0"])
                w.writerow(["2024-04-02 09:15", "1", "1", "1", "22600.0", "0"])
            got = load_spot_minutes(p, date(2024, 4, 1))
            self.assertEqual(got, {"09:15": 22479.4})
