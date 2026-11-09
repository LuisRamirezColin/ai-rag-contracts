# ADR 0001 — Hexagonal architecture and a clean rewrite

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

A previous prototype extracted contract clauses with an LLM pipeline. It proved the
extraction approach (page batches → two complementary extractors → consolidating
judge), but:

- domain logic, persistence, cloud SDKs and prompts were interleaved in the same
  modules, so use cases could only be tested by mocking infrastructure;
- adapters were selected with `if/else` branches and wired by hand-written factories;
- it had no retrieval layer and no API, although both were on its roadmap;
- it contained data that cannot be published.

The project is now meant to showcase production-grade AI engineering, so the
architecture itself is part of the deliverable.

## Decision

1. Adopt **hexagonal architecture** (ports and adapters):
   - `domain` — pure Python value objects and invariants;
   - `application` — use cases plus ports declared as `typing.Protocol`;
   - `adapters` — every framework or SDK (LLM, database, object storage, vector index);
   - `bootstrap` — the composition root, the only module that knows concrete adapters;
   - two inbound adapters: Dagster pipelines (writer) and a FastAPI service (reader).
2. **Rewrite from scratch** instead of refactoring in place. The prototype is kept
   outside version control as a reference for prompts and lessons learned, and is
   never imported (enforced, see ADR 0004).

## Alternatives considered

- **Strangler refactor of the prototype.** Keeps working code, but every step would
  carry the old coupling and the non-publishable data along. Rejected: the valuable
  part (prompts and the extraction graph design) is small and easy to re-express
  behind a port.
- **Layered "clean architecture" without explicit ports.** Simpler, but it does not
  make the RAG writer/reader split or adapter substitution explicit.

## Consequences

- Use cases are tested against in-memory adapters, with no mocks of SDKs.
- Swapping a provider (LLM, embeddings, vector store) means adding an adapter and
  changing one line in the composition root.
- More files and indirection up front; mitigated by one-port-per-module and the
  guide in [`../hexagonal.md`](../hexagonal.md).
