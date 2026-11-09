# Proposal

## Why

Los contratos ya están ingeridos e indexados en pgvector, pero nadie puede consultarlos: la API solo expone `/health`. Este cambio cierra el RAG de punta a punta: una pregunta en lenguaje natural se responde con Claude usando únicamente los fragmentos recuperados del índice, y cada afirmación cita el documento y las páginas de donde sale.

## What Changes

- **Endpoint `POST /ask`** en `rag_api/` (lado lector): recibe la pregunta y un filtro opcional por tipos de cláusula; devuelve la respuesta y sus citas (documento, rango de páginas, extracto). Errores explícitos para entrada inválida, proveedor no disponible o con límite de uso, y respuesta rechazada por el modelo.
- **Use case `AnswerQuestionUseCase`** (implementa el puerto inbound `AnswerQuestion` existente): codifica la pregunta, recupera los fragmentos más similares, pide la respuesta al generador y registra el uso de tokens y su costo. Si el índice no devuelve nada, responde que no hay información sin llamar al modelo.
- **Puerto `AnswerGenerator` refinado** (**BREAKING** solo interno): devuelve `GeneratedAnswer` (respuesta + modelo + tokens de entrada y salida), igual que `Embedder` devuelve `EmbeddingBatch`, para que el use case registre el costo.
- **Dominio**: `GeneratedAnswer`; errores `ProviderRateLimitedError`, `ProviderUnavailableError` y `AnswerRefusedError`, a los que los adaptadores traducen las excepciones de cada SDK.
- **Adaptadores reales**:
  - `PgVectorSearch`: similitud coseno en pgvector (índice HNSW existente) con filtro opcional por tipo de cláusula.
  - `AnthropicAnswerGenerator`: SDK oficial `anthropic`, modelo `claude-sonnet-5-5` (configurable); cada fragmento recuperado va como documento con **citations** activado, de modo que la API devuelve qué fragmento respalda cada parte de la respuesta y se traduce a documento y páginas. Pensamiento adaptativo con `effort` configurable y fallback del lado del servidor ante rechazos, desactivado por defecto y activable por setting.
  - `VoyageEmbedder` traduce sus errores de límite y de conexión a los errores de dominio.
- **Composition root (`bootstrap/reader.py`)**: ramas reales de `vector_search` y `answer_generator`, engine con pool para la API, `Factory` del use case; cierre del engine al apagar la API.
- **Settings**: `llm` pasa a Claude (`chat_model=claude-sonnet-5-5`, `effort`, `max_tokens`, precios por millón de tokens, `fallbacks`); nueva sección `retrieval` (`top_k`).

**Capas hexagonales afectadas**: domain (respuesta generada, errores de proveedor), application (puerto refinado, use case), adapters (pgvector search, Claude, errores de Voyage), inbound adapters (`rag_api/`: `/ask`), bootstrap (lector y settings).

## Capabilities

### New Capabilities
- `contract-question-answering`: responder preguntas sobre los contratos indexados con respuestas basadas solo en fragmentos recuperados, citando documento y páginas, con filtros por tipo de cláusula, errores explícitos y registro del costo de cada respuesta.

### Modified Capabilities
<!-- Ninguna: architecture-conformance ya exige que la API sea solo lectora del índice; document-vectorization ya exige la codificación de consultas. -->

## Impact

- **Código**: `core/src/contract_intel/{domain,application,adapters,bootstrap}`, `rag_api/src/contract_intel_api/`, `.env.example`, `pyproject.toml` (import-linter, marcador de pruebas), `docs/architecture/`, README.
- **Dependencias**: runtime `anthropic` en `core`.
- **Sistemas**: API de Anthropic (`CONTRACT_INTEL_LLM__API_KEY`, o las credenciales que el SDK resuelve por defecto) y Voyage para codificar cada pregunta. Con la cuenta gratuita de Voyage (3 peticiones por minuto) la API admite como mucho 3 preguntas por minuto.
- **Costo**: ~8 fragmentos de contexto por pregunta → unos $0.02–0.05 por respuesta con `claude-sonnet-5-5` ($2 / $10 por millón de tokens); queda registrado en `usage_records`.
