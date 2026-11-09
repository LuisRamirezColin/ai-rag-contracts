# Design

## Context

Estado actual (cambio archivado `2026-11-09-scaffold-hexagonal`):
- Puertos de ingesta definidos con fakes in-memory: inbound `IngestDocuments` (batch, devuelve `IngestionReport`, sin consumidores) y outbound `DocumentSource`, `DocumentStorage`, `TextExtractor`.
- `ExtractClauses` y `VectorizeDocument` ya reciben un `DocumentId`: el resto del lado escritor piensa por documento.
- `bootstrap/containers.py` lanza `RealAdaptersUnavailableError` al construir el contenedor si `use_fakes=false`.
- Dagster solo expone el `WriterContainer` como recurso `container`; Alembic tiene la migración `0001_enable_pgvector`.
- `import-linter` ya prohíbe `boto3`, `botocore`, `sqlalchemy` y `pypdf` en dominio y aplicación.

Motivación en `proposal.md` (Why); requisitos en `specs/document-ingestion/spec.md`.

## Goals / Non-Goals

**Goals:**
- Unidad de trabajo = un documento, para que la extracción y la vectorización se encadenen por documento en los cambios siguientes.
- Los adaptadores reales son intercambiables con los fakes y se verifican con los mismos contract tests.
- Las pruebas unitarias corren sin Docker; las de integración son explícitas y también corren en CI.

**Non-Goals:**
- OCR de PDFs escaneados (fallan con motivo; puede llegar en otro cambio).
- Persistir el agregado `Contract` y sus cláusulas (llega con clause-extraction).
- Fuentes distintas de CUAD, borrado de documentos que desaparecen de la fuente, despliegue de Dagster fuera de local.

## Decisions

### D1 — Puertos inbound por documento: `DiscoverDocuments` + `IngestDocument`
Se elimina `IngestDocuments` (batch) y se crean dos puertos en `application/ports/inbound/`:

```python
class DiscoverDocuments(Protocol):
    async def execute(self) -> tuple[DocumentId, ...]: ...   # pendientes, orden determinista

class IngestDocument(Protocol):
    async def execute(self, document_id: DocumentId) -> IngestionRecord: ...
```
- `IngestionReport` desaparece; el resultado por documento es `IngestionRecord` (dominio, D3).
- **Alternativa**: mantener el batch y que Dagster lo llame en un solo asset. Se descarta: un documento malo marcaría todo el run como fallido, no habría reintento por documento y no encaja con las particiones de los cambios siguientes.
- **SOLID**: SRP — descubrir (qué falta) y ingerir (procesar uno) cambian por razones distintas. ISP — el sensor solo ve `DiscoverDocuments`; el asset solo `IngestDocument`.

### D2 — Puerto outbound nuevo `DocumentRepository`
```python
class DocumentRepository(Protocol):
    async def save_ingested(self, document: Document, pages: tuple[Page, ...]) -> None
    async def save_failed(self, document: Document, reason: str) -> None
    async def get_record(self, document_id: DocumentId) -> IngestionRecord | None
    async def ingested_ids(self) -> frozenset[DocumentId]
    async def get_pages(self, document_id: DocumentId) -> tuple[Page, ...]  # DocumentNotAvailableError
```
- `save_ingested` y `save_failed` reemplazan por completo el estado anterior (idempotencia, spec "La reingesta es idempotente").
- Fake: `InMemoryDocumentRepository`. Real: `SqlAlchemyDocumentRepository` (D8).
- **Alternativa**: ampliar `ContractRepository`. Se descarta: el agregado `Contract` (cláusulas) tiene otro ciclo de vida y llega en clause-extraction; mezclarlos crearía una interfaz "repositorio de todo".
- **SOLID**: ISP + SRP — un puerto por agregado y ciclo de vida. DIP — el use case depende del `Protocol`, no de SQLAlchemy.

### D3 — Dominio: estado de ingesta y errores traducidos
- `domain/ingestion.py`: `IngestionStatus(StrEnum)` (`ingested`, `failed`), `IngestionRecord` (`document_id`, `status`, `page_count`, `failure_reason: str | None`) con invariantes (fallido ⇒ motivo no vacío y 0 páginas; ingerido ⇒ sin motivo y `page_count >= 1`), y `has_extractable_text(pages) -> bool`.
- `domain/errors.py` añade `UnknownDocumentError` (id ausente en fuente o almacenamiento), `UnreadableDocumentError` (archivo corrupto) y `DocumentNotAvailableError` (páginas pedidas de un documento no ingerido).
- Los adaptadores traducen las excepciones de librería (`botocore`, `pypdf`, `FileNotFoundError`) a estos errores; el use case nunca ve excepciones de infraestructura.
- **SOLID**: DIP — la regla "sin texto ⇒ fallido" vive en el dominio, no en el extractor; cambiar de extractor no cambia la regla.

### D4 — Use cases en `application/use_cases/`
`DiscoverDocumentsUseCase(source, repository, max_documents)`:
1. `source.list_documents()` ordenado por `id` y truncado a `max_documents` (el límite se aplica a la fuente, antes de filtrar: con límite 5 el sistema converge a esos 5).
2. Quita los `repository.ingested_ids()`.

`IngestDocumentUseCase(source, storage, extractor, repository)`:
1. Busca el `Document` en la fuente (`UnknownDocumentError` si no está).
2. `content = source.fetch_content(id)` → `storage.save(id, content)`: el original se conserva aunque luego falle la extracción.
3. `extractor.extract_pages(id, content)`; si lanza `UnreadableDocumentError` o `not has_extractable_text(pages)` → `repository.save_failed(document, reason)`.
4. Si hay texto → `repository.save_ingested(document, pages)`.
5. Devuelve `repository.get_record(id)`.

Un fallo de negocio se devuelve como `IngestionRecord` fallido; solo los errores inesperados (red, BD) se propagan. `max_documents` llega por constructor desde settings (sin números mágicos en el use case).

### D5 — `CuadDocumentSource` sobre un directorio local
- Recorre `ingestion.cuad_dir` buscando `*.pdf` sin distinguir mayúsculas (CUAD mezcla `.pdf` y `.PDF`).
- `DocumentId` estable y legible: slug del nombre de archivo (minúsculas, no alfanumérico → `-`, máx. 64 caracteres) + `-` + 8 hex del SHA-256 de la ruta relativa. Ejemplo: `acme-corp-ex-10-distributor-agreement-3f2a9c1b`.
- Un PDF de CUAD = un contrato: `contract_id` = `document_id`, `title` = nombre del archivo sin extensión, `document_type = OTHER` (ver Open Questions).
- I/O de disco con `asyncio.to_thread`.
- **Alternativa**: leer directamente del zip o de un mirror remoto. Se descarta: el directorio local hace la fuente determinista y rápida en tests; la descarga queda en un script aparte (D11).

### D6 — `S3DocumentStorage` (boto3)
- Clave `raw/{document_id}.pdf` en `storage.bucket`; `endpoint_url` y `region` desde settings (LocalStack en local).
- Cliente boto3 creado de forma perezosa; las llamadas bloqueantes van en `asyncio.to_thread`. `exists` usa `head_object` y exige `ContentLength > 0`; `NoSuchKey`/404 → `UnknownDocumentError`.
- **Alternativa**: `aioboto3`. Se descarta por ahora: añade una dependencia y otra capa async por un volumen bajo (decenas de archivos). Si el throughput lo pide, el cambio queda encapsulado en el adaptador (OCP).

### D7 — `PypdfTextExtractor` (sin OCR)
- `PdfReader(BytesIO(content))`, `extract_text()` por página (`None` → `""`), numeración desde `FIRST_PAGE`, en `asyncio.to_thread`.
- `PdfReadError` y PDFs cifrados → `UnreadableDocumentError`.
- El nombre previsto en el scaffold (`PypdfOcrTextExtractor`) se corrige porque no hay OCR; se actualiza `docs/architecture/hexagonal.md`.

### D8 — Persistencia en Postgres
Migración `0002_documents_and_pages`:

| Tabla | Columnas |
|---|---|
| `documents` | `id` text PK, `contract_id` text, `title` text, `document_type` text, `status` text (check `ingested`/`failed`), `failure_reason` text null, `page_count` int, `updated_at` timestamptz |
| `pages` | `document_id` text FK → `documents.id` on delete cascade, `number` int (check ≥ 1), `text` text; PK (`document_id`, `number`) |

- Modelos en `adapters/outbound/persistence/models.py` sobre la `Base` existente.
- `save_ingested`: en una transacción, upsert del documento (`INSERT ... ON CONFLICT DO UPDATE`), `DELETE` de sus páginas e inserción de las nuevas. `save_failed`: upsert con estado fallido y `DELETE` de páginas.
- El adaptador elimina `\x00` del texto (Postgres no lo admite en `text` y pypdf puede emitirlo).
- Engine async y `async_sessionmaker` como providers perezosos del composition root. El lado escritor usa `NullPool`: Dagster ejecuta cada materialización con su propio `asyncio.run`, y un pool reutilizaría conexiones atadas a un event loop ya cerrado.

### D9 — Composition root: selección real/fake perezosa por puerto
- `_resolve_settings` deja de lanzar. Cada puerto outbound del contenedor es un `providers.Selector` sobre `settings.use_fakes` con ramas `fake` y `real`.
- Rama `real` implementada: `document_source`, `document_storage`, `text_extractor`, `document_repository`. El resto apunta a un provider que lanza `RealAdaptersUnavailableError(port_name)` **al resolverse**, no al construir el contenedor.
- `WriterContainer` añade los use cases como `Factory`: `discover_documents`, `ingest_document`. `ReaderContainer` no recibe ninguno de ingesta.
- Dependencias:

```
contract_intel_pipelines (sensor, asset)
        │ resuelve use cases tipados como puertos inbound
        ▼
bootstrap.WriterContainer ──► adapters.outbound.{cuad, s3, pypdf, persistence, in_memory}
        │                                   │ implementan
        ▼                                   ▼
application.use_cases ──► application.ports.{inbound,outbound} ──► domain
```
- **Alternativa**: lanzar al construir si falta cualquier adaptador real (comportamiento actual). Se descarta: impediría usar la ingesta real hasta que existan todos los adaptadores de los cambios siguientes.
- **SOLID**: OCP — cada cambio futuro solo rellena la rama `real` de su puerto. DIP — solo `bootstrap` conoce clases concretas.

### D10 — Dagster: particiones dinámicas, sensor y asset por documento
- `DynamicPartitionsDefinition(name="documents")`.
- Sensor `pending_documents_sensor` (`default_status=RUNNING`, intervalo en una constante con nombre): ejecuta `DiscoverDocuments`, descarta las claves que ya son particiones y devuelve `SensorResult` con `dynamic_partitions_requests` (alta) y un `RunRequest` por documento nuevo. Como solo programa claves que aún no son partición, un documento fallido no se reprograma solo (spec "Detección continua").
- Asset `ingested_document` particionado: `asyncio.run(ingest_document.execute(DocumentId(partition_key)))`; publica `status` y `page_count` como metadata. Si el registro es fallido, lanza `dagster.Failure(description=reason)` después de que el estado ya esté persistido, para que el run falle visiblemente y los assets posteriores no se ejecuten.
- Los cambios siguientes añaden assets particionados (`extracted_clauses`, `indexed_chunks`) que dependen de `ingested_document`.
- **Alternativa**: un schedule sin particiones. Se descarta: no da visibilidad ni reintento por documento en la UI.

### D11 — Obtención del dataset: `scripts/download_cuad.py`
- Solo stdlib (`urllib`, `hashlib`, `zipfile`, `tempfile`). Descarga `CUAD_v1.zip` desde el registro público de CUAD en Zenodo a un archivo temporal, verifica un SHA-256 fijado como constante y extrae a un directorio temporal hermano que se renombra a `data/cuad/` solo si todo salió bien (sin datos parciales).
- Default de `ingestion.cuad_dir`: `data/cuad/CUAD_v1/full_contract_pdf`. Se conserva el resto del zip (`master_clauses.csv`, `CUAD_v1.json`) para la evaluación de clause-extraction.
- La URL exacta y el SHA-256 se confirman en la implementación (tarea 1.2) contra la suma que publica Zenodo.

### D12 — Estrategia de pruebas
- **Unitarias (sin Docker)**: use cases con fakes (`core/tests/application/`); dominio (`IngestionRecord`, `has_extractable_text`); script de descarga con transporte inyectado (checksum incorrecto ⇒ error y sin directorio final).
- **Contract tests** (`core/tests/adapters/contracts/`): una suite por puerto (`DocumentStorage`, `DocumentRepository`, `TextExtractor`, `DocumentSource`) parametrizada sobre fake y real. LSP verificado: mismos tests, mismas expectativas.
- **PDFs de prueba** generados en fixtures con `fpdf2` (dev): PDF con texto en N páginas, PDF de páginas en blanco y bytes corruptos. Ningún contrato real en el repo.
- **Integración**: marcador `integration`; `addopts` excluye `-m "not integration"` por defecto. Los parámetros reales de S3 y Postgres llevan el marcador; `CuadDocumentSource` y `PypdfTextExtractor` son locales y corren siempre.
- **Dagster**: sensor con `build_sensor_context` sobre una `DagsterInstance.ephemeral()`, asset con `materialize()` y contenedor de fakes.
- **CI**: job nuevo `integration` con servicios `pgvector/pgvector:pg16` y `localstack/localstack:3.8`, `alembic upgrade head`, creación del bucket y `pytest -m integration`.

### D13 — ADRs
- `docs/architecture/adr/0005-per-document-ingestion-with-dynamic-partitions.md` — D1 + D10.
- `docs/architecture/adr/0006-lazy-per-port-adapter-selection.md` — D9.

## Risks / Trade-offs

- [La URL o el contenido de CUAD en Zenodo cambian] → SHA-256 fijado: el script falla con un mensaje claro en vez de ingerir datos distintos.
- [PDFs de CUAD con texto pobre o sin capa de texto] → se marcan fallidos con motivo y quedan visibles en Dagster; el OCR queda como cambio futuro.
- [Event loops distintos por materialización rompen conexiones async] → `NullPool` en el lado escritor (D8).
- [`\x00` u otros caracteres que Postgres rechaza] → saneado en el adaptador de persistencia, cubierto por un contract test.
- [Slug truncado con colisiones] → el sufijo hash de la ruta relativa garantiza unicidad; la fuente falla si detecta un id duplicado.
- [Integración lenta o inestable en CI] → job separado; los tests unitarios no dependen de él.
- [Dagster con `asyncio.run` dentro de un asset] → aceptable para el volumen de la demo; si crece, se migra a un executor async sin tocar los use cases.

## Migration Plan

1. `uv run python scripts/download_cuad.py` (una vez por máquina).
2. `docker compose up -d --wait` → `uv run alembic upgrade head` (aplica `0002`).
3. `CONTRACT_INTEL_USE_FAKES=false uv run dagster dev -m contract_intel_pipelines.definitions`: el sensor programa los primeros `max_documents` (5).

Rollback: `alembic downgrade 0001` borra `documents` y `pages`; el bucket y `data/` se pueden borrar sin afectar al código. Con `use_fakes=true` el sistema vuelve al comportamiento sin infraestructura.

## Open Questions

- Mapeo de las categorías de CUAD (carpetas como *Distributor*, *License_Agreements*) a `DocumentType`. Por ahora todo es `OTHER`; refinar el enum no cambia las specs y puede decidirse en clause-extraction.
- Intervalo exacto del sensor (propuesta inicial: 60 s), ajustable sin cambiar specs ni tareas.
