import pytest

from contract_intel.adapters.outbound.in_memory.document_repository import (
    InMemoryDocumentRepository,
)
from contract_intel.adapters.outbound.in_memory.document_source import (
    InMemoryDocumentSource,
)
from contract_intel.adapters.outbound.in_memory.document_storage import (
    InMemoryDocumentStorage,
)
from contract_intel.adapters.outbound.in_memory.text_extractor import (
    PAGE_BREAK,
    InMemoryTextExtractor,
)
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.ids import ContractId, DocumentId


def make_document(document_id: str) -> Document:
    return Document(
        id=DocumentId(document_id),
        contract_id=ContractId(document_id),
        title=f"Contract {document_id}",
        document_type=DocumentType.OTHER,
    )


def text_pages(*pages: str) -> bytes:
    """Content the in-memory extractor splits into one page per argument."""
    return PAGE_BREAK.join(pages).encode()


def make_source(contents: dict[str, bytes]) -> InMemoryDocumentSource:
    return InMemoryDocumentSource(
        {DocumentId(i): (make_document(i), content) for i, content in contents.items()}
    )


@pytest.fixture
def repository() -> InMemoryDocumentRepository:
    return InMemoryDocumentRepository()


@pytest.fixture
def storage() -> InMemoryDocumentStorage:
    return InMemoryDocumentStorage()


@pytest.fixture
def extractor() -> InMemoryTextExtractor:
    return InMemoryTextExtractor()
