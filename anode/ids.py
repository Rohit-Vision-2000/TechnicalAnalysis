"""Deterministic identifier generation.

ID formats (all traceable, sortable, human-readable):

    decision:   DEC-YYYYMMDD-HHMMSS-NNNNN   (NNNNN = per-day sequence)
    trade:      TRD-YYYYMMDD-NNNNN
    strategy:   STRAT-NNN
    experiment: EXP-NNN
"""

import re
from datetime import datetime
from typing import Iterable

_STRAT_RE = re.compile(r"^STRAT-(\d{3,})$")
_EXP_RE = re.compile(r"^EXP-(\d{3,})$")


def decision_id(ts: datetime, seq: int) -> str:
    return "DEC-{}-{:05d}".format(ts.strftime("%Y%m%d-%H%M%S"), seq)


def trade_id(ts: datetime, seq: int) -> str:
    return "TRD-{}-{:05d}".format(ts.strftime("%Y%m%d"), seq)


def strategy_id(n: int) -> str:
    return "STRAT-{:03d}".format(n)


def experiment_id(n: int) -> str:
    return "EXP-{:03d}".format(n)


def next_strategy_id(existing: Iterable[str]) -> str:
    """Return the next STRAT-NNN id given existing ids."""
    highest = 0
    for vid in existing:
        m = _STRAT_RE.match(vid)
        if m:
            highest = max(highest, int(m.group(1)))
    return strategy_id(highest + 1)


def next_experiment_id(existing: Iterable[str]) -> str:
    """Return the next EXP-NNN id given existing ids."""
    highest = 0
    for eid in existing:
        m = _EXP_RE.match(eid)
        if m:
            highest = max(highest, int(m.group(1)))
    return experiment_id(highest + 1)
