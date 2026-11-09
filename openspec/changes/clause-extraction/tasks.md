# Tasks

> Todos los comandos se ejecutan dentro de WSL. Las pruebas `integration` se corren contra la base de pruebas para no vaciar la de desarrollo: `export TEST_DB=postgresql+asyncpg://contract_intel:contract_intel@localhost:5432/contract_intel_test`, `CONTRACT_INTEL_DATABASE__URL=$TEST_DB uv run alembic upgrade head` y `CONTRACT_INTEL_DATABASE__URL=$TEST_DB uv run pytest -m integration`. Cada grupo deja `uv run ruff check .`, `uv run mypy scripts core/src core/tests core/migrations pipelines/src pipelines/tests rag_api/src rag_api/tests` y `uv run lint-imports` en verde antes de cerrarse.

## 1. Dependencias y settings

- [ ] 1.1 Añadir `langgraph` a `core/pyproject.toml` y a las listas prohibidas de dominio y aplicación en `[tool.importlinter]` (`"langgraph"` ya figura; verificar y añadir `"langchain_core"` si LangGraph lo arrastra); verificar `uv sync --all-packages`, que `from langgraph.graph import StateGraph` y `from langgraph.types import Send` importan, `uv run lint-imports` y `uv run pytest` en verde
- [ ] 1.2 Añadir `ExtractionSettings` y `EvaluationSettings` (D8) a `bootstrap/settings.py`, variables en `.env.example` y tests en `core/tests/bootstrap/test_settings.py`; verificar `uv run pytest core/tests/bootstrap/test_settings.py`

## 2. Dominio

- [ ] 2.1 Añadir `ClauseExtraction`, `ModelRefusedError` (con `AnswerRefusedError` como subclase) y `domain/clause_rules.py` (verificación literal por páginas, consolidación de candidatos del mismo tipo, ids deterministas) con tests en `core/tests/domain/test_clause_rules.py` (literal aceptado con espacios distintos, parafraseado descartado, páginas fuera de rango descartadas, candidatos solapados consolidados con unión de páginas, tipos distintos no se mezclan); verificar `uv run pytest core/tests/domain`
- [ ] 2.2 Cambiar `Chunk.clause_type` por `Chunk.clause_types: frozenset[ClauseType]` y crear `domain/chunk_labels.py` (`label_chunks`, D4) con tests en `core/tests/domain/test_chunk_labels.py` (sin cláusulas, un tipo, varios tipos en un fragmento, cláusula que cruza dos fragmentos, páginas solapadas sin texto común → sin etiqueta); actualizar usos de `clause_type` en fakes y tests existentes; verificar `uv run pytest core/tests` y `uv run mypy core`
- [ ] 2.3 Crear `domain/evaluation.py` (`ExpertLabels`, `TypeMetrics`, `EvaluationReport`, `evaluate`, D7) con tests en `core/tests/domain/test_evaluation.py` (TP/FP/FN, métricas no definidas sin casos, evidencia coincidente sin distinguir mayúsculas ni espacios, documentos excluidos, totales micro-promediados, `OTHER` ignorado); verificar `uv run pytest core/tests/domain`

## 3. Puertos y fakes

- [ ] 3.1 Refinar `ClauseExtractor` (devuelve `ClauseExtraction`), ampliar `DocumentRepository` (`get_document`) y `ContractRepository` (`clauses_of_document`), crear `GroundTruthSource`; actualizar `InMemoryClauseExtractor`, `InMemoryDocumentRepository`, `InMemoryContractRepository`, crear `InMemoryGroundTruthSource`, registrar todo en `test_conformance.py` y ampliar la suite de contrato de `DocumentRepository` con `get_document`; verificar `uv run pytest core/tests/adapters` y `uv run mypy core`

## 4. Use cases

- [ ] 4.1 Implementar `application/use_cases/extract_clauses.py` (D2) con tests sobre fakes: cláusulas guardadas en el contrato del documento, contrato creado si no existe, reextracción reemplaza solo las del documento, uso registrado con costo y `document_id`, documento fallido o inexistente → `DocumentNotAvailableError` sin cambios; verificar `uv run pytest core/tests/application`
- [ ] 4.2 Ampliar `VectorizeDocumentUseCase` para etiquetar fragmentos con `label_chunks` usando `ContractRepository.clauses_of_document`, con tests: fragmentos con varios tipos, documento sin cláusulas → fragmentos sin tipos; verificar `uv run pytest core/tests/application`
- [ ] 4.3 Implementar `application/use_cases/evaluate_clause_extraction.py` (D7) con tests sobre fakes (etiquetas sintéticas, documento sin etiquetas excluido, sin llamadas al extractor); verificar `uv run pytest core/tests/application`

## 5. Adaptadores reales

- [ ] 5.1 Confirmar en `langgraph` instalado la API de `StateGraph`, `Send` y reducers, y en `anthropic` `AsyncAnthropic().messages.parse(output_format=...)`; implementar `adapters/outbound/langgraph/clause_extraction_graph.py` y `langgraph_clause_extractor.py` (D3) extrayendo a un módulo compartido la traducción de errores de Anthropic; suite de contrato de `ClauseExtractor` en `core/tests/adapters/contracts/test_clause_extractor_contract.py` sobre el fake y sobre el adaptador con un cliente falso inyectado (ventanas por páginas completas y `window_chars`, una llamada por ventana, candidatos no literales descartados, consolidación entre ventanas, tokens sumados, modelo informado, rechazo → `ModelRefusedError`, errores → errores de dominio); verificar `uv run pytest core/tests/adapters/contracts -k clause_extractor`
- [ ] 5.2 Crear los modelos y la migración `core/migrations/versions/0004_contracts_clauses_and_chunk_labels.py` (D6); verificar en la base de desarrollo y en `contract_intel_test` `alembic upgrade head`, `alembic check`, `downgrade 0003` y `upgrade head`, y que `\d clauses` y `\d chunk_clause_types` muestran FKs en cascada y que `chunks` ya no tiene `clause_type`
- [ ] 5.3 Implementar `SqlAlchemyContractRepository` y su suite de contrato fake vs Postgres (`integration`): guardar y leer contrato con documentos y cláusulas, reemplazo de cláusulas por documento, `clauses_of_document`, aislamiento entre contratos; verificar `uv run pytest core/tests/adapters/contracts -k contract_repository` y la variante `integration`
- [ ] 5.4 Actualizar `PgVectorIndexWriter` (etiquetas en `chunk_clause_types` en la misma transacción) y `PgVectorSearch` (filtro `EXISTS` y reconstrucción de `clause_types`), y ampliar sus suites de contrato con fragmentos de varios tipos (filtro por cualquiera de los tipos, etiquetas reemplazadas al revectorizar); verificar las suites `vector_index_writer` y `vector_search` en ambos modos
- [ ] 5.5 Implementar `adapters/outbound/cuad/cuad_ground_truth.py` (`CuadGroundTruth`) con suite de contrato fake vs adaptador sobre un CSV de fixture (columnas mapeadas por tipo, listas vacías, celdas con comillas y saltos de línea); verificar además contra el `master_clauses.csv` real que se obtienen 510 contratos y las etiquetas de ley aplicable de Ability y 2TheMart; verificar `uv run pytest core/tests/adapters/contracts -k ground_truth`
- [ ] 5.6 Añadir un smoke test real `anthropic` del extractor: un documento fijo de dos páginas con una cláusula de ley aplicable devuelve esa cláusula tipada con su página y tokens > 0; verificar `uv run pytest -m anthropic`

## 6. Composition root

- [ ] 6.1 Actualizar `bootstrap/core.py` (rama real de `contract_repository`) y `bootstrap/writer.py` (rama real de `clause_extractor`, `ground_truth_source`, `Factory` de `extract_clauses` y `evaluate_clause_extraction`, `vectorize_document` con `ContractRepository`); actualizar `core/tests/bootstrap/test_containers.py`: adaptadores reales resuelven sin red, ya no quedan puertos sin rama real, y de punta a punta con fakes ingestar → extraer → vectorizar deja fragmentos etiquetados; verificar `uv run pytest core/tests/bootstrap` y `uv run lint-imports`

## 7. Dagster y CLI

- [ ] 7.1 Añadir el asset `extracted_clauses` y reordenar el job (D5); tests en `pipelines/tests/`: el job materializa ingest → extract → index en ese orden, `indexed_document` depende de `extracted_clauses`, extracción fallida omite la vectorización, metadata con `clause_count`; verificar `uv run pytest pipelines/tests` y `uv run dagster definitions validate -m contract_intel_pipelines.definitions`
- [ ] 7.2 Añadir el asset no particionado `extraction_evaluation` (metadata con la tabla Markdown) y `scripts/evaluate_extraction.py`, con tests (asset con contenedor de fakes y etiquetas sintéticas; el script imprime la tabla); verificar `uv run pytest pipelines/tests scripts/tests`

## 8. Documentación

- [ ] 8.1 Escribir el ADR `0009-clause-extraction-map-reduce-with-langgraph` (MADR corto, inglés); actualizar `docs/architecture/hexagonal.md` (puertos y adaptadores nuevos, flujo de extracción, todos los puertos con adaptador real) y el `README.md` (estado, flujo ingest → extract → index, cómo extraer y revectorizar, cómo correr la evaluación con un reporte de ejemplo real, filtro `clause_types` de `/ask` con ejemplo, costo de la extracción); verificar que el ADR tiene Status, Context, Decision y Consequences y que los comandos nuevos del README funcionan tal como están escritos

## 9. Verificación integral

- [ ] 9.1 Extracción real de punta a punta con Claude sobre los 3 contratos indexados: aplicar `0004`, materializar `extracted_clauses` + `indexed_document` de cada partición (respetando el límite de Voyage), y comprobar que cada contrato tiene cláusulas con texto literal y páginas, que Ability tiene ley aplicable (Israel, p. 8) y terminación por conveniencia, que `chunk_clause_types` etiqueta los fragmentos correspondientes, que `/ask` con `"clause_types": ["governing_law"]` responde citando solo fragmentos de ley aplicable, que `usage_records` tiene registros `extract_clauses` por documento, y ejecutar la evaluación contra CUAD guardando el reporte real para el README
- [ ] 9.2 Desde un clon limpio (último commit más los cambios del working tree): `uv sync --frozen --all-packages && uv run ruff format --check . && uv run ruff check . && uv run mypy scripts core/src core/tests core/migrations pipelines/src pipelines/tests rag_api/src rag_api/tests && uv run lint-imports && uv run python scripts/check_forbidden_identifiers.py && uv run pytest` y `CONTRACT_INTEL_DATABASE__URL=$TEST_DB uv run pytest -m integration` todo en verde
- [ ] 9.3 Ejecutar `openspec validate clause-extraction --strict` sin errores

## Workflow follow-up

- Revisar el cambio y archivarlo con `/opsx:archive` (crea `openspec/specs/clause-extraction` y `openspec/specs/extraction-evaluation`, y actualiza `openspec/specs/document-vectorization`).
- Posibles siguientes cambios: ampliar la taxonomía de cláusulas, endpoint de cláusulas en la API, streaming de respuestas, evaluación de la recuperación del RAG.
