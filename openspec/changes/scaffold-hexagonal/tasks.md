# Tasks

> Este cambio no trae use cases ni adaptadores reales: los tests de use cases con fakes y los contract tests de comportamiento fake/adaptador llegan en los cambios que los implementan. Aquí se crean los fakes y su verificación de conformidad (D7). Todos los comandos se ejecutan dentro de WSL.

## 1. Workspace y tooling

- [x] 1.1 Crear `pyproject.toml` raíz como workspace `uv` (Python 3.12) con miembros `core`, `pipelines`, `rag_api` y grupo dev (`ruff`, `mypy`, `pytest`, `pytest-asyncio`, `import-linter`, `pre-commit`); verificar que `uv sync --all-packages` termina sin errores y genera `uv.lock`
- [x] 1.2 Crear `core/pyproject.toml` (paquete `contract_intel`, layout `src/`) con deps `pydantic-settings`, `dependency-injector`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pgvector`; verificar `uv run python -c "import contract_intel"`
- [x] 1.3 Crear `pipelines/pyproject.toml` (paquete `contract_intel_pipelines`, deps `dagster`, `dagster-webserver`, `core`) y `rag_api/pyproject.toml` (paquete `contract_intel_api`, deps `fastapi`, `uvicorn`, `core`); verificar que ambos importan
- [x] 1.4 Configurar `ruff` (line-length 88, reglas `E,F,I,B,UP,SIM,N,S,ANN,D`, docstrings Google), `mypy --strict` y `pytest` (asyncio mode auto, testpaths por paquete) en el `pyproject.toml` raíz; verificar `uv run ruff check .` y `uv run mypy core pipelines rag_api` en verde sobre el esqueleto
- [x] 1.5 Añadir `.env.example` con todas las variables `CONTRACT_INTEL_*` (sin valores reales) y ampliar `.gitignore` con `.forbidden-names`; verificar que `git check-ignore legacy .forbidden-names .env` lista los tres

## 2. Dominio

- [x] 2.1 Crear `contract_intel/domain/` con `ids.py` (`NewType`), `clause_type.py` (`ClauseType` StrEnum: 10 categorías CUAD + `OTHER`), `errors.py` (excepciones de dominio) y entidades/value objects `Document`, `Page`, `Clause`, `Contract`, `Chunk`, `Citation`, `Answer` como dataclasses `frozen=True, slots=True`; verificar con `mypy --strict`
- [x] 2.2 Implementar invariantes mínimas en `__post_init__` (número de página >= 1, rangos de página válidos en `Citation`/`Chunk`, texto no vacío en `Clause`) y tests unitarios en `core/tests/domain/` que cubran caso válido e inválido por invariante; verificar `uv run pytest core/tests/domain`

## 3. Puertos de aplicación

- [x] 3.1 Crear `application/ports/inbound/` con un módulo por puerto (`ingest_documents.py`, `extract_clauses.py`, `vectorize_document.py`, `answer_question.py`) como `Protocol` `@runtime_checkable` con firmas async tipadas con tipos de dominio; verificar con `mypy --strict`
- [x] 3.2 Crear `application/ports/outbound/` con un módulo por puerto (`document_source.py`, `document_storage.py`, `text_extractor.py`, `clause_extractor.py`, `embedder.py`, `vector_index_writer.py`, `vector_search.py`, `contract_repository.py`, `answer_generator.py`, `usage_tracker.py`) y `application/use_cases/__init__.py` vacío; verificar con `mypy --strict`
- [x] 3.3 Crear fakes in-memory en `contract_intel/adapters/outbound/in_memory/` (uno por puerto outbound) y `core/tests/adapters/in_memory/test_conformance.py` con asignaciones anotadas al `Protocol` (chequeo estático) e `isinstance` (chequeo runtime); verificar `uv run mypy core` y `uv run pytest core/tests/adapters/in_memory`

## 4. Composition root

- [x] 4.1 Crear `bootstrap/settings.py` (`AppSettings` con secciones `database`, `storage`, `llm`, prefijo `CONTRACT_INTEL_`, flag `use_fakes`) y tests que carguen settings desde variables de entorno; verificar `uv run pytest core/tests/bootstrap/test_settings.py`
- [x] 4.2 Crear `bootstrap/containers.py` con `CoreContainer`, `WriterContainer` y `ReaderContainer` (este último sin `VectorIndexWriter`), providers perezosos cableados a los fakes de `adapters/outbound/in_memory/` cuando `use_fakes=true`; verificar con test que construye ambos contenedores sin red (socket bloqueado vía monkeypatch) y que `ReaderContainer` no expone writer
- [x] 4.3 Crear `contract_intel_pipelines/definitions.py` (`Definitions` vacías que construyen `WriterContainer`) y `contract_intel_api/main.py` (app FastAPI con `GET /health` que construye `ReaderContainer`); verificar `uv run dagster definitions validate -m contract_intel_pipelines.definitions` y test con `TestClient` que `/health` responde 200

## 5. Reglas de arquitectura ejecutables

- [x] 5.1 Declarar en `[tool.importlinter]` los 6 contratos de D3 (layers, forbidden domain, forbidden application, inbound↛adapters, API↛vector_index_writer, ↛legacy `contract`/`contract_pipelines`); verificar `uv run lint-imports` en verde
- [x] 5.2 Añadir `core/tests/architecture/test_import_contracts.py` que ejecuta `lint-imports`, más un test negativo que crea en `tmp_path` un paquete temporal con un import prohibido en dominio y comprueba que `lint-imports` falla; verificar `uv run pytest core/tests/architecture`
- [x] 5.3 Crear `scripts/check_forbidden_identifiers.py` + `scripts/forbidden_patterns.txt` (patrones genéricos D10) leyendo nombres sensibles de `.forbidden-names` o `FORBIDDEN_NAMES` con advertencia si faltan, y tests en `scripts/tests/` (detección con archivo/línea, repo limpio, fuente ausente → warning sin fallo); verificar `uv run pytest scripts/tests` y `uv run python scripts/check_forbidden_identifiers.py` sin coincidencias

## 6. Entorno local y migraciones

- [ ] 6.1 Crear `docker-compose.yml` con `postgres` (`pgvector/pgvector:pg16`, healthcheck) y `localstack` (`SERVICES=s3`, script `ops/localstack/init-s3.sh` que crea el bucket `contracts`); verificar `docker compose up -d` con ambos servicios `healthy` y `awslocal s3 ls` mostrando `contracts`
- [ ] 6.2 Configurar Alembic async en `core/migrations/` con `alembic.ini` en la raíz (URL desde `AppSettings`, revisiones `0001_...`, `Base` en `adapters/outbound/persistence/base.py`) con migración `0001_enable_pgvector`; verificar `uv run alembic upgrade head` y que `SELECT extname FROM pg_extension` incluye `vector`

## 7. CI y pre-commit

- [x] 7.1 Crear `.pre-commit-config.yaml` (ruff, ruff-format, mypy, lint-imports, escaneo de identificadores); verificar `uv run pre-commit run --all-files` en verde
- [x] 7.2 Crear `.github/workflows/ci.yml` (`uv sync --frozen --all-packages` → ruff → mypy → lint-imports → escaneo con secreto `FORBIDDEN_NAMES` → pytest, cache uv); verificar sintaxis con `uvx actionlint` (o ejecución en GitHub tras el primer push)

## 8. Documentación de arquitectura

- [x] 8.1 Escribir ADRs en `docs/architecture/adr/` (inglés, MADR corto): `0001-hexagonal-architecture-and-rewrite`, `0002-uv-workspace-monorepo`, `0003-composition-root-reader-writer-containers`, `0004-executable-architecture-rules`; verificar que cada uno tiene Status, Context, Decision, Consequences
- [ ] 8.2 Escribir `docs/architecture/hexagonal.md` (diagrama Mermaid de capas, tabla puertos→adaptadores previstos, mapa SOLID, cómo agregar un puerto/adaptador) y un `README.md` raíz inicial (pitch breve, estructura, quickstart: `uv sync`, `docker compose up -d`, `alembic upgrade head`, `pytest`); verificar que los comandos del quickstart funcionan tal como están escritos

## 9. Verificación integral

- [ ] 9.1 Desde un clon limpio en WSL: `uv sync --frozen --all-packages && uv run ruff check . && uv run mypy core pipelines rag_api && uv run lint-imports && uv run python scripts/check_forbidden_identifiers.py && uv run pytest` todo en verde, y `git ls-files | grep -c '^legacy/'` devuelve 0
- [x] 9.2 Ejecutar `openspec validate scaffold-hexagonal --strict` sin errores

## Workflow follow-up

- Revisar el cambio y archivarlo con `/opsx:archive` (crea `openspec/specs/architecture-conformance/spec.md`).
- Siguiente cambio: `/opsx:propose document-ingestion`.
