# ADR 0002 — `uv` workspace monorepo with three packages

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

The system has one core (domain, use cases, adapters) and two independently deployed
processes: the Dagster pipelines and the FastAPI service. Each process pulls a heavy
framework that the other must not need.

## Decision

A single repository managed as a **`uv` workspace** with three packages and one
lockfile:

| Directory | Package | Role |
|---|---|---|
| `core/` | `contract_intel` | Domain, application, outbound adapters, composition root |
| `pipelines/` | `contract_intel_pipelines` | Inbound adapter (Dagster), writer of the vector index |
| `rag_api/` | `contract_intel_api` | Inbound adapter (FastAPI), reader of the vector index |

`pipelines` and `rag_api` depend on `core`; `core` depends on neither. The package
names are deliberately distinct from the prototype's module names, so an accidental
import of the reference code is detectable.

## Alternatives considered

- **One package.** Simplest, but both deployables would install Dagster and FastAPI,
  and nothing would stop the API from importing pipeline code.
- **Poetry with separate projects.** No native workspaces, several lockfiles to keep
  in sync, slower CI.

## Consequences

- One `uv.lock` gives reproducible installs for every package (`uv sync --frozen`).
- Each deployable image can install only its own package and `core`.
- Tool configuration (ruff, mypy, pytest, import-linter) lives once in the root
  `pyproject.toml`.
