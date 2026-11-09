# Tasks

> Todos los comandos se ejecutan dentro de WSL. Las pruebas `integration` requieren `docker compose up -d --wait` y `uv run alembic upgrade head`. Cada grupo deja `uv run ruff check .`, `uv run mypy core pipelines rag_api scripts` y `uv run lint-imports` en verde antes de cerrarse.

## 1. Dependencias y dataset

- [x] 1.1 Añadir `boto3` y `pypdf` a `core/pyproject.toml`, y `fpdf2` y `boto3-stubs[s3]` al grupo dev raíz; registrar el marcador `integration` en `[tool.pytest.ini_options]` con `addopts` que excluya `-m "not integration"`; verificar `uv sync --all-packages`, que `uv.lock` se actualiza y que `uv run pytest` sigue en verde
- [x] 1.2 Crear `scripts/download_cuad.py` (D11: stdlib, URL pública de CUAD v1 en Zenodo, SHA-256 fijado tras confirmarlo contra la suma publicada, extracción atómica a `data/cuad/`) y tests en `scripts/tests/test_download_cuad.py` con transporte inyectado (descarga válida → directorio final; checksum incorrecto → error y sin `data/cuad/`); verificar `uv run pytest scripts/tests` y ejecutar el script real, comprobando que hay PDFs en `data/cuad/CUAD_v1/full_contract_pdf` y que `git status --short data` no muestra nada

## 2. Dominio

- [x] 2.1 Crear `domain/ingestion.py` (`IngestionStatus`, `IngestionRecord` con invariantes de D3, `has_extractable_text`) y añadir `UnknownDocumentError`, `UnreadableDocumentError` y `DocumentNotAvailableError` a `domain/errors.py`; tests en `core/tests/domain/test_ingestion.py` con caso válido e inválido por invariante y casos de páginas vacías o solo con espacios; verificar `uv run pytest core/tests/domain`

## 3. Puertos y fakes

- [x] 3.1 Reemplazar `application/ports/inbound/ingest_documents.py` por `discover_documents.py` (`DiscoverDocuments`) e `ingest_document.py` (`IngestDocument`) según D1, eliminando `IngestionReport`; verificar `uv run mypy core` y que `grep -rn "IngestDocuments\|IngestionReport" core pipelines rag_api` no devuelve nada
- [x] 3.2 Crear `application/ports/outbound/document_repository.py` (`DocumentRepository`, D2) y `adapters/outbound/in_memory/document_repository.py` (`InMemoryDocumentRepository`); ajustar los fakes de fuente y almacenamiento para lanzar `UnknownDocumentError` en vez de `KeyError`; añadir el nuevo fake a `core/tests/adapters/in_memory/test_conformance.py`; verificar `uv run pytest core/tests/adapters/in_memory` y `uv run mypy core`

## 4. Use cases

- [x] 4.1 Implementar `application/use_cases/discover_documents.py` (D4) con tests unitarios sobre fakes en `core/tests/application/test_discover_documents.py`: límite aplicado a la fuente, orden estable entre ejecuciones y exclusión de los ya ingeridos; verificar `uv run pytest core/tests/application`
- [x] 4.2 Implementar `application/use_cases/ingest_document.py` (D4) con tests unitarios sobre fakes en `core/tests/application/test_ingest_document.py`: documento con texto → ingerido con N páginas y original almacenado; sin texto → fallido con motivo y sin páginas; ilegible → fallido; reingesta → un único conjunto de páginas; fallido → reingesta exitosa limpia el motivo; id desconocido → `UnknownDocumentError`; verificar `uv run pytest core/tests/application`

## 5. Adaptadores reales locales (fuente y extractor)

- [x] 5.1 Crear fixtures de PDF con `fpdf2` en `core/tests/adapters/contracts/conftest.py` (texto en N páginas, páginas en blanco, bytes corruptos) y la suite de contrato de `TextExtractor` parametrizada sobre `InMemoryTextExtractor` y `PypdfTextExtractor` (`adapters/outbound/pdf/pypdf_text_extractor.py`, D7); verificar `uv run pytest core/tests/adapters/contracts -k text_extractor`
- [x] 5.2 Implementar `adapters/outbound/cuad/cuad_document_source.py` (D5: búsqueda sin distinguir mayúsculas, slug + hash, fallo ante id duplicado) y la suite de contrato de `DocumentSource` sobre el fake y sobre un directorio temporal con PDFs de fixture; verificar `uv run pytest core/tests/adapters/contracts -k document_source`

## 6. Adaptadores reales con infraestructura (S3 y Postgres)

- [x] 6.1 Implementar `adapters/outbound/s3/s3_document_storage.py` (D6) y la suite de contrato de `DocumentStorage` parametrizada sobre el fake y S3 (marcada `integration`, con un bucket aislado por test en LocalStack); verificar `uv run pytest core/tests/adapters/contracts -k document_storage` y `uv run pytest -m integration -k document_storage`
- [x] 6.2 Crear `adapters/outbound/persistence/models.py` y la migración `core/migrations/versions/0002_documents_and_pages.py` (D8); verificar `uv run alembic upgrade head`, `uv run alembic downgrade 0001` y de nuevo `upgrade head`, y que `\d pages` en Postgres muestra la PK compuesta y la FK con `ON DELETE CASCADE`
- [x] 6.3 Implementar `adapters/outbound/persistence/document_repository.py` (`SqlAlchemyDocumentRepository`, D8: upsert y reemplazo de páginas en una transacción, saneado de `\x00`) y la suite de contrato de `DocumentRepository` sobre el fake y Postgres (marcada `integration`, tablas limpias por test), incluyendo reingesta, fallido→ingerido, `get_pages` de documento fallido o inexistente y texto con `\x00`; verificar `uv run pytest core/tests/adapters/contracts -k document_repository` y `uv run pytest -m integration -k document_repository`

## 7. Composition root y settings

- [x] 7.1 Añadir `IngestionSettings` (`cuad_dir`, `max_documents=5`) a `bootstrap/settings.py` y las variables `CONTRACT_INTEL_INGESTION__*` a `.env.example`; ampliar `core/tests/bootstrap/test_settings.py`; verificar `uv run pytest core/tests/bootstrap/test_settings.py`
- [x] 7.2 Reescribir `bootstrap/containers.py` según D9 (`Selector` por puerto, rama real para los cuatro puertos de ingesta, `RealAdaptersUnavailableError(port_name)` al resolver los demás, engine async con `NullPool` en el escritor, `Factory` de `discover_documents` e `ingest_document` solo en `WriterContainer`); actualizar `core/tests/bootstrap/test_containers.py`: construir con `use_fakes=false` no abre red, resolver un puerto sin adaptador real lanza el error con su nombre, `ReaderContainer` no expone use cases de ingesta, y descubrir + ingerir de punta a punta con fakes y socket bloqueado deja el documento ingerido; verificar `uv run pytest core/tests/bootstrap` y `uv run lint-imports`

## 8. Dagster (lado escritor)

- [x] 8.1 Añadir en `contract_intel_pipelines` la partición dinámica `documents`, el sensor `pending_documents_sensor` y el asset `ingested_document` (D10), registrados en `definitions.py`; tests en `pipelines/tests/` con contenedor de fakes: el sensor añade particiones y `RunRequest` solo para claves nuevas, no reprograma una clave existente aunque haya fallado, el asset materializa con metadata `status`/`page_count` y lanza `Failure` cuando el registro es fallido; verificar `uv run pytest pipelines/tests` y `uv run dagster definitions validate -m contract_intel_pipelines.definitions`

## 9. CI y documentación

- [x] 9.1 Añadir a `.github/workflows/ci.yml` el job `integration` (servicios Postgres pgvector y LocalStack, `alembic upgrade head`, creación del bucket, `uv run pytest -m integration`) y ampliar el paso de mypy para que incluya los módulos nuevos; verificar con `uvx actionlint` y con un run verde en GitHub tras el primer push
- [x] 9.2 Escribir los ADRs `0005-per-document-ingestion-with-dynamic-partitions` y `0006-lazy-per-port-adapter-selection` en `docs/architecture/adr/` (MADR corto, inglés); actualizar `docs/architecture/hexagonal.md` (tabla de puertos: `DiscoverDocuments`, `IngestDocument`, `DocumentRepository`, `PypdfTextExtractor`; diagrama del flujo de ingesta) y el `README.md` (paso de descarga de CUAD, `pytest -m integration`, cómo ejecutar Dagster con `CONTRACT_INTEL_USE_FAKES=false`); verificar que cada ADR tiene Status, Context, Decision y Consequences y que los comandos nuevos del README funcionan tal como están escritos

## 10. Verificación integral

- [x] 10.1 Ingesta real de punta a punta: con `docker compose up -d --wait`, `alembic upgrade head` y `CONTRACT_INTEL_USE_FAKES=false`, arrancar Dagster y comprobar que el sensor programa exactamente 5 documentos, que `SELECT status, count(*) FROM documents GROUP BY status` suma 5, que cada documento ingerido tiene páginas en `pages` y su PDF en `s3://contracts/raw/`, y que una segunda pasada del sensor no programa nada nuevo
- [x] 10.2 Desde un clon limpio: `uv sync --frozen --all-packages && uv run ruff format --check . && uv run ruff check . && uv run mypy scripts core/src core/tests core/migrations pipelines/src pipelines/tests rag_api/src rag_api/tests && uv run lint-imports && uv run python scripts/check_forbidden_identifiers.py && uv run pytest && uv run pytest -m integration` todo en verde, y `git ls-files | grep -c '^data/'` devuelve 0
- [x] 10.3 Ejecutar `openspec validate document-ingestion --strict` sin errores

## Workflow follow-up

- Revisar el cambio y archivarlo con `/opsx:archive` (crea `openspec/specs/document-ingestion/spec.md`).
- Siguiente cambio: `/opsx:propose clause-extraction`.
