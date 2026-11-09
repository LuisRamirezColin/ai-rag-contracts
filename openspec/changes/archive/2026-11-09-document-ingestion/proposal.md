# Proposal

## Why

El esqueleto hexagonal ya existe, pero el sistema todavía no tiene datos: los puertos de ingesta solo tienen fakes y las capas de extracción de cláusulas y de vectorización no tienen nada que procesar. Este cambio trae los contratos públicos de CUAD al sistema, guarda el PDF original y su texto por página, y deja el lado escritor del RAG alimentándose solo cuando aparecen documentos nuevos.

## What Changes

- **Dataset reproducible**: script que descarga CUAD v1 desde su distribución pública, verifica la integridad (SHA-256 fijado) y extrae los PDFs en `data/` (ya git-ignorado). Ningún contrato se versiona.
- **Use cases** (primeros del proyecto) en `application/use_cases/`:
  - `DiscoverDocuments`: devuelve los documentos de la fuente que todavía no están ingeridos, en orden determinista y limitados por un setting (por defecto 5).
  - `IngestDocument`: para un documento, guarda el archivo original, extrae el texto por página y persiste páginas y estado (`ingested`), o lo marca `failed` con motivo cuando no hay texto extraíble.
- **Puertos**:
  - Inbound: `IngestDocuments` (batch, sin uso aún) se reemplaza por `DiscoverDocuments` + `IngestDocument`, alineados con los puertos por documento que ya tienen extracción y vectorización. **BREAKING** solo interno; no hay consumidores.
  - Outbound nuevo: `DocumentRepository` (estado de ingesta y páginas por documento), con su fake in-memory.
- **Dominio**: `IngestionStatus` (`ingested`, `failed`) y la excepción `NoExtractableTextError`.
- **Adaptadores outbound reales**: `CuadDocumentSource` (directorio local de CUAD), `S3DocumentStorage` (boto3, LocalStack en local), `PypdfTextExtractor` (pypdf, sin OCR) y `SqlAlchemyDocumentRepository` (Postgres), más la migración `0002_documents_and_pages`.
- **Composition root**: con `use_fakes=false` se cablean los adaptadores reales de ingesta. Los puertos que aún no tienen adaptador real fallan solo al resolverse, no al construir el contenedor.
- **Dagster** (lado escritor): particiones dinámicas por documento, un sensor que registra los documentos nuevos y un asset `ingested_document` por partición que invoca `IngestDocument`.
- **Settings**: sección `ingestion` (`cuad_dir`, `max_documents=5`) y variables nuevas en `.env.example`.
- **Pruebas**: use cases con fakes, contract tests compartidos fake/real para cada puerto outbound de ingesta, y pruebas de integración contra Postgres y LocalStack, también en CI.

**Capas hexagonales afectadas**: domain (estado de ingesta y error), application (puertos inbound redefinidos, puerto `DocumentRepository`, dos use cases), adapters (cuatro adaptadores reales, persistencia y migración), inbound adapters (`pipelines/`: sensor y asset), bootstrap (selección real/fake y settings).

## Capabilities

### New Capabilities
- `document-ingestion`: obtener contratos de la fuente pública, conservar el archivo original, extraer y persistir su texto por página con su estado de ingesta, detectar documentos nuevos de forma continua y exponer las páginas a los procesos posteriores.

### Modified Capabilities
<!-- Ninguna: architecture-conformance no cambia sus requisitos; los adaptadores nuevos deben cumplirlos tal como están. -->

## Impact

- **Código**: `core/src/contract_intel/{domain,application,adapters,bootstrap}`, `core/migrations/versions/0002_*`, `pipelines/src/contract_intel_pipelines/`, `scripts/download_cuad.py`, `.env.example`, `.github/workflows/ci.yml`, README (quickstart de datos).
- **Dependencias**: runtime `boto3`, `pypdf` en `core`; dev `fpdf2` (PDFs de prueba generados en los tests) y `boto3-stubs[s3]` para `mypy --strict`.
- **Sistemas**: Postgres (tablas `documents`, `pages`), bucket S3 `contracts` en LocalStack, descarga única de CUAD (~100 MB) desde su distribución pública. CI agrega servicios Postgres y LocalStack para las pruebas de integración.
- **Datos**: solo CUAD (público). `data/` sigue fuera del control de versiones.
