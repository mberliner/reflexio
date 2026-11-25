# SPEC-105-punto-llamada-desacoplado — Punto de llamada propio, desacoplado de los internos de DSPy y GEPA

Estado: draft
Iteracion: 2 (rev. 2026-11-25)
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
- Resuelto (2026-11-25): en dspy 3.4.1 `JSONAdapter.__call__` ya no tiene el
  `except Exception` y `ChatAdapter` cae a `JSONAdapter` solo ante
  `AdapterParseError`. `_SafeJSONAdapter`/`_SafeChatAdapter` siguen haciendo falta
  sobre 3.2.1 y se eliminan al subir a 3.4.1 (D-018 b2); el corte con
  `ContextWindowExceededError` (excepcion publica) queda sin efecto desde 3.4.
- [NEEDS CLARIFICATION: la reflexion en `dspy.GEPA` llama al LM con texto (no con
  `Request`); confirmar en 3.5.0 que ese camino tambien pasa por el engine propio
  y que `on_proposal_start` sigue llegando via `gepa_kwargs={"callbacks": [...]}`.]

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

## Coverage mapping (requisito -> derivado)

Parcial: lo marcado "hecho" esta implementado sobre dspy 3.2.1 (D-018 b1).

| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | hecho: `shared/llm/call.py::checked_response` (unica llamada a `litellm.completion`), usado por `checked_completion*` y por `CheckedLM.forward`; `tests/test_single_call_point.py` |
| FR-002 | transicion hecha: `CheckedLM(dspy.BaseLM)` en `shared/llm/dspy_lm.py` (`num_retries=0`); pendiente el engine propio (D-018 b3) |
| FR-003 | hecho: `raise_for_response` / `call_with_infra_retry` dentro de `checked_response`; `tests/test_litellm_failure_mapping.py` (`TestCheckedLMRaiseForResponse`, `test_retry_counts_checked_lm`) |
| FR-004 | hecho: `record_usage` y `capture_finish_reason` en `checked_response`; `baseline_caller` usa `capture_finish_reason`; el orquestador reinicia el tracker en `setup_models`; eliminados `record_dspy_history` y `_HistoryRecorder` |
| FR-005 | parcial: `CheckedLM` ya no sobrescribe privados de dspy; falta quitar los adapters `_Safe*` de `dspy_gepa_poc/call_failures.py` (D-018 b2) y el test de SC-005 |
| FR-006 | `tests/test_sc006_no_failure_regression.py`, tests de SPEC-104 |
| FR-007 | tests de contrato (a crear) sobre `dspy.LM(engine=...)`, `dspy.GEPA`, `Evaluate`, `gepa.optimize`, `EvaluationBatch`, callbacks |
| FR-008 | `requirements.txt` |
| FR-009 | `LLMConfig.get_dspy_lm()`; `tests/test_shared_llm.py::TestLLMConfigGetDspyLM::test_cache_is_rejected` |
| SC-001 | diff del paso 3.4.1 -> 3.5.0 (D-018 b3) |
| SC-002 | `python -m shared.utils.seed_protocol --cross-versions` (D-018 c2) |
| SC-003 | `tests/test_sc006_no_failure_regression.py` + `tests/orchestrator_e2e.py` |
| SC-004 | `tests/test_litellm_failure_mapping.py` |
| SC-005 | test de imports privados (a crear) |
| SC-006 | tests de contrato (a crear) |
