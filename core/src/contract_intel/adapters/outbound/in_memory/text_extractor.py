from contract_intel.domain.errors import UnreadableDocumentError
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.page import FIRST_PAGE, Page

PAGE_BREAK = "\f"


class InMemoryTextExtractor:
    """Treat content as UTF-8 text whose pages are separated by form feeds."""

    async def extract_pages(
        self, document_id: DocumentId, content: bytes
    ) -> tuple[Page, ...]:
        """Split the decoded text into pages numbered from the first page.

        Raises:
            UnreadableDocumentError: If ``content`` is not valid UTF-8.
        """
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise UnreadableDocumentError(document_id, str(error)) from error
        return tuple(
            Page(document_id=document_id, number=number, text=text)
            for number, text in enumerate(decoded.split(PAGE_BREAK), start=FIRST_PAGE)
        )
