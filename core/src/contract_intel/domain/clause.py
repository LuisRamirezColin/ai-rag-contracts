from dataclasses import dataclass

from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.errors import NegativeQuantityError
from contract_intel.domain.ids import ClauseId, DocumentId
from contract_intel.domain.page import PageRange
from contract_intel.domain.text import ensure_not_blank


@dataclass(frozen=True, slots=True)
class Clause:
    """A clause found in a document, classified by type and located by pages."""

    id: ClauseId
    document_id: DocumentId
    clause_type: ClauseType
    text: str
    pages: PageRange

    def __post_init__(self) -> None:
        ensure_not_blank(self.text, "text")


@dataclass(frozen=True, slots=True)
class ClauseExtraction:
    """Clauses found in a document plus the model and tokens that found them."""

    clauses: tuple[Clause, ...]
    model: str
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        ensure_not_blank(self.model, "model")
        for field_name in ("input_tokens", "output_tokens"):
            value = getattr(self, field_name)
            if value < 0:
                raise NegativeQuantityError(field_name, value)
