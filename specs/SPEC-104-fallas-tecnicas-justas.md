# SPEC-104-fallas-tecnicas-justas — Fallas tecnicas visibles y medicion justa

Estado: draft
Iteracion: 1 (rev. 2026-11-23)
Relacionada con: [[SPEC-103-proveedor-anthropic]] (reclasifica la respuesta sin
texto de su FR-009 y completa la parte de "cortadas por `max_tokens`" de su
SC-004), [[SPEC-100-veredicto-senal-ruido]], [[SPEC-105-roles-intercambiables]]

## User Story (prioridad)

Como persona que experimenta con DSPy y GEPA, quiero que cada falla tecnica de
una llamada al LLM se clasifique por su causa, quede registrada y contada, y se
le cargue al prompt candidato solo cuando el prompt la provoco, para que los
scores y las comparaciones entre prompts midan calidad y no fallas de
infraestructura, de configuracion o del dato, y para que una corrida con
demasiadas fallas se detenga en vez de reportar resultados enganosos.
Prioridad: P1

## Contexto (estado al 2026-11-23)

Hallazgos de la revision posterior a la fase 6 de SPEC-103:

- `simple_classifier_adapter.py` y `simple_sql_adapter.py` descartan el ejemplo
  ante cualquier excepcion que no sea de conexion ni de respuesta sin texto: lo
  sacan de `scores` y `outputs`. `universal_optimizer.py` promedia sobre los
  ejemplos que sobrevivieron, asi que el baseline y el optimizado se comparan
  sobre subconjuntos distintos y la accuracy puede subir sin que nada lo avise.
  Dentro de GEPA rompe el alineamiento entre `outputs` y el batch.
  `simple_extractor_adapter.py` y `simple_rag_adapter.py` en cambio puntuan 0.
- Nada revisa `finish_reason=length`: un texto truncado se puntua como completo
  y una propuesta de reflexion truncada se adopta como candidato.
- El juez de `simple_rag_adapter.py` convierte sus fallas, y un puntaje que no
  puede leer, en score 0.0 del candidato, sin registro.
- SPEC-103 FR-009 puntua 0 toda respuesta sin texto, sin mirar su causa.
- Los avisos de los adapters son `print`; `run.json` no guarda cuantas fallas
  hubo de cada tipo.

## Alcance

Incluye: clasificacion de fallas de las llamadas de tarea, reflexion y juez;
tratamiento de cada clase en el score; registro y conteo en log y `run.json`;
umbrales de corte; metricas reportadas (baseline, optimizado, test) sobre casos
evaluados y comparacion pareada. Ambos subproyectos y todos los adapters.

Excluye: reintentos de red ya existentes (se reutilizan); cambios en la
logica de optimizacion de GEPA o DSPy; el veredicto senal-ruido de SPEC-100
(consume las metricas de esta spec, no se redefine).

## Clasificacion de fallas

Fuente de la clase: la excepcion o el `finish_reason` normalizado de LiteLLM,
nunca la sola ausencia de texto.

| Clase | Causa | Tratamiento |
|---|---|---|
| `candidato_filtro_entrada` | Filtro de contenido de entrada (antes del LLM) en un caso que paso con el prompt baseline | Score 0 del candidato |
| `candidato_formato` | Hay texto pero no respeta el formato que pide el prompt | Score 0 del candidato |
| `dato_filtro_entrada` | Filtro de entrada en un caso que tambien bloqueo al baseline | No evaluado; el caso se reporta como problematico del dataset |
| `presupuesto` | `finish_reason=length`, con texto parcial o sin texto | No evaluado; corte por umbral (FR-006) |
| `sin_texto` | Respuesta sin texto con `finish_reason=stop` o sin causa, con o sin HTTP 200 | No evaluado |
| `filtro_salida` | Filtro de salida o rechazo del proveedor (`content_filter`, `refusal`) | No evaluado |
| `infraestructura` | Red, 5xx, rate limit o timeout que persiste tras los reintentos | No evaluado |
| `evaluador` | Falla del juez o puntaje del juez ilegible | No evaluado |
| `configuracion` | 4xx de autenticacion, modelo o parametros | Corta la corrida de inmediato |

"No evaluado" significa: el caso no suma ni resta al score del candidato, se
cuenta y se registra.

## Requisitos funcionales

- FR-001 El sistema MUST clasificar cada falla de una llamada de tarea,
  reflexion o juez en una de las clases de la tabla, en un componente comun de
  `shared/` que usen todos los adapters de `gepa_standalone` y el LM y los
  envoltorios de `dspy_gepa_poc`. Ningun adapter MUST decidir el tratamiento de
  una falla por su cuenta.
- FR-002 El sistema MUST tratar cada clase como indica la tabla. Ningun caso
  MUST desaparecer en silencio de una evaluacion: el numero de casos evaluados
  mas los no evaluados MUST igualar el tamano del lote.
- FR-003 Las metricas reportadas (baseline, optimizado, test, y las que consume
  SPEC-100) MUST calcularse solo sobre casos evaluados, y la comparacion entre
  dos prompts MUST ser pareada: sobre los casos evaluados en ambos. El reporte
  MUST mostrar `n_evaluados / n_total` junto a cada metrica.
- FR-004 Para `candidato_filtro_entrada` y `dato_filtro_entrada` el sistema MUST
  conservar por caso el resultado del prompt baseline y atribuir el bloqueo
  segun la tabla.
- FR-005 Una propuesta de reflexion con falla de cualquier clase MUST
  descartarse y no adoptarse como candidato; se cuenta como falla de reflexion.
- FR-006 El sistema MUST contar las fallas por clase y por rol durante la
  corrida y MUST detenerla con un error que nombre la clase, el conteo y la
  causa probable cuando una clase supere su umbral. `presupuesto` MUST tener un
  umbral bajo y su mensaje MUST sugerir subir `max_tokens` o bajar el effort.
  Los umbrales MUST ser configurables en el YAML, con defaults documentados.
- FR-007 Cada falla MUST registrarse con `logger` (no `print`) con rol, clase,
  causa (`finish_reason` o tipo de error) e identificador del caso.
- FR-008 `run.json` MUST guardar los conteos por clase y por rol, la lista de
  casos `dato_filtro_entrada` y `n_evaluados / n_total` de cada metrica.
- FR-009 El juez MUST pedir su puntaje en una salida estructurada y MUST
  reintentar ante un puntaje ilegible antes de clasificarlo como `evaluador`.
- FR-010 La deteccion MUST ser agnostica al proveedor: se apoya en el
  `finish_reason` y en los tipos de error normalizados de LiteLLM, verificados
  para Azure, OpenAI y Anthropic.
- [NEEDS CLARIFICATION: dentro de la optimizacion (GEPA standalone y
  `dspy.GEPA`) cada caso necesita un score numerico y no existe "no evaluado".
  Opciones: puntuar 0 esos casos (contados y acotados por los umbrales de
  FR-006) o cortar la corrida ante el primer "no evaluado" durante la
  optimizacion. Las metricas reportadas de FR-003 los excluyen en ambos casos.]
- [NEEDS CLARIFICATION: valores default de los umbrales de FR-006 por clase.]
- [NEEDS CLARIFICATION: confirmar contra LiteLLM como llegan el filtro de
  entrada (error 400 de Azure), el filtro de salida y el `refusal` de
  Anthropic, para fijar la regla de deteccion de cada clase.]

## Criterios de exito (medibles, agnosticos a tecnologia)

- SC-001 Con fallas inyectadas de cada clase, el 100% de los casos queda
  evaluado o contado como no evaluado: ningun lote pierde casos sin registro.
- SC-002 Con un mismo prompt y fallas `infraestructura` inyectadas en el 10%
  de los casos, la metrica reportada coincide con la de la corrida sin fallas
  sobre los casos evaluados, y el reporte muestra `n_evaluados / n_total`.
- SC-003 Una respuesta truncada en reflexion nunca produce un candidato.
- SC-004 Superar el umbral de cualquier clase detiene la corrida con un error
  que nombra la clase; ninguna corrida que supere un umbral escribe resultados
  como si fuera valida.
- SC-005 Los conteos de `run.json` coinciden con las fallas registradas en el
  log en el 100% de las corridas de prueba.
- SC-006 Sin fallas, scores y `run.json` de una corrida son iguales a los de
  antes del cambio salvo los campos nuevos (sin regresion).

## Escenarios (Given/When/Then)

- Given un clasificador con 30 casos y un 5xx persistente en 3, When se evalua,
  Then la metrica se calcula sobre 27, el reporte muestra 27/30 y el log y
  `run.json` cuentan 3 `infraestructura`.
- Given una respuesta con `finish_reason=length`, When se evalua el caso, Then
  queda no evaluado como `presupuesto`; y When las fallas `presupuesto` superan
  su umbral, Then la corrida se detiene sugiriendo subir `max_tokens` o bajar el
  effort.
- Given un caso bloqueado por el filtro de entrada con el candidato y no con el
  baseline, When se evalua, Then puntua 0 como `candidato_filtro_entrada`.
- Given un caso bloqueado por el filtro de entrada con el candidato y con el
  baseline, When se evalua, Then queda no evaluado y figura en la lista de
  casos problematicos de `run.json`.
- Given un juez que devuelve un puntaje ilegible, When se agotan los
  reintentos, Then el caso queda no evaluado como `evaluador` y el candidato no
  recibe 0.
- Given una propuesta de reflexion truncada, When GEPA la recibe, Then se
  descarta y se cuenta, y el candidato vigente no cambia.
- Given un 401 de autenticacion, When ocurre en cualquier rol, Then la corrida
  se detiene de inmediato.

## Coverage mapping (requisito -> derivado)

| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | pendiente |
| FR-002 | pendiente |
| FR-003 | pendiente |
| FR-004 | pendiente |
| FR-005 | pendiente |
| FR-006 | pendiente |
| FR-007 | pendiente |
| FR-008 | pendiente |
| FR-009 | pendiente |
| FR-010 | pendiente |
| SC-001 | pendiente |
| SC-002 | pendiente |
| SC-003 | pendiente |
| SC-004 | pendiente |
| SC-005 | pendiente |
| SC-006 | pendiente |
