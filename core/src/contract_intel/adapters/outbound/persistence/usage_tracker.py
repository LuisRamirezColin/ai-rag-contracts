from decimal import Decimal

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contract_intel.adapters.outbound.persistence.models import UsageRecordRow
from contract_intel.domain.usage import UsageRecord


class SqlAlchemyUsageTracker:
    """Model usage records persisted in Postgres."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, usage: UsageRecord) -> None:
        """Insert ``usage`` as a new row."""
        async with self._session_factory.begin() as session:
            await session.execute(
                insert(UsageRecordRow).values(
                    operation=usage.operation,
                    model=usage.model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cost_usd=Decimal(str(usage.cost_usd)),
                    document_id=usage.document_id,
                )
            )
