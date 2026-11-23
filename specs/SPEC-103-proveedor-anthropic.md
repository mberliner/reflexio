# SPEC-103-proveedor-anthropic — Anthropic como proveedor verificado

Estado: active
Iteracion: 3 (rev. 2026-11-23)
Relacionada con: [[SPEC-104-fallas-tecnicas-justas]] (reemplaza FR-009 en los roles tarea y juez y cubre los cortes de SC-004), [[SPEC-105-roles-intercambiables]], [[SPEC-100-veredicto-senal-ruido]],
[[SPEC-101-triaje-casos-nseeds]], docs/LLM_CONFIG.md, docs/METADATA_REPRODUCIBILIDAD.md,
docs/ANALISIS_UTILIDADES.md, docs/GEPA_MANEJO_ERRORES.md, docs/PROTOCOLO_N_SEEDS.md
Plan de implementacion: docs/plans/PLAN_SPEC-103_proveedor_anthropic.md

## User Story (prioridad)

Como persona que experimenta con DSPy y GEPA, quiero declarar cualquier modelo
Claude de la matriz de soporte (desde Haiku 4.5 hasta Opus 5.5 y Fable) como
estudiante o como profesor en cualquiera de los dos subproyectos
(`dspy_gepa_poc` y `gepa_standalone`) solo cambiando el `.env`, para comparar su
rendimiento real contra los modelos actuales sin tocar codigo ni recibir errores
de la API. El juez de `gepa_standalone` (caso RAG) usa la configuracion del
profesor, por lo que tambien queda cubierto.
Prioridad: P1

## Contexto (estado al 2026-11-22, LiteLLM 1.108.5)

El formato `anthropic/<id>` ya esta documentado y LiteLLM reconoce los IDs, pero
hoy no funciona con los modelos recientes. Comportamiento de LiteLLM 1.108.5
(fijado en `requirements.txt`) verificado sin red en
`tests/test_litellm_regression.py`:

- `temperature`: con `drop_params=True` LiteLLM la elimina en los modelos que no
  la aceptan (Opus 4.7 en adelante); con `drop_params=False` lanza
  `UnsupportedParamsError`. `get_lm_function`, `call_llm` y `SimpleRAGAdapter`
  activan `drop_params`; `get_dspy_lm` no. Ademas, `LLMConfig` siempre incluye
  `temperature` en `to_kwargs()`, y `describe()`/metadata no saben si se envio.
  `dspy.LM` (3.2.1) no inyecta un default: si la clave no viene, el pedido sale
  sin `temperature` (verificado sin red).
- `max_tokens`: los modelos que razonan por defecto lo consumen en ese
  razonamiento, y algunos adapters piden 50-400.
- `reasoning_effort` de LiteLLM se traduce a `output_config.effort` mas
  `thinking={"type": "adaptive", "display": "summarized"}`. Esa inyeccion
  implicita de `thinking` choca con apagar el razonamiento y lo enciende en
  modelos donde viene apagado. En cambio, `output_config={"effort": ...}` pasado
  directo a `litellm.completion` llega intacto sin agregar `thinking`.
  `extra_body` NO sirve: LiteLLM lo envia literal como campo del cuerpo.
- LiteLLM envia `anthropic-version: 2023-06-01`, por lo que la regla de la API
  `2026-10-21` (rechazo de `temperature` en todos los modelos) no aplica todavia.
  `api_version` (de Azure) no altera el pedido a Anthropic.

## Alcance

Incluye: API directa de Anthropic via LiteLLM, en ambos subproyectos, para los
roles tarea, reflexion y juez (este ultimo hereda la configuracion de reflexion
hasta que [[SPEC-105-roles-intercambiables]] lo haga configurable; no existen
`LLM_EFFORT_JUDGE` ni `LLM_THINKING_JUDGE` en esta spec).

Excluye: Bedrock, Vertex AI y Foundry; SDK nativo de Anthropic (el proyecto se
mantiene sobre LiteLLM por arquitectura, ver `docs/ARCHITECTURE.md`); prompt
caching, batches, tools y structured outputs nativos; Mythos (requiere
organizacion verificada); `claude-sonnet-4-5` (deprecado, se retira el
2026-11-30: se trata como ID fuera de la matriz, FR-001); mezclar proveedores
entre roles (eso es [[SPEC-105-roles-intercambiables]]); configurar effort o
razonamiento desde el YAML (ver Decisiones); modificar el criterio de
comparabilidad de [[SPEC-100-veredicto-senal-ruido]] (ver FR-011).

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
| `claude-haiku-5-5` | no se envia | low..max | adaptativo | `disabled`, solo con effort <= high | real |
| `claude-sonnet-5-5` | no se envia | low..max | adaptativo | `between_tools`, solo con effort <= high | real |
| `claude-opus-5-5` | no se envia | low..max | adaptativo | no permitido | sin red |
| `claude-fable-5`, `claude-fable-5-1`, `claude-fable-5-2` | no se envia | low..max | siempre activo | no permitido | sin red |

Notas de la matriz:

- `low..max` = low, medium, high, xhigh, max.
- "no se envia": la API de Haiku 5.5 y Sonnet 5.5 admite solo el valor por
  defecto; para el sistema es igual que el resto (FR-003: se omite siempre,
  cualquiera sea el valor configurado).
- Mecanismo de apagado en el pedido: `disabled` = `thinking={"type": "disabled"}`;
  `between_tools` = `thinking={"type": "between_tools"}`. En ambos casos sin otros
  campos de `thinking`. "no-op" = `LLM_THINKING_<ROL>=off` es valido y no envia
  `thinking`.
- Cada fila cubre el alias y sus snapshots con fecha (`<alias>-YYYYMMDD`).
- "real" = verificado con API real (acceso disponible hasta Sonnet 5.5); "sin
  red" = verificado solo por tests que construyen el pedido sin llamar a la API.

## Requisitos funcionales

- FR-001 El sistema MUST aceptar `anthropic/<id>` en cualquier
  `LLM_MODEL_<ROL>` para todos los modelos de la matriz de soporte. Un `<id>`
  que sea un alias de la matriz seguido de `-YYYYMMDD` MUST recibir las
  restricciones de ese alias. Un ID `anthropic/` fuera de la matriz (incluido
  `claude-sonnet-4-5`) SHOULD funcionar sin restricciones aplicadas y MUST emitir
  un aviso al arrancar que nombre el ID.
- FR-002 Las restricciones de la matriz MUST resolverse en un unico punto
  (`shared/llm/config.py`) y aplicarse igual en los cuatro caminos de llamada:
  `get_dspy_lm`, `get_lm_function`, `call_llm` y
  `SimpleRAGAdapter._call_llm_with_retry` (tarea y juez). Los subproyectos MUST
  NOT reimplementarlas. Un adapter que fije su propio `max_tokens` por llamada
  MUST hacerlo antes de aplicar las restricciones, para que FR-006 lo eleve.
- FR-003 El sistema MUST NOT enviar `temperature` a los modelos marcados "no se
  envia", venga del default de `LLMConfig`, del YAML (`models.temperature`), de
  un override de `from_env` o del constructor de un adapter. La omision MUST
  hacerse quitando la clave de los kwargs (no confiar en `drop_params`, que
  `get_dspy_lm` no activa).
- FR-004 El esfuerzo MUST configurarse por rol con `LLM_EFFORT_<ROL>` y enviarse
  como `output_config={"effort": <valor>}` (MUST NOT usarse `reasoning_effort`,
  porque LiteLLM inyecta `thinking` adaptativo). Si no se configura, MUST
  enviarse `medium` a los modelos que aceptan effort, y nada a los que no. Un
  valor que el modelo no acepta (por ejemplo `xhigh` en Opus 4.5, o cualquier
  valor en Haiku 4.5) MUST producir un error de configuracion al validar que
  liste los valores aceptados.
- FR-005 El razonamiento MUST poder apagarse por rol con `LLM_THINKING_<ROL>=off`
  (valor por defecto: `default`, que no envia nada). Con `off` el sistema MUST
  enviar el mecanismo de apagado de la matriz para ese modelo (nada en los
  no-op), y MUST producir un error de configuracion al validar cuando el modelo
  no lo permite o cuando la combinacion con el effort es invalida.
- FR-006 Para los modelos cuyo razonamiento queda activo (adaptativo o siempre
  activo, y `LLM_THINKING_<ROL>` distinto de `off`), `max_tokens` MUST elevarse a
  un minimo de 16000, el mismo tope que ya usan los reasoning models de OpenAI
  (`_REASONING_MIN_MAX_TOKENS`). Los tokens no usados no se cobran.
- FR-007 Para `anthropic/`, `validate()` MUST NOT exigir `LLM_API_BASE` ni
  `LLM_API_VERSION`; `api_version` MUST NOT enviarse; y un `LLM_API_BASE`
  presente en el `.env` MUST NOT enviarse y MUST producir un aviso al arrancar
  (evita redirigir el pedido al endpoint Azure que quedo en un `.env` editado).
  [NEEDS CLARIFICATION: si hace falta un `api_base` propio para Anthropic (proxy,
  gateway), el mecanismo se define en [[SPEC-105-roles-intercambiables]] FR-003
  (`LLM_API_BASE_<ROL>`); en esta spec no hay override.]
  `validate_connection()` MUST funcionar con todos los modelos de la matriz (la
  prueba de conexion respeta FR-003 a FR-006).
- FR-008 Variables `LLM_EFFORT_<ROL>` y `LLM_THINKING_<ROL>`: el parseo MUST
  ignorar mayusculas y espacios; una variable vacia MUST equivaler a no
  configurada; un valor fuera de los permitidos (effort: low..max; thinking:
  `default`, `off`) MUST producir un error de configuracion al validar que liste
  los valores permitidos.
- FR-009 Respuesta sin texto (contenido `None` o vacio: rechazo por politica,
  salida vacia o cortada por `max_tokens`). No es un error tecnico en el sentido
  de `docs/GEPA_MANEJO_ERRORES.md` y MUST NOT descartarse en silencio ni
  interrumpir la corrida. Su causa (`stop_reason` / `finish_reason`) MUST
  registrarse en el log. Por rol:
  - tarea: MUST contar como prediccion fallida con score 0.0, en todos los
    adapters de `gepa_standalone/adapters/` y en la metrica DSPy (mismo patron que
    ya usa `simple_extractor_adapter.py`, que preserva `len(outputs)`).
  - juez: MUST contar como fallo de evaluacion del caso (score 0.0), con causa
    que distinga que el fallo fue del juez.
  - reflexion: un texto vacio (tras `strip()`) MUST NOT usarse como prompt
    candidato. El LM de reflexion MUST lanzar una excepcion con la causa en lugar
    de devolverlo, en ambos subproyectos: en `get_lm_function(role="reflection")`
    para `gepa_standalone`, y en el LM que `get_dspy_lm` entrega como
    `reflection_lm` a `dspy.GEPA` en `dspy_gepa_poc`. MUST NOT devolverse el
    prompt actual como sustituto (crearia un candidato duplicado que gasta
    evaluaciones). Motivo (GEPA 0.0.27 + dspy 3.2.1, verificado en el codigo):
    `ReflectiveMutationProposer.propose` atrapa cualquier excepcion de la
    propuesta, la registra en el log de GEPA y saltea la iteracion conservando el
    candidato vigente; en cambio un texto vacio pasa por
    `InstructionProposalSignature.output_extractor` como instruccion `""` y se
    evalua como candidato nuevo. Hoy un contenido `None` ya cae en ese `except`
    por accidente (`.strip()` sobre `None` en GEPA, `TypeError` en
    `DspyAdapter.stripped_lm_call`), pero sin causa legible. Si D-018 actualiza
    GEPA/DSPy, este comportamiento MUST reverificarse.
  - Nota de implementacion (2c, RESOLUCION B-2c-1): en `dspy_gepa_poc` la tarea
    tambien lanza `EmptyResponseError` y el envoltorio del programa
    (`dspy_gepa_poc/empty_response.py`) la convierte en prediccion fallida con
    score 0.0 en `dspy.GEPA` y en los `Evaluate` de `reflexio_declarativa.py` y
    `scripts/baseline_only.py`. Excepcion aceptada: la inferencia directa
    (`run_inference.py` y scripts sin `Evaluate`) corta ante una respuesta sin
    texto (deuda D-020). Costo: `ChatAdapter` reintenta con `JSONAdapter`, asi
    que una respuesta de tarea sin texto cuesta 3 llamadas.
- FR-010 `describe()` MUST mostrar los parametros efectivos enviados:
  `temperature` enviada u omitida, effort, modo de razonamiento y `max_tokens`
  final, indicando cuando un valor de config fue ignorado o elevado. Cuando un
  adapter fija `max_tokens` por llamada, lo reportado MUST ser el valor efectivo
  de esas llamadas, no el de `LLMConfig`.
- FR-011 El calculo de costo (`shared/analysis/roi_calculator.py`) MUST tener
  precio para cada modelo de la matriz (snapshots incluidos via FR-001). La
  fuente de los precios MUST ser la pagina oficial de precios de Anthropic, con
  la fecha de consulta registrada junto a la tabla sincronizada de
  `docs/ANALISIS_UTILIDADES.md` (los valores no se copian en esta spec).
  `get_model_pricing` MUST usar `normalize_model`, y `normalize_model` MUST
  quitar los prefijos `azure/`, `openai/` y `anthropic/`. Los tokens de
  razonamiento MUST contarse como tokens de salida en ambos engines
  (`shared/llm/usage.py`).
- FR-012 El registro de cada corrida MUST guardar en `run.json` los parametros
  efectivos de cada rol (temperatura enviada u omitida, effort, modo de
  razonamiento, `max_tokens`), tomados de las configuraciones realmente usadas
  (no recreadas con defaults al guardar). MUST NOT alterarse el formato de
  `metricas_optimizacion.csv` ([[SPEC-100-veredicto-senal-ruido]] FR-007).
  [NEEDS CLARIFICATION: el criterio de comparabilidad de SPEC-100 (FR-008, hoy
  solo el par de modelos) y de [[SPEC-101-triaje-casos-nseeds]] no ve estos
  parametros. Extenderlo (leer `run.json` desde `seed_protocol.py` /
  `seed_triage.py`, o migrar el CSV) es un cambio a SPEC-100 que conviene hacer
  junto con D-018 (a). Hasta entonces, `docs/PROTOCOLO_N_SEEDS.md` MUST advertir
  que corridas Claude con distinto effort/razonamiento no deben mezclarse en un
  mismo lote de referencia.]
- FR-013 `docs/LLM_CONFIG.md` MUST documentar el formato, las variables
  `LLM_EFFORT_<ROL>` y `LLM_THINKING_<ROL>` con IDs vigentes y el tratamiento de
  `LLM_API_BASE` para `anthropic/`, y MUST enlazar a la matriz de esta spec en
  lugar de copiarla.

## Decisiones

- Effort y razonamiento van en `.env` y no en el YAML: su validez depende del
  modelo y del rol, que ya viven en `.env`, y la User Story pide comparar modelos
  cambiando solo el `.env`. Esto se aparta de `docs/LECCIONES_APRENDIDAS.md` §4
  (parametros de comportamiento en YAML); la reproducibilidad se cubre
  registrando los valores efectivos en `run.json` (FR-012).
  [NEEDS CLARIFICATION: si en una iteracion futura `models:` del YAML puede
  sobreescribirlos, y si `dspy_gepa_poc/run_inference.py` debe reconstruirlos
  desde `run.json` en lugar del `.env` vigente.]

## Criterios de exito (medibles, agnosticos a tecnologia)

- SC-001 Para el 100% de los modelos de la matriz (alias y un snapshot con fecha)
  y para cada combinacion valida de effort y razonamiento, los parametros
  construidos por los cuatro caminos de llamada coinciden con la matriz y no
  contienen ningun parametro que ese modelo rechace, verificado sobre el cuerpo
  HTTP interceptado (sin llamar a la API), incluido `get_dspy_lm` sin
  `drop_params`. El mismo conjunto de tests MUST fijar el header
  `anthropic-version` esperado, para que un cambio de LiteLLM no pase
  inadvertido.
- SC-002 Para el 100% de las combinaciones invalidas (apagar en Opus 5.5 o
  Fable, effort no aceptado, apagar con effort xhigh/max donde no se permite,
  valores no reconocidos en `LLM_EFFORT_<ROL>` / `LLM_THINKING_<ROL>`), la
  validacion falla antes de la primera llamada con un mensaje que nombra modelo
  y parametro.
- SC-003 El caso Email Urgency corre de punta a punta con API real en ambos
  subproyectos para cada modelo "real" de la matriz (Haiku 4.5, Sonnet 4.6,
  Sonnet 5, Haiku 5.5, Sonnet 5.5) como estudiante y profesor a la vez (10
  corridas), mas una corrida por subproyecto con `LLM_THINKING_TASK=off` en
  Haiku 5.5 y en Sonnet 5.5 con el mismo modelo como profesor (4 corridas), con
  0 errores 4xx de la API. El gasto total MUST NOT superar USD 10: antes de
  lanzar se estima el costo con los YAML del caso (`max_metric_calls: 50`); si la
  estimacion supera el tope, se MAY usar un YAML de verificacion con menor
  `max_metric_calls`, registrado en `historial/sdd.md`.
- SC-004 En esas corridas, menos del 1% de las predicciones terminan sin texto o
  cortadas por `max_tokens`, y todas las que ocurren aparecen en el log con su
  causa.
- SC-005 El costo reportado por cada corrida de SC-003 sale del uso real medido
  (con tokens de razonamiento como salida) y de precios de la tabla, sin el aviso
  de "modelo sin precio configurado".
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
- Given `LLM_MODEL_TASK=anthropic/claude-haiku-5-5` y `LLM_THINKING_TASK=off`,
  When se construyen los parametros, Then se envia `thinking={"type": "disabled"}`.
- Given `LLM_MODEL_TASK=anthropic/claude-sonnet-4-6` y `LLM_THINKING_TASK=off`,
  When se valida, Then no hay error y no se envia `thinking`.
- Given `LLM_MODEL_REFLECTION=anthropic/claude-opus-5-5` y
  `LLM_THINKING_REFLECTION=off`, When arranca la corrida, Then la validacion falla
  indicando que ese modelo no permite apagar el razonamiento.
- Given `LLM_MODEL_TASK=anthropic/claude-opus-4-5` y `LLM_EFFORT_TASK=xhigh`, When
  arranca la corrida, Then la validacion falla indicando los valores aceptados.
- Given `LLM_MODEL_TASK=anthropic/claude-sonnet-5-5-20260514`, When se
  construyen los parametros, Then se aplican las restricciones de
  `claude-sonnet-5-5` y no se emite aviso de modelo fuera de la matriz.
- Given un `.env` con `LLM_MODEL_*=anthropic/...` y sin `LLM_API_BASE`, When se
  ejecuta `validate()`, Then no hay error de configuracion.
- Given un `.env` Azure editado solo en `LLM_MODEL_*=anthropic/...` (queda
  `LLM_API_BASE` de Azure), When se construyen los parametros, Then no se envian
  `api_base` ni `api_version` y se emite un aviso al arrancar.
- Given el modelo de tarea rechaza responder un caso por politica, When se evalua
  ese caso, Then cuenta como fallo con score 0.0, queda en el log con la causa y
  la corrida sigue.

## Riesgos

- Si una version futura de LiteLLM pasa a enviar `anthropic-version: 2026-10-21`,
  Haiku 4.5, Opus 4.5 y los 4.6 tambien rechazaran `temperature` (lo detecta
  SC-001).
- Los modelos con temperatura no fija hacen mas ruidosas las comparaciones:
  medir con N seeds segun `docs/PROTOCOLO_N_SEEDS.md`.
- Los precios de los modelos "sin red" no se validan contra uso real; un error
  en la tabla solo se detecta comparando con la facturacion.

## Coverage mapping (requisito -> derivado)

| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | tabla de familias en `shared/llm/config.py`; `tests/test_anthropic_matrix.py` (vigente) |
| FR-002 | `LLMConfig.to_kwargs` y restricciones por familia; usado por `get_dspy_lm`, `get_lm_function`, `gepa_standalone/core/llm_factory.py::call_llm`, `gepa_standalone/adapters/simple_rag_adapter.py::_call_llm_with_retry` (vigente en los cuatro caminos, tarea y juez en RAG, con `tests/test_anthropic_matrix.py`) |
| FR-003 | idem FR-002; `tests/test_anthropic_matrix.py` (vigente) |
| FR-004 | `LLMConfig.from_env` (`LLM_EFFORT_<ROL>`) + `_check_params`; `tests/test_anthropic_matrix.py` (vigente) |
| FR-005 | `LLMConfig.from_env` (`LLM_THINKING_<ROL>`) + `_check_params`; `tests/test_anthropic_matrix.py` (vigente) |
| FR-006 | idem FR-002; `tests/test_anthropic_matrix.py` (vigente) |
| FR-007 | `LLMConfig.to_kwargs`, `LLMConfig.validate`, `LLMConfig.validate_connection`; `tests/test_anthropic_matrix.py` (vigente) |
| FR-008 | `LLMConfig.from_env` + `_check_params`; `tests/test_anthropic_matrix.py` (vigente) |
| FR-009 | `get_lm_function`, `get_dspy_lm` (`shared/llm/dspy_lm.py::CheckedLM`, tarea y reflexion), `call_llm`, `gepa_standalone/adapters/` (classifier, sql, rag, extractor), envoltorio de programa y metrica DSPy (`dspy_gepa_poc/empty_response.py`, aplicado en `ReflexioDeclarativa.create_module_and_metric`), `docs/GEPA_MANEJO_ERRORES.md`; tests `tests/test_empty_response.py` y `tests/test_empty_response_dspy.py` (vigente en LiteLLM y DSPy tras 2c; inferencia directa fuera, D-020) |
| FR-010 | `LLMConfig.describe`, `gepa_standalone/universal_optimizer.py` (reporte por adapter), `task_max_tokens`/`judge_max_tokens` en `gepa_standalone/adapters/`; `tests/test_describe_effective.py` (vigente) |
| FR-011 | `shared/analysis/roi_calculator.py` (`DEFAULT_PRICING`, `normalize_model`, `get_model_pricing`), `shared/llm/usage.py`, `docs/ANALISIS_UTILIDADES.md`; `tests/test_shared_analysis.py`, `tests/test_shared_usage.py` |
| FR-012 | `shared/logging/metadata.py`, `dspy_gepa_poc/reflexio_declarativa.py`, `gepa_standalone/universal_optimizer.py` (`save_results`), `docs/METADATA_REPRODUCIBILIDAD.md`, `docs/PROTOCOLO_N_SEEDS.md` (vigente en codigo: `run.json` con `effective_params` por rol, 4b; docs vigentes, fase 5) |
| FR-013 | `docs/LLM_CONFIG.md` (vigente, fase 5) |
| SC-001 | `tests/test_litellm_regression.py` (vigente: header `anthropic-version`, `temperature` por modelo con `drop_params`, pase de `output_config` y `thinking` a nivel LiteLLM); y `tests/test_anthropic_matrix.py` sobre los cuatro caminos de `LLMConfig` (vigente tras 1c y 2a) |
| SC-002 | `tests/test_anthropic_matrix.py::TestValidateCombinations` (vigente) |
| SC-003 | corridas manuales con API real, registradas en `historial/sdd.md` (vigente: 14/14 sin 4xx, USD 1.14, 2026-11-23) |
| SC-004 | conteo de `Respuesta sin texto del LLM` en los logs de las corridas de SC-003 (vigente: 0 sobre 1134 llamadas de tarea y 34 de reflexion; `run.json` no vuelca predicciones por ejemplo). Limitacion: los cortes por `max_tokens` con texto parcial no se detectan ni se registran; quedan para [[SPEC-104-fallas-tecnicas-justas]] (D-021) |
| SC-005 | `run.json` de las corridas de SC-003 (vigente: `usage.cost_usd` = tokens x `DEFAULT_PRICING` en las 14, sin aviso de precio) |
| SC-006 | `tests/test_litellm_regression.py::TestAzureOpenAIWireRegression` y `tests/test_anthropic_matrix.py::TestAzureOpenAIConfigRegression` (vigente: `to_kwargs()` y cuerpo HTTP de `azure/gpt-4.1-mini`, `azure/gpt-5.4-mini`, `azure/gpt-4o` y `openai/gpt-4o-mini`) y `tests/test_sc006_azure_openai_paths.py` (vigente: `call_llm`, `get_dspy_lm`, `validate_connection` y effort/thinking ignorados fuera de `anthropic/`) |
