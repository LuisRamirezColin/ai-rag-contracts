from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from contract_intel.adapters.outbound.in_memory.contract_repository import (
    InMemoryContractRepository,
)
from contract_intel.adapters.outbound.persistence.contract_repository import (
    SqlAlchemyContractRepository,
)
from contract_intel.adapters.outbound.persistence.document_repository import (
    SqlAlchemyDocumentRepository,
)
from contract_intel.application.ports.outbound.contract_repository import (
    ContractRepository,
)
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.contract import Contract
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.ids import ClauseId, ContractId, DocumentId
from contract_intel.domain.page import Page, PageRange

MAIN, AMEND, OTHER_DOC = (
    DocumentId("msa-main"),
    DocumentId("msa-amend"),
    DocumentId("nda"),
)
MSA, NDA = ContractId("msa"), ContractId("nda")


def clause(document_id, clause_type, page, ordinal=0):
    return Clause(
        ClauseId(f"{document_id}:{clause_type}:{ordinal:03d}"),
        document_id,
        clause_type,
        f"{clause_type} clause of {document_id}",
        PageRange(page, page),
    )


LAW_MAIN = clause(MAIN, ClauseType.GOVERNING_LAW, 8)
CAP_MAIN = clause(MAIN, ClauseType.CAP_ON_LIABILITY, 3)
LAW_AMEND = clause(AMEND, ClauseType.GOVERNING_LAW, 1)
LAW_NDA = clause(OTHER_DOC, ClauseType.GOVERNING_LAW, 2)


@pytest.fixture
async def postgres_repository() -> AsyncIterator[SqlAlchemyContractRepository]:
    engine = create_async_engine(AppSettings().database.url, poolclass=NullPool)
    sessions = async_sessionmaker(engine)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE documents, contracts CASCADE"))
    documents = SqlAlchemyDocumentRepository(sessions)
    for document_id in (MAIN, AMEND, OTHER_DOC):
        document = Document(
            document_id, ContractId(document_id), document_id, DocumentType.OTHER
        )
        await documents.save_ingested(document, (Page(document_id, 1, "text"),))
    yield SqlAlchemyContractRepository(sessions)
    await engine.dispose()


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def repository(request: pytest.FixtureRequest) -> ContractRepository:
    if request.param == "postgres":
        real: ContractRepository = request.getfixturevalue("postgres_repository")
        return real
    return InMemoryContractRepository()


async def test_saved_contract_is_read_back_sorted(repository):
    contract = Contract(
        MSA, "Master Services Agreement", (MAIN, AMEND), (LAW_MAIN, LAW_AMEND, CAP_MAIN)
    )

    await repository.save(contract)

    stored = await repository.get(MSA)
    assert stored == Contract(
        MSA, "Master Services Agreement", (AMEND, MAIN), (LAW_AMEND, CAP_MAIN, LAW_MAIN)
    )


async def test_unknown_contract_is_none(repository):
    assert await repository.get(MSA) is None
    assert await repository.clauses_of_document(MAIN) == ()


async def test_save_replaces_documents_and_clauses(repository):
    await repository.save(
        Contract(MSA, "Old title", (MAIN, AMEND), (LAW_MAIN, LAW_AMEND))
    )

    await repository.save(Contract(MSA, "New title", (MAIN,), (CAP_MAIN,)))

    assert await repository.get(MSA) == Contract(MSA, "New title", (MAIN,), (CAP_MAIN,))
    assert await repository.clauses_of_document(AMEND) == ()


async def test_clauses_of_document_are_per_document(repository):
    await repository.save(
        Contract(MSA, "MSA", (MAIN, AMEND), (LAW_MAIN, CAP_MAIN, LAW_AMEND))
    )

    assert await repository.clauses_of_document(MAIN) == (CAP_MAIN, LAW_MAIN)
    assert await repository.clauses_of_document(AMEND) == (LAW_AMEND,)


async def test_contracts_are_isolated(repository):
    await repository.save(Contract(MSA, "MSA", (MAIN,), (LAW_MAIN,)))
    await repository.save(Contract(NDA, "NDA", (OTHER_DOC,), (LAW_NDA,)))

    await repository.save(Contract(MSA, "MSA", (MAIN,), ()))

    assert await repository.clauses_of_document(OTHER_DOC) == (LAW_NDA,)


async def test_contract_without_clauses_is_kept(repository):
    await repository.save(Contract(MSA, "MSA", (MAIN,), ()))

    assert await repository.get(MSA) == Contract(MSA, "MSA", (MAIN,), ())
