# Spec Delta

## Purpose

Mide de forma reproducible la calidad de la extracción de cláusulas comparándola con las etiquetas de expertos del dataset de demostración, por tipo de cláusula.

## ADDED Requirements

### Requirement: Métricas de presencia por tipo de cláusula
Para los documentos procesados que tienen etiquetas de expertos, el sistema SHALL calcular por tipo de cláusula la precisión, el recall y el F1 de la detección de presencia (el documento tiene o no tiene al menos una cláusula de ese tipo), junto con los conteos de verdaderos positivos, falsos positivos y falsos negativos.

#### Scenario: Detección correcta
- **WHEN** los expertos marcan un tipo como presente en un documento y la extracción encontró al menos una cláusula de ese tipo
- **THEN** cuenta como verdadero positivo para ese tipo

#### Scenario: Cláusula no encontrada
- **WHEN** los expertos marcan un tipo como presente y la extracción no encontró ninguna cláusula de ese tipo
- **THEN** cuenta como falso negativo para ese tipo

#### Scenario: Cláusula de más
- **WHEN** los expertos no marcan un tipo en un documento y la extracción encontró una cláusula de ese tipo
- **THEN** cuenta como falso positivo para ese tipo

#### Scenario: Tipo sin casos
- **WHEN** un tipo no tiene positivos reales ni predichos en los documentos evaluados
- **THEN** sus métricas se reportan como no definidas en lugar de cero o uno

### Requirement: Solapamiento del texto extraído con la evidencia de expertos
Para cada verdadero positivo, el sistema SHALL indicar si alguna cláusula extraída de ese tipo comparte texto con alguno de los extractos de los expertos, y reportar por tipo la proporción de verdaderos positivos con evidencia coincidente.

#### Scenario: Evidencia coincidente
- **WHEN** el texto extraído contiene un extracto de los expertos o está contenido en él (sin distinguir espacios ni mayúsculas)
- **THEN** ese verdadero positivo cuenta con evidencia coincidente

### Requirement: Alcance explícito de la evaluación
El reporte SHALL indicar cuántos documentos se evaluaron y cuáles documentos procesados se excluyeron por no tener etiquetas de expertos.

#### Scenario: Documento sin etiquetas
- **WHEN** un documento procesado no aparece en las etiquetas de expertos
- **THEN** no se usa para las métricas y figura como excluido en el reporte

### Requirement: Reporte reproducible
La evaluación SHALL poder ejecutarse a demanda sobre las cláusulas guardadas, sin volver a invocar el modelo, y producir un reporte legible con las métricas por tipo y los totales agregados.

#### Scenario: Ejecución de la evaluación
- **WHEN** se ejecuta la evaluación sobre cláusulas ya extraídas
- **THEN** se obtiene un reporte con una fila por tipo de cláusula, los totales y el alcance, sin llamadas al modelo
