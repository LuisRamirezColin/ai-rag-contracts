from typing import Protocol, runtime_checkable

from contract_intel.domain.usage import UsageRecord


@runtime_checkable
class UsageTracker(Protocol):
    """Record token usage and cost of model invocations."""

    async def record(self, usage: UsageRecord) -> None:
        """Persist ``usage``."""
        ...
