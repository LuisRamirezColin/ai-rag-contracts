import pytest

from contract_intel.adapters.outbound.in_memory.clause_extractor import (
    IN_MEMORY_EXTRACTION_MODEL,
    InMemoryClauseExtractor,
)
from contract_intel.adapters.outbound.in_memory.contract_repository import (
    InMemoryContractRepository,
)
from contract_intel.adapters.outbound.in_memory.usage_tracker import (
    InMemoryUsageTracker,
)
from contract_intel.application.ports.inbound.extract_clauses import ExtractClauses
from contract_intel.application.use_cases.extract_clauses import (
    EXTRACT_CLAUSES_OPERATION,
    ExtractClausesUseCase,
)
from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.errors import DocumentNotAvailableError
from contract_intel.domain.ids import ClauseId, ContractId, DocumentId
from contract_intel.domain.page import Page, PageRange
from contract_intel.domain.usage import TokenPricing

CONTRACT = ContractId("msa")
DOC = Document(DocumentId("msa-main"), CONTRACT, "MSA", DocumentType.OTHER)
AMENDMENT = Document(DocumentId("msa-amend"), CONTRACT, "MSA", DocumentType.AMENDMENT)
PRICING = TokenPricing(input_per_million=2.0, output_per_million=10.0)


def clause(document, clause_type, text):
    return Clause(
        ClauseId(f"{document.id}:{clause_type}:000"),
        document.id,
        clause_type,
        text,
        PageRange(1, 1),
    )


LAW = clause(DOC, ClauseType.GOVERNING_LAW, "Governed by Delaware law.")
CAP = clause(DOC, ClauseType.CAP_ON_LIABILITY, "Liability capped at fees.")
AMEND_LAW = clause(AMENDMENT, ClauseType.GOVERNING_LAW, "Amendment governed by NY law.")


@pytest.fixture
def contracts():
    return InMemoryContractRepository()


@pytest.fixture
def tracker():
    return InMemoryUsageTracker()


async def _ingest(repository, document):
    await repository.save_ingested(document, (Page(document.id, 1, "Some text."),))


def _use_case(repository, contracts, tracker, configured):
    return ExtractClausesUseCase(
        repository, InMemoryClauseExtractor(configured), contracts, tracker, PRICING
    )


def test_satisfies_inbound_port(repository, contracts, tracker):
    assert isinstance(_use_case(repository, contracts, tracker, {}), ExtractClauses)


async def test_clauses_are_stored_in_a_new_contract(repository, contracts, tracker):
    await _ingest(repository, DOC)

    result = await _use_case(
        repository, contracts, tracker, {DOC.id: (LAW, CAP)}
    ).execute(DOC.id)

    assert result == (LAW, CAP)
    contract = await contracts.get(CONTRACT)
    assert contract is not None
    assert contract.title == "MSA"
    assert contract.document_ids == (DOC.id,)
    assert set(await contracts.clauses_of_document(DOC.id)) == {LAW, CAP}


async def test_reextraction_replaces_only_that_documents_clauses(
    repository, contracts, tracker
):
    await _ingest(repository, DOC)
    await _ingest(repository, AMENDMENT)
    first = _use_case(
        repository, contracts, tracker, {DOC.id: (LAW, CAP), AMENDMENT.id: (AMEND_LAW,)}
    )
    await first.execute(DOC.id)
    await first.execute(AMENDMENT.id)

    second = _use_case(repository, contracts, tracker, {DOC.id: (LAW,)})
    await second.execute(DOC.id)

    assert await contracts.clauses_of_document(DOC.id) == (LAW,)
    assert await contracts.clauses_of_document(AMENDMENT.id) == (AMEND_LAW,)
    contract = await contracts.get(CONTRACT)
    assert contract is not None
    assert set(contract.document_ids) == {DOC.id, AMENDMENT.id}


async def test_usage_is_recorded_for_the_document(repository, contracts, tracker):
    await _ingest(repository, DOC)

    await _use_case(repository, contracts, tracker, {DOC.id: (LAW,)}).execute(DOC.id)

    (usage,) = tracker.records
    assert usage.operation == EXTRACT_CLAUSES_OPERATION
    assert usage.model == IN_MEMORY_EXTRACTION_MODEL
    assert usage.document_id == DOC.id
    assert usage.cost_usd == pytest.approx(
        PRICING.cost_usd(usage.input_tokens, usage.output_tokens)
    )


@pytest.mark.parametrize("state", ["missing", "failed"])
async def test_unavailable_document_changes_nothing(
    repository, contracts, tracker, state
):
    if state == "failed":
        await repository.save_failed(DOC, "no extractable text")

    with pytest.raises(DocumentNotAvailableError):
        await _use_case(repository, contracts, tracker, {DOC.id: (LAW,)}).execute(
            DOC.id
        )

    assert await contracts.get(CONTRACT) is None
    assert tracker.records == []
