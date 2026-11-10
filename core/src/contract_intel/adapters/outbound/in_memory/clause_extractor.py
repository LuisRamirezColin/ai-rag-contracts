from collections.abc import Mapping, Sequence

from contract_intel.domain.clause import Clause, ClauseExtraction
from contract_intel.domain.document import Document
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.page import Page

IN_MEMORY_EXTRACTION_MODEL = "in-memory-preconfigured"
CHARS_PER_TOKEN = 4


class InMemoryClauseExtractor:
    """Return clauses preconfigured per document instead of calling a model."""

    def __init__(
        self, clauses_by_document: Mapping[DocumentId, tuple[Clause, ...]] | None = None
    ) -> None:
        self._clauses_by_document = dict(clauses_by_document or {})

    async def extract(
        self, document: Document, pages: Sequence[Page]
    ) -> ClauseExtraction:
        """Return the clauses configured for ``document`` with estimated tokens."""
        clauses = self._clauses_by_document.get(document.id, ())
        return ClauseExtraction(
            clauses=clauses,
            model=IN_MEMORY_EXTRACTION_MODEL,
            input_tokens=sum(len(p.text) for p in pages) // CHARS_PER_TOKEN,
            output_tokens=sum(len(c.text) for c in clauses) // CHARS_PER_TOKEN,
        )
