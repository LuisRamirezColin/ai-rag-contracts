from dataclasses import dataclass, field

from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.ids import ContractId, DocumentId
from contract_intel.domain.text import ensure_not_blank


@dataclass(frozen=True, slots=True)
class Contract:
    """Aggregate of the documents of one agreement and their extracted clauses."""

    id: ContractId
    title: str
    document_ids: tuple[DocumentId, ...] = field(default_factory=tuple)
    clauses: tuple[Clause, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        ensure_not_blank(self.title, "title")

    def clauses_of_type(self, clause_type: ClauseType) -> tuple[Clause, ...]:
        """Return the clauses classified as ``clause_type``."""
        return tuple(c for c in self.clauses if c.clause_type == clause_type)
