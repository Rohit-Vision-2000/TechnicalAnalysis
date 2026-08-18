"""Transaction-cost model for a long-option round trip (buy, then sell).

Components (rates from config/config.json `costs`, expressed in percent
unless noted):

    brokerage_per_order      flat, applied twice (buy + sell)
    exchange_txn_charge_pct  % of premium turnover, both sides
    gst_pct                  % on (brokerage + exchange txn + SEBI)
    stt_sell_pct             % of sell-side premium turnover
    sebi_charge_per_crore    rupees per crore of total turnover
    stamp_duty_buy_pct       % of buy-side premium turnover

Slippage is NOT a cost here — it is modeled in the fill prices by the paper
trading engine, so it can never be double-counted.
"""

from typing import Any, Dict

DEFAULT_COSTS: Dict[str, Any] = {
    "brokerage_per_order": 20.0,
    "exchange_txn_charge_pct": 0.03503,
    "gst_pct": 18.0,
    "stt_sell_pct": 0.1,
    "sebi_charge_per_crore": 10.0,
    "stamp_duty_buy_pct": 0.003,
}


def round_trip_costs(
    entry_price: float, exit_price: float, quantity: int, cfg: Dict[str, Any]
) -> float:
    c = dict(DEFAULT_COSTS)
    c.update(cfg or {})

    buy_turnover = entry_price * quantity
    sell_turnover = exit_price * quantity
    total_turnover = buy_turnover + sell_turnover

    brokerage = 2.0 * c["brokerage_per_order"]
    exchange = total_turnover * c["exchange_txn_charge_pct"] / 100.0
    sebi = total_turnover / 1e7 * c["sebi_charge_per_crore"]
    stt = sell_turnover * c["stt_sell_pct"] / 100.0
    stamp = buy_turnover * c["stamp_duty_buy_pct"] / 100.0
    gst = (brokerage + exchange + sebi) * c["gst_pct"] / 100.0

    return round(brokerage + exchange + sebi + stt + stamp + gst, 2)
