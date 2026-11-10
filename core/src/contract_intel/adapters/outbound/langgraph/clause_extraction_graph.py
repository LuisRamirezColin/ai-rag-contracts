"""Map-reduce LangGraph for clause extraction.

``plan`` splits the pages into windows, one ``extract_window`` branch per window
runs in parallel (each a single model call), and ``consolidate`` applies the
domain rules: literal-text verification and merging of overlapping candidates.
"""

import operator
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from contract_intel.domain.clause_rules import ClauseCandidate, consolidate, is_literal
from contract_intel.domain.page import Page

EXTRACT_WINDOW = "extract_window"
CONSOLIDATE = "consolidate"


@dataclass(frozen=True, slots=True)
class WindowResult:
    """Candidates a model proposed for one window, and what the call consumed."""

    candidates: tuple[ClauseCandidate, ...]
    model: str
    input_tokens: int
    output_tokens: int


ExtractWindow = Callable[[Sequence[Page]], Awaitable[WindowResult]]


class ExtractionState(TypedDict, total=False):
    """Graph state; list and int fields are summed across parallel branches."""

    windows: list[list[Page]]
    pages: list[Page]
    candidates: Annotated[list[ClauseCandidate], operator.add]
    models: Annotated[list[str], operator.add]
    input_tokens: Annotated[int, operator.add]
    output_tokens: Annotated[int, operator.add]
    consolidated: list[ClauseCandidate]


class WindowState(TypedDict):
    """Payload sent to one ``extract_window`` branch."""

    window: list[Page]


def plan_windows(pages: Sequence[Page], window_chars: int) -> list[list[Page]]:
    """Group consecutive pages with text into windows of at most ``window_chars``.

    Pages are never split; a single page longer than the limit gets its own window.
    """
    windows: list[list[Page]] = []
    current: list[Page] = []
    size = 0
    for page in sorted(pages, key=lambda p: p.number):
        if not page.text.strip():
            continue
        if current and size + len(page.text) > window_chars:
            windows.append(current)
            current, size = [], 0
        current.append(page)
        size += len(page.text)
    if current:
        windows.append(current)
    return windows


def build_graph(extract_window: ExtractWindow) -> Any:  # noqa: ANN401 - compiled graph type is internal to LangGraph
    """Compile the extraction graph around ``extract_window``."""

    def fan_out(state: ExtractionState) -> list[Send]:
        return [Send(EXTRACT_WINDOW, {"window": w}) for w in state["windows"]]

    async def extract(state: WindowState) -> dict[str, object]:
        window = state["window"]
        result = await extract_window(window)
        literal = [c for c in result.candidates if is_literal(c, window)]
        return {
            "candidates": literal,
            "models": [result.model],
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        }

    def merge(state: ExtractionState) -> dict[str, object]:
        return {"consolidated": list(consolidate(state.get("candidates", [])))}

    graph = StateGraph(ExtractionState)
    graph.add_node(EXTRACT_WINDOW, extract)
    graph.add_node(CONSOLIDATE, merge)
    graph.add_conditional_edges(START, fan_out, [EXTRACT_WINDOW])
    graph.add_edge(EXTRACT_WINDOW, CONSOLIDATE)
    graph.add_edge(CONSOLIDATE, END)
    return graph.compile()
