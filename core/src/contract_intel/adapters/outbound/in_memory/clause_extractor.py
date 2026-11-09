from collections.abc import Mapping, Sequence

from contract_intel.domain.clause import Clause
from contract_intel.domain.document import Document
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.page import Page


class InMemoryClauseExtractor:
    """Return clauses preconfigured per document instead of calling a model."""

    def __init__(
        self, clauses_by_document: Mapping[DocumentId, tuple[Clause, ...]] | None = None
    ) -> None:
        self._clauses_by_document = dict(clauses_by_document or {})

    async def extract(
        self, document: Document, pages: Sequence[Page]
    ) -> tuple[Clause, ...]:
        """Return the clauses configured for ``document``, or none."""
        return self._clauses_by_document.get(document.id, ())
