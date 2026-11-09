from dataclasses import dataclass

from contract_intel.domain.clause_type import ClauseType
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
