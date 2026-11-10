from collections.abc import Callable
from dataclasses import dataclass

import pytest

from contract_intel.adapters.outbound.in_memory.text_extractor import (
    PAGE_BREAK,
    InMemoryTextExtractor,
)
from contract_intel.adapters.outbound.pdf.pypdf_text_extractor import (
    PypdfTextExtractor,
)
from contract_intel.application.ports.outbound.text_extractor import TextExtractor
from contract_intel.domain.errors import UnreadableDocumentError
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.ingestion import has_extractable_text

from .conftest import build_pdf

DOC = DocumentId("doc-1")


@dataclass(frozen=True)
class ExtractorCase:
    """An extractor plus how to encode pages in the format it reads."""

    extractor: TextExtractor
    encode: Callable[..., bytes]
    unreadable: bytes


def _encode_text(*pages: str) -> bytes:
    return PAGE_BREAK.join(pages).encode()


@pytest.fixture(
    params=[
        ExtractorCase(InMemoryTextExtractor(), _encode_text, b"\xff\xfe"),
        ExtractorCase(PypdfTextExtractor(), build_pdf, b"not a pdf at all"),
    ],
    ids=["in_memory", "pypdf"],
)
def case(request: pytest.FixtureRequest) -> ExtractorCase:
    case: ExtractorCase = request.param
    return case


async def test_returns_every_page_numbered_in_order(case):
    content = case.encode("Recitals", "Term and termination", "Governing law")

    pages = await case.extractor.extract_pages(DOC, content)

    assert [p.number for p in pages] == [1, 2, 3]
    assert all(p.document_id == DOC for p in pages)
    assert "Governing law" in pages[2].text


async def test_blank_pages_have_no_extractable_text(case):
    pages = await case.extractor.extract_pages(DOC, case.encode("", ""))

    assert len(pages) == 2
    assert not has_extractable_text(pages)


async def test_unreadable_content_raises_domain_error(case):
    with pytest.raises(UnreadableDocumentError):
        await case.extractor.extract_pages(DOC, case.unreadable)
