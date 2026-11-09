# ADR 0004 — Executable architecture rules

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

Architecture that relies on code review erodes. The rules in ADR 0001 and ADR 0003,
and the requirement that nothing non-publishable is committed, must fail the build
when violated.

## Decision

### Import contracts (`import-linter`, root `pyproject.toml`)

| Contract | Rule |
|---|---|
| Core layers | `bootstrap` > `adapters` > `application` > `domain`; lower layers never import higher ones |
| Domain is framework-free | `domain` imports no persistence, cloud, LLM, orchestration, HTTP or DI package |
| Application is framework-free | Same list, applied to `application` |
| Inbound → outbound only via bootstrap | `pipelines` and `rag_api` never import `contract_intel.adapters` directly |
| API is read-only on the vector index | `rag_api` never imports the `VectorIndexWriter` port |
| Legacy is never imported | No package imports the prototype's modules |
| Inbound adapters are independent | `pipelines` and `rag_api` never import each other |

`core/tests/architecture/test_import_contracts.py` runs the contracts and, for each
rule, injects a violation into a temporary copy of the sources and asserts that the
contract reports it as broken. This guards against contracts that silently stop
matching anything.

### Adapter substitutability

Every outbound port has an in-memory adapter. A conformance test assigns each one to
a variable annotated with its `Protocol` (checked by `mypy --strict`) and checks
`isinstance` at runtime. It also fails if a port module is added without an
in-memory adapter.

### Forbidden identifiers

`scripts/check_forbidden_identifiers.py` scans tracked files:

- generic patterns are versioned (`scripts/forbidden_patterns.txt`): cloud account
  ids in ARNs, non-example email addresses, internal collaboration hosts, tunnels,
  SSO parameters, local home paths;
- sensitive names (employers, clients) come from the git-ignored `.forbidden-names`
  file or the `FORBIDDEN_NAMES` CI secret, because versioning them would publish them.
  Without either source the scan warns and checks the generic patterns only.

### Enforcement

Pre-commit runs ruff, mypy, import contracts and the scan. CI runs the same checks
plus the test suite on every pull request.

## Alternatives considered

- **Ad hoc AST tests.** More custom code to maintain, poorer error messages.
- **`gitleaks` only.** Built for secrets, not for client names; it can be added later
  as a complement.

## Consequences

- Breaking a rule fails locally (pre-commit, `pytest`) and in CI, with a message
  naming the offending import or file and line.
- New third-party SDKs must be added to the framework-free lists when introduced.
