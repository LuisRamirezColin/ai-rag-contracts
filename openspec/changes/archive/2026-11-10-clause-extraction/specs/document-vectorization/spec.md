# Spec Delta

## ADDED Requirements

### Requirement: Fragmentos etiquetados con los tipos de cláusula que contienen
Al vectorizar un documento, el sistema SHALL etiquetar cada fragmento con el conjunto de tipos de las cláusulas extraídas de ese documento que contiene, total o parcialmente. Un fragmento sin cláusulas extraídas MUST quedar sin tipos, y un fragmento con cláusulas de varios tipos MUST quedar con todos ellos.

#### Scenario: Fragmento con dos cláusulas
- **WHEN** un fragmento contiene parte de una cláusula de ley aplicable y parte de una cláusula de límite de responsabilidad
- **THEN** el fragmento queda etiquetado con ambos tipos

#### Scenario: Fragmento sin cláusulas
- **WHEN** ningún texto de cláusula extraída aparece en un fragmento
- **THEN** el fragmento queda sin tipos de cláusula

#### Scenario: Documento sin extracción
- **WHEN** se vectoriza un documento del que aún no hay cláusulas extraídas
- **THEN** todos sus fragmentos quedan sin tipos y la vectorización termina con éxito

## MODIFIED Requirements

### Requirement: Vectorización automática tras la ingesta
El lado escritor SHALL vectorizar cada documento automáticamente, sin intervención manual, después de ingerirlo y de extraer sus cláusulas con éxito, para que sus fragmentos nazcan etiquetados. Si la ingesta o la extracción fallan, la vectorización de ese documento MUST NOT ejecutarse.

#### Scenario: Documento nuevo
- **WHEN** un documento nuevo se ingiere y se extraen sus cláusulas con éxito
- **THEN** a continuación queda vectorizado y sus fragmentos están en el índice con sus tipos de cláusula

#### Scenario: Ingesta fallida
- **WHEN** la ingesta de un documento termina en estado fallido
- **THEN** no se intenta vectorizarlo

#### Scenario: Extracción fallida
- **WHEN** la extracción de cláusulas de un documento falla
- **THEN** no se intenta vectorizarlo en esa ejecución y puede reintentarse explícitamente
