from contract_intel.domain.ids import DocumentId
from contract_intel.domain.page import FIRST_PAGE, Page

PAGE_BREAK = "\f"


class InMemoryTextExtractor:
    """Treat content as UTF-8 text whose pages are separated by form feeds."""

    async def extract_pages(
        self, document_id: DocumentId, content: bytes
    ) -> tuple[Page, ...]:
        """Split the decoded text into pages numbered from the first page."""
        texts = content.decode("utf-8").split(PAGE_BREAK)
        return tuple(
            Page(document_id=document_id, number=number, text=text)
            for number, text in enumerate(texts, start=FIRST_PAGE)
        )
