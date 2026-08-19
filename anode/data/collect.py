"""Collect live NSE snapshots into a replay-format CSV.

Built for unattended runs on ephemeral machines (e.g. GitHub Actions):
rows are appended and flushed per snapshot, so whatever was collected
survives a crash or a killed runner. The CSV uses the exact column layout
CsvReplayProvider expects, so a collected day replays through the normal
pipeline with no conversion.

PAPER TRADING ONLY. This module only reads market data.
"""

import csv
import logging
import time as time_mod
from datetime import time as dtime
from pathlib import Path
from typing import Optional, Union

from anode.data.live import NseLiveProvider, now_ist
from anode.models import MarketSnapshot

log = logging.getLogger(__name__)

CSV_COLUMNS = (
    "timestamp", "nifty_spot", "expiry", "strike", "option_type", "ltp",
    "bid", "ask", "volume", "oi", "oi_change", "iv",
)


def append_snapshot(path: Union[str, Path], snap: MarketSnapshot) -> None:
    """Append one snapshot's option rows; create file with header if new."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    ts = snap.timestamp.isoformat(sep=" ")
    with open(path, "a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        if new_file:
            writer.writerow(CSV_COLUMNS)
        for o in snap.options:
            writer.writerow([
                ts, snap.nifty_spot, o.expiry, o.strike, o.option_type,
                o.ltp,
                "" if o.bid is None else o.bid,
                "" if o.ask is None else o.ask,
                "" if o.volume is None else o.volume,
                "" if o.open_interest is None else o.open_interest,
                "" if o.oi_change is None else o.oi_change,
                "" if o.iv is None else o.iv,
            ])
        fh.flush()


def _parse_hhmm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def collect(
    out_path: Union[str, Path],
    interval_seconds: int = 60,
    open_time: str = "09:15",
    until: str = "15:30",
    max_consecutive_failures: int = 15,
    provider: Optional[NseLiveProvider] = None,
) -> int:
    """Poll NSE from market open until `until` (IST), appending to CSV.

    Returns the number of snapshots written.
    """
    open_t = _parse_hhmm(open_time)
    end_t = _parse_hhmm(until)
    provider = provider or NseLiveProvider(interval_seconds=interval_seconds)

    written = 0
    failures = 0
    while True:
        now = now_ist()
        if now.time() >= end_t:
            log.info("end time %s IST reached — collected %d snapshots",
                     until, written)
            return written
        if now.time() < open_t:
            time_mod.sleep(min(30, interval_seconds))
            continue
        try:
            snap = provider.fetch_snapshot()
            append_snapshot(out_path, snap)
            written += 1
            failures = 0
            if written == 1 or written % 30 == 0:
                log.info("collected %d snapshots (last: spot=%s)",
                         written, snap.nifty_spot)
        except Exception as exc:
            failures += 1
            log.warning("fetch failed (%d in a row): %s", failures, exc)
            if failures >= max_consecutive_failures:
                log.error("%d consecutive failures — giving up with %d "
                          "snapshots collected", failures, written)
                return written
        time_mod.sleep(interval_seconds)
