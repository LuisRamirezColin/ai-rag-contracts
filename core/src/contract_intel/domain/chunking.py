"""Split a document's pages into overlapping, page-aware text windows."""

from collections.abc import Sequence
from dataclasses import dataclass

from contract_intel.domain.chunk import Chunk
from contract_intel.domain.errors import InvalidChunkingError
from contract_intel.domain.ids import ChunkId, DocumentId
from contract_intel.domain.page import Page, PageRange

PAGE_SEPARATOR = "\n\n"
# Preferred cut points, best first: paragraph, line, word.
_CUT_MARKERS = ("\n\n", "\n", " ")
# A cut is only taken if it keeps at least this share of the window.
_MIN_WINDOW_SHARE = 0.5


@dataclass(frozen=True, slots=True)
class ChunkingPolicy:
    """Maximum chunk size and overlap between consecutive chunks, in characters."""

    max_chars: int
    overlap_chars: int

    def __post_init__(self) -> None:
        if self.max_chars <= 0 or not 0 <= self.overlap_chars < self.max_chars:
            raise InvalidChunkingError(self.max_chars, self.overlap_chars)


@dataclass(frozen=True, slots=True)
class _PageSpan:
    number: int
    start: int
    end: int


def chunk_id_for(document_id: DocumentId, ordinal: int) -> ChunkId:
    """Return the deterministic id of the ``ordinal``-th chunk of a document."""
    return ChunkId(f"{document_id}:{ordinal:04d}")


def chunk_pages(
    document_id: DocumentId, pages: Sequence[Page], policy: ChunkingPolicy
) -> tuple[Chunk, ...]:
    """Split ``pages`` into chunks of at most ``policy.max_chars`` characters.

    Pages without visible text are skipped. Each chunk records the range of pages
    its text comes from, so a chunk crossing a page break covers both pages.
    """
    text, spans = _join_pages(pages)
    chunks: list[Chunk] = []
    for start, end in _windows(text, policy):
        window_text = text[start:end].strip()
        if not window_text:
            continue
        chunks.append(
            Chunk(
                id=chunk_id_for(document_id, len(chunks)),
                document_id=document_id,
                text=window_text,
                pages=_page_range(spans, start, end),
            )
        )
    return tuple(chunks)


def _join_pages(pages: Sequence[Page]) -> tuple[str, list[_PageSpan]]:
    parts: list[str] = []
    spans: list[_PageSpan] = []
    offset = 0
    for page in sorted(pages, key=lambda p: p.number):
        if not page.text.strip():
            continue
        if parts:
            parts.append(PAGE_SEPARATOR)
            offset += len(PAGE_SEPARATOR)
        parts.append(page.text)
        spans.append(_PageSpan(page.number, offset, offset + len(page.text)))
        offset += len(page.text)
    return "".join(parts), spans


def _windows(text: str, policy: ChunkingPolicy) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        end = _cut_point(text, start, policy.max_chars)
        windows.append((start, end))
        if end >= len(text):
            break
        start = _next_start(text, start, end, policy.overlap_chars)
    return windows


def _cut_point(text: str, start: int, max_chars: int) -> int:
    hard_end = min(start + max_chars, len(text))
    if hard_end == len(text):
        return hard_end
    earliest = start + int(max_chars * _MIN_WINDOW_SHARE)
    for marker in _CUT_MARKERS:
        position = text.rfind(marker, earliest, hard_end)
        if position != -1:
            return position + len(marker)
    return hard_end


def _next_start(text: str, start: int, end: int, overlap_chars: int) -> int:
    candidate = end - overlap_chars
    if candidate <= start:
        return end
    # Begin the overlap on a word boundary when one is available.
    boundary = text.find(" ", candidate, end)
    return boundary + 1 if boundary != -1 else candidate


def _page_range(spans: Sequence[_PageSpan], start: int, end: int) -> PageRange:
    covered = [span.number for span in spans if span.start < end and span.end > start]
    return PageRange(first=min(covered), last=max(covered))
