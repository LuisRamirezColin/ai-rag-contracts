"""Shared fixtures for the outbound-port contract suites.

Every suite runs the same expectations against the in-memory fake and the real
adapter (LSP). Sample PDFs are generated here so no real contract is versioned.
"""

from fpdf import FPDF

PDF_FONT = "Helvetica"
PDF_FONT_SIZE = 12
PDF_LINE_HEIGHT = 10
FULL_WIDTH = 0


def build_pdf(*page_texts: str) -> bytes:
    """Return a PDF with one page per argument; empty strings give blank pages."""
    pdf = FPDF()
    pdf.set_font(PDF_FONT, size=PDF_FONT_SIZE)
    for text in page_texts:
        pdf.add_page()
        if text:
            pdf.multi_cell(FULL_WIDTH, PDF_LINE_HEIGHT, text)
    return bytes(pdf.output())
