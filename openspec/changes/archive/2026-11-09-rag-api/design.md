# Design

## Context

Estado actual (cambios archivados hasta `2026-11-09-vectorize-pgvector`):
- Índice en Postgres: tabla `chunks` (`vector(1024)`, índice HNSW `vector_cosine_ops`, `clause_type` hoy siempre `NULL`) alimentada por Dagster.
- `Embedder.embed_query(text) -> Embedding` ya existe (`VoyageEmbedder`, `input_type="query"`).
- Dominio: `Answer(question, text, citations)`, `Citation(document_id, pages, excerpt)`, `ScoredChunk(chunk, score)`, `UsageRecord`, `TokenPricing`.
- Puertos con solo fakes: `VectorSearch.search(query, limit, clause_types)`, `AnswerGenerator.generate(question, context) -> Answer`; inbound `AnswerQuestion.execute(question, clause_types) -> Answer` sin use case.
- Composition root por proceso: `bootstrap/reader.py` (`ReaderContainer`: `vector_search` y `answer_generator` solo fake) sobre `CoreContainer` (engine con pool por defecto, `embedder`, `usage_tracker` reales).
- `rag_api`: `create_app(container)` con `GET /health`; import-linter prohíbe que la API importe el puerto de escritura o `bootstrap.writer`.
- Settings `llm`: `api_key`, `chat_model="gpt-4o-mini"` (heredado del scaffold, sin uso).

Motivación en `proposal.md`; requisitos en `specs/contract-question-answering/spec.md`.

## Goals / Non-Goals

**Goals:**
- `/ask` de punta a punta con citas verificables a documento y página.
- Cambiar de modelo o proveedor de generación toca un adaptador y settings.
- Errores de proveedores traducidos a errores de dominio y a códigos HTTP claros; ninguna excepción de SDK cruza a la aplicación ni a la API.

**Non-Goals:**
- Streaming de la respuesta (SSE): se puede añadir después sin cambiar la spec.
- Historial de conversación, autenticación, rate limiting propio de la API, despliegue.
- Reranking, búsqueda híbrida léxica o umbral de similitud: se evaluarán con métricas en un cambio de evaluación.
- Filtros por tipo de cláusula con datos reales: el filtro funciona, pero los fragmentos tendrán `clause_type` cuando llegue clause-extraction.

## Decisions

### D1 — Puerto `AnswerGenerator` refinado: `GeneratedAnswer`
```python
@dataclass(frozen=True, slots=True)
class GeneratedAnswer:
    answer: Answer
    model: str
    input_tokens: int
    output_tokens: int

class AnswerGenerator(Protocol):
    async def generate(self, question: str, context: Sequence[ScoredChunk]) -> GeneratedAnswer
```
- Mismo patrón que `EmbeddingBatch`: el adaptador informa lo consumido y el use case registra el costo con `TokenPricing` (SRP: el adaptador no conoce precios ni el `UsageTracker`).
- **Alternativa**: que el adaptador registre el uso él mismo. Se descarta: acoplaría cada adaptador al `UsageTracker` y repetiría la lógica de costo.

### D2 — Use case `AnswerQuestionUseCase`
Dependencias: `Embedder`, `VectorSearch`, `AnswerGenerator`, `UsageTracker`, `TokenPricing` (de generación) y `top_k`.
1. `query = embedder.embed_query(question)`.
2. `context = search.search(query, limit=top_k, clause_types)`.
3. Si `context` está vacío → `Answer(question, NO_INFORMATION_ANSWER)` sin citas; no llama al generador ni registra uso (spec "Índice vacío").
4. `generated = generator.generate(question, context)`.
5. Verifica que cada cita pertenezca a un fragmento del contexto (documento y rango de páginas dentro de alguno); descarta las que no (defensa ante alucinación de citas) — el adaptador de Claude ya las deriva del índice de documento, así que en la práctica es una invariante.
6. `usage_tracker.record(UsageRecord("answer_question", model, input, output, cost))`.
7. Devuelve `generated.answer`.
- La validación de la pregunta (no vacía, longitud máxima) vive en el esquema HTTP y en `Answer` (dominio); el use case no consulta nada si la pregunta es inválida.

### D3 — `PgVectorSearch`
- `SELECT ... ORDER BY embedding <=> :query LIMIT :k` con `ChunkRow.embedding.cosine_distance(query)`; `score = 1 - distance` (similitud coseno, mayor es mejor, igual que el fake).
- Filtro `clause_type IN (...)` solo si `clause_types` no está vacío.
- Reconstruye `Chunk` (`id`, `document_id`, `text`, `PageRange(first_page, last_page)`, `clause_type`).
- Usa el `session_factory` del lector (engine con pool, `CoreContainer` sin `NullPool`).
- **SOLID**: ISP — lectura separada de `PgVectorIndexWriter`; la API sigue sin poder alcanzar el puerto de escritura.

### D4 — `AnthropicAnswerGenerator` con citations
- SDK oficial `anthropic` (`AsyncAnthropic`), `client.beta.messages.create` (necesario para el fallback del servidor).
- Modelo por defecto `claude-sonnet-5-5` (elegido por costo; `claude-opus-5-5` se activa por setting). Pensamiento adaptativo (activo por defecto; no se envía `thinking`), `output_config={"effort": settings.effort}` con default `"medium"` explícito, `max_tokens=16000` (no streaming; el pensamiento cuenta dentro de `max_tokens`).
- **Fallback ante rechazos** (desactivado por defecto por decisión del usuario; `llm.fallbacks=true` lo activa): `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`. En cualquier caso, si `stop_reason == "refusal"`, lanza `AnswerRefusedError` con la categoría de `stop_details`.
- Mensaje de usuario: un bloque `document` por fragmento recuperado, en orden de similitud, con `source={"type": "text", "media_type": "text/plain", "data": chunk.text}`, `title=f"{document_id} — pages {first}-{last}"` y `citations={"enabled": True}`; después, la pregunta como bloque de texto.
- System prompt fijo: responder solo con los documentos proporcionados, decir explícitamente cuando no contienen la información, no usar conocimiento externo; en el idioma de la pregunta.
- Respuesta: concatena los bloques `text` (ignora `thinking` y bloques de fallback); cada cita `char_location` del SDK trae `document_index` → fragmento `context[document_index]` → `Citation(document_id, pages, excerpt=cited_text)`. Citas duplicadas se fusionan.
- Uso: `response.usage.input_tokens` / `output_tokens` y `response.model` (el modelo que realmente respondió, que puede ser el de fallback).
- Traducción de errores: `anthropic.RateLimitError` → `ProviderRateLimitedError`; `APIConnectionError`, `APITimeoutError` e `InternalServerError`/5xx → `ProviderUnavailableError`; el resto (400, 401) se propaga como error de configuración.
- La firma exacta de los tipos de citas y de `fallbacks` se confirma contra el SDK instalado al implementar (tarea 5.1).
- **Alternativa**: pedir JSON estructurado con las citas. Se descarta: citations está diseñado para esto, garantiza extractos literales y es incompatible con `output_config.format`.
- **Alternativa**: LangChain/LangGraph para la generación. Se descarta aquí: una sola llamada no necesita orquestación; LangGraph llega con clause-extraction.

### D5 — Errores de proveedor en `VoyageEmbedder`
- `voyageai.error.RateLimitError` → `ProviderRateLimitedError("voyage", ...)`; `APIConnectionError`, `ServiceUnavailableError`, `ServerError` → `ProviderUnavailableError`.
- Beneficia también al lado escritor: el run de Dagster falla con un error de dominio legible. (Reintentar automáticamente en Dagster queda fuera de este cambio; ver README "Running on free tiers".)

### D6 — Endpoint `POST /ask`
- Router `contract_intel_api/ask.py`; esquemas Pydantic propios de la API (no del dominio):
  - Request: `question: str` (1–2000 caracteres, se recorta y no puede quedar vacía), `clause_types: list[ClauseType] = []`.
  - Response: `answer: str`, `citations: list[{document_id, first_page, last_page, excerpt}]`.
- Obtiene el use case de `app.state.container.answer_question()` tipado como puerto inbound `AnswerQuestion`.
- Mapeo de errores: validación → 422 (FastAPI); `ProviderRateLimitedError` → 503 con `Retry-After: 60`; `ProviderUnavailableError` → 503; `AnswerRefusedError` → 422 con `detail` explicativo.
- Lifespan de FastAPI: al apagar, `await container.core.database_engine().dispose()` solo si el engine fue creado.
- **SOLID**: SRP — el router traduce HTTP ↔ puerto; ninguna regla de negocio.

### D7 — Composition root y settings
- `ReaderContainer`: `vector_search` real `PgVectorSearch(core.session_factory)`; `answer_generator` real `AnthropicAnswerGenerator(AnthropicConfig)`; `answer_question = Factory(AnswerQuestionUseCase, ...)`.
- `LlmSettings`: `api_key: SecretStr` (vacía → el SDK resuelve sus credenciales por defecto), `chat_model="claude-sonnet-5-5"`, `effort="medium"`, `max_tokens=16000`, `input_price_per_million=2.0`, `output_price_per_million=10.0`, `fallbacks=False`.
- `RetrievalSettings`: `top_k=8`.
- `anthropic` se añade a las listas prohibidas de dominio y aplicación en import-linter.

### D8 — Estrategia de pruebas
- **Dominio**: `GeneratedAnswer` (tokens no negativos), errores.
- **Use case con fakes**: respuesta con citas del contexto; índice vacío → sin llamada al generador ni uso; filtro de tipos propagado a la búsqueda; uso registrado con costo; cita ajena descartada; errores de proveedor propagados.
- **Contract tests**:
  - `VectorSearch`: fake vs Postgres (`integration`) sobre fragmentos sembrados con vectores conocidos: orden por similitud, `limit`, filtro por tipo, índice vacío.
  - `AnswerGenerator`: fake vs `AnthropicAnswerGenerator` con un cliente falso inyectado que devuelve bloques de texto con citas, bloques de pensamiento y rechazos: texto concatenado, citas mapeadas a documento y páginas, uso informado, rechazo → `AnswerRefusedError`, errores del SDK → errores de dominio, parámetros enviados (modelo, effort, betas/fallbacks, documentos con citations).
  - `Embedder`: se amplía con la traducción de errores de Voyage.
- **API**: `TestClient` con contenedor de fakes: 200 con citas, 422 por validación, 503 con `Retry-After`, 422 por rechazo.
- **Smoke real** marcado `anthropic` (se omite sin credenciales): una pregunta con un fragmento fijo devuelve texto y al menos una cita.

### D9 — ADR
`docs/architecture/adr/0008-grounded-answers-with-claude-citations.md`: Claude (Sonnet 5.5 por defecto) con citations sobre fragmentos de pgvector, fallback del servidor, errores de proveedor como dominio, `GeneratedAnswer` para el costo.

## Risks / Trade-offs

- [Límite gratuito de Voyage: 3 peticiones por minuto] → cada pregunta usa una; la API responde 503 con `Retry-After` en vez de colgarse. Se documenta en el README.
- [Costo por pregunta con Sonnet 5.5] → ~$0.02–0.05, registrado en `usage_records`; `effort` y modelo configurables (Opus 5.5: $4 / $20).
- [Latencia de pensamiento adaptativo] → `effort="medium"` por defecto; streaming queda como mejora.
- [Fragmentos irrelevantes recuperados (sin umbral)] → el system prompt obliga a decir que no hay información; la evaluación de recuperación ajustará `top_k`/umbral.
- [Forma exacta de citas/fallbacks en el SDK instalado] → se verifica al implementar contra el SDK y un smoke test real.
- [Solo 3 de los 5 contratos indexados por la capa gratuita] → suficiente para demostrar `/ask`; se documenta.

## Migration Plan

1. `uv sync` (añade `anthropic`); definir `CONTRACT_INTEL_LLM__API_KEY` en `.env` (o credenciales por defecto del SDK).
2. `uv run uvicorn contract_intel_api.main:app` con `CONTRACT_INTEL_USE_FAKES=false`.
3. `curl -X POST localhost:8000/ask -H 'content-type: application/json' -d '{"question": "..."}'`.

Rollback: volver a `use_fakes=true` (respuestas extractivas del fake) o revertir el cambio; no hay migraciones de base de datos.
