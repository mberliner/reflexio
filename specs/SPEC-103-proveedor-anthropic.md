# SPEC-103-proveedor-anthropic — Anthropic como proveedor verificado

Estado: draft
Iteracion: 1 (rev. 2026-11-22)
Relacionada con: [[SPEC-104-roles-intercambiables]], docs/LLM_CONFIG.md

## User Story (prioridad)

Como persona que experimenta con DSPy y GEPA, quiero declarar cualquier modelo
Claude de la matriz de soporte (desde Haiku 4.5 hasta Opus 5.5 y Fable) como
estudiante o como profesor en cualquiera de los dos subproyectos
(`dspy_gepa_poc` y `gepa_standalone`) solo cambiando el `.env`, para comparar su
rendimiento real contra los modelos actuales sin tocar codigo ni recibir errores
de la API.
Prioridad: P1

## Contexto (estado al 2026-11-22)

El formato `anthropic/<id>` ya esta documentado y LiteLLM 1.81.7 reconoce los
IDs, pero hoy no funciona con los modelos recientes:

- `temperature` siempre se envia. `drop_params` no la quita porque LiteLLM la
  declara soportada para todos los Claude.
- Los modelos que razonan por defecto consumen `max_tokens` en ese razonamiento,
  y algunos adapters piden 50-200.
- El parametro `reasoning_effort` de LiteLLM se traduce a
  `thinking.budget_tokens`, que los modelos 4.7+ y 5.x rechazan con 400. En
  cambio, `output_config={"effort": ...}` pasado directo a `litellm.completion`
  llega intacto a la API (verificado interceptando el pedido HTTP, sin red).
  `extra_body` NO sirve: LiteLLM lo envia literal como campo del cuerpo.
- LiteLLM envia `anthropic-version: 2023-06-01`, por lo que la regla de la API
  `2026-10-21` (rechazo de `temperature` en todos los modelos) no aplica todavia.

## Alcance

Incluye: API directa de Anthropic via LiteLLM, en ambos subproyectos, para los
roles tarea, reflexion y juez.

Excluye: Bedrock, Vertex AI y Foundry; SDK nativo de Anthropic (el proyecto se
mantiene sobre LiteLLM por arquitectura, ver `docs/ARCHITECTURE.md`); prompt
caching, batches, tools y structured outputs nativos; Mythos (requiere
organizacion verificada); `claude-sonnet-4-5` (deprecado, se retira el
2026-11-30); mezclar proveedores entre roles (eso es
[[SPEC-104-roles-intercambiables]]).

## Matriz de soporte

Esta tabla es el contrato de la capacidad. El codigo la implementa en un unico
lugar (FR-002) y `docs/LLM_CONFIG.md` la referencia, sin copiarla.

| Modelo | `temperature` | `effort` aceptado | Razonamiento si no se configura | Apagar razonamiento | Verificacion |
|---|---|---|---|---|---|
| `claude-haiku-4-5` | se envia | no se envia (da error) | apagado | no-op (ya esta apagado) | real |
| `claude-opus-4-5` | se envia | low, medium, high | apagado | no-op | sin red |
| `claude-sonnet-4-6` | se envia | low, medium, high, max | apagado | no-op | real |
| `claude-opus-4-6` | se envia | low, medium, high, max | apagado | no-op | sin red |
| `claude-opus-4-7`, `claude-opus-4-8` | no se envia | low..max | apagado | no-op | sin red |
| `claude-sonnet-5` | no se envia | low..max | adaptativo | `disabled` | real |
| `claude-opus-5` | no se envia | low..max | adaptativo | `disabled`, solo con effort <= high | sin red |
| `claude-haiku-5-5` | no se envia (solo admite el default) | low..max | adaptativo | `disabled`, solo con effort <= high | real |
| `claude-sonnet-5-5` | no se envia (solo admite el default) | low..max | adaptativo | `between_tools`, solo con effort <= high | real |
| `claude-opus-5-5` | no se envia | low..max | adaptativo | no permitido | sin red |
| `claude-fable-5`, `claude-fable-5-1`, `claude-fable-5-2` | no se envia | low..max | siempre activo | no permitido | sin red |

`low..max` = low, medium, high, xhigh, max. "real" = verificado con API real
(acceso disponible hasta Sonnet 5.5); "sin red" = verificado solo por tests que
construyen el pedido sin llamar a la API.

## Requisitos funcionales

- FR-001 El sistema MUST aceptar `anthropic/<id>` en cualquier
  `LLM_MODEL_<ROL>` para todos los modelos de la matriz de soporte. Un ID
  `anthropic/` fuera de la matriz SHOULD funcionar sin restricciones aplicadas y
  MUST emitir un aviso al arrancar.
- FR-002 Las restricciones de la matriz MUST resolverse en un unico punto
  (`shared/llm/config.py`) y aplicarse igual en los tres caminos de llamada:
  `get_dspy_lm`, `get_lm_function` y `call_llm`. Ningun subproyecto MUST
  reimplementarlas.
- FR-003 El sistema MUST NOT enviar `temperature` ni `top_p` a los modelos
  marcados "no se envia", aunque vengan del `.env`, del YAML
  (`models.temperature`) o de un adapter.
- FR-004 El esfuerzo MUST configurarse por rol con `LLM_EFFORT_<ROL>` y enviarse
  como `output_config.effort` (nunca como `reasoning_effort`). Si no se configura,
  MUST enviarse `medium` a los modelos que aceptan effort, y nada a los que no.
  Un valor que el modelo no acepta (por ejemplo `xhigh` en Opus 4.5) MUST
  producir un error de configuracion al validar.
- FR-005 El razonamiento MUST poder apagarse por rol con `LLM_THINKING_<ROL>=off`
  (valor por defecto: `default`, que no envia nada). Con `off` el sistema MUST
  enviar el mecanismo de apagado de la matriz para ese modelo, y MUST producir un
  error de configuracion al validar cuando el modelo no lo permite o cuando la
  combinacion con el effort es invalida.
- FR-006 Para los modelos cuyo razonamiento queda activo (adaptativo o siempre
  activo, y `LLM_THINKING_<ROL>` distinto de `off`), `max_tokens` MUST elevarse a
  un minimo de 16000, el mismo tope que ya usan los reasoning models de OpenAI
  (`_REASONING_MIN_MAX_TOKENS`). Los tokens no usados no se cobran.
- FR-007 `validate()` MUST NOT exigir `LLM_API_BASE` ni `LLM_API_VERSION` para
  `anthropic/`, y `validate_connection()` MUST funcionar con todos los modelos
  de la matriz (la prueba de conexion respeta FR-003 a FR-006).
- FR-008 Una respuesta sin texto (rechazo por politica, salida vacia o cortada
  por `max_tokens`) MUST registrarse como prediccion fallida con su causa en el
  log, y MUST NOT interrumpir la corrida ni descartarse en silencio.
- FR-009 `describe()` MUST mostrar los parametros efectivos enviados:
  `temperature` enviada u omitida, effort, modo de razonamiento y `max_tokens`
  final, indicando cuando un valor de config fue ignorado o elevado.
- FR-010 El calculo de costo (`shared/analysis/roi_calculator.py`) MUST tener
  precio para cada modelo de la matriz y MUST reconocer el prefijo `anthropic/`
  (hoy `normalize_model` solo quita `azure/`). Los tokens de razonamiento MUST
  contarse como tokens de salida.
- FR-011 El registro de cada corrida MUST guardar los parametros efectivos de
  cada rol (temperatura enviada u omitida, effort, modo de razonamiento,
  `max_tokens`), para que el criterio de comparabilidad de
  [[SPEC-100-veredicto-senal-ruido]] no trate como equivalentes corridas con
  configuraciones distintas.
- FR-012 `docs/LLM_CONFIG.md` MUST documentar el formato, las variables
  `LLM_EFFORT_<ROL>` y `LLM_THINKING_<ROL>` con IDs vigentes, y MUST enlazar a la
  matriz de esta spec en lugar de copiarla.

## Criterios de exito (medibles, agnosticos a tecnologia)

- SC-001 Para el 100% de los modelos de la matriz y para cada combinacion
  valida de effort y razonamiento, los parametros construidos por los tres
  caminos de llamada coinciden con la matriz y no contienen ningun parametro que
  ese modelo rechace (verificado sin llamar a la API).
- SC-002 Para el 100% de las combinaciones invalidas de la matriz (apagar en
  Opus 5.5 o Fable, effort no aceptado, apagar con effort xhigh/max donde no se
  permite), la validacion falla antes de la primera llamada con un mensaje que
  nombra modelo y parametro.
- SC-003 El caso Email Urgency corre de punta a punta en cada subproyecto con API
  real para cada modelo "real" de la matriz (Haiku 4.5, Sonnet 4.6, Sonnet 5,
  Haiku 5.5, Sonnet 5.5) como estudiante y profesor a la vez, mas una corrida con
  `LLM_THINKING_TASK=off` en Haiku 5.5 y en Sonnet 5.5, con 0 errores 4xx de la
  API. El gasto total de esta verificacion MUST NOT superar USD 10.
- SC-004 En esas corridas, menos del 1% de las predicciones terminan sin texto o
  cortadas por `max_tokens`, y todas las que ocurren aparecen en el log con su
  causa.
- SC-005 El costo reportado por cada corrida de SC-003 sale del uso real medido y
  de precios de la tabla, sin el aviso de "modelo sin precio configurado".
- SC-006 Un `.env` existente con modelos Azure/OpenAI produce exactamente los
  mismos parametros enviados que antes del cambio (sin regresion).

## Escenarios (Given/When/Then)

- Given `LLM_MODEL_TASK=anthropic/claude-opus-5-5` y un YAML con
  `models.temperature: 0.1`, When se construyen los parametros, Then no se envia
  `temperature`, se envia `output_config.effort=medium`, `max_tokens` es al menos
  16000 y `describe()` informa lo omitido y lo elevado.
- Given `LLM_MODEL_TASK=anthropic/claude-haiku-4-5` y `temperature: 0.1`, When se
  construyen los parametros, Then se envia `temperature=0.1` y no se envia effort.
- Given `LLM_MODEL_TASK=anthropic/claude-sonnet-5-5` y `LLM_THINKING_TASK=off`,
  When se construyen los parametros, Then se envia
  `thinking={"type": "between_tools"}` sin otros campos de thinking, y no se
  eleva `max_tokens`.
- Given `LLM_MODEL_REFLECTION=anthropic/claude-opus-5-5` y
  `LLM_THINKING_REFLECTION=off`, When arranca la corrida, Then la validacion falla
  indicando que ese modelo no permite apagar el razonamiento.
- Given `LLM_MODEL_TASK=anthropic/claude-opus-4-5` y `LLM_EFFORT_TASK=xhigh`, When
  arranca la corrida, Then la validacion falla indicando los valores aceptados.
- Given un `.env` con `LLM_MODEL_*=anthropic/...` y sin `LLM_API_BASE`, When se
  ejecuta `validate()`, Then no hay error de configuracion.
- Given el modelo rechaza responder un caso por politica, When se evalua ese
  caso, Then cuenta como fallo, queda en el log con la causa y la corrida sigue.

## Riesgos

- Si una version futura de LiteLLM pasa a enviar `anthropic-version: 2026-10-21`,
  Haiku 4.5, Opus 4.5 y los 4.6 tambien rechazaran `temperature`. SC-001 MUST
  incluir un test que fije el header esperado, para que el cambio no pase
  inadvertido al actualizar LiteLLM.
- Los modelos con temperatura no fija hacen mas ruidosas las comparaciones:
  medir con N seeds segun `docs/PROTOCOLO_N_SEEDS.md`.

## Coverage mapping (requisito -> derivado)

| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | tabla de familias en `shared/llm/config.py`; `tests/test_shared_llm.py` (pendiente) |
| FR-002 | `LLMConfig.to_kwargs` y restricciones por familia; usado por `get_dspy_lm`, `get_lm_function`, `gepa_standalone/core/llm_factory.py::call_llm` (pendiente) |
| FR-003 | idem FR-002; test parametrizado por modelo (pendiente) |
| FR-004 | `LLMConfig.from_env` (`LLM_EFFORT_<ROL>`) + validacion; test (pendiente) |
| FR-005 | `LLMConfig.from_env` (`LLM_THINKING_<ROL>`) + validacion; test (pendiente) |
| FR-006 | idem FR-002; test (pendiente) |
| FR-007 | `LLMConfig.validate`, `LLMConfig.validate_connection`; test (pendiente) |
| FR-008 | `get_lm_function`, `call_llm`, metricas DSPy (`dspy_gepa_poc/metrics.py`); test (pendiente) |
| FR-009 | `LLMConfig.describe`; test (pendiente) |
| FR-010 | `shared/analysis/roi_calculator.py` (`DEFAULT_PRICING`, `normalize_model`); `tests/test_shared_analysis.py` (pendiente) |
| FR-011 | `dspy_gepa_poc/reflexio_declarativa.py`, `gepa_standalone/universal_optimizer.py`, `shared/logging/csv_writer.py` (pendiente) |
| FR-012 | `docs/LLM_CONFIG.md` (pendiente) |
| SC-001 | test parametrizado sobre la matriz completa, sin red, incluido el header `anthropic-version` (pendiente) |
| SC-002 | test parametrizado sobre las combinaciones invalidas (pendiente) |
| SC-003 | corridas manuales con API real, registradas en `historial/sdd.md` (pendiente) |
| SC-004 | conteo sobre las predicciones volcadas de las corridas de SC-003 (pendiente) |
| SC-005 | `run.json` / CSV de las corridas de SC-003 (pendiente) |
| SC-006 | test de regresion con modelos `azure/` y `openai/` (pendiente) |
