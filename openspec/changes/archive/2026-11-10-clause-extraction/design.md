# Design

## Context

Estado actual (cambios archivados hasta `2026-11-09-rag-api`):
- Dominio: `Clause(id, document_id, clause_type, text, pages)`, `ClauseType` (10 categorías CUAD + `OTHER`), `Contract(id, title, document_ids, clauses)` con `clauses_of_type`, `Chunk.clause_type: ClauseType | None`, `UsageRecord`, `TokenPricing`.
- Puertos con solo fakes: `ClauseExtractor.extract(document, pages) -> tuple[Clause, ...]`, `ContractRepository.get/save`; inbound `ExtractClauses.execute(document_id) -> tuple[Clause, ...]` sin use case.
- `DocumentRepository` guarda `documents` (incluidos `title`, `contract_id`, `document_type`) pero no expone `get_document`.
- `chunks.clause_type` existe y siempre es `NULL`; `PgVectorSearch` filtra por esa columna. `/ask` ya acepta `clause_types`.
- Dagster: job por documento `ingested_document` → `indexed_document`; la vectorización usa `chunk_pages` y reemplaza los fragmentos de forma atómica.
- Claude ya se usa en el lector (`AnthropicAnswerGenerator`, settings `llm`); `usage_records` registra costo por operación.
- CUAD `master_clauses.csv`: columna `Filename` igual al nombre del PDF (nuestro `Document.title` es su stem) y, por tipo de cláusula, una lista de extractos literales de abogados (`[]` si no hay).

Motivación en `proposal.md`; requisitos en `specs/clause-extraction`, `specs/extraction-evaluation` y el delta de `specs/document-vectorization`.

## Goals / Non-Goals

**Goals:**
- Cláusulas tipadas, literales y localizadas por página, verificadas contra el texto del documento.
- Fragmentos del índice con todos los tipos de cláusula que contienen, para filtrar `/ask`.
- Calidad medida contra CUAD con un reporte reproducible sin volver a llamar al modelo.

**Non-Goals:**
- Ampliar la taxonomía más allá de las 10 categorías actuales (CUAD tiene 41); se puede extender sin cambiar la arquitectura.
- Extraer valores normalizados (fechas, montos, jurisdicción como campo) o resúmenes de cláusulas.
- Contratos multi-documento (enmiendas): en CUAD un PDF es un contrato.
- Endpoint HTTP para listar cláusulas: se puede añadir al lector después.

## Decisions

### D1 — Puertos refinados y nuevos
```python
@dataclass(frozen=True, slots=True)
class ClauseExtraction:          # domain
    clauses: tuple[Clause, ...]
    model: str
    input_tokens: int
    output_tokens: int

class ClauseExtractor(Protocol):
    async def extract(self, document: Document, pages: Sequence[Page]) -> ClauseExtraction

class DocumentRepository(Protocol):          # + get_document
    async def get_document(self, document_id: DocumentId) -> Document   # DocumentNotAvailableError

class ContractRepository(Protocol):          # + clauses_of_document, replace_document_clauses
    async def get(self, contract_id) -> Contract | None
    async def save(self, contract) -> None
    async def clauses_of_document(self, document_id) -> tuple[Clause, ...]
```
- `ClauseExtraction` sigue el patrón de `EmbeddingBatch`/`GeneratedAnswer`: el adaptador informa lo consumido y el use case registra el costo.
- **SOLID**: SRP/DIP — el extractor no conoce precios ni persistencia; ISP — `clauses_of_document` es la única lectura que necesita la vectorización.

### D2 — `ExtractClausesUseCase`
1. `record = documents.get_record(id)`; si no está ingerido → `DocumentNotAvailableError` (sin tocar cláusulas).
2. `document = documents.get_document(id)`, `pages = documents.get_pages(id)`.
3. `extraction = extractor.extract(document, pages)`.
4. `contract = contracts.get(document.contract_id) or Contract(id=document.contract_id, title=document.title, document_ids=(id,))`; reemplaza las cláusulas de ese documento por las nuevas (las de otros documentos del contrato se conservan) → `contracts.save(contract)`.
5. `usage_tracker.record(UsageRecord("extract_clauses", model, in, out, cost, document_id=id))`.
6. Devuelve las cláusulas.
- `ClauseId` determinista `"{document_id}:{clause_type}:{ordinal:03d}"`, asignado por el extractor.

### D3 — `LangGraphClauseExtractor` (map-reduce con Claude)
Grafo `StateGraph` de LangGraph en `adapters/outbound/langgraph/`:

```
plan_windows ──Send(window)──▶ extract_window (en paralelo) ──▶ consolidate ──▶ END
```
- **plan_windows**: agrupa páginas consecutivas en ventanas de hasta `window_chars` (default 24,000 caracteres, ~6–8K tokens), sin partir páginas.
- **extract_window**: una llamada `AsyncAnthropic().messages.parse(..., output_format=WindowClauses)` por ventana (salida estructurada validada con Pydantic, solo en el adaptador). `WindowClauses = list[{clause_type: ClauseTypeLiteral, text: str, first_page: int, last_page: int}]`. El prompt incluye cada página con su número (`<page number="8">…</page>`), la definición breve de cada tipo (inspirada en las definiciones de CUAD) y exige texto literal y páginas reales. `effort` y modelo desde settings (`claude-sonnet-5-5` por defecto). El estado acumula candidatos y tokens con reducers (`operator.add`).
- **consolidate** (determinista, sin LLM): normaliza espacios; descarta candidatos cuyo texto normalizado no aparece en el texto normalizado de las páginas `first..last` (spec "texto literal") o con páginas fuera de la ventana; consolida candidatos del mismo tipo cuyo texto se solapa (uno contiene al otro o comparten ≥ 80 caracteres consecutivos), quedándose con el más largo y la unión de páginas; asigna ids.
- Las reglas de verificación y consolidación son funciones puras de dominio (`domain/clause_rules.py`) para poder probarlas sin LLM.
- Errores de Anthropic → `ProviderRateLimitedError`/`ProviderUnavailableError` (misma traducción que el generador de respuestas, extraída a un helper compartido del adaptador); un rechazo → `AnswerRefusedError` se renombra conceptualmente como rechazo del modelo: se introduce `ModelRefusedError` en dominio y `AnswerRefusedError` pasa a ser su subclase para no romper `/ask`.
- **Alternativa**: una sola llamada con el documento completo. Se descarta como diseño base: contratos largos (Accuray, ~29K tokens) degradan la atención y el map-reduce paraleliza; con documentos cortos el grafo hace una sola ventana igualmente.
- **Alternativa**: reduce con un segundo LLM. Se descarta: el reduce determinista es más barato, reproducible y testeable.
- **SOLID**: OCP — otra estrategia de extracción es otro adaptador del mismo puerto; SRP — grafo (orquestación), cliente Claude (llamada) y reglas (dominio) separados.

### D4 — Varios tipos por fragmento
- Dominio: `Chunk.clause_type` → `Chunk.clause_types: frozenset[ClauseType]` (default vacío).
- Regla pura `domain/chunk_labels.py`: `label_chunks(chunks, clauses) -> tuple[Chunk, ...]`: un fragmento recibe el tipo T si existe una cláusula de tipo T con rango de páginas solapado y texto solapado (el texto normalizado del fragmento contiene un trozo de ≥ 60 caracteres de la cláusula, o la cláusula entera si es más corta, o viceversa).
- `VectorizeDocumentUseCase` gana `ContractRepository` (solo `clauses_of_document`) y etiqueta los fragmentos tras `chunk_pages` y antes de embeber.
- Persistencia: tabla `chunk_clause_types(chunk_id FK → chunks.id ON DELETE CASCADE, clause_type)` con PK compuesta; `PgVectorIndexWriter.replace_document` inserta etiquetas en la misma transacción; `PgVectorSearch` filtra con `EXISTS (SELECT 1 FROM chunk_clause_types WHERE chunk_id = chunks.id AND clause_type IN (...))` y reconstruye `clause_types` con un `array_agg` agrupado. El fake filtra por intersección de conjuntos.
- **Alternativa**: un tipo por fragmento en `chunks.clause_type`. Descartada por el usuario: un fragmento de 2,000 caracteres suele mezclar cláusulas.

### D5 — Orden del job en Dagster
- Nuevo asset particionado `extracted_clauses` con `deps=[ingested_document]`; publica `clause_count` y conteo por tipo como metadata.
- `indexed_document` pasa a `deps=[ingested_document, extracted_clauses]`; `ingest_documents_job` selecciona los tres. Si la extracción falla, Dagster omite la vectorización (spec modificada).
- Para reetiquetar fragmentos tras una reextracción: materializar `extracted_clauses` + `indexed_document` de la partición.

### D6 — Persistencia de contratos (migración `0004`)

| Tabla | Columnas |
|---|---|
| `contracts` | `id` text PK, `title` text |
| `contract_documents` | `contract_id` FK → contracts (cascade), `document_id` FK → documents (cascade); PK compuesta |
| `clauses` | `id` text PK, `contract_id` FK → contracts (cascade), `document_id` FK → documents (cascade), `clause_type` text, `text` text, `first_page` int, `last_page` int (checks de rango) ; índice por `document_id` |
| `chunk_clause_types` | `chunk_id` FK → chunks (cascade), `clause_type` text; PK compuesta; índice por `clause_type` |

- Se elimina `chunks.clause_type`.
- `SqlAlchemyContractRepository.save` hace upsert del contrato, de sus documentos y reemplaza sus cláusulas en una transacción.

### D7 — Evaluación contra CUAD
- Dominio `domain/evaluation.py`: `ExpertLabels(document_title, excerpts_by_type: Mapping[ClauseType, tuple[str, ...]])`, `TypeMetrics(clause_type, tp, fp, fn, precision | None, recall | None, f1 | None, evidence_match_rate | None)`, `EvaluationReport(types, totals, evaluated_documents, excluded_documents)` y la función pura `evaluate(predictions_by_title, labels_by_title) -> EvaluationReport`. Coincidencia de evidencia: texto normalizado (minúsculas, espacios colapsados) contenido uno en otro.
- Puerto `GroundTruthSource.labels() -> Mapping[str, ExpertLabels]` (clave: título = stem del PDF). Adaptador `CuadGroundTruth` lee `master_clauses.csv` (columna por `ClauseType`: `Governing Law`, `Termination For Convenience`, `Cap On Liability`, `Renewal Term`, `Exclusivity`, `Most Favored Nation`, `Non-Compete`, `Ip Ownership Assignment`, `Price Restrictions`, `Volume Restriction`; celdas como listas literales de Python parseadas con `ast.literal_eval`).
- Use case `EvaluateClauseExtractionUseCase`: lista los documentos ingeridos con cláusulas (`ContractRepository` + `DocumentRepository`), cruza con las etiquetas por título y evalúa. `OTHER` no se evalúa.
- Inbound: asset de Dagster no particionado `extraction_evaluation` (metadata con la tabla Markdown) y `scripts/evaluate_extraction.py` que imprime el reporte; ambos llaman al mismo use case vía el contenedor escritor.

### D8 — Settings
`ExtractionSettings`: `model="claude-sonnet-5-5"`, `effort="medium"`, `max_tokens=16000`, `window_chars=24000`, `input_price_per_million=2.0`, `output_price_per_million=10.0`; reusa `llm.api_key`. `EvaluationSettings`: `labels_path="data/cuad/CUAD_v1/master_clauses.csv"`, que lee `CuadGroundTruth`.

### D9 — Estrategia de pruebas
- **Dominio**: verificación literal y consolidación de candidatos; `label_chunks` (sin cláusulas, una, varias, solapamiento de páginas sin texto); métricas (TP/FP/FN, no definidas, evidencia).
- **Use cases con fakes**: extracción (guardado, reemplazo por documento, costo, documento no disponible); vectorización etiqueta fragmentos con varios tipos; evaluación con etiquetas sintéticas.
- **Contract tests**: `ClauseExtractor` fake vs `LangGraphClauseExtractor` con cliente falso inyectado (ventanas, paralelismo, descarte de no literales, consolidación entre ventanas, tokens sumados, errores traducidos); `ContractRepository` fake vs Postgres (`integration`, base `contract_intel_test`); `VectorIndexWriter`/`VectorSearch` ampliados con varios tipos; `GroundTruthSource` sobre un CSV de fixture.
- **Dagster**: orden ingest → extract → index; extracción fallida omite la vectorización.
- **Smoke real** `anthropic`: extraer de un fragmento fijo con ley aplicable.
- Las pruebas de integración usan la base `contract_intel_test` (documentado en el README) para no vaciar la base de desarrollo.

### D10 — ADR
`docs/architecture/adr/0009-clause-extraction-map-reduce-with-langgraph.md`.

## Risks / Trade-offs

- [Claude devuelve texto parafraseado] → verificación literal en dominio descarta el candidato; se mide su efecto en la evaluación (recall).
- [Ventanas cortan una cláusula entre páginas] → ventanas por páginas completas y consolidación entre ventanas; una cláusula partida en el límite puede salir en dos trozos consolidados por solapamiento.
- [Pocos documentos para métricas estables] → con 3 contratos el reporte es ilustrativo; el mismo pipeline escala a más documentos (límites de Voyage documentados).
- [Costo de Claude en el escritor] → ~$0.03–0.06 por contrato con Sonnet, registrado por documento.
- [Cambio de `Chunk.clause_type` a conjunto] → toca dominio, fakes, writer, search y migración; cubierto por las suites de contrato existentes ampliadas.
- [Acoplar la vectorización a la extracción] → un fallo de Claude deja el documento sin indexar hasta reintentar; preferido para que los fragmentos nazcan etiquetados (spec).

## Migration Plan

1. `uv sync` (añade `langgraph`); `uv run alembic upgrade head` (aplica `0004`).
2. En Dagster, materializar `extracted_clauses` + `indexed_document` de las particiones existentes (o todo el job) para extraer y reetiquetar.
3. `uv run python scripts/evaluate_extraction.py` o materializar `extraction_evaluation`.

Rollback: `alembic downgrade 0003` (recrea `chunks.clause_type` vacía y elimina las tablas nuevas); revertir el código.

## Open Questions

- Ampliación de la taxonomía a más categorías de CUAD: decisión de producto que no cambia la arquitectura.
