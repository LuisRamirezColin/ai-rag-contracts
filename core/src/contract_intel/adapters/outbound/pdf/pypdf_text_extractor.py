import asyncio
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from contract_intel.domain.errors import UnreadableDocumentError
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.page import FIRST_PAGE, Page

EMPTY_PASSWORD = ""


class PypdfTextExtractor:
    """Extract the text layer of PDF files page by page (no OCR)."""

    async def extract_pages(
        self, document_id: DocumentId, content: bytes
    ) -> tuple[Page, ...]:
        """Return every page of the PDF, numbered from the first page.

        Raises:
            UnreadableDocumentError: If the file is not a readable PDF.
        """
        return await asyncio.to_thread(_extract_pages, document_id, content)


def _extract_pages(document_id: DocumentId, content: bytes) -> tuple[Page, ...]:
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            reader.decrypt(EMPTY_PASSWORD)
        texts = [page.extract_text() or "" for page in reader.pages]
    except (PyPdfError, ValueError, OSError) as error:
        raise UnreadableDocumentError(document_id, str(error)) from error
    return tuple(
        Page(document_id=document_id, number=number, text=text)
        for number, text in enumerate(texts, start=FIRST_PAGE)
    )
