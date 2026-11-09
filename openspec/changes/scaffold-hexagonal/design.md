# Design

## Context

El repositorio parte vacío salvo `openspec/`, `.claude/` y `legacy/` (git-ignorado, solo referencia). Motivación en `proposal.md` — Why; requisitos verificables en `specs/architecture-conformance/spec.md`.

Restricciones que moldean el diseño:
- Los paquetes del legacy se llaman `contract` y `contract_pipelines`; los nuevos módulos deben usar nombres distintos para que cualquier import accidental del legacy sea detectable y no ambiguo.
- Desarrollo en WSL (Ubuntu) con Docker; CI en GitHub Actions.
- Dos procesos desplegables independientes (Dagster escritor, API lectora) que comparten el mismo núcleo.

## Goals / Non-Goals

**Goals:**
- Que las reglas hexagonales fallen en CI, no en code review.
- Que cada cambio posterior solo tenga que "rellenar" un puerto con un use case o un adaptador, sin tocar la estructura.
- Entorno local reproducible con un comando (`docker compose up -d`).

**Non-Goals:**
- Implementar use cases, adaptadores reales (S3, OpenAI, LangGraph, pgvector) o tablas de negocio.
- Despliegue a la nube, Dockerfiles de producción, autenticación de la API.
- Elegir modelos LLM/embeddings (se decide en clause-extraction y vectorize-pgvector).

## Decisions

### D1 — Monorepo con workspace `uv` y tres paquetes
```
<repo>/
  pyproject.toml                # workspace root + tool config (ruff, mypy, pytest, importlinter)
  core/      -> package contract_intel           (domain, application, adapters, bootstrap)
  pipelines/ -> package contract_intel_pipelines (inbound: Dagster, writer)
  rag_api/   -> package contract_intel_api       (inbound: FastAPI, reader)
```
- `pipelines` y `rag_api` dependen de `core`; `core` no depende de ninguno.
- **Alternativas**: un único paquete (más simple, pero mezcla las dependencias de Dagster y FastAPI en ambos despliegues); Poetry multi-proyecto (usado en el legacy; sin workspaces nativos, lockfiles separados). `uv` da un lockfile único, workspaces nativos y CI rápido.
- **SOLID**: SRP a nivel de despliegue — cada paquete inbound tiene una sola razón para cambiar (su framework).

### D2 — Capas y dirección de dependencias
```
   contract_intel_pipelines      contract_intel_api        (inbound adapters)
              \                       /
               v                     v
            contract_intel.bootstrap  (composition root: único lugar que conoce adapters)
               |                \
               v                 v
   contract_intel.adapters --> contract_intel.application --> contract_intel.domain
        (outbound)                (use_cases, ports)            (stdlib only)
```
- Inbound adapters → `bootstrap` y `application.ports.inbound`; nunca `adapters`.
- `adapters` → `application.ports.outbound` + `domain` (implementan puertos).
- **SOLID**: DIP — application define las abstracciones (puertos) y los adaptadores dependen de ellas, no al revés.

### D3 — Reglas ejecutables con `import-linter`
Contratos en `pyproject.toml` (`[tool.importlinter]`, `include_external_packages = true`, root packages `contract_intel`, `contract_intel_pipelines`, `contract_intel_api`):
1. **layers**: `bootstrap` > `adapters` > `application` > `domain` dentro de `contract_intel`.
2. **forbidden (domain)**: `contract_intel.domain` ↛ `pydantic`, `sqlalchemy`, `asyncpg`, `pgvector`, `boto3`, `openai`, `langchain*`, `langgraph`, `dagster`, `fastapi`, `httpx`, `dependency_injector`.
3. **forbidden (application)**: misma lista sobre `contract_intel.application`.
4. **forbidden (inbound → outbound adapters)**: `contract_intel_pipelines`, `contract_intel_api` ↛ `contract_intel.adapters`.
5. **forbidden (API reader-only)**: `contract_intel_api` ↛ `contract_intel.application.ports.outbound.vector_index_writer`.
6. **forbidden (legacy)**: todos los root packages ↛ `contract`, `contract_pipelines`.

Un test de pytest (`core/tests/architecture/test_import_contracts.py`) ejecuta `lint-imports` para que la regla también corra localmente con `pytest`.
- **Alternativas**: `pytest-archon` o tests ad hoc con `ast` (más código propio que mantener); `import-linter` es declarativo y produce mensajes legibles.

### D4 — Dominio con `dataclasses(frozen=True, slots=True)` y `StrEnum`
- Entidades/value objects: `Contract`, `Document`, `Page`, `Clause`, `Chunk`, `Citation`, `Answer`; ids con `NewType`; `ClauseType(StrEnum)` con la taxonomía CUAD inicial (Governing Law, Termination for Convenience, Cap on Liability, Renewal Term, Exclusivity, Most Favored Nation, Non-Compete, IP Ownership Assignment, Price Restrictions, Volume Restriction) más `OTHER`.
- Invariantes mínimas en `__post_init__` (p.ej. `Page.number >= 1`, `Citation` referencia página válida) con excepciones de dominio propias (`domain/errors.py`).
- **Alternativa**: Pydantic en el dominio (cómodo, pero acopla el núcleo a una librería y viola la spec "solo stdlib"). Pydantic queda en bordes: settings (bootstrap) y esquemas HTTP (API).
- **SOLID**: SRP — el dominio solo modela conceptos e invariantes; validación de I/O vive en adaptadores.

### D5 — Puertos como `typing.Protocol` asíncronos, un puerto por módulo
| Puerto (application/ports) | Tipo | Adaptador previsto (cambio) |
|---|---|---|
| `IngestDocuments` | inbound | use case (document-ingestion) |
| `ExtractClauses` | inbound | use case (clause-extraction) |
| `VectorizeDocument` | inbound | use case (vectorize-pgvector) |
| `AnswerQuestion` | inbound | use case (rag-api) |
| `DocumentSource` | outbound | `CuadDocumentSource` (document-ingestion) |
| `DocumentStorage` | outbound | `S3DocumentStorage` (document-ingestion) |
| `TextExtractor` | outbound | `PypdfOcrTextExtractor` (document-ingestion) |
| `ClauseExtractor` | outbound | `LangGraphClauseExtractor` (clause-extraction) |
| `Embedder` | outbound | `OpenAIEmbedder` (vectorize-pgvector) |
| `VectorIndexWriter` | outbound | `PgVectorIndexWriter` (vectorize-pgvector) |
| `VectorSearch` | outbound | `PgVectorSearch` (rag-api) |
| `ContractRepository` | outbound | `SqlAlchemyContractRepository` (clause-extraction) |
| `AnswerGenerator` | outbound | `OpenAIAnswerGenerator` (rag-api) |
| `UsageTracker` | outbound | `SqlAlchemyUsageTracker` (clause-extraction) |

- Firmas mínimas tipadas con tipos de dominio; se refinan en el cambio que implementa cada puerto.
- **SOLID**: ISP — `VectorIndexWriter` y `VectorSearch` separados (la API nunca ve escritura); puertos pequeños en vez de un "VectorStore" o "Repository" gigante. OCP — nuevos proveedores = nuevos adaptadores sin tocar use cases.

### D6 — Composition root con `dependency-injector`, contenedores separados lector/escritor
- `bootstrap/settings.py`: `pydantic-settings` (`AppSettings` con secciones `database`, `storage`, `llm`), prefijo `CONTRACT_INTEL_`, `.env.example` versionado.
- `bootstrap/containers.py`: `CoreContainer` (settings + recursos compartidos), `WriterContainer` (lo que usa Dagster) y `ReaderContainer` (lo que usa la API; **no expone** `VectorIndexWriter`).
- Providers perezosos (`Singleton`/`Factory`): construir el contenedor no abre conexiones.
- En este cambio los providers de puertos outbound apuntan a los fakes in-memory, cableados vía `bootstrap/` con flag `CONTRACT_INTEL_USE_FAKES=true`; los cambios siguientes los reemplazan por adaptadores reales.
- **Alternativas**: factories manuales (el legacy; difícil sobrescribir en tests); FastAPI `Depends` (acopla el wiring al framework inbound). `dependency-injector` permite `container.override(...)` en tests y es agnóstico al framework.
- **SOLID**: DIP + SRP — solo el composition root conoce implementaciones concretas.

### D7 — Fakes in-memory y verificación de contrato
- `contract_intel/adapters/outbound/in_memory/` con una clase por puerto outbound (`InMemoryDocumentSource`, ...), deterministas y sin I/O. Viven en `adapters` (no en `tests/`) porque el composition root los cablea cuando `use_fakes=true` y `bootstrap` no debe importar código de tests.
- Conformidad estática: `core/tests/adapters/in_memory/test_conformance.py` asigna cada fake a una variable anotada con su `Protocol` → `mypy --strict` falla si no cumple. Conformidad en runtime: protocolos `@runtime_checkable` + `isinstance` en pytest.
- Los contract tests de comportamiento (mismos tests para fake y adaptador real) se agregan en cada cambio que trae un adaptador.
- **SOLID**: LSP — fake y adaptador real son sustituibles para cualquier consumidor.

### D8 — Persistencia local: Postgres 16 + pgvector, Alembic async en `adapters`
- Imagen `pgvector/pgvector:pg16`; `Base` declarativa en `contract_intel/adapters/outbound/persistence/base.py`; Alembic en `core/migrations/` (fuera del paquete de runtime) con `env.py` async y URL tomada de `AppSettings`, y `alembic.ini` en la raíz.
- **Por qué fuera del paquete** (ajuste durante la implementación): `env.py` necesita la metadata de `adapters` y los settings de `bootstrap`; dentro de `contract_intel.adapters` violaría el contrato de capas (adapters ↛ bootstrap). Las migraciones son tooling de despliegue, no código de runtime.
- Migración `0001_enable_pgvector`: `CREATE EXTENSION IF NOT EXISTS vector`. Sin tablas de negocio.
- Revisiones con prefijo secuencial (`0001_...`) para lectura clara en el portafolio.

### D9 — LocalStack solo con S3
- Servicio `localstack` con `SERVICES=s3` y script de init que crea el bucket `contracts`. Sin SQS/SNS/Redis (en el legacy estaban sin uso).

### D10 — Escaneo de identificadores prohibidos
- `scripts/check_forbidden_identifiers.py` recorre `git ls-files`.
- Patrones genéricos versionados en `scripts/forbidden_patterns.txt`: ids de cuenta cloud (12 dígitos en contextos ARN/URL), correos fuera de `example.com`, dominios `*.atlassian.net`, `ngrok`, rutas `/Users/<name>/`.
- Nombres sensibles: archivo local `.forbidden-names` (git-ignorado) o variable `FORBIDDEN_NAMES` desde un secreto de GitHub Actions; si falta, advertencia y solo patrones genéricos (ver spec).
- **Alternativa**: `gitleaks` (enfocado a secretos, no a nombres de clientes); puede añadirse después como complemento.

### D11 — Calidad y CI
- `ruff` (lint + format, line-length 88, reglas `E,F,I,B,UP,SIM,N,S,ANN,D` con convención Google en docstrings), `mypy --strict`, `pytest` + `pytest-asyncio`.
- `.pre-commit-config.yaml`: ruff, mypy, lint-imports, escaneo de identificadores.
- `.github/workflows/ci.yml`: `uv sync --frozen` → ruff → mypy → lint-imports → escaneo → pytest; cache de `uv`.

### D12 — ADRs
Se crean en `docs/architecture/adr/` (inglés, formato MADR corto):
- `0001-hexagonal-architecture-and-rewrite.md` — hexagonal + reescritura vs refactor del legacy.
- `0002-uv-workspace-monorepo.md` — D1.
- `0003-composition-root-reader-writer-containers.md` — D6 y separación lector/escritor del RAG.
- `0004-executable-architecture-rules.md` — D3 + D10.

## Risks / Trade-offs

- [Dagster es una dependencia pesada para CI] → cache de `uv`; el paquete `pipelines` instala Dagster solo en su grupo; jobs de CI pueden separarse por paquete más adelante.
- [`dependency-injector` y `mypy --strict`] → tipar providers explícitamente; si aparecen falsos positivos, `ignore` acotado al módulo `bootstrap` documentado en el ADR 0003.
- [`import-linter` necesita los paquetes externos instalados para resolver `include_external_packages`] → se ejecuta tras `uv sync` con todos los grupos.
- [Puertos definidos antes de sus use cases pueden quedar mal dimensionados] → firmas mínimas; cada cambio posterior puede refinarlas (son internas, no rompen specs).
- [Rutas UNC de Windows sobre WSL lentas/ambiguas para herramientas] → todos los comandos se ejecutan dentro de WSL.
- [Falsos positivos del escaneo (p.ej. números de 12 dígitos en datos CUAD)] → patrones con contexto (ARN/URL) y allowlist explícita por archivo.

## Migration Plan

No hay sistema en producción. Pasos: crear estructura y tooling → verificar localmente (`uv run pytest`, `uv run lint-imports`, `docker compose up -d` + `alembic upgrade head`) → primer commit (sin `legacy/`) → CI verde. Rollback: eliminar los directorios nuevos; `legacy/` permanece intacto.
