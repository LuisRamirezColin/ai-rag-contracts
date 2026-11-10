# ADR 0006 — Lazy, per-port selection between fake and real adapters

- **Status:** Accepted
- **Date:** 2026-11-09
- **Amends:** [ADR 0003](0003-composition-root-reader-writer-containers.md) ("asking
  for real adapters fails fast")

## Context

Real adapters arrive one change at a time: document ingestion brings the CUAD source,
S3 storage, the pypdf extractor and the Postgres document repository, while the
embedder, clause extractor, vector index and answer generator are still fakes. The
scaffold's composition root refused to build any container when
`CONTRACT_INTEL_USE_FAKES=false`, which would block the real ingestion until every
other adapter exists.

## Decision

- Every outbound port in the containers is a `dependency-injector` `Selector` keyed by
  `settings.use_fakes`, with a `fake` branch (in-memory adapter) and a `real` branch.
- A port without a real adapter yet gets a `real` branch that raises
  `RealAdaptersUnavailableError(<port name>)` **when resolved**, never when the
  container is built.
- Use cases are `Factory` providers in the container that owns them
  (`discover_documents`, `ingest_document` in `WriterContainer`).
- The writer's async engine uses `NullPool`, because each Dagster materialization runs
  its own event loop.

## SOLID rationale

- **OCP** — each later change only fills the `real` branch of its own port.
- **DIP** — only `bootstrap` knows concrete classes; inbound adapters resolve use cases
  typed as inbound ports.

## Alternatives considered

- **Fail fast on build (previous behaviour).** Blocks partially real setups.
- **Silently fall back to fakes for missing real adapters.** Dangerous: a "real" run
  could write to process memory and look successful.

## Consequences

- **Update (ADR 0009):** since clause extraction, every outbound port has a real
  adapter, so the "not implemented yet" branch and `RealAdaptersUnavailableError`
  were removed; the per-port `Selector` remains.

- Real ingestion works today with `CONTRACT_INTEL_USE_FAKES=false`; resolving a port
  without a real adapter names the port in the error.
- Container tests assert both branches: real ingestion adapters resolve without
  network, and unimplemented ports fail on resolution.
