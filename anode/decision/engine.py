"""Decision engine.

Evaluates a TechnicalState against a strategy version's rule configuration
and produces a Decision: BUY CALL / BUY PUT / NO_TRADE.

Principles:
- Every check is conservative: a value that is None (unknown / warming up)
  FAILS the check. The engine never trades on missing information.
- Reason codes record exactly why: passed codes on a SIGNAL, failed codes
  (FAIL_*) on a NO_TRADE. The full TechnicalState is attached as features.
- The engine is deterministic and stateless between calls except for the
  signal cooldown clock.
"""

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from anode import ids
from anode.analysis.state import TechnicalState
from anode.decision.defaults import merged_config
from anode.models import (
    Decision,
    DecisionStatus,
    Direction,
    MarketSnapshot,
    StrategyVersion,
)


class DecisionEngine:
    def __init__(
        self,
        strategy: StrategyVersion,
        seq_base_fn: Optional[Callable[[str], int]] = None,
    ) -> None:
        self.strategy = strategy
        self.config = merged_config(strategy.config or {})
        # seq_base_fn("YYYYMMDD") -> already-used decision count for that day,
        # so IDs continue across separate runs instead of colliding.
        self._seq_base_fn = seq_base_fn
        self._last_signal_ts: Optional[datetime] = None
        self._day: Optional[str] = None
        self._day_seq = 0

    def evaluate(
        self,
        state: TechnicalState,
        snapshot: MarketSnapshot,
        snapshot_id: Optional[int] = None,
    ) -> Decision:
        failed: List[str] = []

        if not state.warmed_up:
            failed.append("FAIL_WARMUP")
        if self._in_cooldown(state.timestamp):
            failed.append("FAIL_COOLDOWN")

        if failed:
            return self._no_trade(state, snapshot_id, failed)

        call_passed, call_failed = self._check_direction("call", state, Direction.CALL)
        if not call_failed:
            return self._signal(state, snapshot, snapshot_id, Direction.CALL, call_passed)

        put_passed, put_failed = self._check_direction("put", state, Direction.PUT)
        if not put_failed:
            return self._signal(state, snapshot, snapshot_id, Direction.PUT, put_passed)

        # Report the near-miss side (fewer failures) for research visibility.
        side_failed = call_failed if len(call_failed) <= len(put_failed) else put_failed
        return self._no_trade(state, snapshot_id, side_failed)

    # ------------------------------------------------------------------ rules

    def _check_direction(
        self, key: str, s: TechnicalState, direction: str
    ) -> Tuple[List[str], List[str]]:
        p = self.config[key]
        passed: List[str] = []
        failed: List[str] = []

        def check(code: str, ok: Optional[bool]) -> None:
            # None (unknown) never passes.
            if ok:
                passed.append(code)
            else:
                failed.append("FAIL_" + code)

        if p.get("trend") is not None:
            check("TREND_{}".format(p["trend"]), s.trend == p["trend"])

        if p.get("require_above_vwap") is not None:
            want_above = bool(p["require_above_vwap"])
            ok = s.price_above_vwap is want_above
            check("ABOVE_VWAP" if want_above else "BELOW_VWAP", ok)

        if p.get("rsi_min") is not None or p.get("rsi_max") is not None:
            lo = p.get("rsi_min") if p.get("rsi_min") is not None else 0.0
            hi = p.get("rsi_max") if p.get("rsi_max") is not None else 100.0
            check("RSI_IN_RANGE", s.rsi14 is not None and lo <= s.rsi14 <= hi)

        if p.get("require_macd_aligned"):
            if direction == Direction.CALL:
                check("MACD_BULLISH", s.macd_bullish is True)
            else:
                check("MACD_BEARISH", s.macd_bullish is False)

        if p.get("adx_min") is not None:
            check("ADX_OK", s.adx14 is not None and s.adx14 >= p["adx_min"])

        if p.get("regimes"):
            check("REGIME_OK", s.regime in p["regimes"])

        if p.get("min_level_distance_pct") is not None:
            # CALL: room to the nearest resistance. PUT: room to support.
            # No level at all on that side counts as clear.
            dist = (
                s.resistance_distance_pct
                if direction == Direction.CALL
                else s.support_distance_pct
            )
            code = "RESISTANCE_CLEAR" if direction == Direction.CALL else "SUPPORT_CLEAR"
            check(code, dist is None or dist >= p["min_level_distance_pct"])

        if p.get("max_atm_spread_pct") is not None:
            spread = s.chain.get("atm_spread_pct")
            check(
                "LIQUIDITY_OK",
                spread is not None and spread * 100.0 <= p["max_atm_spread_pct"],
            )

        if p.get("max_iv_change") is not None:
            # Unknown IV change (warm-up) is tolerated; a large IV spike is not.
            check(
                "IV_STABLE",
                s.atm_iv_change is None or s.atm_iv_change <= p["max_iv_change"],
            )

        if p.get("pcr_min") is not None or p.get("pcr_max") is not None:
            pcr = s.chain.get("pcr_oi")
            lo = p.get("pcr_min") if p.get("pcr_min") is not None else 0.0
            hi = p.get("pcr_max") if p.get("pcr_max") is not None else float("inf")
            check("PCR_OK", pcr is not None and lo <= pcr <= hi)

        return passed, failed

    # ---------------------------------------------------------------- outputs

    def _signal(
        self,
        state: TechnicalState,
        snapshot: MarketSnapshot,
        snapshot_id: Optional[int],
        direction: str,
        passed: List[str],
    ) -> Decision:
        plan = self.config["trade_plan"]
        option_type = "CE" if direction == Direction.CALL else "PE"
        atm = state.chain.get("atm_strike") or snapshot.compute_atm_strike()
        expiry = state.chain.get("expiry") or snapshot.nearest_expiry
        contract = snapshot.option(atm, option_type, expiry)

        if contract is None:
            return self._no_trade(state, snapshot_id, ["FAIL_NO_CONTRACT"])

        ref = contract.ask if contract.ask is not None else contract.ltp
        if ref is None or ref <= 0:
            return self._no_trade(state, snapshot_id, ["FAIL_NO_QUOTE"])

        band = plan["entry_band_pct"] / 100.0
        entry_low = round(ref * (1.0 - band), 2)
        entry_high = round(ref * (1.0 + band), 2)
        stop_loss = round(ref * (1.0 - plan["sl_pct_of_premium"] / 100.0), 2)
        target = round(ref * (1.0 + plan["target_pct_of_premium"] / 100.0), 2)

        self._last_signal_ts = state.timestamp
        return Decision(
            decision_id=self._next_id(state.timestamp),
            timestamp=state.timestamp,
            strategy_version=self.strategy.version_id,
            status=DecisionStatus.SIGNAL,
            snapshot_id=snapshot_id,
            direction=direction,
            expiry=expiry,
            strike=atm,
            option_type=option_type,
            entry_low=entry_low,
            entry_high=entry_high,
            stop_loss=stop_loss,
            target=target,
            max_holding_minutes=plan["max_holding_minutes"],
            reason_codes=passed,
            features=state.to_dict(),
        )

    def _no_trade(
        self, state: TechnicalState, snapshot_id: Optional[int], failed: List[str]
    ) -> Decision:
        return Decision(
            decision_id=self._next_id(state.timestamp),
            timestamp=state.timestamp,
            strategy_version=self.strategy.version_id,
            status=DecisionStatus.NO_TRADE,
            snapshot_id=snapshot_id,
            reason_codes=failed,
            features=state.to_dict(),
        )

    def _in_cooldown(self, ts: datetime) -> bool:
        if self._last_signal_ts is None:
            return False
        cooldown = timedelta(minutes=self.config["engine"]["cooldown_minutes"])
        return ts - self._last_signal_ts < cooldown

    def _next_id(self, ts: datetime) -> str:
        day = ts.strftime("%Y%m%d")
        if day != self._day:
            self._day = day
            self._day_seq = self._seq_base_fn(day) if self._seq_base_fn else 0
        self._day_seq += 1
        return ids.decision_id(ts, self._day_seq)
