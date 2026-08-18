"""Default (baseline) strategy configuration.

A strategy version's ``config`` overrides these values key-by-key (one level
deep). An empty config — like the STRAT-001 placeholder — therefore runs this
baseline. All thresholds here are STARTING POINTS to be tuned via experiments,
never by hand-editing an evaluated version.

Rule parameters set to ``null``/``None`` disable that check.
"""

from typing import Any, Dict

DEFAULT_STRATEGY_CONFIG: Dict[str, Any] = {
    "call": {
        "trend": "BULLISH",
        "require_above_vwap": True,
        "rsi_min": 55.0,
        "rsi_max": 70.0,
        "require_macd_aligned": True,     # MACD line above signal for calls
        "adx_min": 20.0,
        "regimes": ["TRENDING_BULLISH"],
        "min_level_distance_pct": 0.35,   # resistance must be at least this far
        "max_atm_spread_pct": 1.0,        # ATM spread as % of mid (liquidity gate)
        "max_iv_change": 1.5,             # ATM IV rise (pct points) over lookback
        "pcr_min": None,
        "pcr_max": None,
    },
    "put": {
        "trend": "BEARISH",
        "require_above_vwap": False,      # price must be BELOW vwap for puts
        "rsi_min": 30.0,
        "rsi_max": 45.0,
        "require_macd_aligned": True,     # MACD line below signal for puts
        "adx_min": 20.0,
        "regimes": ["TRENDING_BEARISH"],
        "min_level_distance_pct": 0.35,   # support must be at least this far
        "max_atm_spread_pct": 1.0,
        "max_iv_change": 1.5,
        "pcr_min": None,
        "pcr_max": None,
    },
    "trade_plan": {
        "entry_band_pct": 0.5,            # entry range around reference premium
        "sl_pct_of_premium": 15.0,
        "target_pct_of_premium": 25.0,
        "max_holding_minutes": 60,
        "quantity_lots": 1,
    },
    "engine": {
        "cooldown_minutes": 15,           # min gap between consecutive signals
        "max_open_positions": 1,
    },
}


def merged_config(overrides: Dict[str, Any]) -> Dict[str, Any]:
    """DEFAULT_STRATEGY_CONFIG with `overrides` applied one section deep."""
    out: Dict[str, Any] = {}
    for section, defaults in DEFAULT_STRATEGY_CONFIG.items():
        merged = dict(defaults)
        merged.update(overrides.get(section, {}))
        out[section] = merged
    return out
