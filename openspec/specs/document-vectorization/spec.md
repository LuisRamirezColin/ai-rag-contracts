# document-vectorization Specification

## Purpose

Convierte cada documento ingerido en fragmentos buscables por similitud semántica, cada uno con el rango de páginas de donde proviene, y mantiene el índice vectorial consistente y al día para que las respuestas puedan citar documento y página.

## Requirements

### Requirement: Fragmentación con ubicación en páginas
El sistema SHALL dividir el texto de un documento ingerido en fragmentos de tamaño acotado por configuración, con un solapamiento configurable entre fragmentos consecutivos. Cada fragmento MUST registrar el rango de páginas que abarca y MUST contener texto visible.

#### Scenario: Documento corto
- **WHEN** se vectoriza un documento cuyo texto completo cabe en un fragmento
- **THEN** se produce un único fragmento cuyo rango de páginas va de la primera a la última página con texto

#### Scenario: Documento largo
- **WHEN** se vectoriza un documento cuyo texto supera varias veces el tamaño máximo
- **THEN** ningún fragmento supera el tamaño máximo, fragmentos consecutivos comparten texto según el solapamiento y la unión de los fragmentos cubre todo el texto

#### Scenario: Fragmento que cruza un salto de página
- **WHEN** un fragmento contiene texto del final de una página y del inicio de la siguiente
- **THEN** su rango de páginas incluye ambas páginas

#### Scenario: Páginas en blanco
- **WHEN** un documento tiene páginas sin texto entre páginas con texto
- **THEN** no se produce ningún fragmento vacío

### Requirement: Cada fragmento indexado tiene un vector del modelo configurado
El sistema SHALL calcular un vector por fragmento con el modelo de embeddings configurado, codificado como documento (no como consulta), y MUST rechazar vectores cuya dimensión no coincida con la del índice.

#### Scenario: Vectores completos
- **WHEN** se vectoriza un documento que produce N fragmentos
- **THEN** el índice contiene N fragmentos de ese documento, cada uno con un vector de la dimensión configurada

#### Scenario: Dimensión incorrecta
- **WHEN** el modelo devuelve vectores de una dimensión distinta a la del índice
- **THEN** la vectorización falla sin modificar los fragmentos existentes del documento

### Requirement: Las consultas se codifican de forma compatible con los documentos
El sistema SHALL ofrecer la codificación de una consulta de texto con el mismo modelo y dimensión que los fragmentos indexados, diferenciada de la codificación de documentos.

#### Scenario: Consulta codificada
- **WHEN** se codifica una pregunta de texto
- **THEN** se obtiene un único vector de la misma dimensión que los fragmentos indexados

### Requirement: El índice de un documento se reemplaza de forma atómica
Vectorizar un documento SHALL reemplazar todos sus fragmentos anteriores por los nuevos en una sola operación. Un lector MUST ver o el conjunto anterior completo o el nuevo completo, nunca una mezcla; los fragmentos de otros documentos MUST NOT cambiar.

#### Scenario: Revectorización
- **WHEN** se vectoriza de nuevo un documento ya indexado
- **THEN** el índice contiene exactamente los fragmentos de la última vectorización para ese documento

#### Scenario: Fallo a mitad de la vectorización
- **WHEN** la obtención de vectores falla después de fragmentar el documento
- **THEN** los fragmentos previos del documento siguen intactos en el índice

#### Scenario: Otros documentos no se tocan
- **WHEN** se revectoriza un documento
- **THEN** los fragmentos de los demás documentos permanecen iguales

### Requirement: Solo se vectorizan documentos ingeridos
El sistema SHALL vectorizar únicamente documentos con estado ingerido. Para un documento inexistente o fallido MUST terminar con un error que indique que no está disponible y MUST NOT modificar el índice.

#### Scenario: Documento fallido
- **WHEN** se solicita vectorizar un documento en estado fallido
- **THEN** la solicitud termina con un error de documento no disponible y el índice no cambia

### Requirement: Vectorización automática tras la ingesta
El lado escritor SHALL vectorizar cada documento inmediatamente después de ingerirlo con éxito, sin intervención manual. Si la ingesta falla, la vectorización de ese documento MUST NOT ejecutarse.

#### Scenario: Documento nuevo
- **WHEN** un documento nuevo se ingiere con éxito
- **THEN** a continuación queda vectorizado y sus fragmentos están en el índice

#### Scenario: Ingesta fallida
- **WHEN** la ingesta de un documento termina en estado fallido
- **THEN** no se intenta vectorizarlo

### Requirement: Registro del consumo de tokens por documento
Cada vectorización SHALL registrar la operación, el modelo, los tokens consumidos, el costo estimado según el precio configurado y el documento al que corresponde.

#### Scenario: Uso registrado
- **WHEN** se vectoriza un documento
- **THEN** existe un registro de uso con el modelo de embeddings, los tokens de entrada consumidos, su costo estimado y el identificador del documento

### Requirement: La vectorización funciona sin servicios externos en modo de prueba
Con la configuración de dobles en memoria activa, el sistema SHALL fragmentar, vectorizar e indexar un documento sin abrir conexiones de red.

#### Scenario: Vectorización con dobles en memoria
- **WHEN** se ingiere y vectoriza un documento con dobles en memoria y la red bloqueada
- **THEN** el índice en memoria contiene sus fragmentos y no se intentó ninguna conexión de red
