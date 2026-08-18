"""Synthetic market-data generator — FOR TESTING AND DEMOS ONLY.

Generates a deterministic (seeded) intraday session of 1-minute snapshots:
a random-walk NIFTY spot with drift segments, and a rough option chain
(intrinsic + decaying time value, OI concentrated near round strikes).

Synthetic data exercises the pipeline; it proves NOTHING about strategy
performance. Never mix it with real data: snapshots generated here should be
stored with source='synthetic' and kept out of research conclusions.
"""

import random
from datetime import date, datetime, timedelta
from typing import Iterator, List

from anode.data.provider import MarketDataProvider
from anode.models import MarketSnapshot, OptionSnapshot

STRIKE_STEP = 50


class SyntheticDayProvider(MarketDataProvider):
    def __init__(
        self,
        session_date: str = "2026-08-19",
        start_spot: float = 25000.0,
        minutes: int = 375,  # 09:15–15:30
        seed: int = 42,
        strikes_each_side: int = 5,
        expiry: str = "2026-08-27",
    ) -> None:
        self.session_date = session_date
        self.start_spot = start_spot
        self.minutes = minutes
        self.seed = seed
        self.strikes_each_side = strikes_each_side
        self.expiry = expiry

    def snapshots(self) -> Iterator[MarketSnapshot]:
        rng = random.Random(self.seed)
        start = datetime.fromisoformat("{} 09:15:00".format(self.session_date))
        spot = self.start_spot

        # Piecewise drift: alternate trending and sideways segments.
        drift = 0.0
        segment_left = 0

        # Persistent OI per (strike, type), mutated tick to tick.
        oi: dict = {}

        for i in range(self.minutes):
            ts = start + timedelta(minutes=i)
            if segment_left <= 0:
                segment_left = rng.randint(30, 90)
                drift = rng.choice([-0.35, -0.15, 0.0, 0.0, 0.15, 0.35])
            segment_left -= 1
            spot = max(1.0, spot + drift + rng.gauss(0, 2.2))

            options = self._chain(rng, ts, spot, i, oi)
            yield MarketSnapshot(
                timestamp=ts, nifty_spot=round(spot, 2), options=options
            )

    def _chain(
        self, rng: random.Random, ts: datetime, spot: float, minute: int, oi: dict
    ) -> List[OptionSnapshot]:
        atm = round(spot / STRIKE_STEP) * STRIKE_STEP
        # crude time value that decays through the session
        base_tv = 150.0 * (1.0 - 0.4 * minute / max(1, self.minutes))
        options: List[OptionSnapshot] = []
        for k in range(-self.strikes_each_side, self.strikes_each_side + 1):
            strike = atm + k * STRIKE_STEP
            for opt_type in ("CE", "PE"):
                intrinsic = max(
                    0.0, (spot - strike) if opt_type == "CE" else (strike - spot)
                )
                distance = abs(spot - strike)
                tv = base_tv * max(0.15, 1.0 - distance / 600.0)
                ltp = max(0.05, intrinsic + tv + rng.gauss(0, 1.5))
                spread = max(0.05, ltp * rng.uniform(0.001, 0.004))

                key = (strike, opt_type)
                if key not in oi:
                    # OI concentrated near ATM and at round-500 strikes
                    base_oi = int(3_000_000 * max(0.2, 1.0 - distance / 800.0))
                    if strike % 500 == 0:
                        base_oi = int(base_oi * 1.6)
                    oi[key] = base_oi
                change = rng.randint(-40_000, 60_000)
                oi[key] = max(0, oi[key] + change)

                iv = max(
                    6.0,
                    11.0 + distance / 250.0
                    + (0.8 if opt_type == "PE" else 0.0)  # put skew
                    + rng.gauss(0, 0.3),
                )
                options.append(
                    OptionSnapshot(
                        expiry=self.expiry,
                        strike=float(strike),
                        option_type=opt_type,
                        ltp=round(ltp, 2),
                        bid=round(ltp - spread / 2, 2),
                        ask=round(ltp + spread / 2, 2),
                        volume=rng.randint(5_000, 150_000),
                        open_interest=oi[key],
                        oi_change=change,
                        iv=round(iv, 2),
                    )
                )
        return options


class SyntheticMultiDayProvider(MarketDataProvider):
    """Several consecutive synthetic sessions (weekdays only), with price
    continuity from one day's close to the next day's open.

    Same disclaimer as SyntheticDayProvider: pipeline exercise only.
    """

    def __init__(
        self,
        days: int = 5,
        start_date: str = "2026-08-03",
        start_spot: float = 25000.0,
        seed: int = 42,
        expiry_weekday: int = 3,  # Thursday-style weekly expiry
    ) -> None:
        if days <= 0:
            raise ValueError("days must be positive")
        self.days = days
        self.start_date = date.fromisoformat(start_date)
        self.start_spot = start_spot
        self.seed = seed
        self.expiry_weekday = expiry_weekday

    def _next_expiry(self, d: date) -> str:
        offset = (self.expiry_weekday - d.weekday()) % 7
        return (d + timedelta(days=offset)).isoformat()

    def snapshots(self) -> Iterator[MarketSnapshot]:
        d = self.start_date
        spot = self.start_spot
        produced = 0
        while produced < self.days:
            if d.weekday() >= 5:  # skip weekends
                d += timedelta(days=1)
                continue
            day_provider = SyntheticDayProvider(
                session_date=d.isoformat(),
                start_spot=spot,
                seed=self.seed + produced,
                expiry=self._next_expiry(d),
            )
            last = None
            for snap in day_provider:
                last = snap
                yield snap
            if last is not None:
                # small overnight gap for realism
                gap = random.Random(self.seed * 1000 + produced).gauss(0, 30)
                spot = max(1.0, last.nifty_spot + gap)
            produced += 1
            d += timedelta(days=1)
