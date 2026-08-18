"""CSV replay provider.

Replays historical market data from a CSV file, one row per option contract,
grouped into MarketSnapshot objects by timestamp.

Expected CSV columns (header required):

    timestamp    ISO-8601, e.g. 2026-08-19 10:32:00 (same for all rows of one snapshot)
    nifty_spot   float
    expiry       ISO date, e.g. 2026-08-27
    strike       float
    option_type  CE | PE
    ltp          float
    bid, ask, volume, oi, oi_change, iv,
    delta, gamma, theta, vega            (optional; blank = unknown)

Rows must be sorted by timestamp. Consecutive rows with the same timestamp
form one snapshot.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional, Union

from anode.data.provider import MarketDataProvider
from anode.models import MarketSnapshot, OptionSnapshot

log = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("timestamp", "nifty_spot", "expiry", "strike", "option_type", "ltp")


def _opt_float(value: str) -> Optional[float]:
    value = (value or "").strip()
    return float(value) if value else None


def _opt_int(value: str) -> Optional[int]:
    value = (value or "").strip()
    return int(float(value)) if value else None


class CsvReplayProvider(MarketDataProvider):
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError("replay file not found: {}".format(self.path))

    def snapshots(self) -> Iterator[MarketSnapshot]:
        with open(self.path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                return
            missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
            if missing:
                raise ValueError(
                    "replay file {} missing required columns: {}".format(
                        self.path, ", ".join(missing)
                    )
                )

            current_ts: Optional[str] = None
            current_spot: Optional[float] = None
            options: List[OptionSnapshot] = []
            last_emitted_ts: Optional[datetime] = None

            for line_no, row in enumerate(reader, start=2):
                ts = row["timestamp"].strip()
                if not ts:
                    raise ValueError(
                        "{}:{}: empty timestamp".format(self.path, line_no)
                    )
                if current_ts is not None and ts != current_ts:
                    snap = self._build(current_ts, current_spot, options)
                    last_emitted_ts = self._check_order(snap, last_emitted_ts)
                    yield snap
                    options = []
                current_ts = ts
                current_spot = float(row["nifty_spot"])
                options.append(self._parse_option(row, line_no))

            if current_ts is not None:
                snap = self._build(current_ts, current_spot, options)
                self._check_order(snap, last_emitted_ts)
                yield snap

    def _parse_option(self, row: dict, line_no: int) -> OptionSnapshot:
        try:
            return OptionSnapshot(
                expiry=row["expiry"].strip(),
                strike=float(row["strike"]),
                option_type=row["option_type"].strip().upper(),
                ltp=float(row["ltp"]),
                bid=_opt_float(row.get("bid", "")),
                ask=_opt_float(row.get("ask", "")),
                volume=_opt_int(row.get("volume", "")),
                open_interest=_opt_int(row.get("oi", "")),
                oi_change=_opt_int(row.get("oi_change", "")),
                iv=_opt_float(row.get("iv", "")),
                delta=_opt_float(row.get("delta", "")),
                gamma=_opt_float(row.get("gamma", "")),
                theta=_opt_float(row.get("theta", "")),
                vega=_opt_float(row.get("vega", "")),
            )
        except (ValueError, KeyError) as exc:
            raise ValueError(
                "{}:{}: invalid option row: {}".format(self.path, line_no, exc)
            )

    @staticmethod
    def _build(ts: str, spot: float, options: List[OptionSnapshot]) -> MarketSnapshot:
        return MarketSnapshot(
            timestamp=datetime.fromisoformat(ts),
            nifty_spot=spot,
            options=list(options),
        )

    @staticmethod
    def _check_order(
        snap: MarketSnapshot, last: Optional[datetime]
    ) -> datetime:
        if last is not None and snap.timestamp < last:
            raise ValueError(
                "replay data out of order: {} after {}".format(snap.timestamp, last)
            )
        return snap.timestamp
