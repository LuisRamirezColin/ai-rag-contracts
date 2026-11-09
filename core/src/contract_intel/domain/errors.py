class DomainError(Exception):
    """Base class for violations of domain invariants."""


class InvalidPageNumberError(DomainError):
    """Raised when a page number is lower than the first page."""

    def __init__(self, number: int) -> None:
        super().__init__(f"Page numbers start at 1, got {number}")


class InvalidPageRangeError(DomainError):
    """Raised when a page range ends before it starts."""

    def __init__(self, first: int, last: int) -> None:
        super().__init__(f"Page range ends before it starts: {first}-{last}")


class BlankTextError(DomainError):
    """Raised when a field that must carry text is empty or whitespace."""

    def __init__(self, field_name: str) -> None:
        super().__init__(f"'{field_name}' must not be blank")


class NegativeQuantityError(DomainError):
    """Raised when a count or amount that cannot be negative is negative."""

    def __init__(self, field_name: str, value: float) -> None:
        super().__init__(f"'{field_name}' must not be negative, got {value}")


class EmptyEmbeddingError(DomainError):
    """Raised when an embedding has no dimensions."""

    def __init__(self) -> None:
        super().__init__("An embedding must have at least one dimension")
