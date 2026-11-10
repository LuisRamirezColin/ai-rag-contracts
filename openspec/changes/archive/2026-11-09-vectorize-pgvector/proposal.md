# Proposal

## Why

Los contratos ya se ingieren con su texto por página, pero nada se puede buscar todavía: el índice vectorial solo existe como fake en memoria. Este cambio convierte cada documento ingerido en fragmentos con su ubicación (páginas), los vectoriza con un modelo de embeddings especializado en texto legal y los escribe en pgvector, de modo que la API de preguntas (`rag-api`) tenga un índice real que leer.

## What Changes

- **Use case `VectorizeDocumentUseCase`** (implementa el puerto inbound `VectorizeDocument` existente): lee las páginas ingeridas, las divide en fragmentos que conservan su rango de páginas, calcula sus embeddings, reemplaza los fragmentos del documento en el índice y registra el uso de tokens.
- **Dominio**:
  - Servicio puro de fragmentación (`chunk_pages`) con tamaño y solapamiento configurables, que respeta los límites de página para citar con precisión.
  - `EmbeddingBatch` (embeddings + tokens consumidos + modelo) y `document_id` opcional en `UsageRecord`.
- **Puertos refinados** (**BREAKING** solo interno, sin consumidores reales):
  - `Embedder`: `embed(texts)` se reemplaza por `embed_documents(texts) -> EmbeddingBatch` y `embed_query(text) -> Embedding`, porque los modelos de embeddings de recuperación codifican distinto documentos y consultas.
  - `VectorIndexWriter`: `upsert` + `delete_document` pasan a `replace_document(document_id, chunks)` atómico (más `delete_document`), para que la API nunca lea un documento a medio indexar.
- **Adaptadores reales**:
  - `VoyageEmbedder` (SDK `voyageai`, modelo `voyage-law-2`, 1024 dimensiones), con lotes dentro de los límites de la API.
  - `PgVectorIndexWriter` sobre la tabla `chunks` (migración `0003`, columna `vector(1024)` e índice HNSW por coseno).
  - `SqlAlchemyUsageTracker` sobre la tabla `usage_records` (misma migración); se reutilizará para el costo de Claude en los cambios siguientes.
- **Composition root**: rama real de `embedder` (en `CoreContainer`, la usarán escritor y lector), `vector_index_writer` y `usage_tracker`; `Factory` del use case en `WriterContainer`.
- **Dagster**: asset particionado `indexed_document` que depende de `ingested_document`; el job de ingesta materializa ambos, así cada documento nuevo queda buscable sin intervención.
- **Settings**: sección `embeddings` (`api_key`, `model`, `dimensions`, `price_per_million_tokens`) y `chunking` (`max_chars`, `overlap_chars`); se elimina `llm.embedding_model`.

**Capas hexagonales afectadas**: domain (fragmentación, lote de embeddings, uso por documento), application (puertos refinados, use case), adapters (Voyage, pgvector, uso en Postgres, migración), inbound adapters (`pipelines/`: asset y job), bootstrap (ramas reales y settings).

## Capabilities

### New Capabilities
- `document-vectorization`: convertir cada documento ingerido en fragmentos buscables con su rango de páginas y su vector, mantener el índice consistente por documento, hacerlo automáticamente tras la ingesta y registrar el consumo de tokens.

### Modified Capabilities
<!-- Ninguna: document-ingestion y architecture-conformance no cambian sus requisitos. -->

## Impact

- **Código**: `core/src/contract_intel/{domain,application,adapters,bootstrap}`, `core/migrations/versions/0003_*`, `pipelines/src/contract_intel_pipelines/`, `.env.example`, `.github/workflows/ci.yml`, `docs/architecture/`, README.
- **Dependencias**: runtime `voyageai` en `core`.
- **Sistemas**: API de Voyage AI (requiere `CONTRACT_INTEL_EMBEDDINGS__API_KEY`); Postgres gana las tablas `chunks` y `usage_records`. Los tests unitarios y de contrato no llaman a Voyage; un test de humo opcional sí, solo con la key presente.
- **Costo**: ~46K tokens para los 5 contratos de la demo y ~6.7M para los 510, dentro de los 50M tokens gratuitos de `voyage-law-2` (precio de lista $0.12 por millón).
