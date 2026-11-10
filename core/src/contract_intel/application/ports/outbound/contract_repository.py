from typing import Protocol, runtime_checkable

from contract_intel.domain.clause import Clause
from contract_intel.domain.contract import Contract
from contract_intel.domain.ids import ContractId, DocumentId


@runtime_checkable
class ContractRepository(Protocol):
    """Persistence of contract aggregates and their clauses."""

    async def get(self, contract_id: ContractId) -> Contract | None:
        """Return the contract, or ``None`` when it does not exist."""
        ...

    async def save(self, contract: Contract) -> None:
        """Create or replace ``contract`` with its documents and clauses."""
        ...

    async def clauses_of_document(self, document_id: DocumentId) -> tuple[Clause, ...]:
        """Return the stored clauses of ``document_id`` (empty if none)."""
        ...
