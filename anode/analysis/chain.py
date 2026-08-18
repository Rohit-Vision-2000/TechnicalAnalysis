"""Option-chain analysis.

Extracts decision-relevant metrics from a MarketSnapshot's option chain,
restricted to one expiry (the nearest by default): PCR, ATM IV, IV skew,
max pain, OI-based support/resistance, aggregate OI flow, and ATM liquidity.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from anode.models import MarketSnapshot, OptionSnapshot


@dataclass
class ChainAnalysis:
    expiry: Optional[str] = None
    atm_strike: Optional[float] = None

    pcr_oi: Optional[float] = None
    pcr_volume: Optional[float] = None

    atm_iv: Optional[float] = None  # mean of ATM CE / PE IV
    atm_iv_ce: Optional[float] = None
    atm_iv_pe: Optional[float] = None
    iv_skew: Optional[float] = None  # OTM put IV - OTM call IV

    max_pain_strike: Optional[float] = None
    oi_resistance_strike: Optional[float] = None  # max call OI
    oi_support_strike: Optional[float] = None  # max put OI

    total_call_oi: Optional[int] = None
    total_put_oi: Optional[int] = None
    total_call_oi_change: Optional[int] = None
    total_put_oi_change: Optional[int] = None

    atm_spread_pct: Optional[float] = None  # ATM CE/PE avg spread / mid

    def to_dict(self) -> Dict:
        return dict(self.__dict__)


def analyze_chain(
    snapshot: MarketSnapshot,
    expiry: Optional[str] = None,
    skew_offset_points: float = 200.0,
) -> ChainAnalysis:
    expiry = expiry or snapshot.nearest_expiry
    chain = [o for o in snapshot.options if o.expiry == expiry]
    result = ChainAnalysis(expiry=expiry)
    if not chain:
        return result

    calls = [o for o in chain if o.option_type == "CE"]
    puts = [o for o in chain if o.option_type == "PE"]
    strikes = sorted({o.strike for o in chain})
    atm = min(strikes, key=lambda s: abs(s - snapshot.nifty_spot))
    result.atm_strike = atm

    # --- PCR ---
    call_oi = sum(o.open_interest or 0 for o in calls)
    put_oi = sum(o.open_interest or 0 for o in puts)
    result.total_call_oi = call_oi or None
    result.total_put_oi = put_oi or None
    if call_oi > 0:
        result.pcr_oi = put_oi / call_oi
    call_vol = sum(o.volume or 0 for o in calls)
    put_vol = sum(o.volume or 0 for o in puts)
    if call_vol > 0:
        result.pcr_volume = put_vol / call_vol

    # --- OI flow ---
    call_oi_chg = [o.oi_change for o in calls if o.oi_change is not None]
    put_oi_chg = [o.oi_change for o in puts if o.oi_change is not None]
    if call_oi_chg:
        result.total_call_oi_change = sum(call_oi_chg)
    if put_oi_chg:
        result.total_put_oi_change = sum(put_oi_chg)

    # --- ATM IV and liquidity ---
    atm_ce = _find(calls, atm)
    atm_pe = _find(puts, atm)
    if atm_ce is not None and atm_ce.iv is not None:
        result.atm_iv_ce = atm_ce.iv
    if atm_pe is not None and atm_pe.iv is not None:
        result.atm_iv_pe = atm_pe.iv
    ivs = [v for v in (result.atm_iv_ce, result.atm_iv_pe) if v is not None]
    if ivs:
        result.atm_iv = sum(ivs) / len(ivs)

    spreads = [
        o.spread_pct
        for o in (atm_ce, atm_pe)
        if o is not None and o.spread_pct is not None
    ]
    if spreads:
        result.atm_spread_pct = sum(spreads) / len(spreads)

    # --- IV skew: OTM put vs OTM call at +/- skew_offset_points from ATM ---
    otm_put = _nearest_strike(puts, atm - skew_offset_points)
    otm_call = _nearest_strike(calls, atm + skew_offset_points)
    if (
        otm_put is not None and otm_put.iv is not None
        and otm_call is not None and otm_call.iv is not None
    ):
        result.iv_skew = otm_put.iv - otm_call.iv

    # --- OI walls ---
    calls_with_oi = [o for o in calls if o.open_interest]
    puts_with_oi = [o for o in puts if o.open_interest]
    if calls_with_oi:
        result.oi_resistance_strike = max(
            calls_with_oi, key=lambda o: o.open_interest
        ).strike
    if puts_with_oi:
        result.oi_support_strike = max(
            puts_with_oi, key=lambda o: o.open_interest
        ).strike

    # --- Max pain ---
    if calls_with_oi or puts_with_oi:
        result.max_pain_strike = _max_pain(strikes, calls_with_oi, puts_with_oi)

    return result


def _find(options: List[OptionSnapshot], strike: float) -> Optional[OptionSnapshot]:
    for o in options:
        if o.strike == strike:
            return o
    return None


def _nearest_strike(
    options: List[OptionSnapshot], target: float
) -> Optional[OptionSnapshot]:
    if not options:
        return None
    return min(options, key=lambda o: abs(o.strike - target))


def _max_pain(
    strikes: List[float],
    calls: List[OptionSnapshot],
    puts: List[OptionSnapshot],
) -> float:
    """Strike at which total option-writer payout is minimized."""
    best_strike = strikes[0]
    best_pain = None
    for s in strikes:
        pain = 0.0
        for c in calls:
            if s > c.strike:
                pain += (s - c.strike) * (c.open_interest or 0)
        for p in puts:
            if s < p.strike:
                pain += (p.strike - s) * (p.open_interest or 0)
        if best_pain is None or pain < best_pain:
            best_pain = pain
            best_strike = s
    return best_strike
