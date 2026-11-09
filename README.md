# Contract Intelligence

Typed clause extraction and a hybrid RAG over commercial contracts, built as a
production-shaped system: hexagonal architecture with executable rules, an
orchestrated writer pipeline and a read-only question-answering API.

Reviewing contracts means finding the same things over and over: governing law,
termination rights, liability caps, exclusivity, renewal terms. This project turns a
contract corpus into **structured clause data** you can filter, and lets you **ask
questions** whose answers cite the exact document and page they come from.

- **Writer side (Dagster):** ingests contracts, embeds page-aware chunks with Voyage
  AI and continuously feeds a pgvector index; typed clause extraction with Claude
  comes next.
- **Reader side (FastAPI):** answers questions with Claude from the chunks retrieved
  by vector similarity (plus clause-type filters), citing document and page.
- **Data:** the public [CUAD](https://www.atticusprojectai.org/cuad) dataset (510
  commercial contracts), which also provides lawyer-labelled ground truth for
  evaluation.

## Status

| Stage | State |
|---|---|
| Hexagonal skeleton, executable architecture rules, CI | Done |
| Document ingestion: CUAD → S3 + per-page text in Postgres, Dagster sensor | Done |
| Vectorization: page-aware chunks, Voyage `voyage-law-2` embeddings, pgvector index | Done |
| RAG API: `POST /ask`, retrieval in pgvector, grounded answers with Claude citing document and pages | Done |
| Clause extraction: LangGraph over pages with Claude, typed CUAD clauses | Next |
| Evaluation against CUAD labels (precision/recall per clause type) | Planned |

Each stage is an [OpenSpec](openspec/) change with its proposal, design, spec and
task list; finished ones are archived in `openspec/changes/archive/`.

## Architecture

```mermaid
flowchart LR
  S[(CUAD PDFs)] -->|sensor| I
  subgraph W["Dagster: writer"]
    I[ingest] --> X[extract clauses]
    I --> E[chunk + embed]
  end
  I --> S3[(S3: originals)]
  I --> PG[(Postgres: pages, clauses)]
  X --> PG
  E --> V[(pgvector)]
  subgraph R["FastAPI: reader"]
    Q["/ask"] --> H[hybrid retrieval] --> G[grounded answer + citations]
  end
  PG --> H
  V --> H
```

The two RAG layers are decoupled: Dagster is the **only writer** of the index and
feeds it continuously; the API can only read it, a rule enforced by import contracts
and by the composition root (the reader container has no index writer).

Inside, the code follows **ports and adapters**. Business rules live in a
framework-free core; LLM SDKs, databases, S3, Dagster and FastAPI are adapters at the
edges, wired in a single composition root.

- [Hexagonal architecture: layers, ports, ingestion flow, SOLID map](docs/architecture/hexagonal.md)
- [Architecture decision records](docs/architecture/adr/)

## How it works

### Document ingestion (implemented)

1. `scripts/download_cuad.py` fetches CUAD v1 from its public Zenodo record and
   verifies a pinned SHA-256 before extracting anything.
2. A Dagster sensor runs `DiscoverDocuments`: source documents not ingested yet, in a
   stable order, capped by `CONTRACT_INTEL_INGESTION__MAX_DOCUMENTS` (default 5).
3. Each new document becomes a **dynamic partition** and gets its own run of the
   `ingested_document` asset, which calls `IngestDocument`:
   - stores the original PDF in S3;
   - extracts text page by page (pypdf, no OCR);
   - records the document as `ingested` with its pages, or `failed` with a reason
     (no text layer, unreadable file). Failures stay visible in Dagster and never
     stop other documents.
4. Re-ingesting is idempotent: state and pages are replaced, never duplicated.

### Vectorization (implemented)

In the same Dagster run, once ingestion succeeds, the `indexed_document` asset calls
`VectorizeDocument`:

1. splits the page text into windows of at most 2,000 characters with 200 of
   overlap, cut at paragraph, line or word boundaries; each chunk keeps the page
   range it covers, so answers can cite pages;
2. embeds the chunks with Voyage AI `voyage-law-2`, a retrieval model trained on
   legal text (Anthropic offers no embeddings model; queries use the same model with
   the query input type);
3. replaces the document's chunks in pgvector in one transaction (HNSW cosine
   index), so a reader never sees a half-indexed document;
4. records tokens and estimated cost per document in `usage_records`.

### Clause extraction (planned)

A LangGraph workflow reads the stored pages and returns clauses typed with the CUAD
taxonomy (governing law, termination for convenience, cap on liability, renewal
term, exclusivity, most favored nation, non-compete, IP assignment, price and volume
restrictions). Outputs are schema-validated, each clause keeps its page range, and
token usage and cost are recorded per document.

### Questions and answers (implemented)

`POST /ask` runs `AnswerQuestion`:

1. embeds the question with Voyage (query input type);
2. retrieves the 8 most similar chunks from pgvector (optionally filtered by clause
   type, useful once clause extraction labels chunks);
3. sends each chunk to Claude as a document with **citations** enabled and a prompt
   that allows only those documents; Claude's citations point to document blocks,
   which map back to chunks, so every citation carries document and page range;
4. records tokens and cost in `usage_records`.

If retrieval finds nothing, the API answers "no information" without calling Claude.
Provider rate limits and outages return `503` (with `Retry-After` for limits), and a
refused answer returns `422`.

## Engineering highlights

- **Architecture as tests.** `import-linter` contracts fail the build if the domain
  imports a framework, an inbound adapter touches an outbound adapter, or the API
  imports the index writer.
- **Swappable adapters, verified.** Every outbound port has an in-memory fake; one
  contract suite runs against both the fake and the real adapter (S3, Postgres,
  pypdf, CUAD), so they are interchangeable by construction.
- **Lazy, per-port wiring.** `CONTRACT_INTEL_USE_FAKES` picks fake or real adapters
  port by port; ports without a real adapter yet fail only when resolved.
- **Per-document orchestration.** Dynamic partitions give one run, one retry and one
  lineage entry per contract, ready for downstream assets to chain on.
- **Reproducible data.** Checksum-verified download, atomic extraction, nothing from
  the dataset in git.
- **Publishable by design.** A scanner blocks cloud account ids, internal domains,
  personal emails and a private list of sensitive names in every tracked file.
- **Spec-driven.** Changes go through OpenSpec: behaviour specs first, then design,
  tasks and verification.

## Design decisions

**Why hexagonal architecture?** The LLM stack changes faster than the business rules.
Keeping prompts, SDKs and storage behind ports lets providers change without touching
use cases, and lets every use case be tested with fakes in milliseconds.
See [ADR 0001](docs/architecture/adr/0001-hexagonal-architecture-and-rewrite.md).

**Why separate writer and reader containers?** The index has exactly one writer, so
the API cannot corrupt it and both sides scale and deploy independently.
See [ADR 0003](docs/architecture/adr/0003-composition-root-reader-writer-containers.md).

**Why one Dagster partition per document?** A bad PDF fails its own run, not the
batch; retries are per document; clause extraction and embedding can depend on
ingestion partition by partition.
See [ADR 0005](docs/architecture/adr/0005-per-document-ingestion-with-dynamic-partitions.md).

**Why pgvector instead of a dedicated vector database?** Clauses, pages and vectors
live in one Postgres, so hybrid retrieval is one SQL query with real filters and
joins, and there is a single system to operate.

**Why CUAD?** It is public, realistic (SEC-filed agreements) and annotated by lawyers
for 41 clause categories, which makes extraction measurable instead of anecdotal.

**Why a `uv` workspace?** One lockfile for three packages, so the API never installs
Dagster and the pipelines never install FastAPI.
See [ADR 0002](docs/architecture/adr/0002-uv-workspace-monorepo.md).

## Tech stack

| Concern | Choice |
|---|---|
| Language and tooling | Python 3.12, `uv` workspace, ruff, mypy `--strict`, pytest |
| Orchestration (writer) | Dagster: dynamic partitions, sensors |
| API (reader) | FastAPI |
| Storage | Postgres 16 + pgvector, S3 (LocalStack locally) |
| Persistence | SQLAlchemy 2 async, Alembic |
| Documents | pypdf |
| Wiring | dependency-injector, pydantic-settings |
| Embeddings | Voyage AI `voyage-law-2` (1024 dimensions) |
| Answers | Claude (Sonnet 5.5 by default) via the Anthropic SDK, with citations |
| Clause extraction | LangGraph with Claude (next) |
| Architecture rules | import-linter |
| Planning | OpenSpec |

## Quickstart

Requirements: [uv](https://docs.astral.sh/uv/), Docker with Compose.

```bash
uv sync --all-packages                   # Python 3.12 + all workspace packages
cp .env.example .env                     # then set the Voyage and Anthropic keys
uv run python scripts/download_cuad.py   # CUAD v1 (~100 MB, SHA-256 verified) into data/cuad/
docker compose up -d --wait              # Postgres + pgvector, LocalStack S3
uv run alembic upgrade head              # vector extension; documents, pages, chunks, usage_records
uv run pytest                            # unit, contract (fakes) and architecture tests
uv run pytest -m integration             # contract tests against Postgres and LocalStack
uv run pytest -m voyage                  # one real call to Voyage AI (skipped without a key)
uv run pytest -m anthropic               # one real call to Claude (skipped without credentials)
```

> Integration tests truncate the tables they use. Point them at a separate database to
> keep your indexed contracts:
>
> ```bash
> docker compose exec postgres psql -U contract_intel -c "CREATE DATABASE contract_intel_test"
> export TEST_DB=postgresql+asyncpg://contract_intel:contract_intel@localhost:5432/contract_intel_test
> CONTRACT_INTEL_DATABASE__URL=$TEST_DB uv run alembic upgrade head
> CONTRACT_INTEL_DATABASE__URL=$TEST_DB uv run pytest -m integration
> ```

Run the inbound adapters:

```bash
# Real ingestion: set CONTRACT_INTEL_USE_FAKES=false in .env first (dagster dev loads .env,
# which overrides shell variables); the sensor then schedules the first
# CONTRACT_INTEL_INGESTION__MAX_DOCUMENTS (5) documents.
uv run dagster dev -m contract_intel_pipelines.definitions    # http://localhost:3000
uv run uvicorn contract_intel_api.main:app --reload           # http://localhost:8000/docs
```

Ask a question (real mode, after indexing):

```bash
curl -s -X POST localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question": "Which law governs the services agreement?"}'
```

```json
{
  "answer": "The Services Agreement is governed by Israeli law. [...] the Parties submit disputes to the exclusive jurisdiction of the courts located in Tel-Aviv, Israel. [...]",
  "citations": [
    {
      "document_id": "abilityinc-06-15-2020-ex-4-25-services-agreement-8098d6a0",
      "first_page": 7,
      "last_page": 8,
      "excerpt": "This Agreement and any claim, controversy or dispute arising out of or related to this Agreement [...] shall be governed by and construed in accordance with the domestic laws of the State of Israel [...]"
    }
  ]
}
```

A question the contracts do not cover gets an explicit "the retrieved contracts do
not contain this information" answer with no citations. Optional filter:
`"clause_types": ["governing_law"]`.

Inspect the result:

```bash
docker compose exec postgres psql -U contract_intel -c \
  "SELECT status, count(*), sum(page_count) FROM documents GROUP BY status"
docker compose exec localstack awslocal s3 ls s3://contracts/raw/
docker compose exec postgres psql -U contract_intel -c \
  "SELECT document_id, count(*) AS chunks, min(first_page), max(last_page) FROM chunks GROUP BY document_id"
docker compose exec postgres psql -U contract_intel -c \
  "SELECT operation, model, sum(input_tokens) AS input, sum(output_tokens) AS output, sum(cost_usd) AS usd FROM usage_records GROUP BY 1, 2"
```

A contract of about ten pages takes 6K–10K Voyage tokens; the 5 demo contracts about
60K and all of CUAD roughly 9M, within the 50M free tokens Voyage gives every account
for `voyage-law-2`. `usage_records` shows the estimate at list price ($0.12 per
million tokens).

## Running on free tiers

This demo runs entirely on free tiers, and that shapes what you see:

- **Voyage AI without a payment method** is limited to **3 requests and 10K tokens
  per minute**. Dagster launches one run per document in parallel, so most runs hit
  the limit, and a contract larger than ~10K tokens (about 12+ pages) cannot be
  embedded at all, because its chunks go in one request. In the reference run, 3 of
  the 5 demo contracts were indexed (43 chunks, 23K tokens, $0 billed); the other
  two failed with `RateLimitError`, stayed visible as failed runs in Dagster and left
  the index untouched, as designed.
- The **free token allowance** (50M tokens for `voyage-law-2`) still applies once a
  payment method is added, so the whole CUAD corpus costs nothing either way.
- **Questions:** each one uses a Voyage request to embed the question, so on the
  free tier the API answers at most 3 questions a minute and then returns `503` with
  `Retry-After`. Claude has no free tier: a question with 8 chunks costs about
  $0.017 with Sonnet 5.5 (measured: ~7.5K input and ~150-300 output tokens).

### How to lift the limits

| Improvement | Effort | Effect |
|---|---|---|
| Add a payment method in the [Voyage dashboard](https://dashboard.voyageai.com/) | none (config) | Standard rate limits within minutes; free tokens still apply. Re-materialize the failed `indexed_document` partitions in Dagster. |
| Cap concurrent runs (Dagster `QueuedRunCoordinator` `max_concurrent_runs`, or a tag concurrency limit on `ingest_documents_job`) | small | Avoids request bursts when many documents arrive at once |
| Token-aware throttling in `VoyageEmbedder` (smaller batches plus a requests/tokens-per-minute limiter) | medium | Works within any rate limit, including the free one, at the cost of throughput; confined to the adapter |
| Retry policy with backoff on `indexed_document` for `RateLimitError` | small | Transient limit hits recover without manual re-runs |
| Voyage Batch API for bulk backfills | medium | 33% cheaper and asynchronous, suited to indexing all 510 contracts |
| Another provider or a local model behind the `Embedder` port | medium | No external limits; one adapter, settings and a new migration if the dimension changes ([ADR 0007](docs/architecture/adr/0007-embeddings-with-voyage-and-pgvector.md)) |

## Configuration

Settings are read from `CONTRACT_INTEL_*` variables or `.env` (see
[`.env.example`](.env.example)); nested sections use `__`.

| Variable | Default | Purpose |
|---|---|---|
| `CONTRACT_INTEL_USE_FAKES` | `true` | In-memory adapters (no infrastructure) or real ones |
| `CONTRACT_INTEL_INGESTION__MAX_DOCUMENTS` | `5` | How many CUAD contracts the demo ingests (up to 510) |
| `CONTRACT_INTEL_INGESTION__CUAD_DIR` | `data/cuad/CUAD_v1/full_contract_pdf` | Local CUAD PDFs |
| `CONTRACT_INTEL_DATABASE__URL` | local Postgres | Async SQLAlchemy URL |
| `CONTRACT_INTEL_STORAGE__BUCKET` / `__ENDPOINT_URL` | `contracts` / LocalStack | Where originals are stored |
| `CONTRACT_INTEL_EMBEDDINGS__API_KEY` | empty | Voyage AI key ([dashboard](https://dash.voyageai.com/)) |
| `CONTRACT_INTEL_EMBEDDINGS__MODEL` / `__DIMENSIONS` | `voyage-law-2` / `1024` | Embedding model; the dimension must match migration `0003` |
| `CONTRACT_INTEL_CHUNKING__MAX_CHARS` / `__OVERLAP_CHARS` | `2000` / `200` | Chunk size and overlap |
| `CONTRACT_INTEL_LLM__API_KEY` | empty | Anthropic key; empty uses the SDK's default credentials |
| `CONTRACT_INTEL_LLM__CHAT_MODEL` | `claude-sonnet-5-5` | Answer model (`claude-opus-5-5` for higher quality, $4 / $20 per million tokens) |
| `CONTRACT_INTEL_LLM__EFFORT` | `medium` | Claude effort (`low` … `max`) |
| `CONTRACT_INTEL_LLM__FALLBACKS` | `false` | Server-side fallback to another model when Claude declines |
| `CONTRACT_INTEL_RETRIEVAL__TOP_K` | `8` | Chunks used as context per question |

## Testing strategy

| Layer | What it proves | Needs |
|---|---|---|
| Domain | Invariants of entities and value objects | nothing |
| Use cases | Business behaviour, using in-memory fakes of every port | nothing |
| Contract | Fake and real adapter behave the same (LSP) | Docker for S3/Postgres cases (`-m integration`); real keys for `-m voyage` / `-m anthropic` |
| API | `/ask` status codes, payloads and error mapping with a fake container | nothing |
| Architecture | Import contracts hold; a forbidden import makes them fail | nothing |
| Pipelines | Sensor scheduling and asset outcomes with an ephemeral Dagster instance | nothing |

## Quality gates

| Check | Command |
|---|---|
| Format and lint | `uv run ruff format --check . && uv run ruff check .` |
| Types | `uv run mypy scripts core/src core/tests core/migrations pipelines/src pipelines/tests rag_api/src rag_api/tests` |
| Architecture | `uv run lint-imports` |
| Forbidden identifiers | `uv run python scripts/check_forbidden_identifiers.py` |
| Tests | `uv run pytest` and `uv run pytest -m integration` |

All of them run in pre-commit (`uv run pre-commit install`) and in CI, where a
separate job runs the integration tests against Postgres and LocalStack services.

## Repository layout

| Path | Contents |
|---|---|
| `core/` | `contract_intel`: domain, application (ports and use cases), adapters, composition root (`bootstrap/core.py`, `writer.py`, `reader.py`) |
| `pipelines/` | `contract_intel_pipelines`: Dagster inbound adapter (writer) |
| `rag_api/` | `contract_intel_api`: FastAPI inbound adapter (reader) |
| `core/migrations/` | Alembic migrations |
| `scripts/` | Dataset download and repository checks |
| `docs/architecture/` | Architecture docs and ADRs |
| `openspec/` | Spec-driven change history (proposals, designs, specs, tasks) |

## Data and attribution

Contracts come from the **Contract Understanding Atticus Dataset (CUAD) v1** by
[The Atticus Project](https://www.atticusprojectai.org/cuad), licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) and described in
Hendrycks et al., *CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review*
(NeurIPS 2021). The dataset is downloaded locally and never committed.

## Author

**Luis Ramirez**: AI engineering, architecture and implementation.
