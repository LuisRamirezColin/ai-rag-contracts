# Design

## Context

Estado actual (cambio archivado `2026-11-09-document-ingestion`):
- `DocumentRepository.get_pages(document_id)` devuelve las páginas en orden de un documento ingerido (`DocumentNotAvailableError` si no lo está).
- Dominio: `Chunk` (`id`, `document_id`, `text`, `pages: PageRange`, `clause_type: ClauseType | None`), `Embedding`, `EmbeddedChunk`, `ScoredChunk`, `UsageRecord`.
- Puertos con solo fakes: `Embedder.embed(texts)`, `VectorIndexWriter.upsert/delete_document`, `VectorSearch.search`, `UsageTracker.record`. El inbound `VectorizeDocument.execute(document_id) -> int` no tiene use case.
- Composition root con `Selector` fake/real por puerto (ADR 0006); `embedder` y `usage_tracker` viven en `CoreContainer`, `vector_index_writer` en `WriterContainer`.
- Dagster: partición dinámica `documents`, sensor y asset `ingested_document`; job `ingest_documents_job`.
- La migración `0001` ya habilita la extensión `vector`.

Motivación en `proposal.md`; requisitos en `specs/document-vectorization/spec.md`.

Datos de Voyage verificados en su documentación: `voyage-law-2` tiene contexto de 16,000 tokens y vectores de 1024 dimensiones (no configurable); una petición admite hasta 1,000 textos y 120K tokens para este modelo; `input_type` acepta `"document"` y `"query"`; `truncation=False` falla en vez de recortar en silencio. El SDK documenta el cliente síncrono `voyageai.Client`; el cliente asíncrono no aparece en la documentación revisada.

## Goals / Non-Goals

**Goals:**
- Cada documento ingerido queda indexado con fragmentos citables (rango de páginas) sin intervención manual.
- El índice de un documento nunca queda a medias para un lector.
- Cambiar de modelo de embeddings toca un adaptador y settings, no use cases.

**Non-Goals:**
- Búsqueda real (`PgVectorSearch`) y la API `/ask`: llegan en `rag-api`. Aquí se verifica el índice por SQL y por contract tests.
- Asignar `clause_type` a los fragmentos (llega con clause-extraction); por ahora es `NULL`.
- Fragmentación semántica o por estructura del contrato (secciones numeradas); se puede evolucionar sin cambiar las specs.
- Reindexado masivo al cambiar de modelo (requeriría migración de dimensión).

## Decisions

### D1 — Fragmentación como servicio puro de dominio
`domain/chunking.py`: `chunk_pages(document_id, pages, max_chars, overlap_chars) -> tuple[Chunk, ...]`.
- Concatena el texto de las páginas recordando el desplazamiento de inicio de cada página; corta ventanas de hasta `max_chars`, preferentemente en el último salto de párrafo o espacio dentro de la ventana; la siguiente ventana empieza `overlap_chars` antes del corte.
- El `PageRange` de cada fragmento se calcula por desplazamientos: primera y última página cuyo texto aparece en la ventana. Las páginas en blanco no generan fragmentos.
- `ChunkId` determinista: `"{document_id}:{ordinal:04d}"`, para que una revectorización produzca los mismos ids si el texto no cambió.
- Defaults en settings: `max_chars=2000` (~500 tokens) y `overlap_chars=200`; validados (`0 <= overlap < max`).
- Se mide en caracteres, no en tokens: no hay tokenizador público de Voyage y 2000 caracteres quedan muy por debajo del contexto de 16K tokens.
- **Alternativa**: fragmentar por página. Se descarta: las páginas de CUAD van de 32 a 7,500 caracteres; fragmentos tan desiguales degradan la recuperación.
- **SOLID**: SRP — la regla de fragmentación es dominio puro, testeable sin I/O y reutilizable por cualquier adaptador.

### D2 — Puerto `Embedder` refinado: documentos vs consulta
```python
class Embedder(Protocol):
    async def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch
    async def embed_query(self, text: str) -> Embedding
```
- `EmbeddingBatch` (dominio): `embeddings: tuple[Embedding, ...]`, `input_tokens: int`, `model: str`; invariante: todas las dimensiones iguales.
- `embedder` sigue en `CoreContainer`: el escritor usa `embed_documents` y el lector (rag-api) `embed_query`.
- **Alternativa**: un solo `embed(texts, kind)`. Se descarta: el lector solo necesita consultas y el escritor solo documentos; dos métodos expresan mejor la intención y evitan banderas.
- **SOLID**: ISP + OCP — otro proveedor implementa los dos métodos sin tocar consumidores.

### D3 — Puerto `VectorIndexWriter` con reemplazo atómico
```python
class VectorIndexWriter(Protocol):
    async def replace_document(self, document_id: DocumentId, chunks: Sequence[EmbeddedChunk]) -> None
    async def delete_document(self, document_id: DocumentId) -> None
```
- `replace_document` borra e inserta en una transacción; rechaza chunks de otro documento.
- **Alternativa**: mantener `upsert` + `delete_document` y orquestar en el use case. Se descarta: entre ambas llamadas el lector vería el documento sin fragmentos (spec "reemplazo atómico").

### D4 — Use case `VectorizeDocumentUseCase`
Dependencias: `DocumentRepository`, `Embedder`, `VectorIndexWriter`, `UsageTracker`, `ChunkingPolicy` (`max_chars`, `overlap_chars`) y `EmbeddingPricing` (`price_per_million_tokens`).
1. `pages = repository.get_pages(id)` (propaga `DocumentNotAvailableError` sin tocar el índice).
2. `chunks = chunk_pages(...)`.
3. `batch = embedder.embed_documents([c.text for c in chunks])`; verifica que hay un vector por chunk.
4. `writer.replace_document(id, [EmbeddedChunk(c, e) ...])`.
5. `usage_tracker.record(UsageRecord(operation="embed_documents", model=batch.model, input_tokens=batch.input_tokens, output_tokens=0, cost_usd=..., document_id=id))`.
6. Devuelve `len(chunks)`.
- El orden (embeddings antes de escribir) garantiza que un fallo del proveedor deja intacto el índice previo.
- `UsageRecord` gana `document_id: DocumentId | None = None`.

### D5 — `VoyageEmbedder`
- `voyageai.Client(api_key=..., max_retries=...)` creado de forma perezosa; las llamadas bloqueantes van en `asyncio.to_thread` (mismo patrón que S3 y pypdf). Si el SDK expone un cliente asíncrono documentado al implementar, se puede usar sin cambiar el puerto.
- `embed(texts, model="voyage-law-2", input_type="document"|"query", truncation=False)`.
- Lotes: como máximo 128 textos y ~300K caracteres por petición (estimación conservadora de ≤100K tokens frente al límite de 120K); los tokens reportados (`total_tokens`) se suman entre lotes.
- Valida que cada vector tenga `embeddings.dimensions` (1024); si no, lanza `EmbeddingDimensionMismatchError` (dominio).
- **Alternativa**: llamar a la API REST con `httpx`. Se descarta: el SDK oficial ya maneja autenticación y reintentos.

### D6 — Persistencia: `chunks` y `usage_records` (migración `0003`)

| Tabla | Columnas |
|---|---|
| `chunks` | `id` text PK, `document_id` text FK → `documents.id` on delete cascade, `ordinal` int, `text` text, `first_page` int, `last_page` int (check `last_page >= first_page >= 1`), `clause_type` text null, `embedding` `vector(1024)`, `model` text |
| `usage_records` | `id` bigint identity PK, `operation` text, `model` text, `input_tokens` int, `output_tokens` int, `cost_usd` numeric(12,6), `document_id` text null, `created_at` timestamptz |

- Índices: HNSW `vector_cosine_ops` sobre `chunks.embedding` (lo usará `PgVectorSearch`), btree sobre `chunks.document_id` y `usage_records.document_id`.
- La dimensión `1024` queda fija en la migración y en `embeddings.dimensions`; el adaptador valida que coincidan al escribir.
- `PgVectorIndexWriter` (tipo `pgvector.sqlalchemy.Vector`) y `SqlAlchemyUsageTracker` reciben el `async_sessionmaker` del escritor (`NullPool`, ADR 0006).
- **Alternativa**: guardar los vectores en la tabla `pages`. Se descarta: un fragmento puede cruzar páginas y una página puede producir varios fragmentos.

### D7 — Composition root
- `CoreContainer.embedder`: rama real `VoyageEmbedder` con settings `embeddings`.
- `CoreContainer.usage_tracker`: rama real `SqlAlchemyUsageTracker`. Necesita un `session_factory`; el engine se mueve de `WriterContainer` a `CoreContainer` con un provider de pool configurable (`NullPool` para el escritor, que se fija al construir `WriterContainer`; el lector configurará el suyo en rag-api).
- `WriterContainer.vector_index_writer`: rama real `PgVectorIndexWriter`; nuevo `Factory` `vectorize_document`.
- Siguen sin rama real: `clause_extractor`, `contract_repository`, `vector_search`, `answer_generator`.
- **Ajuste durante la implementación**: `bootstrap/containers.py` se divide en `bootstrap/core.py` (`CoreContainer`, engine, embedder, uso), `bootstrap/writer.py` (`WriterContainer`) y `bootstrap/reader.py` (`ReaderContainer`). Con un solo módulo, la API importaba indirectamente `VectorizeDocumentUseCase` y con él el puerto `VectorIndexWriter`, y el contrato "API is read-only on the vector index" fallaba. Ahora el proceso de la API no carga código del escritor, y el contrato también prohíbe `contract_intel.bootstrap.writer` desde `contract_intel_api`. **SOLID**: ISP a nivel de despliegue — cada proceso depende solo de su composición.

### D8 — Dagster: asset `indexed_document` en el mismo job
- Asset particionado por `documents`, con `deps=[ingested_document]`; ejecuta `VectorizeDocument` y publica `chunk_count` como metadata.
- `ingest_documents_job` selecciona `[ingested_document, indexed_document]`: cada run del sensor ingiere y luego vectoriza. Si `ingested_document` lanza `Failure`, Dagster omite el asset dependiente (spec "Ingesta fallida").
- Revectorizar un documento = materializar solo `indexed_document` de esa partición desde la UI.
- **Alternativa**: condiciones de automatización declarativas (`AutomationCondition.eager()`). Se descarta por ahora: depende de un sensor de automatización adicional y el job compartido es determinista y fácil de probar.

### D9 — Settings
- `EmbeddingsSettings`: `api_key: SecretStr`, `model="voyage-law-2"`, `dimensions=1024`, `price_per_million_tokens=0.12`, `max_retries=3`.
- `ChunkingSettings`: `max_chars=2000`, `overlap_chars=200`.
- Se elimina `llm.embedding_model` (el LLM de chat se reconfigura para Claude en rag-api).
- `.env.example`: `CONTRACT_INTEL_EMBEDDINGS__API_KEY=replace-me` y las variables de chunking.

### D10 — Estrategia de pruebas
- **Dominio**: `chunk_pages` (documento corto, largo con solapamiento y cobertura total, cruce de página, páginas en blanco, ids deterministas, parámetros inválidos); `EmbeddingBatch`.
- **Use case con fakes**: fragmentos escritos, uso registrado con `document_id`, documento fallido → error sin tocar el índice, fallo del embedder → índice previo intacto, revectorización reemplaza.
- **Contract tests**:
  - `Embedder`: fake vs `VoyageEmbedder` con un cliente de Voyage falso inyectado (lotes, suma de tokens, `input_type`, error de dimensión). Un smoke test real marcado `voyage` corre solo si `CONTRACT_INTEL_EMBEDDINGS__API_KEY` está definida; nunca en CI por defecto.
  - `VectorIndexWriter`: fake vs Postgres (`integration`): reemplazo, aislamiento entre documentos, rechazo de chunks ajenos, atomicidad (fallo a mitad → estado previo).
  - `UsageTracker`: fake vs Postgres (`integration`).
- **Dagster**: el job con contenedor de fakes materializa ambos assets; si la ingesta falla, `indexed_document` no se ejecuta.
- El fake de embeddings pasa a producir vectores de la dimensión configurada para que los contract tests compartan expectativas.

### D11 — ADR
`docs/architecture/adr/0007-embeddings-with-voyage-and-pgvector.md`: elección de Voyage `voyage-law-2` (Anthropic no ofrece embeddings; modelo legal; free tier), pgvector con HNSW coseno, fragmentación por caracteres con páginas, reemplazo atómico por documento.

## Risks / Trade-offs

- [Contratos con texto OCR pobre producen fragmentos ruidosos] → fuera de alcance; la ingesta ya marca como fallidos los PDFs sin texto.
- [Límites de Voyage (rate limit, 120K tokens por petición)] → lotes conservadores y reintentos del SDK; un fallo deja el índice previo y el run se reintenta desde Dagster.
- [Dimensión fija en la migración] → cambiar de modelo exige una migración nueva; queda documentado en el ADR.
- [Costo] → ~6.7M tokens para todo CUAD, dentro del free tier; el uso queda registrado por documento.
- [Cliente síncrono de Voyage en `to_thread`] → suficiente para el volumen de la demo; encapsulado en el adaptador.
- [Mover el engine a `CoreContainer`] → cambia el wiring del escritor; los tests de contenedor existentes cubren que no se abra red al construir.

## Migration Plan

1. `uv run alembic upgrade head` (aplica `0003`).
2. Definir `CONTRACT_INTEL_EMBEDDINGS__API_KEY` en `.env`.
3. `uv run dagster dev -m contract_intel_pipelines.definitions`: los documentos nuevos se ingieren y vectorizan; los ya ingeridos se vectorizan materializando `indexed_document` (o backfill de la partición) desde la UI.

Rollback: `alembic downgrade 0002` elimina `chunks` y `usage_records`; con `CONTRACT_INTEL_USE_FAKES=true` se vuelve al índice en memoria.

## Open Questions

- Tamaño y solapamiento óptimos de los fragmentos: se ajustan con la evaluación de recuperación en rag-api, cambiando settings.
