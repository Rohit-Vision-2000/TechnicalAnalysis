import unittest
from datetime import datetime, timedelta

from anode.data.synthetic import SyntheticMultiDayProvider
from anode.models import Decision, PaperTrade, StrategyVersion
from anode.research import (
    ListProvider,
    compare_results,
    compute_metrics,
    failure_analysis,
    run_session,
)


def closed_trade(i, pnl, entry_ts, minutes=20, exit_reason=None):
    entry = 100.0
    qty = 75
    exit_price = entry + pnl / qty
    t = PaperTrade(
        trade_id="TRD-20260819-{:05d}".format(i),
        decision_id="DEC-20260819-1030{:02d}-{:05d}".format(i % 60, i),
        status="OPEN",
        entry_time=entry_ts,
        entry_price=entry,
        quantity=qty,
    )
    t.close(
        entry_ts + timedelta(minutes=minutes),
        exit_price,
        exit_reason or ("TARGET" if pnl > 0 else "STOP_LOSS"),
        costs=0.0,
    )
    return t


def decision_for(trade, regime="TRENDING_BULLISH", direction="CALL",
                 rsi=62.0, res_dist=0.5):
    return Decision(
        decision_id=trade.decision_id,
        timestamp=trade.entry_time,
        strategy_version="STRAT-001",
        status="SIGNAL",
        direction=direction,
        expiry="2026-08-27", strike=25000.0,
        entry_low=99.0, entry_high=101.0, stop_loss=85.0, target=125.0,
        features={
            "regime": regime, "rsi14": rsi,
            "resistance_distance_pct": res_dist,
            "support_distance_pct": 0.5,
            "atm_iv_change": 0.1,
            "chain": {"pcr_oi": 1.0},
        },
    )


class TestMetrics(unittest.TestCase):
    def test_basic_metrics(self):
        t0 = datetime(2026, 8, 19, 10, 0)
        trades = [
            closed_trade(1, 1500.0, t0),
            closed_trade(2, 1500.0, t0 + timedelta(minutes=30)),
            closed_trade(3, -750.0, t0 + timedelta(minutes=60)),
        ]
        m = compute_metrics(trades, signals=5, no_trades=100)
        self.assertEqual(m["trades"], 3)
        self.assertEqual(m["wins"], 2)
        self.assertEqual(m["losses"], 1)
        self.assertAlmostEqual(m["win_rate"], 2 / 3)
        self.assertAlmostEqual(m["net_pnl"], 2250.0)
        self.assertAlmostEqual(m["profit_factor"], 3000.0 / 750.0)
        self.assertAlmostEqual(m["expectancy"], 750.0)
        self.assertEqual(m["signals"], 5)

    def test_max_drawdown(self):
        t0 = datetime(2026, 8, 19, 10, 0)
        # equity: +1000, -1500 (dd 1500), +2000
        trades = [
            closed_trade(1, 1000.0, t0),
            closed_trade(2, -1500.0, t0 + timedelta(minutes=30)),
            closed_trade(3, 2000.0, t0 + timedelta(minutes=60)),
        ]
        m = compute_metrics(trades)
        self.assertAlmostEqual(m["max_drawdown"], 1500.0)

    def test_empty(self):
        m = compute_metrics([])
        self.assertEqual(m["trades"], 0)
        self.assertIsNone(m["win_rate"])

    def test_regime_breakdown(self):
        t0 = datetime(2026, 8, 19, 10, 0)
        trades = [closed_trade(1, 1000.0, t0), closed_trade(2, -500.0, t0)]
        decisions = {
            trades[0].decision_id: decision_for(trades[0], regime="TRENDING_BULLISH"),
            trades[1].decision_id: decision_for(trades[1], regime="SIDEWAYS"),
        }
        m = compute_metrics(trades, decisions=decisions)
        self.assertEqual(m["by_regime"]["TRENDING_BULLISH"]["wins"], 1)
        self.assertEqual(m["by_regime"]["SIDEWAYS"]["win_rate"], 0.0)


class TestCompare(unittest.TestCase):
    def metrics(self, signals=50, trades=40, win_rate=0.6, pf=2.0,
                net=10000.0, dd=2000.0, by_regime=None):
        return {
            "signals": signals, "trades": trades,
            "win_rate": win_rate, "profit_factor": pf,
            "net_pnl": net, "max_drawdown": dd,
            "by_regime": by_regime or {},
        }

    def test_candidate_passes_when_better(self):
        r = compare_results(
            self.metrics(win_rate=0.60, pf=2.0, dd=2000.0),
            self.metrics(win_rate=0.66, pf=2.5, dd=1500.0),
        )
        self.assertEqual(r["verdict"], "PASS")

    def test_min_signals_gate_blocks_selectivity_gaming(self):
        # candidate "improves" accuracy by barely trading — must FAIL
        r = compare_results(
            self.metrics(signals=100, trades=80, win_rate=0.55),
            self.metrics(signals=3, trades=3, win_rate=1.0, pf=99.0, dd=0.0),
        )
        self.assertEqual(r["verdict"], "FAIL")
        gates = {c["gate"]: c["result"] for c in r["checks"]}
        self.assertEqual(gates["min_signals"], "FAIL")

    def test_win_rate_drop_fails(self):
        r = compare_results(
            self.metrics(win_rate=0.65),
            self.metrics(win_rate=0.55),
        )
        gates = {c["gate"]: c["result"] for c in r["checks"]}
        self.assertEqual(gates["win_rate"], "FAIL")

    def test_regime_degradation_fails(self):
        base_regimes = {
            "TRENDING_BULLISH": {"trades": 30, "win_rate": 0.7, "net_pnl": 1},
            "SIDEWAYS": {"trades": 20, "win_rate": 0.5, "net_pnl": 1},
        }
        cand_regimes = {
            "TRENDING_BULLISH": {"trades": 30, "win_rate": 0.75, "net_pnl": 1},
            "SIDEWAYS": {"trades": 20, "win_rate": 0.30, "net_pnl": 1},  # -20pp
        }
        r = compare_results(
            self.metrics(by_regime=base_regimes),
            self.metrics(win_rate=0.66, pf=2.5, by_regime=cand_regimes),
        )
        gates = {c["gate"]: c["result"] for c in r["checks"]}
        self.assertEqual(gates["regime_stability"], "FAIL")

    def test_negative_pnl_fails(self):
        r = compare_results(self.metrics(), self.metrics(net=-500.0, pf=2.5, win_rate=0.7))
        gates = {c["gate"]: c["result"] for c in r["checks"]}
        self.assertEqual(gates["net_pnl_positive"], "FAIL")


class TestFailureAnalysis(unittest.TestCase):
    def test_weak_spot_detected(self):
        t0 = datetime(2026, 8, 19, 10, 0)
        trades = []
        decisions = {}
        i = 1
        # trending: 8 wins, 2 losses
        for _ in range(8):
            t = closed_trade(i, 1000.0, t0 + timedelta(minutes=i)); i += 1
            trades.append(t); decisions[t.decision_id] = decision_for(t, "TRENDING_BULLISH")
        for _ in range(2):
            t = closed_trade(i, -500.0, t0 + timedelta(minutes=i)); i += 1
            trades.append(t); decisions[t.decision_id] = decision_for(t, "TRENDING_BULLISH")
        # sideways: 1 win, 7 losses — a weak spot
        t = closed_trade(i, 1000.0, t0 + timedelta(minutes=i)); i += 1
        trades.append(t); decisions[t.decision_id] = decision_for(t, "SIDEWAYS")
        for _ in range(7):
            t = closed_trade(i, -500.0, t0 + timedelta(minutes=i)); i += 1
            trades.append(t); decisions[t.decision_id] = decision_for(t, "SIDEWAYS")

        report = failure_analysis(trades, decisions)
        self.assertEqual(report["trades_analyzed"], 18)
        weak_dims = {(w["dimension"], w["bucket"]) for w in report["weak_spots"]}
        self.assertIn(("regime", "SIDEWAYS"), weak_dims)
        sideways = report["dimensions"]["regime"]["SIDEWAYS"]
        self.assertTrue(sideways["significant"])
        self.assertAlmostEqual(sideways["win_rate"], 1 / 8)

    def test_small_buckets_flagged_insignificant(self):
        t0 = datetime(2026, 8, 19, 10, 0)
        t = closed_trade(1, -500.0, t0)
        report = failure_analysis([t], {t.decision_id: decision_for(t, "SIDEWAYS")})
        self.assertFalse(report["dimensions"]["regime"]["SIDEWAYS"]["significant"])
        self.assertEqual(report["weak_spots"], [])


class TestRunSession(unittest.TestCase):
    def test_full_pipeline_on_synthetic_days(self):
        strategy = StrategyVersion(
            version_id="STRAT-001",
            created_at=datetime(2026, 8, 1, 9, 0),
            status="CANDIDATE",
            config={},
        )
        snapshots = list(SyntheticMultiDayProvider(days=3, seed=11))
        result = run_session(ListProvider(snapshots), strategy, {})
        self.assertEqual(result.snapshots_processed, len(snapshots))
        self.assertGreater(len(result.decisions), 0)
        # every decision has features recorded
        for d in result.decisions[:50]:
            self.assertIn("regime", d.features)
        # trades only exist for signals, and all are closed at the end
        self.assertLessEqual(len(result.trades), len(result.signals))
        for t in result.trades:
            self.assertEqual(t.status, "CLOSED")
            self.assertIsNotNone(t.net_pnl)
        self.assertEqual(result.metrics["trades"], len(result.trades))

    def test_deterministic(self):
        strategy = StrategyVersion(
            version_id="STRAT-001",
            created_at=datetime(2026, 8, 1, 9, 0),
            status="CANDIDATE",
            config={},
        )
        snapshots = list(SyntheticMultiDayProvider(days=2, seed=5))
        r1 = run_session(ListProvider(snapshots), strategy, {})
        r2 = run_session(ListProvider(snapshots), strategy, {})
        self.assertEqual(r1.metrics, r2.metrics)
        self.assertEqual(
            [d.decision_id for d in r1.decisions],
            [d.decision_id for d in r2.decisions],
        )


if __name__ == "__main__":
    unittest.main()
