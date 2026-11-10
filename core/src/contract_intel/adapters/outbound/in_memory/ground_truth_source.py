from collections.abc import Mapping

from contract_intel.domain.evaluation import ExpertLabels


class InMemoryGroundTruthSource:
    """Expert labels provided directly, keyed by document title."""

    def __init__(self, labels: Mapping[str, ExpertLabels] | None = None) -> None:
        self._labels = dict(labels or {})

    async def labels(self) -> Mapping[str, ExpertLabels]:
        """Return the configured labels."""
        return dict(self._labels)
