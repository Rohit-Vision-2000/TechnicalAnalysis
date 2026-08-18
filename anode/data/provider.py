"""Market-data provider abstraction.

Every data source — historical replay files, and later a live feed — is an
adapter that yields normalized ``MarketSnapshot`` objects. Nothing downstream
may depend on a specific provider, so providers are swappable without touching
analysis, decision, or trading code.
"""

from abc import ABC, abstractmethod
from typing import Iterator

from anode.models import MarketSnapshot


class MarketDataProvider(ABC):
    """Yields MarketSnapshot objects in strictly non-decreasing time order."""

    @abstractmethod
    def snapshots(self) -> Iterator[MarketSnapshot]:
        """Iterate over market snapshots."""
        raise NotImplementedError

    def __iter__(self) -> Iterator[MarketSnapshot]:
        return self.snapshots()
