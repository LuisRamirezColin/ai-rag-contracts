from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from contract_intel.domain.clause import Clause
from contract_intel.domain.document import Document
from contract_intel.domain.page import Page


@runtime_checkable
class ClauseExtractor(Protocol):
    """Identify and classify the clauses contained in a document's pages."""

    async def extract(
        self, document: Document, pages: Sequence[Page]
    ) -> tuple[Clause, ...]:
        """Return the clauses found in ``pages`` of ``document``."""
        ...
