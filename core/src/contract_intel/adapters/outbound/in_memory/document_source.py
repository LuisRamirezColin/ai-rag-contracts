from collections.abc import Mapping

from contract_intel.domain.document import Document
from contract_intel.domain.ids import DocumentId


class InMemoryDocumentSource:
    """Document source backed by a dictionary of documents and their bytes."""

    def __init__(
        self, documents: Mapping[DocumentId, tuple[Document, bytes]] | None = None
    ) -> None:
        self._documents = dict(documents or {})

    async def list_documents(self) -> tuple[Document, ...]:
        """Return every registered document."""
        return tuple(document for document, _ in self._documents.values())

    async def fetch_content(self, document_id: DocumentId) -> bytes:
        """Return the bytes registered for ``document_id``.

        Raises:
            KeyError: If the document is unknown.
        """
        _, content = self._documents[document_id]
        return content
