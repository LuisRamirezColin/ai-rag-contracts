from typing import Protocol, runtime_checkable

from contract_intel.domain.clause import Clause
from contract_intel.domain.ids import DocumentId


@runtime_checkable
class ExtractClauses(Protocol):
    """Extract and persist the typed clauses of a stored document."""

    async def execute(self, document_id: DocumentId) -> tuple[Clause, ...]:
        """Extract the clauses of ``document_id``."""
        ...
