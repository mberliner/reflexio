# SPEC-105-punto-llamada-desacoplado — Punto de llamada propio, desacoplado de los internos de DSPy y GEPA

Estado: active
Iteracion: 5 (rev. 2026-11-26)
Origen: D-018 de `historial/sdd.md` (upgrade DSPy 3.2.1 -> 3.5.0 y GEPA 0.0.27 -> 0.1.4)
Depende de: [[SPEC-104-fallas-tecnicas-justas]] (sus requisitos no cambian; cambia donde se implementan)
Relacionada con: [[SPEC-100-veredicto-senal-ruido]] (regresion con N seeds y FR-009 de versiones),
[[SPEC-106-roles-intercambiables]] (las credenciales por rol viviran en este punto de llamada),
[[SPEC-103-proveedor-anthropic]], `docs/ARCHITECTURE.md`, `docs/LLM_CONFIG.md`

## User Story (prioridad)

Como persona que mantiene el laboratorio, quiero que toda llamada al LLM de los
dos subproyectos pase por un punto de llamada propio que dependa solo de la API
publica de DSPy y GEPA, para poder actualizar esas librerias sin reimplementar la
deteccion de fallas, el conteo de tokens ni la medicion, y para que un upgrade
incompatible falle en CI y no en una corrida paga.
Prioridad: P1

## Contexto (estado al 2026-11-25)

Relevado sobre el codigo de los wheels de dspy 3.2.1, 3.4.1 y 3.5.0 (detalle en
la fila D-018):

- `gepa_standalone` ya llama a LiteLLM por un punto propio (`shared/llm/call.py`:
  `checked_completion`, `call_with_infra_retry`, `raise_for_response`). Usa de
  GEPA solo API publica (`optimize`, `EvaluationBatch`, `GEPAAdapter`,
  `callbacks` con `on_proposal_start`), que GEPA 0.1.4 conserva.
- `dspy_gepa_poc` implementa SPEC-104 sobre internos de dspy 3.2.1 que 3.5.0
  elimina o cambia:
  - `CheckedLM` (`shared/llm/dspy_lm.py`) sobrescribe `forward`,
    `_process_lm_response` y `_check_truncation`. En 3.5.0 no existen: el LM
    habla `lm15.Request`/`Response` aun con `engine="litellm"`.
  - `call_failures.py` subclasea `ChatAdapter`/`JSONAdapter` usando
    `_json_adapter_call_common` y `_get_structured_outputs_response_format`
    (privados) y fuerza `ContextWindowExceededError` para cortar el fallback a
    `JSONAdapter`. En 3.5.0 ese fallback se dispara solo con `AdapterParseError`.
  - El `finish_reason` del baseline (FR-004 de SPEC-104) y el uso de tokens
    (`record_dspy_history`) se leen de `dspy.LM.history`, cuyo formato cambia en
    3.5.0.
  - En 3.5.0 las excepciones de LiteLLM llegan convertidas a
    `dspy.utils.exceptions.LM*Error`, no las crudas que clasifica SPEC-104.
- dspy 3.4.1 ya rompe lo mismo que 3.5.0 para un `dspy.LM` subclaseado (verificado
  al instalarlo, D-018): `LM.forward` corre dentro de `error_boundary` (excepciones
  de LiteLLM convertidas a `LM*Error`), `_process_lm_response` no se llama y
  `_json_adapter_call_common` no existe. Un `dspy.BaseLM` que implementa `forward`
  (interfaz de LM propio de 3.2.1) en 3.4.x corre como plugin legacy: sin
  `error_boundary`, sin reintentos ni cache de DSPy y con las excepciones crudas.
  3.5.0 elimina esa interfaz.
- dspy 3.4.1 cambia el prompt de reflexion por defecto de `dspy.GEPA`
  (verificado al instalarlo, D-018 b2): en lugar de la plantilla de GEPA
  (`InstructionProposalSignature`, instruccion dentro de un bloque de triple
  backtick) usa `dspy.teleprompt.gepa.InstructionProposer`
  (`@experimental(version="3.4.1")`): `dspy.Predict` + `JSONAdapter` sobre la
  signature `ProposeInstruction`, con otro texto y los ejemplos como lista
  estructurada. Sin aviso, una actualizacion menor cambio la optimizacion.
  `dspy.GEPA(instruction_proposer=...)` y `gepa.optimize(custom_candidate_proposer=...)`
  aceptan un proposer propio con el protocolo publico `ProposalFn` de GEPA
  (`(candidate, reflective_dataset, components_to_update) -> dict[str, str]`).
- GEPA 0.1.4 reintenta una vez la reflexion fallida de cada iteracion
  (`_propose_texts_batch_safe`: "Batched reflection failed ...; retrying per
  task"), en los dos subproyectos; 0.0.27 no lo hacia.
- dspy 3.4.0+ y 3.5.0 aceptan un engine propio como API publica:
  `dspy.LM(engine=<objeto con complete(Request) -> Response>)`, y dspy reintenta
  solo errores propios reintentables (`num_retries=0` lo anula). Corregido al
  instalar 3.5.0 (D-018 b3): la premisa "las excepciones de un engine propio que
  no son de dspy se propagan sin convertir" era falsa. `execution.execute` corre
  el engine dentro de `error_boundary(unexpected=True)`: toda excepcion que no es
  `dspy.LMError` sale como `LMUnexpectedError` (la original queda en
  `__cause__`); las `dspy.LMError` pasan por identidad
  (`clients/errors.py::wrap_error`). Sin tratamiento, `LLMCallFailure` y
  `RunAborted` no llegarian a los `except` del repo (SPEC-104 roto).
- dspy 3.5.0 cambia el adapter por defecto de `ChatAdapter` a
  `XMLAdapter(use_native_function_calling=True)` (`adapters/utils.py::_get_adapter`,
  tambien en el formateo del dataset reflexivo de `dspy.GEPA`): otro formato del
  prompt de la tarea, sin aviso. `ChatAdapter` y `JSONAdapter` producen en 3.5.0
  los mismos mensajes que en 3.4.1 (verificado con el codigo real de ambas
  versiones).
- dspy 3.5.0 cambia tambien el tipo por defecto del campo `reasoning` de
  `ChainOfThought` de `str` a `dspy.Reasoning` (y su descripcion a "A short plan
  for solving the task."). Con un LM que declara `supports_reasoning` (gpt-5.x)
  el adapter quita el campo del prompt y pide razonamiento nativo
  (`reasoning_effort="low"` -> `Config.reasoning`); dspy 3.4.1 lo evitaba para
  gpt-5 en Chat Completions y el campo era `str`. Los tests de b3 usaban un
  modelo sin reasoning y no lo vieron: aparecio en la primera corrida real de
  (c2) como `UnsupportedFeatureError` del engine (D-027) en cada ejemplo, antes
  de llamar al proveedor (falla fuerte, sin gasto).
- lm15 guarda `Config.response_format` en su forma canonica
  (`{"type": "json_schema", "schema", "name"?, "strict"?}`), no en la de Chat
  Completions (`{"type": "json_schema", "json_schema": {...}}`). La traduccion de
  b3 la copiaba tal cual: con `JSONAdapter` (el fallback de `ChatAdapter` ante un
  parseo fallido) Azure respondia 400 `Missing required parameter:
  'response_format.json_schema'`, que SPEC-104 aborta como `configuracion`. El
  golden de b3 verificaba los mensajes pero no el `response_format`. Lo mostro
  el segundo intento de (c2); la conversion propia
  (`chat_response_format`) deja el mismo dict, en el mismo orden, que LiteLLM
  armaba en dspy 3.4.1 desde el modelo pydantic de `JSONAdapter`.
- lm15 (incluido en dspy 3.5.0) no expone un conversor publico de `Request` a
  Chat Completions (`clients/lm15_boundary.py::request_kwargs` usa internos del
  dialecto); si expone los tipos (`dspy.lm15.Request`, `Message`, `TextPart`,
  `Config`, `Response`, `Usage`).

## Requisitos funcionales

- FR-001 Toda llamada al LLM de `dspy_gepa_poc` y de `gepa_standalone`, en todos
  los roles (tarea, reflexion, juez), MUST pasar por un unico punto de llamada
  propio (`shared/llm/`), que es el que invoca a LiteLLM.
- FR-002 En `dspy_gepa_poc`, el punto de llamada MUST conectarse a DSPy mediante
  un engine propio pasado a `dspy.LM(engine=...)` (contrato publico
  `complete(Request) -> Response`), con los reintentos de DSPy desactivados
  (`num_retries=0`): el unico reintento es el de infraestructura de SPEC-104.
  El engine MUST ser dueno de la conexion y de los parametros de generacion de
  la config (ya restringidos por `LLMConfig.apply_constraints`); `dspy.LM` no los
  recibe. La traduccion `Request` -> Chat Completions MUST ser del repo, sobre los
  tipos publicos de `dspy.lm15`, y MUST rechazar
  (`dspy.lm15.UnsupportedFeatureError`, antes de llamar) lo que no sabe enviar
  (herramientas, partes no textuales, `continuation`, campos de `Config` no
  traducidos, incluidos los que agregue una version nueva; alcance actual y
  ampliacion en D-027). Las `LLMCallFailure`
  y `RunAborted` que lanza el punto de llamada MUST llegar al codigo del repo con
  su clase, sus atributos y su causa: el engine las relanza como subclase de su
  clase y de `dspy.LMError` (publica), que dspy deja pasar por identidad.
  Transicion (D-018, cerrada en b3): sobre dspy 3.2.1 y 3.4.x el conector fue un
  `dspy.BaseLM` cuyo `forward` llamaba al punto de llamada.
- FR-003 La deteccion y clasificacion de fallas de SPEC-104 (capa 1,
  `finish_reason`, respuesta sin texto, mapeo de excepciones de LiteLLM) MUST
  hacerse en el punto de llamada sobre la respuesta y las excepciones crudas de
  LiteLLM, igual en los dos subproyectos. MUST NOT depender de como DSPy
  convierta o registre esas respuestas.
- FR-004 El uso de tokens y el `finish_reason` que necesita la atribucion contra
  el baseline (SPEC-104 FR-004) MUST registrarse en el punto de llamada. MUST NOT
  leerse de `dspy.LM.history`.
- FR-005 El codigo del repo MUST NOT sobrescribir metodos ni importar simbolos
  privados (prefijo `_`) o no documentados de `dspy`, `gepa` ni `litellm`. Lo que
  hoy lo hace (`CheckedLM`, `_SafeJSONAdapter`, `_SafeChatAdapter`,
  `_HistoryRecorder`) MUST reemplazarse o eliminarse.
- FR-006 Los requisitos de SPEC-104 MUST seguir cumpliendose sin cambio de
  comportamiento observable: misma clasificacion, mismos conteos, mismos abortos,
  mismo `run.json` y mismo CSV.
- FR-007 Cada superficie publica de `dspy`, `gepa` y `litellm` que usa el repo
  MUST tener un test de contrato que falle en CI si un upgrade la cambia de forma
  incompatible (firma, tipo devuelto o comportamiento del que dependemos).
- FR-008 `requirements.txt` MUST fijar `dspy`, `gepa`, `litellm` y `openai` con
  version exacta (`==`).
- FR-009 `cache: true` MUST fallar al armar el LM (`LLMConfigError`), no
  apagarse en silencio. Revisado con el engine (D-018 b3): la cache de DSPy
  aplicaria (`execute` la consulta antes del engine), pero una respuesta
  cacheada no pasa por el punto de llamada: sin uso de tokens del rol ni
  `finish_reason` para la atribucion contra el baseline (FR-004). Se mantiene el
  rechazo; habilitarla exige registrar esos datos tambien en el acierto de
  cache.
- FR-010 El paso de reflexion de GEPA MUST ser del repo y unico para los dos
  subproyectos (`shared/llm/reflection.py::ReflectionProposer`): plantilla del
  prompt, renderizado de los ejemplos con feedback, extraccion de la instruccion
  y deteccion de `formato` (SPEC-104 FR-005). MUST conectarse solo por los
  parametros publicos `instruction_proposer` (`dspy.GEPA`) y
  `custom_candidate_proposer` (`gepa.optimize`), y ser tambien el callback
  `on_proposal_start`. MUST NOT depender de los prompts, extractores ni
  proposers por defecto de `dspy` o `gepa`. La plantilla vigente
  (`REFLECTION_PROMPT_ID = "gepa-0.0.27-default"`) MUST producir byte a byte el
  prompt historico (GEPA 0.0.27 / dspy 3.2.1); cambiarla es un cambio de
  optimizacion: id nuevo y medicion con N seeds (SPEC-100), no un ajuste.
- FR-011 El reintento de la reflexion fallida que agrega GEPA 0.1.4 MUST NOT
  llamar de nuevo al LLM ni registrar otra falla: con la iteracion conocida,
  el guard relanza la falla ya registrada (SPEC-104: una propuesta, un intento,
  una falla; el unico reintento es el de `infraestructura`).
- Resuelto (2026-11-25, D-018 b2): en dspy 3.4.1 `ChatAdapter` cae a
  `JSONAdapter` solo ante `AdapterParseError` y `JSONAdapter` elige el
  `response_format` antes de llamar (sin reintento con `json_object`). Se
  eliminaron `_SafeJSONAdapter`/`_SafeChatAdapter`, el filtro del aviso
  "Failed to use structured output format" y el corte con
  `ContextWindowExceededError` de `CheckedLM` (`DspyLLMCallFailure`,
  `DspyEmptyResponseError`): ademas `dspy.ReAct` trata esa excepcion como
  ventana excedida y truncaria la trayectoria ante cualquier falla nuestra.
- FR-012 El adapter de la tarea en `dspy_gepa_poc` MUST ser del repo: los entry
  points configuran dspy solo con `shared/llm/dspy_lm.py::configure_dspy`, que
  fija `dspy.ChatAdapter()`. MUST NOT depender del adapter por defecto de
  `dspy`. Cambiar de adapter es un cambio de optimizacion (medicion con N seeds,
  como FR-010), no un ajuste. Igual con el campo `reasoning` de
  `ChainOfThought`: el codigo de produccion crea CoT solo con
  `shared/llm/dspy_lm.py::chain_of_thought`, que lo fija como texto (`str`, el de
  dspy 3.4.1); MUST NOT depender del tipo por defecto de `dspy` (iter 5, D-018 c2).
- Resuelto (2026-11-25, D-018 b3): en dspy 3.5.0 `dspy.GEPA` conserva
  `instruction_proposer` y `gepa_kwargs` (el diff de `teleprompt/gepa/` contra
  3.4.1 solo quita `@experimental` y cambia docstrings y el adapter del
  formateo, ver FR-012), y la llamada del proposer al LM de reflexion (texto)
  pasa por el engine propio como un unico mensaje `user`
  (`tests/test_dspy_engine.py::TestCheckedEngine::test_reflection_prompt_is_one_user_message`).

## Criterios de exito (medibles, agnosticos a tecnologia)

- SC-001 Pasar de dspy 3.4.1 a 3.5.0 (con GEPA 0.1.4 fijo) no requiere cambios
  de codigo fuera del punto de llamada y de sus tests de contrato.
- SC-002 Tras ese paso, la regresion con N=5 seeds en los casos de referencia de
  D-018 da primario `RUIDO` o `MEJORA` (no `REGRESION`) con el veredicto de
  SPEC-100 (`--cross-versions`).
- SC-003 Implementar el punto de llamada sobre dspy 3.4.1 no cambia los scores:
  SC-006 de SPEC-104 sigue verde y la corrida simulada de cada orquestador da los
  mismos scores, `run.json` y CSV que antes del cambio.
- SC-004 SC-009 de SPEC-104 (mapeo de fallas de LiteLLM) sigue verde en los dos
  subproyectos.
- SC-005 Cero imports de simbolos privados de `dspy`/`gepa`/`litellm` en el
  codigo del repo, verificado por un test que recorre los imports.
- SC-006 Ante un cambio incompatible simulado de una superficie publica usada, al
  menos un test de contrato falla.
- SC-007 El prompt de reflexion que llega al LLM en los dos subproyectos es
  identico byte a byte al historico (GEPA 0.0.27 / dspy 3.2.1) para el mismo
  dataset reflexivo, verificado contra un golden generado con el codigo real de
  GEPA 0.0.27.
- SC-008 Los mensajes de la tarea que llegan a LiteLLM con `ChatAdapter` y con
  `JSONAdapter` (incluido el `response_format` de `JSONAdapter`), y los de
  `ChainOfThought` con `ChatAdapter` (con un modelo con y sin reasoning, sin
  `reasoning_effort` en la llamada), son identicos byte a byte a los de dspy 3.4.1 para la misma firma, demos e input, verificado contra
  un golden generado con el codigo real de dspy 3.4.1.

## Escenarios (Given/When/Then)

- Given una corrida de `dspy_gepa_poc` con dspy 3.5.0, When el proveedor
  devuelve `finish_reason="length"`, Then la falla se clasifica `presupuesto`
  igual que con dspy 3.2.1 y queda en `run.json` con el mismo conteo.
- Given LiteLLM lanza un `RateLimitError`, When ocurre dentro de una llamada de
  DSPy, Then el punto de llamada lo clasifica antes de que DSPy lo vea y DSPy no
  lo reintenta.
- Given una evaluacion del baseline, When se necesita su `finish_reason` para
  atribuir una falla, Then sale del punto de llamada y no del historial de DSPy.
- Given un upgrade de `dspy` que cambia la firma de `dspy.GEPA` o el contrato de
  engine, When corre el CI, Then falla un test de contrato antes de cualquier
  corrida paga.
- Given el codigo del repo, When se agrega un import de un simbolo privado de
  `dspy`, Then falla el test de SC-005.
- Given un upgrade de `dspy` o `gepa` que cambia su prompt de reflexion por
  defecto, When corre una optimizacion, Then el prompt enviado no cambia (es el
  del repo).
- Given una reflexion con falla de `formato` en la iteracion 3, When GEPA 0.1.4
  la reintenta, Then no hay segunda llamada al LLM y la falla cuenta una vez.
- Given dspy 3.5.0 y un engine propio, When el punto de llamada lanza
  `LLMCallFailure` o `RunAborted`, Then el codigo del repo la atrapa con su
  clase y su causa (no un `LMUnexpectedError`).
- Given un upgrade de `dspy` que cambia el adapter por defecto, When corre una
  optimizacion, Then el prompt de la tarea no cambia (es el de `configure_dspy`).

## Coverage mapping (requisito -> derivado)

Completo: implementado sobre dspy 3.5.0 + gepa 0.1.4 (D-018 b1 sobre 3.2.1, b2
sobre 3.4.1, b3 sobre 3.5.0), regresion paga (SC-002) en D-018 c2 y contratos
con mutacion simulada por superficie (SC-006, 2026-11-26).

| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | hecho: `shared/llm/call.py::checked_response` (unica llamada a `litellm.completion`), usado por `checked_completion*` y por `CheckedEngine.complete`; `tests/test_single_call_point.py` |
| FR-002 | hecho (D-018 b3): `shared/llm/dspy_lm.py` (`CheckedEngine`, `request_to_chat`, `chat_response`, `dspy_visible`, `checked_lm`); `LLMConfig.get_dspy_lm()` devuelve `dspy.LM(engine=CheckedEngine(...), num_retries=0, cache=False)`; `tests/test_dspy_engine.py` |
| FR-003 | hecho: `raise_for_response` / `call_with_infra_retry` dentro de `checked_response`; el engine propaga la `LLMCallFailure` sin disfraz (`dspy_visible`, `tests/test_dspy_engine.py::TestFailuresThroughDspy`); `tests/test_litellm_failure_mapping.py` (`TestCheckedLMRaiseForResponse`, `test_retry_counts_checked_lm`), `tests/test_failures.py::test_checked_lm_context_window_is_entrada_with_litellm_cause` |
| FR-004 | hecho: `record_usage` y `capture_finish_reason` en `checked_response`; `baseline_caller` usa `capture_finish_reason`; el orquestador reinicia el tracker en `setup_models`; eliminados `record_dspy_history` y `_HistoryRecorder` |
| FR-005 | hecho: sin overrides ni imports privados de dspy; eliminados `_SafeJSONAdapter`/`_SafeChatAdapter` (`dspy_gepa_poc/call_failures.py`) el corte de `CheckedLM` y despues `CheckedLM` (b3); `tests/test_lib_contracts.py::TestNoPrivateLibrarySymbols` |
| FR-006 | `tests/test_sc006_no_failure_regression.py`, tests de SPEC-104 |
| FR-007 | hecho: inventario `tests/test_lib_contracts.py::SURFACES` (30 superficies de `dspy`, `gepa` y `litellm`); contratos en `tests/test_lib_contracts.py` (`TestOptimizerConstructionContracts`, `TestDspyContracts`: tipos y `Config` de `dspy.lm15`, excepciones, `compile`/`DspyGEPAResult`, `Evaluate`, `named_predictors`, `LabeledFewShot`; `TestGepaContracts`: `EvaluationBatch`, `GEPAAdapter`, `GEPAResult`, `ProposalStartEvent`; `TestLitellmContracts`: firma de `completion`, pistas de capacidad, `drop_params`), `tests/test_dspy_engine.py` (`TestDspyEngineContract`, `TestTaskPromptUnchanged`), `tests/test_single_call_point.py` (fallback de adapters, una llamada por falla), e2e de `tests/test_reflection_guard.py` (proposer y callbacks en `dspy.GEPA` y `gepa.optimize`), `tests/test_litellm_failure_mapping.py` (excepciones y respuesta 200) |
| FR-008 | hecho: `requirements.txt` (`dspy==3.5.0`, `gepa==0.1.4`, `litellm`, `openai`); `tests/litellm_failure_payloads.py::EXPECTED_VERSIONS` |
| FR-009 | `LLMConfig.get_dspy_lm()`; `tests/test_shared_llm.py::TestLLMConfigGetDspyLM::test_cache_is_rejected` |
| FR-010 | hecho: `shared/llm/reflection.py` (`REFLECTION_PROMPT_TEMPLATE`, `render_reflection_prompt`, `extract_instruction`, `ReflectionProposer`); conectores `shared/llm/dspy_lm.py::dspy_reflection_proposer` -> `GEPAOptimizer` y `gepa_standalone/core/llm_factory.py::create_reflection_proposer` -> `universal_optimizer`; `tests/test_reflection_guard.py`, `tests/test_reflection_prompt.py` |
| FR-011 | hecho: `ReflectionGuard.run` (falla por iteracion); `tests/test_reflection_guard.py::TestReflectionProposer::test_retry_of_failed_iteration_does_not_call_again` y los e2e de umbral (3 llamadas, 4 intentos) |
| FR-012 | hecho: `shared/llm/dspy_lm.py::configure_dspy` en los entry points de `dspy_gepa_poc` (orquestadores, `run_inference`, scripts) y `chain_of_thought` en `dspy_gepa_poc/dynamic_factory.py`; `tests/test_dspy_engine.py::TestEntryPointsUseConfigureDspy` (incluye `test_no_bare_chain_of_thought_in_production`), `TestTaskPromptUnchanged`; `tests/conftest.py::repo_dspy_adapter` |
| SC-001 | cumplido (D-018 b3): fuera del punto de llamada (`shared/llm/dspy_lm.py`, `config.py::get_dspy_lm`) y sus tests, el paso 3.4.1 -> 3.5.0 solo cambio la version fijada y la llamada a `dspy.configure` de los entry points (FR-012, hallazgo del upgrade) |
| SC-002 | cumplido (D-018 c2, 2026-11-25): `seed_protocol.report(..., cross_versions=True)` en `CV Extraction v3` de `dspy_gepa_poc`, N=5 vs el lote dspy 3.4.1 de (c1): RUIDO (delta Rob -0,33) |
| SC-003 | `tests/test_sc006_no_failure_regression.py` + `tests/orchestrator_e2e.py` (verde sobre 3.4.1 y 3.5.0); la regresion real es D-018 (c1) y (c2) |
| SC-004 | `tests/test_litellm_failure_mapping.py` (re-verificado sobre 3.5.0) |
| SC-005 | hecho: `tests/test_lib_contracts.py::TestNoPrivateLibrarySymbols` (AST de `shared`, `dspy_gepa_poc`, `gepa_standalone`) |
| SC-006 | hecho (2026-11-26): `tests/test_lib_contracts.py::TestContractsDetectIncompatibleChanges`: `MUTATIONS` simula con `monkeypatch` 31 cambios incompatibles (al menos uno por cada superficie de `SURFACES`, verificado por `test_every_surface_has_a_mutation`) y `test_contract_turns_red` exige que el contrato de esa superficie falle con la excepcion esperada; verificado que cada uno falla por el motivo simulado y no por un efecto colateral |
| SC-007 | hecho: `tests/test_reflection_prompt.py` + `tests/fixtures/reflection_prompt_gepa_0_0_27.json` |
| SC-008 | hecho: `tests/test_dspy_engine.py::TestTaskPromptUnchanged` (incluye `test_chain_of_thought_messages_match_dspy_3_4_1` y `test_json_adapter_messages_match_dspy_3_4_1` con `openai/gpt-4o-mini` y `azure/gpt-5.4-mini`), `TestChatResponseFormat` + `tests/fixtures/task_prompt_dspy_3_4_1.json` |
