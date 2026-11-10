# Proposal

## Why

El sistema ya responde preguntas citando páginas, pero todavía no entiende la estructura de un contrato: no sabe qué fragmento es una cláusula de ley aplicable, de terminación o de límite de responsabilidad. Extraer cláusulas tipadas permite consultar contratos por tipo de cláusula, hace útil el filtro `clause_types` que `/ask` ya acepta, y —comparado con las etiquetas de abogados de CUAD— convierte la calidad del sistema en una métrica medible en vez de una impresión.

## What Changes

- **Use case `ExtractClausesUseCase`** (implementa el puerto inbound `ExtractClauses` existente): lee el documento ingerido y sus páginas, obtiene las cláusulas tipadas del extractor, las guarda en el contrato al que pertenece el documento (reemplazando las anteriores de ese documento) y registra tokens y costo.
- **Extractor real `LangGraphClauseExtractor`**: grafo map-reduce de LangGraph con Claude (`claude-sonnet-5-5` por defecto, configurable): divide el documento en ventanas de páginas, extrae candidatos por ventana en paralelo con salida estructurada (tipo, texto literal, páginas) y los consolida de forma determinista; descarta candidatos cuyo texto no aparece literalmente en las páginas indicadas.
- **Puertos refinados** (**BREAKING** solo interno):
  - `ClauseExtractor.extract` devuelve `ClauseExtraction` (cláusulas + modelo + tokens), igual que `EmbeddingBatch` y `GeneratedAnswer`.
  - `DocumentRepository.get_document(document_id)`; `ContractRepository.clauses_of_document(document_id)`.
- **Varios tipos de cláusula por fragmento**: `Chunk.clause_type` pasa a `Chunk.clause_types: frozenset[ClauseType]` (**BREAKING** interno). Al vectorizar, cada fragmento se etiqueta con los tipos de las cláusulas extraídas que contiene (regla de dominio por solapamiento de páginas y texto). La búsqueda filtra fragmentos que tengan alguno de los tipos pedidos.
- **Orden del lado escritor**: el job por documento pasa a ingesta → extracción de cláusulas → vectorización, para que los fragmentos nazcan etiquetados.
- **Persistencia** (migración `0004`): tablas `contracts`, `clauses` y `chunk_clause_types`; se elimina la columna `chunks.clause_type` (siempre `NULL` hasta hoy).
- **Evaluación contra CUAD**: use case `EvaluateClauseExtraction` con un puerto `GroundTruthSource` (adaptador que lee `master_clauses.csv`), métricas de dominio por tipo de cláusula (precisión, recall, F1 a nivel de presencia por contrato, y solapamiento del texto extraído con los extractos de los abogados); se ejecuta como asset de Dagster y por línea de comandos, y el reporte queda en Markdown.
- **Settings**: sección `extraction` (`model`, `effort`, `max_tokens`, `window_chars`, precios).

**Capas hexagonales afectadas**: domain (extracción, etiquetado de fragmentos, métricas de evaluación, `Chunk.clause_types`), application (puertos refinados y nuevos, dos use cases), adapters (LangGraph+Claude, repositorio de contratos en Postgres, ground truth CUAD, migración), inbound adapters (`pipelines/`: asset de extracción y de evaluación, orden del job), bootstrap (escritor y settings).

## Capabilities

### New Capabilities
- `clause-extraction`: identificar y clasificar las cláusulas de cada documento ingerido según la taxonomía soportada, con texto literal y páginas, persistirlas por contrato, ejecutarlo automáticamente y registrar su costo.
- `extraction-evaluation`: medir la calidad de la extracción contra las etiquetas de expertos del dataset, por tipo de cláusula, de forma reproducible.

### Modified Capabilities
- `document-vectorization`: los fragmentos indexados se etiquetan con los tipos de cláusula que contienen, y la vectorización automática pasa a ejecutarse después de la extracción de cláusulas.

## Impact

- **Código**: `core/src/contract_intel/{domain,application,adapters,bootstrap}`, `core/migrations/versions/0004_*`, `pipelines/src/contract_intel_pipelines/`, `scripts/` (CLI de evaluación), `.env.example`, `docs/architecture/`, README.
- **Dependencias**: runtime `langgraph` en `core` (prohibido en dominio y aplicación por import-linter).
- **Sistemas**: Claude se usa también en el lado escritor (una pasada por ventana de páginas). Postgres gana `contracts`, `clauses` y `chunk_clause_types`.
- **Costo**: ~$0.03–0.06 por contrato con Sonnet 5.5 (texto completo como entrada más la salida estructurada), registrado en `usage_records`; para los 3 contratos indexados, menos de $0.20.
- **Compatibilidad**: los fragmentos existentes se revectorizan para recibir etiquetas (rematerializar en Dagster).
