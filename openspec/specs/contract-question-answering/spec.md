# contract-question-answering Specification

## Purpose

Permite hacer preguntas en lenguaje natural sobre los contratos indexados y recibir respuestas basadas únicamente en fragmentos recuperados del índice, con citas verificables de documento y páginas.

## Requirements

### Requirement: Recuperación de contexto por similitud semántica
Para cada pregunta, el sistema SHALL recuperar del índice los fragmentos más similares a la pregunta, hasta un número máximo configurable, ordenados de mayor a menor similitud. Si la pregunta incluye tipos de cláusula, MUST considerar solo fragmentos de esos tipos.

#### Scenario: Pregunta sin filtro
- **WHEN** se pregunta sobre un tema presente en los contratos indexados
- **THEN** el contexto usado para responder contiene a lo sumo el número máximo configurado de fragmentos, ordenados por similitud

#### Scenario: Pregunta con filtro por tipo de cláusula
- **WHEN** se pregunta indicando uno o más tipos de cláusula
- **THEN** solo se usan fragmentos clasificados con alguno de esos tipos

### Requirement: Respuesta basada solo en el contexto recuperado
El sistema SHALL generar la respuesta usando exclusivamente los fragmentos recuperados para esa pregunta. Cuando los fragmentos no contienen la información pedida, la respuesta MUST decirlo en lugar de inventarla.

#### Scenario: Información presente
- **WHEN** los fragmentos recuperados contienen la respuesta a la pregunta
- **THEN** la respuesta la expone y está respaldada por al menos una cita

#### Scenario: Información ausente en el contexto
- **WHEN** los fragmentos recuperados no tratan lo que se pregunta
- **THEN** la respuesta indica que los contratos recuperados no contienen esa información

### Requirement: Cada cita identifica documento y páginas
Toda cita de una respuesta SHALL identificar el documento, el rango de páginas y el extracto que la respalda, y MUST corresponder a uno de los fragmentos recuperados para esa pregunta.

#### Scenario: Citas verificables
- **WHEN** se recibe una respuesta con citas
- **THEN** cada cita trae documento, página inicial, página final y un extracto no vacío que pertenece a un fragmento recuperado para esa pregunta

### Requirement: Índice vacío o sin coincidencias
Si la recuperación no devuelve ningún fragmento, el sistema SHALL responder que no se encontró información en los contratos indexados, sin citas y sin invocar al modelo generador.

#### Scenario: Índice sin fragmentos
- **WHEN** se pregunta y el índice no devuelve fragmentos
- **THEN** la respuesta indica que no hay información, no trae citas y no se registra uso del modelo generador

### Requirement: Validación de la pregunta
El sistema SHALL rechazar como error del cliente una pregunta vacía, compuesta solo de espacios o más larga que el máximo permitido, así como tipos de cláusula desconocidos, sin consultar el índice ni el modelo.

#### Scenario: Pregunta vacía
- **WHEN** se envía una pregunta vacía o solo con espacios
- **THEN** la solicitud termina con un error de validación del cliente

#### Scenario: Tipo de cláusula desconocido
- **WHEN** se envía un tipo de cláusula que no existe en la taxonomía
- **THEN** la solicitud termina con un error de validación del cliente

### Requirement: Errores de proveedores explícitos
Si un proveedor externo (codificación de la pregunta o generación de la respuesta) no está disponible o limita el uso, el sistema SHALL responder con un error de servicio no disponible que lo indique, sin devolver una respuesta parcial. Si el modelo rechaza responder, MUST devolver un error que lo indique.

#### Scenario: Límite de uso del proveedor
- **WHEN** el proveedor de embeddings o el de generación responde que se excedió su límite de uso
- **THEN** la solicitud termina con un error de servicio no disponible que indica reintentar más tarde

#### Scenario: Proveedor caído
- **WHEN** un proveedor no responde o falla por un error de servidor
- **THEN** la solicitud termina con un error de servicio no disponible

#### Scenario: Respuesta rechazada
- **WHEN** el modelo generador rechaza responder la pregunta
- **THEN** la solicitud termina con un error que indica que la respuesta fue rechazada

### Requirement: Registro del costo de cada respuesta
Cada respuesta generada por el modelo SHALL registrar la operación, el modelo, los tokens de entrada y salida y el costo estimado según los precios configurados.

#### Scenario: Uso registrado
- **WHEN** se responde una pregunta usando el modelo generador
- **THEN** existe un registro de uso con el modelo de generación, sus tokens de entrada y salida y su costo estimado

### Requirement: La API de preguntas funciona sin servicios externos en modo de prueba
Con la configuración de dobles en memoria activa, el sistema SHALL responder preguntas de punta a punta sin abrir conexiones de red.

#### Scenario: Pregunta con dobles en memoria
- **WHEN** se indexa un documento y se pregunta por su contenido con dobles en memoria y la red bloqueada
- **THEN** la respuesta cita ese documento y no se intentó ninguna conexión de red
