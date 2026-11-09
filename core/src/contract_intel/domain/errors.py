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


class UnknownDocumentError(DomainError):
    """Raised when a document id is unknown to a source or to storage."""

    def __init__(self, document_id: str) -> None:
        super().__init__(f"Unknown document '{document_id}'")


class UnreadableDocumentError(DomainError):
    """Raised when a document file is corrupt or cannot be parsed."""

    def __init__(self, document_id: str, detail: str) -> None:
        super().__init__(f"Document '{document_id}' cannot be read: {detail}")


class DocumentNotAvailableError(DomainError):
    """Raised when pages are requested for a document that is not ingested."""

    def __init__(self, document_id: str) -> None:
        super().__init__(f"Document '{document_id}' is not ingested")


class InconsistentIngestionRecordError(DomainError):
    """Raised when an ingestion record's fields contradict its status."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"Inconsistent ingestion record: {detail}")


class InvalidChunkingError(DomainError):
    """Raised when chunk size or overlap make no sense."""

    def __init__(self, max_chars: int, overlap_chars: int) -> None:
        super().__init__(
            "Chunking needs max_chars > 0 and 0 <= overlap_chars < max_chars, "
            f"got max_chars={max_chars}, overlap_chars={overlap_chars}"
        )


class EmbeddingDimensionMismatchError(DomainError):
    """Raised when embeddings do not have the dimension the index expects."""

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"Expected {expected}-dimensional embeddings, got {actual}")


class ChunkDocumentMismatchError(DomainError):
    """Raised when a chunk is written under a document it does not belong to."""

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(f"Chunk of document '{actual}' written under '{expected}'")


class EmbeddingCountMismatchError(DomainError):
    """Raised when an embedder returns a different number of vectors than texts."""

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"Expected {expected} embeddings, got {actual}")


class ProviderRateLimitedError(DomainError):
    """Raised when an external model provider rejects a call for rate limits."""

    def __init__(self, provider: str, detail: str) -> None:
        super().__init__(f"{provider} rate limit exceeded: {detail}")
        self.provider = provider


class ProviderUnavailableError(DomainError):
    """Raised when an external model provider cannot be reached or fails."""

    def __init__(self, provider: str, detail: str) -> None:
        super().__init__(f"{provider} is unavailable: {detail}")
        self.provider = provider


class AnswerRefusedError(DomainError):
    """Raised when the answer model declines to answer a question."""

    def __init__(self, category: str | None) -> None:
        reason = f" (category: {category})" if category else ""
        super().__init__(f"The model declined to answer{reason}")
        self.category = category
