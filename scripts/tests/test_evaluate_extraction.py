import evaluate_extraction

from contract_intel.adapters.outbound.in_memory.clause_extractor import (
    InMemoryClauseExtractor,
)
from contract_intel.adapters.outbound.in_memory.ground_truth_source import (
    InMemoryGroundTruthSource,
)
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.bootstrap.writer import build_writer_container
from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.evaluation import ExpertLabels
from contract_intel.domain.ids import ClauseId, ContractId, DocumentId
from contract_intel.domain.page import Page, PageRange

DOC = Document(
    DocumentId("msa"), ContractId("msa"), "MSA AGREEMENT", DocumentType.OTHER
)
LAW = Clause(
    ClauseId("msa:governing_law:000"),
    DOC.id,
    ClauseType.GOVERNING_LAW,
    "Governed by the laws of Delaware.",
    PageRange(1, 1),
)


async def test_report_is_rendered_from_stored_clauses():
    container = build_writer_container(AppSettings(_env_file=None, use_fakes=True))
    container.clause_extractor.override(InMemoryClauseExtractor({DOC.id: (LAW,)}))
    container.ground_truth_source.override(
        InMemoryGroundTruthSource(
            {
                DOC.title: ExpertLabels(
                    DOC.title, {ClauseType.GOVERNING_LAW: ("laws of Delaware",)}
                )
            }
        )
    )
    await container.document_repository().save_ingested(
        DOC, (Page(DOC.id, 1, "Governed by the laws of Delaware."),)
    )
    await container.extract_clauses().execute(DOC.id)

    markdown = await evaluate_extraction.render_report(container)

    assert "| governing_law | 1 | 0 | 0 | 100% | 100% | 100% | 100% |" in markdown
    assert "Evaluated documents: 1" in markdown
