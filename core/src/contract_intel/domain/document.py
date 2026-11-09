from dataclasses import dataclass
from enum import StrEnum

from contract_intel.domain.ids import ContractId, DocumentId
from contract_intel.domain.text import ensure_not_blank


class DocumentType(StrEnum):
    """Kind of legal document within a contract."""

    MASTER_SERVICE_AGREEMENT = "master_service_agreement"
    NON_DISCLOSURE_AGREEMENT = "non_disclosure_agreement"
    STATEMENT_OF_WORK = "statement_of_work"
    AMENDMENT = "amendment"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Document:
    """A single legal document (file) that belongs to a contract."""

    id: DocumentId
    contract_id: ContractId
    title: str
    document_type: DocumentType

    def __post_init__(self) -> None:
        ensure_not_blank(self.title, "title")
