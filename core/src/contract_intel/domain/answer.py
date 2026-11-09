from dataclasses import dataclass, field

from contract_intel.domain.ids import DocumentId
from contract_intel.domain.page import PageRange
from contract_intel.domain.text import ensure_not_blank


@dataclass(frozen=True, slots=True)
class Citation:
    """Evidence supporting an answer: an excerpt and where it was found."""

    document_id: DocumentId
    pages: PageRange
    excerpt: str

    def __post_init__(self) -> None:
        ensure_not_blank(self.excerpt, "excerpt")


@dataclass(frozen=True, slots=True)
class Answer:
    """Response to a question over contracts, grounded on citations."""

    question: str
    text: str
    citations: tuple[Citation, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        ensure_not_blank(self.question, "question")
        ensure_not_blank(self.text, "text")
