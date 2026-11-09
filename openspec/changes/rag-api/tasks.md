# Tasks

> Todos los comandos se ejecutan dentro de WSL. Las pruebas `integration` requieren `docker compose up -d --wait` y `uv run alembic upgrade head`. Cada grupo deja `uv run ruff check .`, `uv run mypy scripts core/src core/tests core/migrations pipelines/src pipelines/tests rag_api/src rag_api/tests` y `uv run lint-imports` en verde antes de cerrarse.

## 1. Dependencias y settings

- [x] 1.1 Añadir `anthropic` a `core/pyproject.toml`, añadir `"anthropic"` a las listas prohibidas de dominio y aplicación en `[tool.importlinter]` y registrar el marcador `anthropic` excluido por defecto; verificar `uv sync --all-packages`, `uv run lint-imports` y que `uv run pytest` sigue en verde
- [x] 1.2 Actualizar `LlmSettings` para Claude y añadir `RetrievalSettings` (D7), actualizar `.env.example` y ampliar `core/tests/bootstrap/test_settings.py` (defaults `claude-sonnet-5-5`, `fallbacks=false`, `effort` válido, precios $2/$10, `top_k` positivo, `api_key` secreta); verificar `uv run pytest core/tests/bootstrap/test_settings.py`

## 2. Dominio

- [x] 2.1 Añadir `GeneratedAnswer` (D1) y los errores `ProviderRateLimitedError`, `ProviderUnavailableError` y `AnswerRefusedError`; tests de invariantes en `core/tests/domain/`; verificar `uv run pytest core/tests/domain` y `uv run mypy core`

## 3. Puertos y fakes

- [x] 3.1 Refinar `AnswerGenerator.generate` para devolver `GeneratedAnswer`, actualizar `InMemoryAnswerGenerator` (modelo y tokens estimados) y sus tests en `core/tests/adapters/in_memory/`; verificar `uv run pytest core/tests/adapters/in_memory` y `uv run mypy core`

## 4. Use case

- [x] 4.1 Implementar `application/use_cases/answer_question.py` (D2) con tests unitarios sobre fakes en `core/tests/application/test_answer_question.py`: respuesta con citas del contexto; índice vacío → respuesta "sin información", sin citas, sin llamada al generador ni uso registrado; `clause_types` llega a la búsqueda; `top_k` limita el contexto; uso registrado con modelo, tokens y costo; cita que no pertenece al contexto se descarta; errores de proveedor se propagan sin registrar uso; verificar `uv run pytest core/tests/application`

## 5. Adaptadores reales

- [x] 5.1 Confirmar en el SDK `anthropic` instalado los tipos de citas (`char_location`, `document_index`, `cited_text`), el parámetro `fallbacks` y la beta `server-side-fallback-2026-07-01`, y las clases de error; implementar `adapters/outbound/anthropic/anthropic_answer_generator.py` (D4) y la suite de contrato de `AnswerGenerator` en `core/tests/adapters/contracts/test_answer_generator_contract.py` sobre el fake y sobre el adaptador con un cliente falso inyectado (texto concatenado ignorando pensamiento, citas → documento y páginas, citas duplicadas fusionadas, uso y modelo informados, rechazo → `AnswerRefusedError`, errores de límite/conexión/servidor → errores de dominio, parámetros enviados: modelo, effort, betas y fallbacks, documentos con citations, pregunta al final); verificar `uv run pytest core/tests/adapters/contracts -k answer_generator`
- [x] 5.2 Traducir en `VoyageEmbedder` los errores de límite, conexión y servidor a `ProviderRateLimitedError`/`ProviderUnavailableError` (D5) y ampliar la suite de contrato de `Embedder` con esos casos; verificar `uv run pytest core/tests/adapters/contracts -k embedder`
- [x] 5.3 Implementar `adapters/outbound/persistence/vector_search.py` (`PgVectorSearch`, D3) y la suite de contrato de `VectorSearch` sobre el fake y Postgres (`integration`) con fragmentos sembrados de vectores conocidos: orden por similitud, `limit`, filtro por tipo de cláusula, índice vacío, rango de páginas reconstruido; verificar `uv run pytest core/tests/adapters/contracts -k vector_search` y `uv run pytest -m integration -k vector_search`
- [x] 5.4 Añadir un smoke test real marcado `anthropic` que se omite sin credenciales (`CONTRACT_INTEL_LLM__API_KEY` vacía y sin credenciales por defecto del SDK): una pregunta sobre un fragmento fijo devuelve texto y al menos una cita a ese fragmento, con tokens > 0; verificar con las credenciales del usuario `uv run pytest -m anthropic` y sin ellas que se reporta omitido

## 6. Composition root

- [x] 6.1 Actualizar `bootstrap/reader.py` (D7): ramas reales de `vector_search` y `answer_generator`, `Factory` `answer_question`; actualizar `core/tests/bootstrap/test_containers.py`: los adaptadores reales del lector resuelven sin red, `ReaderContainer` sigue sin exponer escritura, y una pregunta de punta a punta con fakes y socket bloqueado (indexar con el contenedor escritor fake compartiendo el almacén en memoria, preguntar con el lector) cita el documento; verificar `uv run pytest core/tests/bootstrap` y `uv run lint-imports`

## 7. API

- [x] 7.1 Implementar `contract_intel_api/ask.py` (D6: esquemas, router, mapeo de errores) y el lifespan que cierra el engine, registrados en `main.py`; tests en `rag_api/tests/test_ask.py` con contenedor de fakes: 200 con respuesta y citas (documento, páginas, extracto), respuesta "sin información" con índice vacío, 422 por pregunta vacía/solo espacios/demasiado larga y por tipo de cláusula desconocido, 503 con `Retry-After` ante límite del proveedor, 503 ante proveedor caído, 422 ante rechazo; verificar `uv run pytest rag_api/tests` y que `/docs` muestra el endpoint

## 8. Documentación

- [x] 8.1 Escribir el ADR `0008-grounded-answers-with-claude-citations` (MADR corto, inglés); actualizar `docs/architecture/hexagonal.md` (tabla de puertos: `AnswerQuestion` ✓, `VectorSearch` → `PgVectorSearch` ✓, `AnswerGenerator` → `AnthropicAnswerGenerator` ✓; flujo de pregunta) y el `README.md` (estado, credenciales de Anthropic en el quickstart, ejemplo `curl` de `/ask` con respuesta, configuración `llm`/`retrieval`, límite de 3 preguntas por minuto con Voyage gratuito, costo por pregunta); verificar que el ADR tiene Status, Context, Decision y Consequences y que los comandos nuevos del README funcionan tal como están escritos

## 9. Verificación integral

- [x] 9.1 Pregunta real de punta a punta con las credenciales de Anthropic del usuario y los 3 contratos indexados: con Docker y `.env` en modo real, arrancar `uvicorn contract_intel_api.main:app` y comprobar con `curl` que una pregunta sobre ley aplicable responde citando el contrato de Ability con su rango de páginas, que una pregunta sin relación con los contratos responde que no hay información, que una pregunta vacía devuelve 422, y que `usage_records` tiene un registro `answer_question` con tokens de entrada y salida y su costo
- [x] 9.2 Desde un clon limpio (último commit más los cambios del working tree): `uv sync --frozen --all-packages && uv run ruff format --check . && uv run ruff check . && uv run mypy scripts core/src core/tests core/migrations pipelines/src pipelines/tests rag_api/src rag_api/tests && uv run lint-imports && uv run python scripts/check_forbidden_identifiers.py && uv run pytest && uv run pytest -m integration` todo en verde
- [x] 9.3 Ejecutar `openspec validate rag-api --strict` sin errores

## Workflow follow-up

- Revisar el cambio y archivarlo con `/opsx:archive` (crea `openspec/specs/contract-question-answering/spec.md`).
- Siguiente cambio: `/opsx:propose clause-extraction` (LangGraph con Claude, cláusulas tipadas CUAD que alimentan el filtro por tipo).
