from contract_intel.adapters.outbound.in_memory.clause_extractor import (
    InMemoryClauseExtractor,
)
from contract_intel.adapters.outbound.in_memory.contract_repository import (
    InMemoryContractRepository,
)
from contract_intel.adapters.outbound.in_memory.ground_truth_source import (
    InMemoryGroundTruthSource,
)
from contract_intel.adapters.outbound.in_memory.usage_tracker import (
    InMemoryUsageTracker,
)
from contract_intel.application.use_cases.evaluate_clause_extraction import (
    EvaluateClauseExtractionUseCase,
)
from contract_intel.application.use_cases.extract_clauses import (
    ExtractClausesUseCase,
)
from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.evaluation import ExpertLabels
from contract_intel.domain.ids import ClauseId, ContractId, DocumentId
from contract_intel.domain.page import Page, PageRange
from contract_intel.domain.usage import TokenPricing

LAW = ClauseType.GOVERNING_LAW


def document(name):
    return Document(
        DocumentId(name),
        ContractId(name),
        f"{name.upper()} AGREEMENT",
        DocumentType.OTHER,
    )


ALPHA, BETA, GAMMA, UNPROCESSED = (
    document(n) for n in ("alpha", "beta", "gamma", "delta")
)
LABELS = {
    ALPHA.title: ExpertLabels(ALPHA.title, {LAW: ("laws of Delaware",)}),
    BETA.title: ExpertLabels(BETA.title, {LAW: ("laws of Israel",)}),
    UNPROCESSED.title: ExpertLabels(UNPROCESSED.title, {LAW: ("laws of Texas",)}),
}


class CountingExtractor(InMemoryClauseExtractor):
    calls = 0

    async def extract(self, document, pages):
        CountingExtractor.calls += 1
        return await super().extract(document, pages)


async def test_evaluates_processed_labelled_documents(repository):
    contracts = InMemoryContractRepository()
    law = Clause(
        ClauseId("alpha:law"),
        ALPHA.id,
        LAW,
        "Governed by the laws of Delaware.",
        PageRange(1, 1),
    )
    extractor = CountingExtractor({ALPHA.id: (law,)})
    extract = ExtractClausesUseCase(
        repository,
        extractor,
        contracts,
        InMemoryUsageTracker(),
        TokenPricing(2.0, 10.0),
    )
    for doc in (ALPHA, BETA, GAMMA, UNPROCESSED):
        await repository.save_ingested(doc, (Page(doc.id, 1, "text"),))
    for doc in (ALPHA, BETA, GAMMA):
        await extract.execute(doc.id)
    calls_after_extraction = CountingExtractor.calls

    report = await EvaluateClauseExtractionUseCase(
        repository, contracts, InMemoryGroundTruthSource(LABELS)
    ).execute()

    law_metrics = next(m for m in report.types if m.clause_type is LAW)
    assert (
        law_metrics.true_positives,
        law_metrics.false_positives,
        law_metrics.false_negatives,
    ) == (1, 0, 1)
    assert law_metrics.evidence_matches == 1
    assert report.evaluated_documents == (ALPHA.title, BETA.title)
    assert report.excluded_documents == (GAMMA.title,)
    assert CountingExtractor.calls == calls_after_extraction
