"""Baseline-vs-candidate comparison with promotion gates.

The gates encode AGENTS.md's anti-gaming rules: a candidate cannot win by
simply trading less (minimum-signals gate), and it must not degrade any
regime it previously handled. Every gate produces an explicit PASS/FAIL
with the numbers, so experiments are auditable.
"""

from typing import Any, Dict, List, Optional

DEFAULT_GATES: Dict[str, Any] = {
    "min_signals": 30,              # candidate must produce at least this many
    "min_trades": 20,               # ...and at least this many filled trades
    "max_win_rate_drop": 0.0,       # candidate win rate may not be lower
    "require_profit_factor_gain": True,
    "max_drawdown_tolerance": 1.10, # candidate max DD <= baseline DD * this
    "require_positive_net_pnl": True,
    "max_regime_win_rate_drop": 0.05,  # no regime may degrade more than this
}


def compare_results(
    baseline: Dict[str, Any],
    candidate: Dict[str, Any],
    gates: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compare two metrics dicts (from compute_metrics). Returns a verdict."""
    g = dict(DEFAULT_GATES)
    g.update(gates or {})
    checks: List[Dict[str, Any]] = []

    def gate(name: str, passed: Optional[bool], detail: str) -> None:
        checks.append({
            "gate": name,
            "result": "PASS" if passed else ("FAIL" if passed is not None else "N/A"),
            "detail": detail,
        })

    cand_signals = candidate.get("signals") or 0
    gate(
        "min_signals",
        cand_signals >= g["min_signals"],
        "candidate signals {} (required >= {})".format(cand_signals, g["min_signals"]),
    )
    gate(
        "min_trades",
        candidate.get("trades", 0) >= g["min_trades"],
        "candidate trades {} (required >= {})".format(
            candidate.get("trades", 0), g["min_trades"]
        ),
    )

    b_wr, c_wr = baseline.get("win_rate"), candidate.get("win_rate")
    if b_wr is None or c_wr is None:
        gate("win_rate", False, "win rate unavailable (baseline={}, candidate={})".format(b_wr, c_wr))
    else:
        gate(
            "win_rate",
            c_wr >= b_wr - g["max_win_rate_drop"],
            "baseline {:.1%} -> candidate {:.1%}".format(b_wr, c_wr),
        )

    b_pf, c_pf = baseline.get("profit_factor"), candidate.get("profit_factor")
    if g["require_profit_factor_gain"]:
        if c_pf is None:
            gate("profit_factor", False, "candidate profit factor unavailable")
        elif b_pf is None:
            gate("profit_factor", True, "no baseline profit factor; candidate {:.2f}".format(c_pf))
        else:
            gate(
                "profit_factor",
                c_pf >= b_pf,
                "baseline {:.2f} -> candidate {:.2f}".format(b_pf, c_pf),
            )

    b_dd = baseline.get("max_drawdown") or 0.0
    c_dd = candidate.get("max_drawdown") or 0.0
    if b_dd > 0:
        gate(
            "max_drawdown",
            c_dd <= b_dd * g["max_drawdown_tolerance"],
            "baseline {:.2f} -> candidate {:.2f} (allowed <= {:.2f})".format(
                b_dd, c_dd, b_dd * g["max_drawdown_tolerance"]
            ),
        )
    else:
        gate("max_drawdown", True, "baseline had no drawdown; candidate {:.2f}".format(c_dd))

    if g["require_positive_net_pnl"]:
        net = candidate.get("net_pnl") or 0.0
        gate("net_pnl_positive", net > 0, "candidate net P&L {:.2f}".format(net))

    # Regime stability: any regime the baseline traded must not degrade badly.
    regime_details = []
    regime_ok = True
    for regime, b_stats in (baseline.get("by_regime") or {}).items():
        c_stats = (candidate.get("by_regime") or {}).get(regime)
        b_r = b_stats.get("win_rate")
        if b_r is None:
            continue
        if c_stats is None or c_stats.get("win_rate") is None:
            regime_details.append("{}: candidate has no trades (baseline {:.1%})".format(regime, b_r))
            continue  # trading less in a regime is selectivity, not degradation
        c_r = c_stats["win_rate"]
        if c_r < b_r - g["max_regime_win_rate_drop"]:
            regime_ok = False
        regime_details.append("{}: {:.1%} -> {:.1%}".format(regime, b_r, c_r))
    gate(
        "regime_stability",
        regime_ok,
        "; ".join(regime_details) if regime_details else "no regime data",
    )

    overall = all(c["result"] == "PASS" for c in checks)
    return {
        "verdict": "PASS" if overall else "FAIL",
        "checks": checks,
        "baseline": _summary(baseline),
        "candidate": _summary(candidate),
        "gates_used": g,
    }


def _summary(m: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("signals", "trades", "wins", "losses", "win_rate", "net_pnl",
            "profit_factor", "expectancy", "max_drawdown")
    out = {k: m.get(k) for k in keys}
    if out.get("profit_factor") == float("inf"):
        out["profit_factor"] = "inf"
    return out
