from dataclasses import dataclass

from contract_intel.domain.errors import InvalidPageNumberError, InvalidPageRangeError
from contract_intel.domain.ids import DocumentId

FIRST_PAGE = 1


def _ensure_valid_page_number(number: int) -> None:
    if number < FIRST_PAGE:
        raise InvalidPageNumberError(number)


@dataclass(frozen=True, slots=True)
class Page:
    """Text of a single document page; text may be empty for blank pages."""

    document_id: DocumentId
    number: int
    text: str

    def __post_init__(self) -> None:
        _ensure_valid_page_number(self.number)


@dataclass(frozen=True, slots=True)
class PageRange:
    """Inclusive range of pages where a piece of text appears."""

    first: int
    last: int

    def __post_init__(self) -> None:
        _ensure_valid_page_number(self.first)
        if self.last < self.first:
            raise InvalidPageRangeError(self.first, self.last)

    @classmethod
    def single(cls, number: int) -> "PageRange":
        """Build a range covering exactly one page."""
        return cls(first=number, last=number)
