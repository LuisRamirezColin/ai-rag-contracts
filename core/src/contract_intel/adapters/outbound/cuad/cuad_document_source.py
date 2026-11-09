import asyncio
import hashlib
import re
from pathlib import Path

from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.errors import UnknownDocumentError
from contract_intel.domain.ids import ContractId, DocumentId

PDF_SUFFIX = ".pdf"
SLUG_MAX_LENGTH = 64
PATH_HASH_LENGTH = 8
_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


class CuadDirectoryMissingError(FileNotFoundError):
    """Raised when the CUAD directory has not been downloaded."""

    def __init__(self, root: Path) -> None:
        super().__init__(
            f"CUAD directory not found: {root}. "
            "Run `uv run python scripts/download_cuad.py` first."
        )


class DuplicateDocumentIdError(RuntimeError):
    """Raised when two files map to the same document id."""

    def __init__(self, document_id: DocumentId, first: Path, second: Path) -> None:
        super().__init__(f"'{first}' and '{second}' both map to id '{document_id}'")


def document_id_for(relative_path: Path) -> DocumentId:
    """Build a stable, readable id: file-name slug plus a hash of the path."""
    slug = _NON_ALPHANUMERIC.sub("-", relative_path.stem.lower()).strip("-")
    slug = slug[:SLUG_MAX_LENGTH].rstrip("-")
    path_hash = hashlib.sha256(relative_path.as_posix().encode()).hexdigest()
    return DocumentId(f"{slug}-{path_hash[:PATH_HASH_LENGTH]}")


class CuadDocumentSource:
    """Contracts of the public CUAD dataset read from a local directory.

    Each PDF is one contract made of a single document.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    async def list_documents(self) -> tuple[Document, ...]:
        """Return one document per PDF under the root, ordered by path."""
        index = await asyncio.to_thread(self._index)
        return tuple(
            _document_from(document_id, path) for document_id, path in index.items()
        )

    async def fetch_content(self, document_id: DocumentId) -> bytes:
        """Return the PDF bytes of ``document_id``.

        Raises:
            UnknownDocumentError: If no PDF maps to ``document_id``.
        """
        index = await asyncio.to_thread(self._index)
        if document_id not in index:
            raise UnknownDocumentError(document_id)
        return await asyncio.to_thread(index[document_id].read_bytes)

    def _index(self) -> dict[DocumentId, Path]:
        if not self._root.is_dir():
            raise CuadDirectoryMissingError(self._root)
        index: dict[DocumentId, Path] = {}
        for path in sorted(self._pdf_files()):
            document_id = document_id_for(path.relative_to(self._root))
            if document_id in index:
                raise DuplicateDocumentIdError(document_id, index[document_id], path)
            index[document_id] = path
        return index

    def _pdf_files(self) -> list[Path]:
        return [
            path
            for path in self._root.rglob("*")
            if path.is_file() and path.suffix.lower() == PDF_SUFFIX
        ]


def _document_from(document_id: DocumentId, path: Path) -> Document:
    return Document(
        id=document_id,
        contract_id=ContractId(document_id),
        title=path.stem,
        document_type=DocumentType.OTHER,
    )
