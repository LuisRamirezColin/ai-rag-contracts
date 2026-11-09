# Hexagonal architecture

This system follows **ports and adapters**. Business rules live in the centre and know
nothing about LLM SDKs, databases, Dagster or FastAPI; those are plugged in at the
edges. The rules below are enforced by the build (see
[ADR 0004](adr/0004-executable-architecture-rules.md)).

## Layers and dependency direction

```mermaid
flowchart TB
  subgraph inbound["Inbound adapters"]
    P["pipelines<br/>(Dagster, writer)"]
    A["rag_api<br/>(FastAPI, reader)"]
  end
  B["bootstrap<br/>composition root"]
  subgraph core["contract_intel"]
    AD["adapters<br/>(outbound)"]
    AP["application<br/>use cases + ports"]
    D["domain<br/>stdlib only"]
  end
  P --> B
  A --> B
  P --> AP
  A --> AP
  B --> AD
  B --> AP
  AD --> AP
  AD --> D
  AP --> D
```

Arrows point from the dependent module to its dependency. Every dependency points
inward:

- `domain` depends on nothing but the standard library;
- `application` depends only on `domain`;
- `adapters` implement `application` ports;
- `bootstrap` is the only place that creates adapters;
- inbound adapters obtain use cases from `bootstrap` and never touch outbound adapters.

## Repository layout

```
core/src/contract_intel/
  domain/                 Contract, Document, Page, PageRange, Clause, ClauseType,
                          Chunk, Embedding, ScoredChunk, Citation, Answer, UsageRecord,
                          IngestionStatus, IngestionRecord, EmbeddingBatch,
                          TokenPricing; chunking (page-aware chunk_pages)
  application/
    ports/inbound/        what the system offers (one Protocol per module)
    ports/outbound/       what the system needs (one Protocol per module)
    use_cases/            implementations of inbound ports
  adapters/outbound/
    in_memory/            deterministic adapters for tests and offline runs
    cuad/                 CUAD dataset source (local directory)
    s3/                   S3 document storage (boto3)
    voyage/               Voyage AI embeddings
    pdf/                  pypdf text extractor
    persistence/          SQLAlchemy base, models and repositories
  bootstrap/              settings; core.py (shared), writer.py (pipelines), reader.py (API)
core/migrations/          Alembic (deployment tooling, outside the runtime package)
pipelines/src/contract_intel_pipelines/   Dagster definitions
rag_api/src/contract_intel_api/           FastAPI application
```

## Ports

| Port | Direction | Purpose | In-memory adapter | Production adapter (✓ = implemented) |
|---|---|---|---|---|
| `DiscoverDocuments` | inbound | Source documents not ingested yet | — | `DiscoverDocumentsUseCase` ✓ |
| `IngestDocument` | inbound | Store, extract and record one document | — | `IngestDocumentUseCase` ✓ |
| `ExtractClauses` | inbound | Extract and persist typed clauses | — | use case |
| `VectorizeDocument` | inbound | Chunk, embed and index a document | — | `VectorizeDocumentUseCase` ✓ |
| `AnswerQuestion` | inbound | Answer a question with citations | — | use case |
| `DocumentSource` | outbound | Where documents come from | `InMemoryDocumentSource` | `CuadDocumentSource` ✓ |
| `DocumentStorage` | outbound | Durable raw files | `InMemoryDocumentStorage` | `S3DocumentStorage` ✓ |
| `TextExtractor` | outbound | Per-page text (no OCR) | `InMemoryTextExtractor` | `PypdfTextExtractor` ✓ |
| `DocumentRepository` | outbound | Ingestion state and page text | `InMemoryDocumentRepository` | `SqlAlchemyDocumentRepository` ✓ |
| `ClauseExtractor` | outbound | Typed clauses from pages | `InMemoryClauseExtractor` | LangGraph map-reduce |
| `Embedder` | outbound | Document and query vectors | `InMemoryEmbedder` | `VoyageEmbedder` (`voyage-law-2`) ✓ |
| `VectorIndexWriter` | outbound | Write side of the index (pipelines only) | `InMemoryVectorIndexWriter` | `PgVectorIndexWriter` ✓ |
| `VectorSearch` | outbound | Read side of the index (API only) | `InMemoryVectorSearch` | pgvector |
| `ContractRepository` | outbound | Contract aggregates | `InMemoryContractRepository` | Postgres |
| `AnswerGenerator` | outbound | Grounded answer from context | `InMemoryAnswerGenerator` | Claude (Anthropic SDK) |
| `UsageTracker` | outbound | Token and cost accounting | `InMemoryUsageTracker` | `SqlAlchemyUsageTracker` ✓ |

## Document ingestion flow

```mermaid
sequenceDiagram
  participant Sensor as Dagster sensor
  participant Asset as ingested_document (partition = document id)
  participant Ingest as IngestDocument
  participant Source as DocumentSource
  participant Storage as DocumentStorage
  participant Extractor as TextExtractor
  participant Repo as DocumentRepository
  Sensor->>Sensor: DiscoverDocuments → new partition keys
  Sensor->>Asset: RunRequest per new key
  Asset->>Ingest: execute(document_id)
  Ingest->>Source: fetch_content
  Ingest->>Storage: save original
  Ingest->>Extractor: extract_pages
  alt pages have text
    Ingest->>Repo: save_ingested(document, pages)
  else no text or unreadable
    Ingest->>Repo: save_failed(document, reason)
  end
  Ingest-->>Asset: IngestionRecord (Failure if failed)
```

See [ADR 0005](adr/0005-per-document-ingestion-with-dynamic-partitions.md).

## Vectorization flow

The same Dagster run continues with the `indexed_document` asset once ingestion
succeeds (it is skipped when ingestion fails):

```mermaid
flowchart LR
  R[DocumentRepository.get_pages] --> C["chunk_pages (domain)"]
  C --> E[Embedder.embed_documents]
  E --> W[VectorIndexWriter.replace_document]
  E --> U[UsageTracker.record]
```

Embeddings are computed before the index is touched, and the writer replaces a
document's chunks in one transaction. See
[ADR 0007](adr/0007-embeddings-with-voyage-and-pgvector.md).

## SOLID map

| Principle | Where it shows |
|---|---|
| **S**ingle responsibility | One use case per inbound port; adapters translate and hold no business rules; each deployable owns one framework. |
| **O**pen/closed | New providers are new adapters registered in `bootstrap`; use cases do not change. |
| **L**iskov substitution | In-memory and production adapters satisfy the same `Protocol` and are swapped without touching consumers (conformance test). |
| **I**nterface segregation | Small ports; the index is split into `VectorIndexWriter` and `VectorSearch`, so the API cannot write. |
| **D**ependency inversion | `application` declares the abstractions; adapters depend on them; only `bootstrap` knows concretions. |

## How to add a port and an adapter

1. Declare the port in `application/ports/outbound/<name>.py` as a
   `@runtime_checkable` `Protocol` using domain types only.
2. Add an in-memory adapter in `adapters/outbound/in_memory/<name>.py` and register
   it in `core/tests/adapters/in_memory/test_conformance.py`.
3. Write the use case against the port and test it with the in-memory adapter.
4. Implement the production adapter in `adapters/outbound/<technology>/` and run the
   same behaviour tests against it (contract tests).
5. Wire it in `bootstrap/core.py`, `writer.py` or `reader.py` as the `real` branch of the port's `Selector`
   (writer, reader or shared core); see
   [ADR 0006](adr/0006-lazy-per-port-adapter-selection.md).
6. If the adapter brings a new SDK, add it to the framework-free lists in
   `[tool.importlinter]`.

## Related decisions

- [ADR 0001 — Hexagonal architecture and a clean rewrite](adr/0001-hexagonal-architecture-and-rewrite.md)
- [ADR 0002 — `uv` workspace monorepo](adr/0002-uv-workspace-monorepo.md)
- [ADR 0003 — Composition root with reader and writer containers](adr/0003-composition-root-reader-writer-containers.md)
- [ADR 0004 — Executable architecture rules](adr/0004-executable-architecture-rules.md)
- [ADR 0005 — Per-document ingestion with dynamic partitions](adr/0005-per-document-ingestion-with-dynamic-partitions.md)
- [ADR 0006 — Lazy, per-port adapter selection](adr/0006-lazy-per-port-adapter-selection.md)
- [ADR 0007 — Embeddings with Voyage AI, index in pgvector](adr/0007-embeddings-with-voyage-and-pgvector.md)
