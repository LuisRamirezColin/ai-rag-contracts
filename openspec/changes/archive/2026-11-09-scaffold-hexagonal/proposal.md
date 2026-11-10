# Proposal

## Why

El proyecto se reescribe desde cero como pieza de portafolio de AI Engineer: el código anterior (`legacy/`, git-ignorado) no tiene capa RAG ni API, mezcla dominio e infraestructura y contiene datos no publicables. Antes de construir ingesta, extracción, vectorización y la API, necesitamos un esqueleto hexagonal cuyas reglas de dependencia se **verifiquen automáticamente**, para que cada cambio posterior nazca dentro de la arquitectura en vez de depender de disciplina manual.

## What Changes

- Nuevo monorepo Python 3.12 con tres paquetes:
  - `core/` (`contract_intel`): `domain/`, `application/ports/{inbound,outbound}/`, `application/use_cases/`, `adapters/outbound/`, `bootstrap/` (composition root + settings).
  - `pipelines/`: adaptador inbound Dagster (escritor del índice), solo con `Definitions` vacías que cargan el composition root.
  - `rag_api/`: adaptador inbound FastAPI (lector), solo con `/health`.
- Modelo de dominio inicial como value objects/entidades inmutables y sin dependencias: `Contract`, `Document`, `Page`, `Clause`, `ClauseType`, `Chunk`, `Citation`, `Answer`.
- Definición de puertos como `typing.Protocol` (sin implementaciones reales): inbound `IngestDocuments`, `ExtractClauses`, `VectorizeDocument`, `AnswerQuestion`; outbound `DocumentSource`, `DocumentStorage`, `TextExtractor`, `ClauseExtractor`, `Embedder`, `VectorIndexWriter`, `VectorSearch`, `ContractRepository`, `AnswerGenerator`, `UsageTracker`.
- Fakes in-memory de los puertos outbound en `core/tests/fakes/` como base para tests de use cases y contract tests.
- Reglas de arquitectura ejecutables con `import-linter` + tests de arquitectura en pytest.
- Tooling: workspace `uv`, `ruff`, `mypy --strict`, `pytest`, `pre-commit`, CI en GitHub Actions (lint, types, import contracts, tests, escaneo de identificadores prohibidos).
- Entorno local: `docker-compose.yml` con Postgres + pgvector y LocalStack (S3); Alembic configurado en `core` con una migración inicial que habilita la extensión `vector`.
- `.env.example` y settings tipados; ninguna credencial en el repo.
- Sin lógica de negocio: los use cases llegarán en cambios posteriores (document-ingestion, clause-extraction, vectorize-pgvector, rag-api).

**Capas hexagonales afectadas**: domain (modelo inicial), application (puertos), adapters (solo estructura y configuración de BD/Alembic), inbound adapters (`pipelines/` y `rag_api/` mínimos), bootstrap (composition root).

## Capabilities

### New Capabilities
- `architecture-conformance`: reglas verificables de la arquitectura hexagonal — dirección de dependencias entre capas, aislamiento del dominio respecto de frameworks, ensamblado exclusivo en el composition root, separación lector/escritor del índice vectorial, intercambiabilidad de adaptadores vía fakes, y ausencia de identificadores no publicables en el repositorio.

### Modified Capabilities
<!-- Ninguna: no existen specs previas. -->

## Impact

- **Código**: nuevos directorios `core/`, `pipelines/`, `rag_api/`, `.github/workflows/`, `docker-compose.yml`, `pyproject.toml` raíz (workspace), `.env.example`, `.pre-commit-config.yaml`, `.importlinter`.
- **Dependencias**: runtime mínimo (`pydantic`, `pydantic-settings`, `dependency-injector`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pgvector`, `dagster`, `fastapi`, `uvicorn`); dev (`ruff`, `mypy`, `pytest`, `pytest-asyncio`, `import-linter`, `pre-commit`). LangChain/LangGraph, OpenAI y boto3 se agregan en los cambios que los usan.
- **Sistemas**: Docker para el entorno local; GitHub Actions.
- **legacy/**: no se toca ni se importa; queda como referencia.
