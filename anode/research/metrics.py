"""Performance metrics over a set of closed paper trades.

All P&L figures are NET of transaction costs. Metrics that need decision
context (regime, direction) read it from the decisions mapping when given.
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional

from anode.models import Decision, PaperTrade


def compute_metrics(
    trades: List[PaperTrade],
    decisions: Optional[Dict[str, Decision]] = None,
    signals: Optional[int] = None,
    no_trades: Optional[int] = None,
) -> Dict[str, Any]:
    closed = sorted(
        [t for t in trades if t.status == "CLOSED"],
        key=lambda t: t.exit_time,
    )
    m: Dict[str, Any] = {
        "signals": signals,
        "no_trades": no_trades,
        "trades": len(closed),
        "wins": 0,
        "losses": 0,
        "win_rate": None,
        "gross_pnl": 0.0,
        "total_costs": 0.0,
        "net_pnl": 0.0,
        "profit_factor": None,
        "expectancy": None,
        "avg_win": None,
        "avg_loss": None,
        "max_drawdown": 0.0,
        "avg_holding_minutes": None,
        "exit_reasons": {},
        "by_regime": {},
        "by_direction": {},
        "by_day": {},
    }
    if not closed:
        return m

    win_total = 0.0
    loss_total = 0.0
    holding_minutes: List[float] = []
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    exit_reasons: Dict[str, int] = defaultdict(int)
    groups: Dict[str, Dict[str, list]] = {
        "by_regime": defaultdict(list),
        "by_direction": defaultdict(list),
        "by_day": defaultdict(list),
    }

    for t in closed:
        pnl = t.net_pnl or 0.0
        m["gross_pnl"] += t.gross_pnl or 0.0
        m["total_costs"] += t.costs or 0.0
        m["net_pnl"] += pnl
        if pnl > 0:
            m["wins"] += 1
            win_total += pnl
        elif pnl < 0:
            m["losses"] += 1
            loss_total += -pnl
        exit_reasons[t.exit_reason] += 1
        holding_minutes.append(
            (t.exit_time - t.entry_time).total_seconds() / 60.0
        )
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

        groups["by_day"][t.entry_time.strftime("%Y-%m-%d")].append(pnl)
        if decisions and t.decision_id in decisions:
            d = decisions[t.decision_id]
            groups["by_direction"][d.direction or "?"].append(pnl)
            regime = (d.features or {}).get("regime", "?")
            groups["by_regime"][regime].append(pnl)

    n = len(closed)
    decided = m["wins"] + m["losses"]
    m["win_rate"] = m["wins"] / decided if decided else None
    m["profit_factor"] = (
        win_total / loss_total if loss_total > 0
        else (float("inf") if win_total > 0 else None)
    )
    m["expectancy"] = m["net_pnl"] / n
    m["avg_win"] = win_total / m["wins"] if m["wins"] else None
    m["avg_loss"] = -loss_total / m["losses"] if m["losses"] else None
    m["max_drawdown"] = max_dd
    m["avg_holding_minutes"] = sum(holding_minutes) / n
    m["exit_reasons"] = dict(exit_reasons)
    for key, grouped in groups.items():
        m[key] = {
            bucket: _bucket_stats(pnls) for bucket, pnls in sorted(grouped.items())
        }
    # round the float aggregates for readability
    for k in ("gross_pnl", "total_costs", "net_pnl", "expectancy",
              "max_drawdown", "avg_holding_minutes"):
        if m[k] is not None:
            m[k] = round(m[k], 2)
    return m


def _bucket_stats(pnls: list) -> Dict[str, Any]:
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    decided = wins + losses
    return {
        "trades": len(pnls),
        "wins": wins,
        "win_rate": round(wins / decided, 4) if decided else None,
        "net_pnl": round(sum(pnls), 2),
    }
