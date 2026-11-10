from dataclasses import replace

from contract_intel.domain.clause import Clause
from contract_intel.domain.contract import Contract
from contract_intel.domain.ids import ContractId, DocumentId


def _clause_order(clause: Clause) -> tuple[int, str]:
    return (clause.pages.first, clause.id)


class InMemoryContractRepository:
    """Contract repository kept in a process-local dictionary.

    Documents are returned sorted by id and clauses by first page and id.
    """

    def __init__(self) -> None:
        self._contracts: dict[ContractId, Contract] = {}

    async def get(self, contract_id: ContractId) -> Contract | None:
        """Return the stored contract, if any."""
        return self._contracts.get(contract_id)

    async def save(self, contract: Contract) -> None:
        """Create or replace ``contract``."""
        self._contracts[contract.id] = replace(
            contract,
            document_ids=tuple(sorted(contract.document_ids)),
            clauses=tuple(sorted(contract.clauses, key=_clause_order)),
        )

    async def clauses_of_document(self, document_id: DocumentId) -> tuple[Clause, ...]:
        """Return the clauses of ``document_id`` across stored contracts."""
        return tuple(
            sorted(
                (
                    clause
                    for contract in self._contracts.values()
                    for clause in contract.clauses
                    if clause.document_id == document_id
                ),
                key=_clause_order,
            )
        )
