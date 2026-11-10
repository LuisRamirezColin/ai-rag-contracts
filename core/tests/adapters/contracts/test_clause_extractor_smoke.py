"""Calls the real Claude API; runs only with ``-m anthropic`` and credentials."""

import os

import pytest

from contract_intel.adapters.outbound.langgraph.langgraph_clause_extractor import (
    ExtractionConfig,
    LangGraphClauseExtractor,
)
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.ids import ContractId, DocumentId
from contract_intel.domain.page import Page

PLACEHOLDER_KEYS = {"", "replace-me"}
DOC = Document(DocumentId("smoke"), ContractId("smoke"), "Smoke", DocumentType.OTHER)
PAGES = (
    Page(DOC.id, 1, "1. Services. Provider shall deliver the services in Schedule A."),
    Page(
        DOC.id,
        2,
        "14. Governing Law. This Agreement shall be governed by and construed in "
        "accordance with the laws of the State of Delaware.",
    ),
)

pytestmark = pytest.mark.anthropic


@pytest.fixture
def extractor() -> LangGraphClauseExtractor:
    settings = AppSettings()
    api_key = settings.llm.api_key.get_secret_value()
    if api_key in PLACEHOLDER_KEYS and not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("No Anthropic credentials configured")
    extraction = settings.extraction
    return LangGraphClauseExtractor(
        ExtractionConfig(
            api_key=None if api_key in PLACEHOLDER_KEYS else api_key,
            model=extraction.model,
            effort=extraction.effort,
            max_tokens=extraction.max_tokens,
            window_chars=extraction.window_chars,
        )
    )


async def test_real_extraction_finds_the_governing_law_clause(extractor):
    extraction = await extractor.extract(DOC, PAGES)

    law = [c for c in extraction.clauses if c.clause_type is ClauseType.GOVERNING_LAW]
    assert law
    assert "Delaware" in law[0].text
    assert law[0].pages.first == 2
    assert extraction.input_tokens > 0
    assert extraction.output_tokens > 0
