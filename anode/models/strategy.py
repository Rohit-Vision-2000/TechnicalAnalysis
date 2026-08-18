"""Strategy version and experiment models.

Strategy versions are immutable once evaluated. Evolution happens by creating
a new version (child of a parent version) inside an experiment, testing it,
and promoting or rejecting it. Exactly one version may be PRODUCTION.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


class StrategyStatus:
    DRAFT = "DRAFT"  # being authored, not yet evaluated
    CANDIDATE = "CANDIDATE"  # under evaluation (backtest / paper)
    PRODUCTION = "PRODUCTION"  # the single live paper-trading strategy
    REJECTED = "REJECTED"  # evaluated and discarded
    RETIRED = "RETIRED"  # was production, replaced by a newer version
    ALL = (DRAFT, CANDIDATE, PRODUCTION, REJECTED, RETIRED)


class ExperimentStatus:
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ALL = (PLANNED, RUNNING, ACCEPTED, REJECTED)


@dataclass
class StrategyVersion:
    version_id: str  # STRAT-NNN
    created_at: datetime
    status: str  # StrategyStatus
    description: str = ""
    parent_version: Optional[str] = None
    # Strategy parameters/rules manifest (also stored on disk under
    # strategies/STRAT-NNN/ for auditability).
    config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in StrategyStatus.ALL:
            raise ValueError("invalid strategy status: {!r}".format(self.status))


@dataclass
class Experiment:
    experiment_id: str  # EXP-NNN
    created_at: datetime
    hypothesis: str
    baseline_version: str
    candidate_version: Optional[str] = None
    status: str = ExperimentStatus.PLANNED
    results: Dict[str, Any] = field(default_factory=dict)
    conclusion: str = ""

    def __post_init__(self) -> None:
        if self.status not in ExperimentStatus.ALL:
            raise ValueError("invalid experiment status: {!r}".format(self.status))
        if not self.hypothesis.strip():
            raise ValueError("experiment requires a hypothesis")
