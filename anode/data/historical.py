"""Convert Kaggle 2024 NIFTY options data into replay-format CSVs.

Source dataset (senthilkumarvaithi/historical-nifty-options-2024-all-expiries,
Apache 2.0): per trade-day-per-expiry option files with 1-minute bars
(`datetime,strike_price,right,open,high,low,close,open_interest,volume`,
datetime is HH:MM) plus monthly spot files
(`datetime,open,high,low,close,volume`, datetime is YYYY-MM-DD HH:MM).

Output matches CsvReplayProvider's layout, so a converted day replays
through the normal pipeline. Historical data has NO bid/ask and NO IV —
those columns stay blank, and any research on this data must account for
estimated spreads. oi_change is derived per contract from consecutive
minutes.
"""

import csv
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

log = logging.getLogger(__name__)

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

REPLAY_COLUMNS = (
    "timestamp", "nifty_spot", "expiry", "strike", "option_type", "ltp",
    "bid", "ask", "volume", "oi", "oi_change", "iv",
)


def parse_ddmmmyy(s: str) -> date:
    """'02MAY24' -> date(2024, 5, 2)."""
    s = s.strip().upper()
    return date(2000 + int(s[5:7]), MONTHS[s[2:5]], int(s[:2]))


def load_spot_minutes(path: Union[str, Path], day: date) -> Dict[str, float]:
    """{'HH:MM': close} for one trade day from a monthly spot file."""
    prefix = day.isoformat()
    out: Dict[str, float] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            dt = row["datetime"].strip()
            if dt.startswith(prefix):
                out[dt[11:16]] = float(row["close"])
    return out


def convert_day(
    options_path: Union[str, Path],
    spot_minutes: Dict[str, float],
    expiry: date,
    trade_day: date,
    out_path: Union[str, Path],
    strikes_each_side: int = 10,
    strike_step: int = 50,
) -> int:
    """One options file + spot minutes -> one replay CSV. Returns snapshots written."""
    # minute -> {(strike, right): (close, oi, volume)}
    minutes: Dict[str, Dict[Tuple[float, str], Tuple[float, int, int]]] = {}
    with open(options_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            hhmm = row["datetime"].strip()[:5]
            key = (float(row["strike_price"]), row["right"].strip().upper())
            minutes.setdefault(hhmm, {})[key] = (
                float(row["close"]),
                int(float(row["open_interest"] or 0)),
                int(float(row["volume"] or 0)),
            )

    expiry_iso = expiry.isoformat()
    prev_oi: Dict[Tuple[float, str], int] = {}
    written = 0
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(REPLAY_COLUMNS)
        for hhmm in sorted(minutes):
            spot = spot_minutes.get(hhmm)
            if spot is None:
                continue
            atm = round(spot / strike_step) * strike_step
            lo = atm - strikes_each_side * strike_step
            hi = atm + strikes_each_side * strike_step
            ts = "{} {}:00".format(trade_day.isoformat(), hhmm)
            rows = []
            for (strike, right), (close, oi, vol) in sorted(minutes[hhmm].items()):
                if not (lo <= strike <= hi) or close <= 0:
                    continue
                change = oi - prev_oi.get((strike, right), oi)
                rows.append([ts, spot, expiry_iso, strike, right, close,
                             "", "", vol, oi, change, ""])
            # update prev_oi for every contract seen this minute (windowed
            # contracts included), so re-entering the window stays sane
            for key_, (_, oi_, _) in minutes[hhmm].items():
                prev_oi[key_] = oi_
            if rows:
                w.writerows(rows)
                written += 1
    log.info("%s: %d snapshots -> %s", trade_day, written, out_path)
    return written


def nearest_expiry_files(
    filenames: List[str],
) -> Dict[date, Tuple[str, date]]:
    """Map trade_day -> (filename, expiry) picking the nearest expiry.

    Filenames look like '.../NIFTY-02MAY24-01APR24.csv'
    (NIFTY-{expiry}-{trade day}).
    """
    best: Dict[date, Tuple[str, date]] = {}
    for name in filenames:
        base = name.rsplit("/", 1)[-1]
        if not base.startswith("NIFTY-") or not base.endswith(".csv"):
            continue
        try:
            _, exp_s, day_s = base[:-4].split("-")
            expiry = parse_ddmmmyy(exp_s)
            trade_day = parse_ddmmmyy(day_s)
        except (ValueError, KeyError, IndexError):
            continue
        if expiry < trade_day:
            continue
        cur = best.get(trade_day)
        if cur is None or expiry < cur[1]:
            best[trade_day] = (name, expiry)
    return best
