"""Every in-memory adapter satisfies its outbound port (LSP).

Static check: the annotated assignments below fail ``mypy --strict`` if a fake
drifts from its Protocol. Runtime check: ``isinstance`` against the
``runtime_checkable`` Protocols.
"""

import pytest

from contract_intel.adapters.outbound.in_memory.answer_generator import (
    InMemoryAnswerGenerator,
)
from contract_intel.adapters.outbound.in_memory.clause_extractor import (
    InMemoryClauseExtractor,
)
from contract_intel.adapters.outbound.in_memory.contract_repository import (
    InMemoryContractRepository,
)
from contract_intel.adapters.outbound.in_memory.document_repository import (
    InMemoryDocumentRepository,
)
from contract_intel.adapters.outbound.in_memory.document_source import (
    InMemoryDocumentSource,
)
from contract_intel.adapters.outbound.in_memory.document_storage import (
    InMemoryDocumentStorage,
)
from contract_intel.adapters.outbound.in_memory.embedder import InMemoryEmbedder
from contract_intel.adapters.outbound.in_memory.text_extractor import (
    InMemoryTextExtractor,
)
from contract_intel.adapters.outbound.in_memory.usage_tracker import (
    InMemoryUsageTracker,
)
from contract_intel.adapters.outbound.in_memory.vector_index import (
    InMemoryVectorIndexWriter,
    InMemoryVectorSearch,
    InMemoryVectorStore,
)
from contract_intel.application.ports.outbound.answer_generator import AnswerGenerator
from contract_intel.application.ports.outbound.clause_extractor import ClauseExtractor
from contract_intel.application.ports.outbound.contract_repository import (
    ContractRepository,
)
from contract_intel.application.ports.outbound.document_repository import (
    DocumentRepository,
)
from contract_intel.application.ports.outbound.document_source import DocumentSource
from contract_intel.application.ports.outbound.document_storage import DocumentStorage
from contract_intel.application.ports.outbound.embedder import Embedder
from contract_intel.application.ports.outbound.text_extractor import TextExtractor
from contract_intel.application.ports.outbound.usage_tracker import UsageTracker
from contract_intel.application.ports.outbound.vector_index_writer import (
    VectorIndexWriter,
)
from contract_intel.application.ports.outbound.vector_search import VectorSearch

_store = InMemoryVectorStore()

document_source: DocumentSource = InMemoryDocumentSource()
document_storage: DocumentStorage = InMemoryDocumentStorage()
document_repository: DocumentRepository = InMemoryDocumentRepository()
text_extractor: TextExtractor = InMemoryTextExtractor()
clause_extractor: ClauseExtractor = InMemoryClauseExtractor()
embedder: Embedder = InMemoryEmbedder()
vector_index_writer: VectorIndexWriter = InMemoryVectorIndexWriter(_store)
vector_search: VectorSearch = InMemoryVectorSearch(_store)
contract_repository: ContractRepository = InMemoryContractRepository()
answer_generator: AnswerGenerator = InMemoryAnswerGenerator()
usage_tracker: UsageTracker = InMemoryUsageTracker()


@pytest.mark.parametrize(
    ("adapter", "port"),
    [
        (document_source, DocumentSource),
        (document_storage, DocumentStorage),
        (document_repository, DocumentRepository),
        (text_extractor, TextExtractor),
        (clause_extractor, ClauseExtractor),
        (embedder, Embedder),
        (vector_index_writer, VectorIndexWriter),
        (vector_search, VectorSearch),
        (contract_repository, ContractRepository),
        (answer_generator, AnswerGenerator),
        (usage_tracker, UsageTracker),
    ],
    ids=lambda value: getattr(value, "__name__", type(value).__name__),
)
def test_in_memory_adapter_satisfies_port(adapter, port):
    assert isinstance(adapter, port)


def test_every_outbound_port_has_an_in_memory_adapter():
    from pathlib import Path

    import contract_intel.application.ports.outbound as outbound

    port_modules = {
        p.stem for p in Path(outbound.__path__[0]).glob("*.py") if p.stem != "__init__"
    }
    covered = {
        "document_source",
        "document_storage",
        "document_repository",
        "text_extractor",
        "clause_extractor",
        "embedder",
        "vector_index_writer",
        "vector_search",
        "contract_repository",
        "answer_generator",
        "usage_tracker",
    }
    assert port_modules == covered
