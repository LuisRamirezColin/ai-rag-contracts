from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from contract_intel.adapters.outbound.in_memory.usage_tracker import (
    InMemoryUsageTracker,
)
from contract_intel.adapters.outbound.persistence.models import UsageRecordRow
from contract_intel.adapters.outbound.persistence.usage_tracker import (
    SqlAlchemyUsageTracker,
)
from contract_intel.application.ports.outbound.usage_tracker import UsageTracker
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.usage import UsageRecord

DOC = DocumentId("doc-1")
EMBED = UsageRecord("embed_documents", "voyage-law-2", 4_600, 0, 0.000552, DOC)
CHAT = UsageRecord("answer_question", "claude-opus-5-5", 7_500, 900, 0.048)


@dataclass(frozen=True)
class TrackerCase:
    tracker: UsageTracker
    read: Callable[[], Awaitable[list[UsageRecord]]]


def _in_memory_case() -> TrackerCase:
    tracker = InMemoryUsageTracker()

    async def read() -> list[UsageRecord]:
        return list(tracker.records)

    return TrackerCase(tracker, read)


@pytest.fixture
async def postgres_case() -> AsyncIterator[TrackerCase]:
    engine = create_async_engine(AppSettings().database.url, poolclass=NullPool)
    sessions = async_sessionmaker(engine)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE usage_records"))

    async def read() -> list[UsageRecord]:
        async with sessions() as session:
            rows = (
                await session.scalars(
                    select(UsageRecordRow).order_by(UsageRecordRow.id)
                )
            ).all()
        return [
            UsageRecord(
                operation=r.operation,
                model=r.model,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                cost_usd=float(r.cost_usd),
                document_id=None
                if r.document_id is None
                else DocumentId(r.document_id),
            )
            for r in rows
        ]

    yield TrackerCase(SqlAlchemyUsageTracker(sessions), read)
    await engine.dispose()


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def case(request: pytest.FixtureRequest) -> TrackerCase:
    if request.param == "postgres":
        real: TrackerCase = request.getfixturevalue("postgres_case")
        return real
    return _in_memory_case()


async def test_records_are_kept_in_order_with_their_document(case):
    await case.tracker.record(EMBED)
    await case.tracker.record(CHAT)

    assert await case.read() == [EMBED, CHAT]


async def test_same_usage_twice_is_two_records(case):
    await case.tracker.record(EMBED)
    await case.tracker.record(EMBED)

    assert len(await case.read()) == 2
