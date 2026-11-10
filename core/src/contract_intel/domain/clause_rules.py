"""Rules that turn model-proposed clause candidates into trustworthy clauses.

A candidate is kept only if its text appears literally (up to whitespace) in the
pages it claims; candidates of the same type whose texts overlap are merged.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.ids import ClauseId, DocumentId
from contract_intel.domain.page import Page, PageRange
from contract_intel.domain.text import ensure_not_blank

MIN_SHARED_CHARS = 80
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ClauseCandidate:
    """A clause proposed by a model, not yet verified against the document."""

    clause_type: ClauseType
    text: str
    pages: PageRange

    def __post_init__(self) -> None:
        ensure_not_blank(self.text, "text")


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace into single spaces and trim."""
    return _WHITESPACE.sub(" ", text).strip()


def is_literal(candidate: ClauseCandidate, pages: Sequence[Page]) -> bool:
    """Tell whether the candidate's text appears in the pages it claims."""
    claimed = [
        page
        for page in pages
        if candidate.pages.first <= page.number <= candidate.pages.last
    ]
    covered = {page.number for page in claimed}
    expected = set(range(candidate.pages.first, candidate.pages.last + 1))
    if covered != expected:
        return False
    haystack = normalize_whitespace(" ".join(page.text for page in claimed))
    return normalize_whitespace(candidate.text) in haystack


def consolidate(candidates: Iterable[ClauseCandidate]) -> tuple[ClauseCandidate, ...]:
    """Merge same-type candidates whose texts overlap, keeping the longest text."""
    merged: list[ClauseCandidate] = []
    for candidate in candidates:
        merged = _absorb(merged, candidate)
    return tuple(sorted(merged, key=_order))


def to_clauses(
    document_id: DocumentId, candidates: Iterable[ClauseCandidate]
) -> tuple[Clause, ...]:
    """Assign deterministic ids (per type, in page order) and build clauses."""
    ordinals: dict[ClauseType, int] = {}
    clauses: list[Clause] = []
    for candidate in sorted(candidates, key=_order):
        ordinal = ordinals.get(candidate.clause_type, 0)
        ordinals[candidate.clause_type] = ordinal + 1
        clauses.append(
            Clause(
                id=ClauseId(f"{document_id}:{candidate.clause_type}:{ordinal:03d}"),
                document_id=document_id,
                clause_type=candidate.clause_type,
                text=normalize_whitespace(candidate.text),
                pages=candidate.pages,
            )
        )
    return tuple(clauses)


def _absorb(
    merged: list[ClauseCandidate], candidate: ClauseCandidate
) -> list[ClauseCandidate]:
    for index, existing in enumerate(merged):
        if existing.clause_type == candidate.clause_type and _overlap(
            existing.text, candidate.text
        ):
            remaining = merged[:index] + merged[index + 1 :]
            return _absorb(remaining, _merge(existing, candidate))
    return [*merged, candidate]


def _overlap(first: str, second: str) -> bool:
    a, b = normalize_whitespace(first), normalize_whitespace(second)
    if a in b or b in a:
        return True
    match = SequenceMatcher(None, a, b, autojunk=False).find_longest_match()
    return match.size >= MIN_SHARED_CHARS


def _merge(first: ClauseCandidate, second: ClauseCandidate) -> ClauseCandidate:
    longest = max(first, second, key=lambda c: len(normalize_whitespace(c.text)))
    pages = PageRange(
        first=min(first.pages.first, second.pages.first),
        last=max(first.pages.last, second.pages.last),
    )
    return ClauseCandidate(longest.clause_type, longest.text, pages)


def _order(candidate: ClauseCandidate) -> tuple[int, str, str]:
    return (candidate.pages.first, candidate.clause_type.value, candidate.text)
