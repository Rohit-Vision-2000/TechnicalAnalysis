"""Failure analysis.

Joins closed trades with the decision features recorded at signal time and
aggregates win rates across feature buckets, so a researcher (human or
Claude) can spot statistically repeatable failure conditions rather than
staring at individual losing trades.

Buckets with fewer than `min_bucket_trades` observations are reported but
flagged, because small buckets are noise, not signal.
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional

from anode.models import Decision, PaperTrade

MIN_BUCKET_TRADES = 5


def failure_analysis(
    trades: List[PaperTrade],
    decisions: Dict[str, Decision],
    min_bucket_trades: int = MIN_BUCKET_TRADES,
) -> Dict[str, Any]:
    closed = [t for t in trades if t.status == "CLOSED"]
    rows = []
    for t in closed:
        d = decisions.get(t.decision_id)
        if d is None:
            continue
        f = d.features or {}
        chain = f.get("chain") or {}
        rows.append({
            "win": (t.net_pnl or 0.0) > 0,
            "pnl": t.net_pnl or 0.0,
            "exit_reason": t.exit_reason,
            "direction": d.direction,
            "regime": f.get("regime"),
            "rsi_bucket": _bucket_value(f.get("rsi14"), 10),
            "adx_bucket": _bucket_value(f.get("adx14"), 10),
            "level_distance": _distance_bucket(
                f.get("resistance_distance_pct")
                if d.direction == "CALL"
                else f.get("support_distance_pct")
            ),
            "iv_change": _sign_bucket(f.get("atm_iv_change")),
            "pcr_bucket": _pcr_bucket(chain.get("pcr_oi")),
            "hour": d.timestamp.strftime("%H") if d.timestamp else None,
        })

    dimensions = (
        "regime", "direction", "rsi_bucket", "adx_bucket",
        "level_distance", "iv_change", "pcr_bucket", "hour", "exit_reason",
    )
    report: Dict[str, Any] = {
        "trades_analyzed": len(rows),
        "overall_win_rate": _win_rate(rows),
        "dimensions": {},
        "weak_spots": [],
    }
    for dim in dimensions:
        grouped: Dict[Any, list] = defaultdict(list)
        for r in rows:
            grouped[r[dim]].append(r)
        stats = {}
        for key, bucket in sorted(grouped.items(), key=lambda kv: str(kv[0])):
            stats[str(key)] = {
                "trades": len(bucket),
                "win_rate": _win_rate(bucket),
                "net_pnl": round(sum(r["pnl"] for r in bucket), 2),
                "significant": len(bucket) >= min_bucket_trades,
            }
        report["dimensions"][dim] = stats

    # Weak spots: significant buckets clearly below the overall win rate.
    overall = report["overall_win_rate"]
    if overall is not None:
        for dim, stats in report["dimensions"].items():
            if dim == "exit_reason":
                continue
            for key, s in stats.items():
                if (
                    s["significant"]
                    and s["win_rate"] is not None
                    and s["win_rate"] < overall - 0.10
                ):
                    report["weak_spots"].append({
                        "dimension": dim,
                        "bucket": key,
                        "trades": s["trades"],
                        "win_rate": s["win_rate"],
                        "vs_overall": round(s["win_rate"] - overall, 4),
                    })
        report["weak_spots"].sort(key=lambda w: w["win_rate"])
    return report


def _win_rate(rows: list) -> Optional[float]:
    if not rows:
        return None
    return round(sum(1 for r in rows if r["win"]) / len(rows), 4)


def _bucket_value(v: Optional[float], width: int) -> Optional[str]:
    if v is None:
        return None
    lo = int(v // width) * width
    return "{}-{}".format(lo, lo + width)


def _distance_bucket(v: Optional[float]) -> Optional[str]:
    if v is None:
        return "no_level"
    if v < 0.2:
        return "<0.2%"
    if v < 0.4:
        return "0.2-0.4%"
    if v < 0.8:
        return "0.4-0.8%"
    return ">=0.8%"


def _sign_bucket(v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    if v > 0.5:
        return "rising"
    if v < -0.5:
        return "falling"
    return "stable"


def _pcr_bucket(v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    if v < 0.8:
        return "<0.8"
    if v <= 1.2:
        return "0.8-1.2"
    return ">1.2"
