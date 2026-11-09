from contract_intel.domain.usage import UsageRecord


class InMemoryUsageTracker:
    """Usage tracker that keeps records in a list for inspection."""

    def __init__(self) -> None:
        self.records: list[UsageRecord] = []

    async def record(self, usage: UsageRecord) -> None:
        """Append ``usage`` to the recorded list."""
        self.records.append(usage)
