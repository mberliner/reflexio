# SPEC-105-punto-llamada-desacoplado — Punto de llamada propio, desacoplado de los internos de DSPy y GEPA

Estado: draft
Iteracion: 3 (rev. 2026-11-25)
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
  `dspy.LM(engine=<objeto con complete(Request) -> Response>)`. En 3.5.0 las
  excepciones que lanza un engine propio y que no son de dspy se propagan sin
  convertir (`clients/execution.py::_attempt`), y dspy reintenta solo errores
  propios reintentables (`num_retries=0` lo anula).

## Requisitos funcionales

- FR-001 Toda llamada al LLM de `dspy_gepa_poc` y de `gepa_standalone`, en todos
  los roles (tarea, reflexion, juez), MUST pasar por un unico punto de llamada
  propio (`shared/llm/`), que es el que invoca a LiteLLM.
- FR-002 En `dspy_gepa_poc`, el punto de llamada MUST conectarse a DSPy mediante
  un engine propio pasado a `dspy.LM(engine=...)` (contrato publico
  `complete(Request) -> Response`), con los reintentos de DSPy desactivados
  (`num_retries=0`): el unico reintento es el de infraestructura de SPEC-104.
  Transicion (D-018): sobre dspy 3.2.1 y 3.4.x, donde no hay engine o convive con
  la interfaz vieja, el conector MAY ser un `dspy.BaseLM` cuyo `forward` llama al
  punto de llamada; MUST reemplazarse por el engine antes de dspy 3.5.0.
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
- FR-009 Mientras el conector sea un `dspy.BaseLM` propio, la cache de respuestas
  de DSPy no aplica: `cache: true` MUST fallar al armar el LM (`LLMConfigError`),
  no apagarse en silencio. Con el engine de FR-002 la cache de DSPy vuelve a
  aplicar (dspy la maneja en llamadas "managed") y este requisito se revisa.
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
- [NEEDS CLARIFICATION: confirmar en dspy 3.5.0 que `instruction_proposer` y
  `gepa_kwargs={"callbacks": [...]}` se conservan y que la llamada del proposer
  al LM de reflexion (texto, no `Request`) pasa por el engine propio de FR-002.]

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

## Coverage mapping (requisito -> derivado)

Parcial: lo marcado "hecho" esta implementado sobre dspy 3.4.1 + gepa 0.1.4
(D-018 b1 sobre 3.2.1, b2 sobre 3.4.1).

| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | hecho: `shared/llm/call.py::checked_response` (unica llamada a `litellm.completion`), usado por `checked_completion*` y por `CheckedLM.forward`; `tests/test_single_call_point.py` |
| FR-002 | transicion hecha: `CheckedLM(dspy.BaseLM)` en `shared/llm/dspy_lm.py` (`num_retries=0`; plugin legacy deprecado en 3.4, aviso filtrado en `pyproject.toml`); pendiente el engine propio (D-018 b3) |
| FR-003 | hecho: `raise_for_response` / `call_with_infra_retry` dentro de `checked_response`; `CheckedLM` propaga la `LLMCallFailure` sin disfraz; `tests/test_litellm_failure_mapping.py` (`TestCheckedLMRaiseForResponse`, `test_retry_counts_checked_lm`), `tests/test_failures.py::test_checked_lm_context_window_is_entrada_with_litellm_cause` |
| FR-004 | hecho: `record_usage` y `capture_finish_reason` en `checked_response`; `baseline_caller` usa `capture_finish_reason`; el orquestador reinicia el tracker en `setup_models`; eliminados `record_dspy_history` y `_HistoryRecorder` |
| FR-005 | hecho: sin overrides ni imports privados de dspy; eliminados `_SafeJSONAdapter`/`_SafeChatAdapter` (`dspy_gepa_poc/call_failures.py`) y el corte de `CheckedLM`; `tests/test_lib_contracts.py::TestNoPrivateLibrarySymbols` |
| FR-006 | `tests/test_sc006_no_failure_regression.py`, tests de SPEC-104 |
| FR-007 | parcial: `tests/test_lib_contracts.py` (parametros de `dspy.GEPA` y `gepa.optimize`, protocolo `ProposalFn`, `dspy.GEPA` sin filtro por firma en `GEPAOptimizer`), `tests/test_single_call_point.py::test_adapter_fallback_only_on_parse_error`, e2e de `tests/test_reflection_guard.py`; pendiente el contrato del engine (D-018 b3) y de `Evaluate` / `EvaluationBatch` |
| FR-008 | hecho: `requirements.txt` (`dspy==3.4.1`, `gepa==0.1.4`, `litellm`, `openai`); `tests/litellm_failure_payloads.py::EXPECTED_VERSIONS` |
| FR-009 | `LLMConfig.get_dspy_lm()`; `tests/test_shared_llm.py::TestLLMConfigGetDspyLM::test_cache_is_rejected` |
| FR-010 | hecho: `shared/llm/reflection.py` (`REFLECTION_PROMPT_TEMPLATE`, `render_reflection_prompt`, `extract_instruction`, `ReflectionProposer`); conectores `shared/llm/dspy_lm.py::dspy_reflection_proposer` -> `GEPAOptimizer` y `gepa_standalone/core/llm_factory.py::create_reflection_proposer` -> `universal_optimizer`; `tests/test_reflection_guard.py`, `tests/test_reflection_prompt.py` |
| FR-011 | hecho: `ReflectionGuard.run` (falla por iteracion); `tests/test_reflection_guard.py::TestReflectionProposer::test_retry_of_failed_iteration_does_not_call_again` y los e2e de umbral (3 llamadas, 4 intentos) |
| SC-001 | diff del paso 3.4.1 -> 3.5.0 (D-018 b3) |
| SC-002 | `python -m shared.utils.seed_protocol --cross-versions` (D-018 c2) |
| SC-003 | `tests/test_sc006_no_failure_regression.py` + `tests/orchestrator_e2e.py` (verde sobre 3.4.1); la regresion real es D-018 (c1) |
| SC-004 | `tests/test_litellm_failure_mapping.py` (re-verificado sobre 3.4.1) |
| SC-005 | hecho: `tests/test_lib_contracts.py::TestNoPrivateLibrarySymbols` (AST de `shared`, `dspy_gepa_poc`, `gepa_standalone`) |
| SC-006 | parcial: `tests/test_lib_contracts.py` (`test_dspy_gepa_rejects_unknown_parameters`, detector de imports privados) |
| SC-007 | hecho: `tests/test_reflection_prompt.py` + `tests/fixtures/reflection_prompt_gepa_0_0_27.json` |
