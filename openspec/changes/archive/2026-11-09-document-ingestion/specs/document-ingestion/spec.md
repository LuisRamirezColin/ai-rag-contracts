# Spec Delta

## Purpose

Lleva los contratos de la fuente pública de demostración al sistema: conserva cada archivo original, extrae y persiste su texto por página con un estado de ingesta, y detecta documentos nuevos de forma continua para que los procesos de extracción y vectorización tengan qué procesar.

## ADDED Requirements

### Requirement: El dataset de demostración se obtiene de forma reproducible
El sistema SHALL proveer un procedimiento que descarga el dataset público de contratos, verifica su integridad contra una huella fijada y lo deja en un directorio local excluido del control de versiones. MUST fallar sin dejar datos parciales si la verificación de integridad no coincide.

#### Scenario: Descarga verificada
- **WHEN** se ejecuta el procedimiento de obtención con acceso a la distribución pública
- **THEN** los archivos de contratos quedan en el directorio local configurado y ninguno aparece entre los archivos versionados

#### Scenario: Integridad no coincide
- **WHEN** el archivo descargado no coincide con la huella fijada
- **THEN** el procedimiento termina con error y no deja contratos en el directorio local

### Requirement: Descubrimiento de documentos pendientes
El sistema SHALL listar los documentos de la fuente que aún no están ingeridos, en un orden determinista y acotados por un límite configurable de documentos considerados de la fuente. Un documento ya ingerido MUST NOT volver a listarse.

#### Scenario: Límite configurable
- **WHEN** la fuente contiene más documentos que el límite configurado
- **THEN** solo se consideran los primeros documentos según el orden determinista, hasta el límite

#### Scenario: Documento ya ingerido
- **WHEN** un documento de la fuente ya tiene estado ingerido
- **THEN** no aparece en la lista de documentos pendientes

#### Scenario: Orden estable
- **WHEN** se descubre dos veces sobre la misma fuente sin cambios
- **THEN** ambas ejecuciones devuelven los mismos documentos en el mismo orden

### Requirement: Ingesta de un documento con texto
Al ingerir un documento, el sistema SHALL almacenar su archivo original de forma durable, extraer su texto página por página conservando el número de página, y registrar el documento con estado ingerido junto con todas sus páginas.

#### Scenario: Documento ingerido
- **WHEN** se ingiere un documento cuyo archivo contiene texto extraíble en N páginas
- **THEN** el archivo original queda almacenado, el documento queda con estado ingerido y se registran N páginas numeradas desde 1 en su orden original

### Requirement: Documento sin texto extraíble se marca como fallido
Si un documento no contiene texto extraíble en ninguna página, el sistema SHALL registrarlo con estado fallido y un motivo legible, MUST NOT registrar páginas para él, y la ingesta de los demás documentos MUST continuar.

#### Scenario: Archivo escaneado sin texto
- **WHEN** se ingiere un documento cuyas páginas no contienen texto extraíble
- **THEN** el documento queda con estado fallido, el motivo indica que no hay texto extraíble y no tiene páginas registradas

#### Scenario: Un fallo no detiene al resto
- **WHEN** en un mismo ciclo hay un documento sin texto y otro con texto
- **THEN** el documento con texto termina con estado ingerido

### Requirement: La reingesta es idempotente
Volver a ingerir un documento SHALL reemplazar su archivo, su estado y sus páginas previas. MUST NOT producir páginas duplicadas ni restos del resultado anterior.

#### Scenario: Reingesta de un documento ingerido
- **WHEN** se vuelve a ingerir un documento que ya tenía páginas registradas
- **THEN** el documento conserva exactamente un conjunto de páginas, el de la última ingesta

#### Scenario: Reingesta tras un fallo
- **WHEN** se reingiere con éxito un documento que estaba en estado fallido
- **THEN** el documento queda con estado ingerido, sin motivo de fallo y con sus páginas registradas

### Requirement: Detección continua de documentos nuevos
El lado escritor SHALL revisar la fuente periódicamente y programar la ingesta de cada documento pendiente sin intervención manual. Un documento ya programado MUST NOT programarse de nuevo automáticamente, aunque su ingesta haya fallado.

#### Scenario: Aparece un documento nuevo
- **WHEN** la fuente pasa a contener un documento pendiente que no estaba programado
- **THEN** en la siguiente revisión se programa su ingesta y, al ejecutarse, el documento queda ingerido

#### Scenario: Fallo no se reprograma solo
- **WHEN** la ingesta programada de un documento termina en estado fallido
- **THEN** las revisiones siguientes no vuelven a programarlo; solo una reejecución explícita lo reintenta

### Requirement: Las páginas ingeridas están disponibles para procesos posteriores
El sistema SHALL devolver, dado un identificador de documento ingerido, todas sus páginas en orden con su número y texto. Para un documento inexistente o no ingerido MUST indicar que no está disponible.

#### Scenario: Lectura de páginas
- **WHEN** un proceso posterior solicita las páginas de un documento ingerido
- **THEN** recibe todas las páginas en orden ascendente de número

#### Scenario: Documento no disponible
- **WHEN** se solicitan las páginas de un documento que no existe o está en estado fallido
- **THEN** la solicitud termina con un error que indica que el documento no está disponible

### Requirement: La ingesta funciona sin infraestructura en modo de prueba
Con la configuración de dobles en memoria activa, el sistema SHALL ejecutar el descubrimiento y la ingesta completos sin abrir conexiones de red ni requerir servicios externos.

#### Scenario: Ingesta con dobles en memoria
- **WHEN** se descubre e ingiere un documento con la configuración de dobles en memoria activa y la red bloqueada
- **THEN** el documento termina con estado ingerido y no se intentó ninguna conexión de red
