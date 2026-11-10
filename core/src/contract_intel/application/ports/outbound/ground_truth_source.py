from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from contract_intel.domain.evaluation import ExpertLabels


@runtime_checkable
class GroundTruthSource(Protocol):
    """Expert clause labels used to evaluate the extraction."""

    async def labels(self) -> Mapping[str, ExpertLabels]:
        """Return the expert labels keyed by document title."""
        ...
