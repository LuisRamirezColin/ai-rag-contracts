# Spec Delta

## Purpose

Identifica y clasifica las cláusulas de cada contrato ingerido según la taxonomía soportada, con su texto literal y las páginas donde aparecen, para poder consultar y filtrar contratos por tipo de cláusula.

## ADDED Requirements

### Requirement: Extracción de cláusulas tipadas con ubicación
Para un documento ingerido, el sistema SHALL identificar sus cláusulas de los tipos soportados por la taxonomía y devolver por cada una su tipo, su texto y el rango de páginas donde aparece. Un tipo de cláusula ausente en el documento MUST NOT producir cláusulas de ese tipo.

#### Scenario: Documento con cláusula de ley aplicable
- **WHEN** se extraen las cláusulas de un documento que contiene una cláusula de ley aplicable en la página 8
- **THEN** el resultado incluye una cláusula de tipo ley aplicable con su texto y un rango de páginas que incluye la 8

#### Scenario: Tipo ausente
- **WHEN** el documento no contiene ninguna cláusula de no competencia
- **THEN** el resultado no incluye cláusulas de no competencia

### Requirement: El texto de cada cláusula es literal del documento
El texto de toda cláusula extraída SHALL aparecer literalmente (salvo diferencias de espacios en blanco) en las páginas indicadas. Los candidatos que no cumplan esta condición MUST descartarse.

#### Scenario: Candidato inventado
- **WHEN** el modelo propone una cláusula cuyo texto no aparece en las páginas indicadas
- **THEN** esa cláusula no forma parte del resultado

### Requirement: Sin duplicados
El resultado SHALL contener a lo sumo una cláusula por tipo y fragmento de texto: candidatos del mismo tipo cuyo texto se solapa MUST consolidarse en una sola cláusula.

#### Scenario: Cláusula vista en dos ventanas
- **WHEN** una cláusula aparece en dos porciones del documento analizadas por separado
- **THEN** el resultado la contiene una sola vez

### Requirement: Las cláusulas se guardan por contrato
El sistema SHALL guardar las cláusulas extraídas en el contrato al que pertenece el documento. Volver a extraer un documento MUST reemplazar sus cláusulas anteriores sin afectar las de otros documentos.

#### Scenario: Reextracción
- **WHEN** se extraen de nuevo las cláusulas de un documento ya procesado
- **THEN** el contrato conserva solo las cláusulas de la última extracción para ese documento

#### Scenario: Consulta de cláusulas de un documento
- **WHEN** se solicitan las cláusulas de un documento procesado
- **THEN** se obtienen las cláusulas guardadas de ese documento con su tipo, texto y páginas

### Requirement: Solo se procesan documentos ingeridos
El sistema SHALL extraer cláusulas únicamente de documentos con estado ingerido; para un documento inexistente o fallido MUST terminar con un error de documento no disponible sin modificar las cláusulas guardadas.

#### Scenario: Documento fallido
- **WHEN** se solicita extraer las cláusulas de un documento en estado fallido
- **THEN** la solicitud termina con un error de documento no disponible

### Requirement: Extracción automática tras la ingesta
El lado escritor SHALL extraer las cláusulas de cada documento después de ingerirlo con éxito, sin intervención manual. Si la ingesta falla, la extracción MUST NOT ejecutarse.

#### Scenario: Documento nuevo
- **WHEN** un documento nuevo se ingiere con éxito
- **THEN** a continuación sus cláusulas quedan extraídas y guardadas

### Requirement: Registro del costo de la extracción
Cada extracción SHALL registrar la operación, el modelo, los tokens de entrada y salida, el costo estimado según los precios configurados y el documento.

#### Scenario: Uso registrado
- **WHEN** se extraen las cláusulas de un documento
- **THEN** existe un registro de uso de extracción con modelo, tokens, costo y el identificador del documento

### Requirement: La extracción funciona sin servicios externos en modo de prueba
Con la configuración de dobles en memoria activa, el sistema SHALL extraer y guardar cláusulas sin abrir conexiones de red.

#### Scenario: Extracción con dobles en memoria
- **WHEN** se ingiere y se extraen las cláusulas de un documento con dobles en memoria y la red bloqueada
- **THEN** las cláusulas configuradas en el doble quedan guardadas y no se intentó ninguna conexión de red
