# Tasks

> Todos los comandos se ejecutan dentro de WSL. Las pruebas `integration` requieren `docker compose up -d --wait` y `uv run alembic upgrade head`. Cada grupo deja `uv run ruff check .`, `uv run mypy scripts core/src core/tests core/migrations pipelines/src pipelines/tests rag_api/src rag_api/tests` y `uv run lint-imports` en verde antes de cerrarse.

## 1. Dependencias y settings

- [x] 1.1 Añadir `voyageai` a `core/pyproject.toml` (y su override de mypy si no trae tipos), registrar el marcador `voyage` en `[tool.pytest.ini_options]` excluido por defecto junto a `integration`, y añadir `"voyageai"` a las listas prohibidas de dominio y aplicación en `[tool.importlinter]`; verificar `uv sync --all-packages`, `uv run lint-imports` y que `uv run pytest` sigue en verde
- [x] 1.2 Añadir `EmbeddingsSettings` y `ChunkingSettings` (D9) a `bootstrap/settings.py`, eliminar `llm.embedding_model`, actualizar `.env.example` y ampliar `core/tests/bootstrap/test_settings.py` (defaults, carga desde entorno, `api_key` secreta, `overlap_chars < max_chars`); verificar `uv run pytest core/tests/bootstrap/test_settings.py`

## 2. Dominio

- [x] 2.1 Crear `domain/chunking.py` con `chunk_pages` (D1) y tests en `core/tests/domain/test_chunking.py`: documento corto → un fragmento con rango correcto; documento largo → ningún fragmento supera `max_chars`, solapamiento entre consecutivos y cobertura total del texto; fragmento que cruza página → rango con ambas; páginas en blanco → sin fragmentos vacíos; ids deterministas; parámetros inválidos → error; verificar `uv run pytest core/tests/domain`
- [x] 2.2 Añadir `EmbeddingBatch` (dimensiones homogéneas) y `EmbeddingDimensionMismatchError`, y `document_id` opcional a `UsageRecord`; tests de invariantes en `core/tests/domain/`; verificar `uv run pytest core/tests/domain` y `uv run mypy core`

## 3. Puertos y fakes

- [x] 3.1 Refinar `Embedder` (`embed_documents`, `embed_query`, D2) y `VectorIndexWriter` (`replace_document`, `delete_document`, D3); actualizar `InMemoryEmbedder` (dimensión configurable, tokens estimados, documento vs consulta distinguibles) e `InMemoryVectorIndexWriter` (reemplazo, rechazo de chunks ajenos) y sus tests en `core/tests/adapters/in_memory/`; verificar `uv run pytest core/tests/adapters/in_memory`, `uv run mypy core` y que `grep -rn "\.upsert(\|\.embed(" core pipelines rag_api --include='*.py'` no devuelve usos del API anterior

## 4. Use case

- [x] 4.1 Implementar `application/use_cases/vectorize_document.py` (D4) con tests unitarios sobre fakes en `core/tests/application/test_vectorize_document.py`: fragmentos indexados y número devuelto; uso registrado con modelo, tokens, costo y `document_id`; documento fallido o inexistente → `DocumentNotAvailableError` sin tocar el índice; fallo del embedder → índice previo intacto; revectorización → solo los fragmentos nuevos; otros documentos intactos; verificar `uv run pytest core/tests/application`

## 5. Adaptador de embeddings (Voyage)

- [x] 5.1 Confirmar en el SDK instalado la firma de `voyageai.Client.embed`, sus reintentos y si existe un cliente asíncrono; implementar `adapters/outbound/voyage/voyage_embedder.py` (D5: lotes ≤128 textos y ≤300K caracteres, `input_type`, `truncation=False`, suma de `total_tokens`, validación de dimensión) y la suite de contrato de `Embedder` en `core/tests/adapters/contracts/test_embedder_contract.py` sobre el fake y sobre `VoyageEmbedder` con un cliente falso inyectado (orden preservado, lotes partidos, tokens sumados, `input_type` correcto, dimensión incorrecta → error); verificar `uv run pytest core/tests/adapters/contracts -k embedder`
- [x] 5.2 Añadir un smoke test real marcado `voyage` (se omite sin `CONTRACT_INTEL_EMBEDDINGS__API_KEY`) que codifica un documento y una consulta y comprueba 1024 dimensiones y tokens > 0; verificar con la key del usuario `uv run pytest -m voyage` y sin key que se reporta como omitido

## 6. Persistencia (pgvector y uso)

- [x] 6.1 Crear los modelos `ChunkRow` y `UsageRecordRow` y la migración `core/migrations/versions/0003_chunks_and_usage_records.py` (D6, con índice HNSW `vector_cosine_ops`); verificar `uv run alembic upgrade head`, `uv run alembic check`, `downgrade 0002` y de nuevo `upgrade head`, y que `\d chunks` muestra `vector(1024)`, la FK en cascada y el índice HNSW
- [x] 6.2 Implementar `adapters/outbound/persistence/vector_index_writer.py` (`PgVectorIndexWriter`) y la suite de contrato de `VectorIndexWriter` sobre el fake y Postgres (`integration`): reemplazo exacto, aislamiento entre documentos, rechazo de chunks de otro documento, dimensión incorrecta rechazada, y fallo a mitad de la inserción → estado previo intacto; verificar `uv run pytest core/tests/adapters/contracts -k vector_index_writer` y `uv run pytest -m integration -k vector_index_writer`
- [x] 6.3 Implementar `adapters/outbound/persistence/usage_tracker.py` (`SqlAlchemyUsageTracker`) y la suite de contrato de `UsageTracker` sobre el fake y Postgres (`integration`), con lectura de registros por documento para la verificación; verificar `uv run pytest core/tests/adapters/contracts -k usage_tracker` y `uv run pytest -m integration -k usage_tracker`

## 7. Composition root

- [x] 7.1 Actualizar `bootstrap/containers.py` (D7): engine y `session_factory` en `CoreContainer` con pool configurable (`NullPool` en el escritor), ramas reales de `embedder`, `usage_tracker` y `vector_index_writer`, y `Factory` `vectorize_document` solo en `WriterContainer`; actualizar `core/tests/bootstrap/test_containers.py`: adaptadores reales nuevos resuelven sin red, puertos aún sin real siguen fallando al resolverse, `ReaderContainer` no expone `vectorize_document` ni `vector_index_writer`, e ingesta + vectorización de punta a punta con fakes y socket bloqueado dejan fragmentos en el índice en memoria; verificar `uv run pytest core/tests/bootstrap` y `uv run lint-imports`

## 8. Dagster

- [x] 8.1 Añadir el asset `indexed_document` (D8) e incluirlo en `ingest_documents_job`; tests en `pipelines/tests/` con contenedor de fakes: el job materializa ambos assets y publica `chunk_count`; si la ingesta falla, `indexed_document` no se ejecuta; materializar solo `indexed_document` revectoriza; verificar `uv run pytest pipelines/tests` y `uv run dagster definitions validate -m contract_intel_pipelines.definitions`

## 9. CI y documentación

- [x] 9.1 Confirmar que el job `integration` de `.github/workflows/ci.yml` cubre las suites nuevas sin cambios (o ajustarlo) y que el marcador `voyage` queda fuera de CI; verificar con `uvx --from actionlint-py actionlint .github/workflows/ci.yml` y reproduciendo en local `uv run pytest -m integration`
- [x] 9.2 Escribir el ADR `0007-embeddings-with-voyage-and-pgvector` (MADR corto, inglés); actualizar `docs/architecture/hexagonal.md` (tabla de puertos: `Embedder` → `VoyageEmbedder` ✓, `VectorIndexWriter` → `PgVectorIndexWriter` ✓, `UsageTracker` → `SqlAlchemyUsageTracker` ✓, `VectorizeDocument` ✓; flujo de vectorización) y el `README.md` (estado, key de Voyage en el quickstart, tabla de configuración, cómo revisar `chunks` y `usage_records`, nota de costo); verificar que el ADR tiene Status, Context, Decision y Consequences y que los comandos nuevos del README funcionan tal como están escritos

## 10. Verificación integral

- [x] 10.1 Vectorización real de punta a punta con la key de Voyage del usuario: con Docker, `alembic upgrade head`, `.env` en modo real y `MAX_DOCUMENTS=5`, arrancar Dagster y comprobar que los 5 documentos quedan ingeridos y vectorizados, que `SELECT document_id, count(*), min(first_page), max(last_page) FROM chunks GROUP BY document_id` muestra fragmentos para cada uno con rangos de página válidos, que `vector_dims(embedding)` es 1024, que `usage_records` tiene un registro por documento con tokens > 0, y que una consulta de similitud por SQL (`ORDER BY embedding <=> :query`) con una pregunta codificada con `embed_query` devuelve fragmentos pertinentes de los contratos
  - Resultado (2026-11-09, alcance reducido de común acuerdo por la capa gratuita de Voyage, 3 RPM / 10K TPM sin método de pago): los 5 documentos quedaron ingeridos; 3 vectorizados (2TheMart 18 chunks p.1-9, Ability 16 p.1-11, Accelerated 9 p.1-3), vectores de 1024 dimensiones, rangos válidos, 3 registros de uso (23,261 tokens). Accuray (~29K tokens) y Adams Golf (~12K) superan el límite por minuto en una sola petición y fallaron con `RateLimitError` sin tocar el índice. La búsqueda por similitud con `embed_query` devolvió la cláusula de ley aplicable (Ability, p.8) y las de terminación/renovación. Limitación y mejoras documentadas en el README ("Running on free tiers").
- [x] 10.2 Desde un clon limpio (último commit más los cambios del working tree): `uv sync --frozen --all-packages && uv run ruff format --check . && uv run ruff check . && uv run mypy scripts core/src core/tests core/migrations pipelines/src pipelines/tests rag_api/src rag_api/tests && uv run lint-imports && uv run python scripts/check_forbidden_identifiers.py && uv run pytest && uv run pytest -m integration` todo en verde
- [x] 10.3 Ejecutar `openspec validate vectorize-pgvector --strict` sin errores

## Workflow follow-up

- Revisar el cambio y archivarlo con `/opsx:archive` (crea `openspec/specs/document-vectorization/spec.md`).
- Siguiente cambio: `/opsx:propose rag-api` (búsqueda en pgvector + respuestas con Claude y citas).
