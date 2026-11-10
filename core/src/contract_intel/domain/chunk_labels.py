"""Label retrievable chunks with the types of the clauses they contain."""

from collections.abc import Sequence
from dataclasses import replace
from difflib import SequenceMatcher

from contract_intel.domain.chunk import Chunk
from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_rules import normalize_whitespace
from contract_intel.domain.page import PageRange

MIN_LABEL_OVERLAP_CHARS = 60


def label_chunks(
    chunks: Sequence[Chunk], clauses: Sequence[Clause]
) -> tuple[Chunk, ...]:
    """Return ``chunks`` with ``clause_types`` set from the clauses they contain.

    A chunk gets a clause's type when their page ranges overlap and they share
    text: one contains the other, or they share at least
    ``MIN_LABEL_OVERLAP_CHARS`` consecutive characters.
    """
    return tuple(_label(chunk, clauses) for chunk in chunks)


def _label(chunk: Chunk, clauses: Sequence[Clause]) -> Chunk:
    types = frozenset(
        clause.clause_type
        for clause in clauses
        if clause.document_id == chunk.document_id
        and _pages_overlap(chunk.pages, clause.pages)
        and _texts_overlap(chunk.text, clause.text)
    )
    return replace(chunk, clause_types=types)


def _pages_overlap(first: PageRange, second: PageRange) -> bool:
    return first.first <= second.last and second.first <= first.last


def _texts_overlap(chunk_text: str, clause_text: str) -> bool:
    chunk, clause = normalize_whitespace(chunk_text), normalize_whitespace(clause_text)
    if chunk in clause or clause in chunk:
        return True
    match = SequenceMatcher(None, chunk, clause, autojunk=False).find_longest_match()
    return match.size >= MIN_LABEL_OVERLAP_CHARS
