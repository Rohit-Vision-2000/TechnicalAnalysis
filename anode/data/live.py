"""Live NSE option-chain provider (EXPERIMENTAL — verify on a live market).

Polls the public NSE option-chain endpoint for NIFTY and normalizes each
response into a MarketSnapshot. NSE requires browser-like headers and a
cookie handshake; the endpoint is rate-limited and occasionally refuses
requests, so every fetch failure is logged and skipped — the session
continues on the next poll.

PAPER TRADING ONLY. This module only READS market data; it can never place
an order.
"""

import gzip
import io
import json
import logging
import time as time_mod
import urllib.request
from datetime import datetime, time as dtime, timedelta, timezone
from http.cookiejar import CookieJar
from typing import Iterator, List, Optional

from anode.data.provider import MarketDataProvider
from anode.models import MarketSnapshot, OptionSnapshot

log = logging.getLogger(__name__)

NSE_HOME = "https://www.nseindia.com/option-chain"
# NSE retired /api/option-chain-indices (404 as of 2026-08-19). The v3 API
# requires an explicit expiry, which comes from the contract-info endpoint.
NSE_CONTRACT_INFO = (
    "https://www.nseindia.com/api/option-chain-contract-info?symbol=NIFTY"
)
NSE_API = (
    "https://www.nseindia.com/api/option-chain-v3"
    "?type=Indices&symbol=NIFTY&expiry={expiry}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip",
    "Referer": "https://www.nseindia.com/option-chain",
}

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Market time is IST (no DST). Snapshots and session clocks must use IST
# regardless of the host's local timezone (GitHub runners are UTC).
IST = timezone(timedelta(hours=5, minutes=30), "IST")


def now_ist() -> datetime:
    """Naive IST wall-clock time (matches stored snapshot timestamps)."""
    return datetime.now(IST).replace(tzinfo=None)


def _parse_expiry(s: str) -> str:
    """'27-Aug-2026' -> '2026-08-27'."""
    day, mon, year = s.split("-")
    return "{}-{:02d}-{:02d}".format(year, MONTHS[mon], int(day))


class NseLiveProvider(MarketDataProvider):
    def __init__(
        self,
        interval_seconds: int = 60,
        duration_minutes: Optional[int] = None,
        strikes_each_side: int = 10,
        strike_step: int = 50,
        session_end: str = "15:30",
        timeout_seconds: int = 15,
    ) -> None:
        self.interval = interval_seconds
        self.duration_minutes = duration_minutes
        self.strikes_each_side = strikes_each_side
        self.strike_step = strike_step
        h, m = session_end.split(":")
        self.session_end = dtime(int(h), int(m))
        self.timeout = timeout_seconds

        self._jar = CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._jar)
        )
        self._primed = False
        self._nearest_expiry = None  # raw NSE format, e.g. '25-Aug-2026'

    # ------------------------------------------------------------------ HTTP

    def _get(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers=HEADERS)
        with self._opener.open(req, timeout=self.timeout) as resp:
            data = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
            return data

    def _prime_cookies(self) -> None:
        self._get(NSE_HOME)
        self._primed = True

    def _fetch_nearest_expiry(self) -> str:
        raw = self._get(NSE_CONTRACT_INFO)
        payload = json.loads(raw.decode("utf-8"))
        expiries = payload.get("expiryDates") or []
        if not expiries:
            raise ValueError("NSE contract-info returned no expiry dates")
        return expiries[0]

    def _fetch_chain(self) -> bytes:
        if self._nearest_expiry is None:
            self._nearest_expiry = self._fetch_nearest_expiry()
        return self._get(NSE_API.format(expiry=self._nearest_expiry))

    def fetch_snapshot(self) -> MarketSnapshot:
        """One normalized snapshot from the NSE option-chain API."""
        if not self._primed:
            self._prime_cookies()
        try:
            raw = self._fetch_chain()
        except Exception:
            # session cookies may have expired — re-prime once and retry
            # (also re-resolve the expiry in case the cached one went stale)
            self._primed = False
            self._nearest_expiry = None
            self._prime_cookies()
            raw = self._fetch_chain()
        payload = json.loads(raw.decode("utf-8"))
        return self._normalize(payload)

    # ------------------------------------------------------------- normalize

    def _normalize(self, payload: dict) -> MarketSnapshot:
        records = payload["records"]
        spot = float(records["underlyingValue"])
        nearest_raw = self._nearest_expiry
        if not nearest_raw:
            raise ValueError("no expiry resolved for NSE chain")
        nearest_iso = _parse_expiry(nearest_raw)

        atm = round(spot / self.strike_step) * self.strike_step
        lo = atm - self.strikes_each_side * self.strike_step
        hi = atm + self.strikes_each_side * self.strike_step

        options: List[OptionSnapshot] = []
        for row in records.get("data", []):
            # v3 rows carry the expiry under 'expiryDates' (raw format)
            if row.get("expiryDates") not in (None, nearest_raw):
                continue
            strike = float(row["strikePrice"])
            if not (lo <= strike <= hi):
                continue
            for side in ("CE", "PE"):
                leg = row.get(side)
                if not leg:
                    continue
                ltp = float(leg.get("lastPrice") or 0.0)
                if ltp <= 0:
                    continue
                bid = float(leg.get("buyPrice1") or 0.0) or None
                ask = float(leg.get("sellPrice1") or 0.0) or None
                iv = float(leg.get("impliedVolatility") or 0.0) or None
                options.append(OptionSnapshot(
                    expiry=nearest_iso,
                    strike=strike,
                    option_type=side,
                    ltp=ltp,
                    bid=bid,
                    ask=ask,
                    volume=int(leg.get("totalTradedVolume") or 0),
                    open_interest=int(leg.get("openInterest") or 0),
                    oi_change=int(leg.get("changeinOpenInterest") or 0),
                    iv=iv,
                ))
        if not options:
            raise ValueError("NSE payload produced no usable option rows")
        return MarketSnapshot(
            timestamp=now_ist().replace(microsecond=0),
            nifty_spot=spot,
            options=options,
        )

    # ---------------------------------------------------------------- stream

    def snapshots(self) -> Iterator[MarketSnapshot]:
        start = time_mod.monotonic()
        failures = 0
        while True:
            now = now_ist()
            if now.time() >= self.session_end:
                log.info("session end %s reached — stopping feed", self.session_end)
                return
            if (
                self.duration_minutes is not None
                and time_mod.monotonic() - start >= self.duration_minutes * 60
            ):
                log.info("duration limit reached — stopping feed")
                return
            try:
                snap = self.fetch_snapshot()
                failures = 0
                yield snap
            except Exception as exc:
                failures += 1
                log.warning("NSE fetch failed (%d in a row): %s", failures, exc)
                if failures >= 10:
                    log.error("10 consecutive fetch failures — stopping feed")
                    return
            time_mod.sleep(self.interval)
