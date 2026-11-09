from contract_intel.domain.contract import Contract
from contract_intel.domain.ids import ContractId


class InMemoryContractRepository:
    """Contract repository kept in a process-local dictionary."""

    def __init__(self) -> None:
        self._contracts: dict[ContractId, Contract] = {}

    async def get(self, contract_id: ContractId) -> Contract | None:
        """Return the stored contract, if any."""
        return self._contracts.get(contract_id)

    async def save(self, contract: Contract) -> None:
        """Create or replace ``contract``."""
        self._contracts[contract.id] = contract
