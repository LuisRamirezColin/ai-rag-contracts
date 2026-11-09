# Spec Delta

## Purpose

Garantiza de forma verificable que el código respeta la arquitectura hexagonal (dirección de dependencias, aislamiento del dominio, ensamblado único, separación lector/escritor del índice) y que el repositorio no contiene identificadores no publicables.

## ADDED Requirements

### Requirement: El dominio no depende de otras capas ni de infraestructura
La capa de dominio SHALL depender únicamente de la biblioteca estándar del lenguaje. MUST NOT importar módulos de aplicación, adaptadores, composition root, adaptadores inbound ni paquetes de terceros de infraestructura (persistencia, nube, LLM, orquestación, HTTP).

#### Scenario: Dominio limpio
- **WHEN** se ejecuta la verificación de arquitectura sobre el código actual
- **THEN** la verificación termina con éxito sin reportar violaciones en la capa de dominio

#### Scenario: Import prohibido en dominio
- **WHEN** un módulo de dominio importa un paquete de persistencia o de un proveedor LLM
- **THEN** la verificación de arquitectura falla e identifica el módulo y el import infractor

### Requirement: La capa de aplicación depende solo del dominio
La capa de aplicación (casos de uso y puertos) SHALL depender únicamente del dominio y de la biblioteca estándar. MUST NOT importar adaptadores, composition root, adaptadores inbound ni paquetes de infraestructura de terceros.

#### Scenario: Caso de uso importa un adaptador
- **WHEN** un módulo de aplicación importa un adaptador concreto
- **THEN** la verificación de arquitectura falla e identifica el import infractor

### Requirement: Los puertos son contratos abstractos
Todo puerto (inbound u outbound) SHALL definirse como un contrato estructural sin implementación ni estado, ubicado en la capa de aplicación.

#### Scenario: Inventario de puertos
- **WHEN** se inspeccionan los puertos declarados
- **THEN** existen como contratos abstractos los puertos inbound de ingesta, extracción de cláusulas, vectorización y respuesta a preguntas, y los puertos outbound de fuente de documentos, almacenamiento de documentos, extracción de texto, extracción de cláusulas, embeddings, escritura del índice vectorial, búsqueda vectorial, repositorio de contratos, generación de respuestas y registro de uso

### Requirement: Los adaptadores solo se instancian en el composition root
Los adaptadores outbound SHALL instanciarse y conectarse únicamente en el composition root. Los adaptadores inbound (pipelines y API) MUST obtener los casos de uso desde el composition root y MUST NOT importar adaptadores outbound directamente.

#### Scenario: Adaptador inbound importa adaptador outbound
- **WHEN** un módulo de pipelines o de la API importa un adaptador outbound
- **THEN** la verificación de arquitectura falla

#### Scenario: Composition root carga
- **WHEN** se construye el composition root con configuración de prueba
- **THEN** la construcción termina sin errores y sin abrir conexiones de red

### Requirement: La API es solo lectora del índice vectorial
El adaptador inbound de la API SHALL tener acceso únicamente al puerto de búsqueda vectorial. MUST NOT depender del puerto de escritura del índice; la escritura queda reservada al adaptador inbound de pipelines.

#### Scenario: API intenta depender del escritor
- **WHEN** un módulo de la API importa o recibe el puerto de escritura del índice vectorial
- **THEN** la verificación de arquitectura falla

### Requirement: Cada puerto outbound tiene un doble en memoria intercambiable
Cada puerto outbound SHALL contar con una implementación en memoria que cumple el mismo contrato y que puede sustituir al adaptador real sin cambiar a los consumidores.

#### Scenario: Fake satisface el contrato
- **WHEN** se verifica cada implementación en memoria contra la definición de su puerto
- **THEN** todas satisfacen el contrato estructural del puerto correspondiente

### Requirement: El código heredado nunca se importa ni se versiona
Ningún módulo del sistema SHALL importar código del directorio heredado de referencia, y dicho directorio MUST quedar excluido del control de versiones.

#### Scenario: Import de código heredado
- **WHEN** un módulo importa algo del directorio heredado
- **THEN** la verificación de arquitectura falla

#### Scenario: Directorio heredado excluido
- **WHEN** se listan los archivos versionados
- **THEN** ninguno pertenece al directorio heredado

### Requirement: El repositorio no contiene identificadores no publicables
Los archivos versionados MUST NOT contener nombres de empleador o clientes, identificadores de cuentas de nube, URLs internas ni correos personales. Los patrones genéricos SHALL versionarse; los nombres sensibles MUST provenir de una fuente no versionada (archivo local ignorado o secreto de CI) para no publicarlos.

#### Scenario: Patrón prohibido detectado
- **WHEN** un archivo versionado contiene un patrón de la lista prohibida
- **THEN** la verificación de integración continua falla indicando archivo y línea

#### Scenario: Repositorio limpio
- **WHEN** se ejecuta el escaneo sobre los archivos versionados actuales
- **THEN** no se reportan coincidencias

#### Scenario: Fuente de nombres sensibles ausente en local
- **WHEN** se ejecuta el escaneo sin la fuente no versionada de nombres sensibles
- **THEN** se aplican solo los patrones genéricos y se emite una advertencia visible, sin fallar

### Requirement: Las verificaciones se ejecutan en integración continua
Toda propuesta de cambio al repositorio SHALL ejecutar automáticamente lint, verificación de tipos, verificación de arquitectura, escaneo de identificadores prohibidos y pruebas, y MUST bloquearse si cualquiera falla.

#### Scenario: Violación bloquea integración
- **WHEN** se envía un cambio que introduce una violación de arquitectura
- **THEN** la ejecución de integración continua termina en fallo
