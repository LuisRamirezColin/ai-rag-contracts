from typing import Protocol, runtime_checkable

from contract_intel.domain.contract import Contract
from contract_intel.domain.ids import ContractId


@runtime_checkable
class ContractRepository(Protocol):
    """Persistence of contract aggregates and their clauses."""

    async def get(self, contract_id: ContractId) -> Contract | None:
        """Return the contract, or ``None`` when it does not exist."""
        ...

    async def save(self, contract: Contract) -> None:
        """Create or replace ``contract``."""
        ...
