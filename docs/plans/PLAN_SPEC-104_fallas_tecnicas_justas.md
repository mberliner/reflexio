# Plan de implementacion — SPEC-104 fallas tecnicas justas

Fuente del plan de ejecucion de [[SPEC-104-fallas-tecnicas-justas]]. La spec
define que debe cumplirse (FR/SC); este documento define en que orden se
implementa, con que modelo de agente, que decisiones de diseno ya estan tomadas
y en que estado esta cada subfase. Si cambia un requisito, se edita la spec y
aca solo se ajusta la referencia.

## Criterio de modelo

"Modelo" es el modelo del agente de codigo que ejecuta cada subfase.

- Opus 5.5: diseno que cruza modulos, interaccion con internals de librerias
  (GEPA, DSPy, LiteLLM), analisis de resultados y revision.
- Sonnet 5.5: implementacion guiada por la spec y por tests ya escritos.

## Reglas de ejecucion

- Tests primero (RED) y luego implementacion (GREEN). Los tests RED se marcan
  `@pytest.mark.xfail(strict=True, reason="SPEC-104 <subfase que los cierra>")`
  para que `ci_local.sh` quede verde; la subfase GREEN quita la marca.
- Cada subfase cierra con `./shared/utils/ci_local.sh` y un commit.
- Al cerrar una subfase: actualizar su estado aca (`pendiente` -> `hecho`, con
  el hash del commit) y pasar a vigente la fila del Coverage mapping de la spec
  que corresponda.
- Si una decision de diseno de este plan choca con el codigo, se corrige aca
  antes de seguir; no se improvisa en la implementacion.
- La spec queda en `draft` hasta el cierre (misma convencion que SPEC-103).
- Payloads de fallas: siempre desde `tests/litellm_failure_payloads.py`; no se
  inventan payloads nuevos sin agregarlos ahi.

## Fases

| Fase | Subfase | Requisitos | Modelo | Estado |
|---|---|---|---|---|
| 1 Nucleo de fallas (`shared/llm`) | 1a Tests sin red del clasificador de capa 1 sobre los 102 payloads y del contador (RED) | FR-001, FR-006, FR-015, SC-009 | Sonnet 5.5 | hecho (2e75a29) |
| | 1b Diseno: confirmar D1 a D4 contra el codigo (API de `failures.py`, destino de `EmptyResponseError`, punto de reintento en `CheckedLM`, conteo una vez por caso) | FR-001, FR-007, FR-011 | Opus 5.5 | hecho (147f5ab) |
| | 1c Clasificador, `FailureTracker` y llamada con reintento propio; `num_retries=0` en LiteLLM y `CheckedLM` (GREEN) | FR-001, FR-006, FR-007, FR-011, FR-015 | Sonnet 5.5 | hecho (6e9617a) |
| 2 Caminos de llamada | 2a Los tres lugares que hoy llaman a `litellm.completion` delegan en la llamada comun: `get_lm_function`, `call_llm` (queda como fachada en `gepa_standalone/core/llm_factory.py`) y `SimpleRAGAdapter._call_llm_with_retry` (se elimina, con su reintento por `content_filter`); `CheckedLM` con `num_retries=0`; `ContextWindowExceededError` de DSPy por `__cause__`; test de que no hay otra llamada a `litellm.completion` en produccion | FR-001, FR-011, FR-015 | Opus 5.5 (relanzada; primer intento Sonnet 5.5) | hecho (d61de1c) |
| | 2b Reflexion: descarte en el envoltorio (clase de capa 1 y `formato` sin bloque de instruccion) en ambos subproyectos; verificacion contra GEPA 0.0.27 y `dspy.GEPA` | FR-005, SC-003 | Opus 5.5 (relanzada) | hecho (bf346c1) |
| 3 Casos y atribucion | 3a Identificador canonico de caso en ambos loaders | FR-013 | Sonnet 5.5 | hecho (60b1ba2) |
| | 3b Diseno de la atribucion contra el baseline (D5) y de la prediccion NE en DSPy (D6) | FR-004, FR-012 | Opus 5.5 | hecho (6d2dec1) |
| | 3c Adapters de `gepa_standalone`: resultado por caso (evaluado / NE / score 0 por clase), atribucion, `make_reflective_dataset` sin NE, `formato` por adapter | FR-002, FR-004, FR-010, FR-011, FR-012, SC-001, SC-008 | Sonnet 5.5 | hecho (cf21af2) |
| | 3d Juez de RAG con JSON en el prompt, validacion de rango y reintentos | FR-009 | Sonnet 5.5 | hecho (e1a3017) |
| | 3e `dspy_gepa_poc`: generaliza `empty_response.py` a fallas clasificadas, atribucion, feedback de falla externa, conteo una vez por caso pese al fallback de adapters | FR-002, FR-004, FR-007, FR-010, FR-012, SC-001, SC-008 | Opus 5.5 | hecho (75cd319) |
| 4 Metricas y orquestacion | 4a Agregacion sobre casos evaluados y delta pareado en `shared/scoring` (incluye `eval_repeats` y `n_evaluados == 0`) | FR-003, SC-002, SC-007 | Sonnet 5.5 | hecho (a7a3bf2) |
| | 4b Orquestadores: aborto por estado tras cada paso y antes de `save_results()`; reporte `n_evaluados / n_total`; sin segunda evaluacion de test (FR-014); `baseline_only.py` | FR-003, FR-006, FR-014, SC-004 | Sonnet 5.5 | hecho (c61ff98) |
| | 4c Seccion `failures` del YAML validada en `BaseConfigValidator`; `run.json` con estado, conteos y casos `entrada_dato`; corrida abortada sin fila de CSV | FR-006, FR-008, SC-004, SC-005 | Sonnet 5.5 | hecho (def60c8) |
| 5 Regresion y docs | 5a Regresion sin fallas (SC-006) y logs vs `run.json` (SC-005) en ambos subproyectos con LLM simulado | SC-005, SC-006 | Opus 5.5 | hecho (6700f3f) |
| | 5b `docs/GEPA_MANEJO_ERRORES.md`, `docs/METADATA_REPRODUCIBILIDAD.md`, `docs/YAML_CONFIG_REFERENCE.md` | FR-016 | Sonnet 5.5 | hecho (8d771ab) |
| 6 Verificacion real (sesion aparte, opcional) | Corrida corta con API real por proveedor disponible: sin fallas (SC-006) y con `max_tokens` forzado bajo (presupuesto y aborto) | SC-004, SC-006 | Sonnet 5.5 | pendiente |
| Cierre | Code review integral, `[SDD-Check]`, cierre de D-019 y D-021, spec a `active` | todos | Opus 5.5 | pendiente |

## Dependencias

- 1a -> 1b -> 1c. Todo lo demas requiere la fase 1.
- 2a requiere 1c. 2b requiere 2a.
- 3a es independiente de la fase 2. 3b requiere 2a y 3a. 3c requiere 3b. 3e
  requiere 3c (fijado en 3b: 3c implementa el nucleo comun
  `shared/llm/attribution.py` y baja a DEBUG el log de la capa de llamada que
  3e reutiliza). 3d requiere 3c.
- 4a puede ir en paralelo con la fase 3 (solo depende de la forma del
  resultado por caso fijada en 3b). 4b requiere 3c, 3e y 4a. 4c requiere 4b.
- 5a requiere 4c. 5b va despues de 4c. La fase 6 requiere 5a.

## Decisiones de diseno (insumo de 1b y 3b; esas subfases las confirman o corrigen aca)

D1 a D4 confirmadas o corregidas en 1b (2026-11-23) contra `shared/llm`, los
tests de 1a y `dspy==3.2.1` (sondas con pytest, ver "Nota de 1b para 1c").

D1. Modulo `shared/llm/failures.py` (sin importar `dspy`, `gepa_standalone`,
`dspy_gepa_poc` ni `shared/llm/errors.py`, que lo importa a el):
- `FailureClass(str, Enum)`: `configuracion`, `entrada`, `infraestructura`,
  `filtro_salida`, `presupuesto`, `sin_texto`, `formato` (valor = nombre).
- `LLMFailure` (dataclass `frozen`): `clase`, `rol`, `causa` (nombre del tipo
  de excepcion o `finish_reason`), `finish_reason`, `case_id` (None en la capa
  de llamada), `atribucion` (`"candidato"` | `"externa"` | None). Los
  envoltorios que conocen el caso crean la copia con `dataclasses.replace`.
- `LLMCallFailure(Exception)`: `LLMCallFailure(failure, message=None)`, atributo
  `failure`; el mensaje por defecto nombra rol, clase y causa. Se lanza con
  `raise ... from exc` para conservar tipo y mensaje originales (regla 3).
- `RunAborted(Exception)`: NO hereda de `LLMCallFailure` (un envoltorio que
  atrapa `LLMCallFailure` para marcar NE no debe tragarse el aborto). Atributos
  `failure`, `motivo`, `conteo`, `intentos`; el mensaje nombra clase (clave de
  conteo), rol, conteo/intentos y causa probable. Para `presupuesto` agrega
  "el baseline tambien se corta en esos casos" (rol tarea) y "subir
  `max_tokens`"; la sugerencia de bajar el effort depende del modelo del rol y
  la agrega el orquestador en 4b, que tiene el `LLMConfig`.
- `classify_exception(exc) -> FailureClass` y
  `classify_response(response) -> FailureClass | None`: funciones puras con las
  reglas 1 a 6 de la spec, en ese orden. `classify_exception` recorre la cadena
  `__cause__` hasta la primera excepcion de `openai`/LiteLLM y clasifica esa
  (asi reconoce el `ContextWindowExceededError` de DSPy sin importar `dspy`);
  si no hay ninguna, clasifica la excepcion recibida (regla 3 si no aplica otra).
  `classify_response(None)` es `configuracion`. Leen `exc.body` y
  `getattr(message, "refusal", None)` en forma defensiva.
- Destino de `EmptyResponseError` (decidido en 1b): pasa a ser subclase de
  `LLMCallFailure` en `errors.py`, con firma compatible
  `EmptyResponseError(role, finish_reason=None, clase=FailureClass.sin_texto)`,
  conserva `role`, `finish_reason` y su mensaje actual. Desde 2a la capa de
  llamada lanza `EmptyResponseError` (con la clase real: `presupuesto`,
  `filtro_salida` o `sin_texto`) cuando la falla de capa 1 viene de una
  respuesta 200 sin texto, y `LLMCallFailure` en los demas casos (excepciones,
  y `filtro_salida`/`presupuesto` con texto). Asi los `except
  EmptyResponseError` de los adapters y de `dspy_gepa_poc/empty_response.py`
  siguen atrapando exactamente lo mismo hasta que 3c y 3e los migren a
  `LLMCallFailure`; el Cierre la elimina si nada la usa. 1c no cambia quien la
  lanza (`response_text` y `CheckedLM` se tocan en 2a).

D2. `FailureTracker` en `failures.py`, mismo patron que `shared/llm/usage.py`
(`threading.Lock`, instancia de modulo con `get_failure_tracker()`):
- Roles: `task`, `judge`, `reflection` (identificadores del codigo, como
  `LLMConfig.role` y `usage.py`; equivalen a tarea, juez y reflexion de la spec).
  A diferencia de `usage.py`, `judge` NO se pliega en `reflection`: tiene
  umbrales propios. Un rol desconocido es `ValueError`. Los textos de log y de
  `RunAborted` usan los mismos identificadores; 5b documenta la equivalencia en
  `docs/GEPA_MANEJO_ERRORES.md`.
- Clave de conteo (`count_key(failure)`): `entrada` con atribucion `candidato`
  -> `entrada_candidato`, con `externa` -> `entrada_dato`; `presupuesto` con
  `candidato` -> `presupuesto_candidato`, con `externa` -> `presupuesto`; el
  resto, el valor de la clase (incluidos `entrada`/`presupuesto` sin atribucion
  en juez y reflexion). Son los nombres de la spec ("En los conteos figuran
  como ...").
- `record_attempt(rol, case_id=None)`: suma un intento del rol (un caso
  intentado, una vez por caso y candidato, nunca por llamada HTTP) y, si hay
  `case_id`, lo agrega al conjunto de casos unicos del rol. Lo llama quien
  cuenta (D4), no la capa de llamada.
- `record(failure)`: suma en `counts[clave][rol]` y loguea a `WARNING` una vez
  (rol, clave, atribucion, causa, `finish_reason`, `case_id`). `entrada_dato`
  cuenta casos unicos: un `case_id` ya registrado no suma y va a `DEBUG`. Una
  falla `configuracion` registrada tambien fija el aborto (si no estaba). Los
  conteos solo salen de `record`; `abort` no cuenta (D4).
- Umbrales (tasa estricta: aborta si `fallas / denominador > umbral`, con
  `denominador >= minimo del rol`). Se evaluan en `record` y en
  `record_attempt` (una tasa que ya superaba el umbral aborta al alcanzar el
  minimo). Defaults de la spec:
  `{"presupuesto": {"task": .05, "judge": .05, "reflection": .25},
  "infraestructura" | "sin_texto" | "filtro_salida": {"task": .10, "judge": .10},
  "entrada_dato": {"task": .10}, "entrada": {"judge": .10},
  "formato": {"judge": .10},
  "total": {"reflection": .50}}`. `total` suma todas las claves del rol.
  Denominador: intentos del rol, salvo `entrada_dato`, cuyo denominador es la
  cantidad de `case_id` unicos intentados en `task` (ver "Nota de 1b", punto b).
  Claves sin umbral: `configuracion` (aborta siempre), `formato`,
  `entrada_candidato` y `presupuesto_candidato` en tarea, y las que la tabla de
  la spec no lista.
- `min_attempts` por rol, default `{"task": 20, "judge": 20, "reflection": 4}`
  (la tabla de la spec fija el minimo por fila y coincide con el rol). Aplica a
  todas las claves del rol, incluido `entrada_dato` (sobre casos unicos).
- `configure(thresholds=None, min_attempts=None, infra_retries=None)`: mezcla
  parcial sobre los defaults (`{clave: {rol: tasa}}`, `{rol: int}`, `int`);
  claves, roles o rangos invalidos son `ValueError` (la validacion para el
  usuario es la de `BaseConfigValidator`, 4c). `infra_retries` (default 3) vive
  en el tracker para que la seccion `failures` del YAML configure un solo
  objeto; la capa de llamada lo lee si no recibe el parametro.
- `reset()` limpia conteos, intentos, casos y aborto, y restaura la
  configuracion por defecto. Los orquestadores llaman `reset()` y despues
  `configure(...)` al arrancar (4b/4c).
- Estado de aborto: `abort(failure, motivo)` fija el primero (los siguientes se
  ignoran) y loguea a `ERROR`; propiedad `aborted`; `check_abort()` lanza
  `RunAborted` si esta abortado.
- `snapshot()`: dict serializable para `run.json`: `counts` (`{clave: {rol:
  int}}`), `attempts` (`{rol: int}`), `unique_cases` (`{rol: int}`),
  `entrada_dato` (lista ordenada de `case_id`), `aborted` y `abort` (`{clase,
  rol, conteo, intentos, causa, motivo}` o None).

D3. Llamada comun con reintento propio: modulo `shared/llm/call.py` (sin
importar `dspy`). Dos piezas, para que `gepa_standalone` y `CheckedLM` compartan
la misma logica:
- `call_with_infra_retry(fn, role, *, infra_retries=None, backoff_base=1.0)`:
  si el tracker esta abortado lanza `RunAborted` sin llamar; ejecuta `fn()`; ante
  excepcion la clasifica; si es `infraestructura` y quedan reintentos, loguea a
  `DEBUG`, espera `backoff_base * 2**n` segundos (`time.sleep`, 1, 2, 4 s) y
  reintenta (verificando de nuevo el aborto); si es `configuracion`, fija
  `abort` y lanza; en otro caso lanza `LLMCallFailure(...) from exc`. Devuelve
  lo que devuelve `fn`.
- `raise_for_response(response, role)`: aplica `classify_response`; sin falla
  devuelve el texto original (sin strip, como `response_text`); con falla lanza
  `EmptyResponseError` o `LLMCallFailure` (D1), y fija el aborto si es
  `configuracion` (respuesta `None`). No reintenta.
- `checked_completion(kwargs, messages, role, *, infra_retries=None,
  backoff_base=1.0) -> str`: `call_with_infra_retry` sobre
  `litellm.completion(messages=messages, **{**kwargs, "num_retries": 0})`,
  `record_usage(role, response)` por cada respuesta recibida (incluidas las 200
  con falla, que gastaron tokens; como hoy) y `raise_for_response`. Recibe los
  kwargs ya restringidos (`apply_constraints` sigue en el llamador). Nunca llama
  a `record` ni a `record_attempt` (D4).
Es la unica llamada a `litellm.completion` en codigo de produccion. Hoy hay
tres copias de la secuencia kwargs -> `apply_constraints` -> `completion` ->
`record_usage` -> texto (`get_lm_function`, `call_llm` de
`gepa_standalone/core/llm_factory.py` y `SimpleRAGAdapter._call_llm_with_retry`);
las tres pasan a delegar aca. `call_llm` queda en `gepa_standalone` como
fachada (resuelve la config por rol y aplica overrides): moverla no aporta
porque DSPy no la usa y obligaria a cambiar imports en `base_adapter.py` y en
cuatro archivos de tests. Quedan fuera las sondas de configuracion
(`LLMConfig.validate_connection`, `shared/utils/check_deployments.py`). Un test
de 2a verifica que no aparezca otra llamada a `litellm.completion` en
produccion fuera de `shared/llm` y esas sondas.
En DSPy (2a), `CheckedLM` se construye con `num_retries=0` y recibe
`infra_retries`; `forward` envuelve `super().forward(...)` con
`call_with_infra_retry`, y `_process_lm_response` llama a `super()` y despues a
`raise_for_response` (reemplaza `_check_empty`; el uso de tokens sigue
contandose porque DSPy guarda `history` antes). Verificado en 1b con
`dspy==3.2.1`: `lm("...")` llama a `forward` una vez y despues a
`_process_lm_response`; `forward` ve todas las excepciones de los 60
`RETRY_CASES` con 1 llamada HTTP usando `num_retries=0` (el 422 de OpenAI da 1
llamada y `BadRequestError` porque `CheckedLM` usa `drop_params=False`; con
`drop_params=True` serian 2 y `None`, limite conocido de la spec); el
`ContextWindowExceededError` llega envuelto en el de DSPy con el de LiteLLM en
`__cause__`. `aforward` no se usa en el repo (sin `acall`/`aforward`); 2a no lo
cubre y lo deja anotado en el docstring.

D4. Conteo una vez por caso (FR-007), confirmado: la capa de llamada
(`call.py`, `CheckedLM`) nunca llama a `record` ni a `record_attempt`; solo
lanza. Cuenta quien conoce el caso: los adapters de `gepa_standalone`, el
envoltorio de programa/metrica de `dspy_gepa_poc` y, para reflexion, el
envoltorio del `reflection_lm` (un intento y a lo sumo una falla por propuesta,
`case_id` = iteracion de GEPA, FR-013). Asi el fallback de adapters de DSPy no
multiplica el conteo. Excepcion: `configuracion` fija el aborto en la capa de
llamada (no cuenta, solo corta), porque `Evaluate` y GEPA pueden tragarse la
excepcion; el envoltorio que conoce el caso la registra con `record` como
cualquier otra falla. `RunAborted` nunca se registra como falla.

D5 y D6 confirmadas o corregidas en 3b (2026-11-23) contra los adapters de
`gepa_standalone`, `dspy_gepa_poc` y el fuente de `dspy==3.2.1` /
`gepa==0.0.27` (ver "Cierre de 3b").

D5. Atribucion contra el baseline (FR-004). Nucleo comun en
`shared/llm/attribution.py` (nuevo; sin importar `dspy`, `gepa_standalone` ni
`dspy_gepa_poc`), mas una forma de llamar al baseline por subproyecto:
- `BaselineOutcome` (dataclass `frozen`): `clase` (`FailureClass` de capa 1 o
  None = la llamada respondio sin falla de capa 1), `causa`, `finish_reason`.
  Un `formato` del baseline (capa 2) es None: la capa 2 no interviene en la
  atribucion.
- `BaselineProbe(call_baseline)`: `call_baseline(case)` ejecuta el baseline
  sobre el caso con los mismos parametros que la tarea y lanza
  `LLMCallFailure` ante una falla de capa 1 (cualquier otro retorno = sin
  falla). `outcome(case_id, case) -> BaselineOutcome` cachea por `case_id` para
  toda la corrida y hace una sola ejecucion por caso aun con hilos concurrentes
  (`threading.Lock` por `case_id`; `Evaluate` de DSPy usa `num_threads`). Se
  cachea todo resultado salvo `infraestructura`, que deja el caso NE esa vez y
  se vuelve a consultar la proxima vez que el caso lo necesite (decision del
  usuario en la parada de 3b, FR-004 ajustado).
  `RunAborted` se propaga y no se cachea. Cualquier otra excepcion se propaga
  (es un error de programacion, no una falla de LLM).
- `attribute_failure(failure, outcome) -> LLMFailure` (pura) y
  `BaselineProbe.attribute(failure, case_id, case, *, is_baseline) ->
  LLMFailure`: solo `entrada` y `presupuesto` del rol `task` se atribuyen; las
  demas clases y roles salen con `case_id` y sin atribucion. Con `is_baseline`
  la atribucion es `externa` sin llamar. Si no: `outcome.clase` None ->
  `candidato` (misma clase); `outcome.clase` igual a la del candidato ->
  `externa`; otra clase -> la falla del caso pasa a ser la del baseline
  (`clase` y `causa` del outcome, `externa` si es `entrada`/`presupuesto`, sin
  atribucion si no), NE por la tabla (FR-004, "falla por otra clase"); si es
  `configuracion`, la capa de llamada ya fijo el aborto. En todos los casos
  atribuidos queda el `finish_reason` de ambas llamadas.
- `LLMFailure` gana el campo `baseline_finish_reason: str | None = None`
  (`failures.py`), y `FailureTracker.record` lo agrega a su linea de log
  cuando no es None (FR-004 "registrar el `finish_reason` de ambas llamadas";
  FR-007).
- `is_evaluated(failure: LLMFailure | None) -> bool` (misma tabla de
  tratamiento, en `attribution.py`): None -> True; rol `task` con clave de
  conteo `entrada_candidato`, `presupuesto_candidato` o `formato` -> True
  (score 0 del candidato); el resto -> False (NE). `failure_to_dict(failure)`:
  dict serializable con todos los campos, `clase` como texto y `clave`
  (`count_key`).
- Por que la llamada de atribucion no cuenta como intento ni como falla: por D4
  solo cuentan el bucle de casos del adapter y la llamada de puntaje de la
  metrica DSPy (abajo); el probe llama directo a la capa de llamada, que nunca
  cuenta. Sus tokens si se registran en `usage` (rol `task`): son gasto real.
  La falla que se registra es una sola por caso: la del candidato ya atribuida.
- Reconocimiento del baseline: igualdad de texto del `system_prompt`
  (`gepa_standalone`) o del snapshot de instrucciones `{predictor:
  instructions}` (`dspy_gepa_poc`; `dspy.GEPA` solo cambia instrucciones en
  `build_program`, no demos) con el inicial.
- `gepa_standalone`: cada adapter expone `_task_call(system_prompt, example) ->
  str`, el mismo metodo que usa `evaluate` para la tarea (`call_model` o
  `_complete` en RAG, con `task_max_tokens`), asi el probe usa los mismos
  parametros. `BaseAdapter.set_baseline(system_prompt)` guarda el texto y crea
  el probe con `lambda example: self._task_call(system_prompt, example)`. El
  orquestador lo llama una vez tras `load_prompt()` (una linea en
  `universal_optimizer.py`, en 3c). Sin baseline fijado, una falla `entrada` o
  `presupuesto` de tarea es `RuntimeError` con mensaje claro (no se adivina la
  atribucion); las demas clases no lo necesitan.
- `dspy_gepa_poc`: el probe vive en el cierre de la metrica envuelta (D6), que
  `dspy.GEPA` guarda por referencia y no copia. Lo crea
  `create_module_and_metric` con una `deepcopy` del programa sin envolver y el
  snapshot de instrucciones, tomados antes de GEPA (`build_program` copia el
  `student` y nunca lo modifica). `call_baseline(example)` corre ese programa
  con `example.inputs()` dentro de `dspy.context(trace=[])` (no ensucia trazas)
  y con el LM configurado (mismo `CheckedLM`, mismo `max_tokens`);
  `AdapterParseError` del baseline es "sin falla de capa 1". En un programa de
  varios predictores ("pipeline", hoy sin configs) el baseline sobre el caso es
  el programa baseline completo: "el baseline tambien falla" si cualquier
  predictor suyo falla con esa clase; ejecutar solo el predictor que fallo no
  es cacheable por caso (sus entradas dependen de los predictores previos del
  candidato). Cuesta una ejecucion del programa por caso, no una llamada.
- `baseline_only.py` evalua solo el baseline: siempre `externa`, sin probe.
- Limite conocido (ya en la spec): con temperatura > 0 o reasoning la
  atribucion tiene ruido; queda registrada con ambos `finish_reason`. Un
  `infraestructura` del probe deja el caso NE solo en esa evaluacion (no se
  cachea).

D6. Resultado por caso, comun a ambos subproyectos: cada caso evaluado expone
`case_id` (FR-013), `score` (0.0 tecnico si es NE), `evaluated` (bool,
`is_evaluated`) y `failure` (None o el `LLMFailure` ya atribuido). La agregacion
de 4a recibe una lista de `(case_id, score, evaluated)` por repeticion y no
llama al modelo; cada orquestador (4b) la extrae de su resultado:
- `gepa_standalone`: cada elemento de `outputs` (y de `trajectories` si hay)
  lleva las claves propias del adapter mas `case_id`, `evaluated` y `failure`
  (`failure_to_dict` o None); `len(outputs) == len(batch)` siempre (FR-002).
  Por caso: `record_attempt("task", case_id)`; `_task_call`; ante
  `LLMCallFailure`, `attribute` (D5), `record` y salida NE o score 0 segun
  `is_evaluated`. `formato` de capa 2 (FR-010: clasificador, respuesta que no
  normaliza a una de `valid_classes`; extractor, JSON no parseable) se registra
  con `record` y puntua 0. RAG: si la tarea respondio,
  `record_attempt("judge", case_id)` y la falla de capa 1 del juez deja el caso
  NE con rol `judge` (el `formato` del juez es de 3d). `RunAborted` y cualquier
  excepcion que no sea `LLMCallFailure` se propagan: se eliminan el `except
  Exception` que descarta el ejemplo (clasificador, SQL) o puntua 0 (extractor,
  RAG) y el `RuntimeError` de "todos los ejemplos fallaron" (un lote todo NE
  lo resuelven 4a, "sin casos evaluados", y los umbrales). `case_id` faltante
  en un ejemplo es `ValueError` (los loaders lo garantizan desde 3a; sin el no
  hay cache del probe ni casos unicos de `entrada_dato`).
  `make_reflective_dataset` decide por `outputs[i]["evaluated"]`: un NE no
  entra nunca (FR-012, SC-008); `entrada_candidato`, `presupuesto_candidato` y
  `formato` entran como ejemplo negativo con un feedback que nombra la causa
  (es error del prompt).
- `dspy_gepa_poc` (reemplaza `empty_response.py`):
  - `FailedCallPrediction(dspy.Prediction)` (generaliza
    `EmptyResponsePrediction`): campos de salida en None; atributos privados
    (prefijo `_`, que `dspy.Example.__setattr__` no mete en el store)
    `failure` (`LLMFailure`), `instructions` (snapshot del programa que la
    produjo) y `attributed`; propiedad `evaluated`.
  - El mixin de `forward` (mismo mecanismo de subclase dinamica, que sobrevive a
    la `deepcopy` de `build_program` y a `bootstrap_trace_data`) atrapa
    `LLMCallFailure` (incluida `EmptyResponseError`) y `AdapterParseError`
    (`formato` de FR-010, tras el fallback de adapters) y devuelve la
    `FailedCallPrediction` con la falla sin `case_id` y el snapshot de `self`.
    No cuenta: `forward` no conoce el caso (`Evaluate` llama
    `program(**example.inputs())` y `case_id` es label). `RunAborted` se
    propaga. Efecto en la reflexion: con `add_format_failure_as_feedback=False`
    (default, el repo no lo cambia) el `FailedPrediction` de formato ya se
    excluia del dataset reflexivo; con la `FailedCallPrediction` sigue
    excluido en programas de un predictor (sin traza del predictor que fallo).
  - La metrica envuelta (reemplaza `zero_on_empty_response`) distingue la
    llamada de puntaje de la de feedback. Verificado en `dspy==3.2.1`: por
    caso evaluado hay exactamente una llamada sin `pred_name` (`Evaluate`
    `metric(example, pred)`, `bootstrap_trace_data` `metric(example, pred,
    trace)`), y `DspyAdapter.make_reflective_dataset` vuelve a llamar a la
    metrica con `pred_name`/`pred_trace` una vez por predictor y trayectoria
    (`feedback_fn` de `dspy.GEPA.compile`) sobre la misma prediccion. Por eso
    solo la llamada de puntaje cuenta: `record_attempt("task",
    example.case_id)` y, si es `FailedCallPrediction` no atribuida,
    `probe.attribute(..., is_baseline=pred.instructions ==
    snapshot_inicial)`, guarda la falla atribuida en la prediccion
    (`attributed`), `record` y devuelve 0.0. Las llamadas de feedback no
    cuentan y, para una `FailedCallPrediction`, devuelven `{"score": 0.0,
    "feedback": ...}`: si `evaluated` es False, que fue una falla externa (rol,
    clase, causa) y no un error del prompt (FR-012); si es True, la causa como
    error del prompt. Las predicciones normales pasan a la metrica original.
  - 4a/4b leen `EvaluationResult.results` (`example.case_id`, score, y
    `evaluated` de la `FailedCallPrediction` o True).

D7. Seccion YAML (4c), comun a ambos subproyectos y opcional:
`failures: {infra_retries, min_attempts: {<rol>: int}, thresholds: {<clave>:
{<rol>: tasa}}}`, con las claves de conteo y roles de D2 (incluida `total` para
reflexion); se pasa tal cual a `FailureTracker.configure`.
Validacion en `BaseConfigValidator` (claves y rangos de tasa en [0, 1]); sin la
seccion se usan los defaults de la spec. Nombres finales a fijar en 4c y
documentar en `docs/YAML_CONFIG_REFERENCE.md` (5b).

D8. `run.json`: `MetadataManager.create_run` agrega `status`
(`completed` | `aborted`), `abort` (clase, rol, conteo, causa) y `failures`
(snapshot del tracker, casos `entrada_dato`, `n_evaluados / n_total` por
metrica). Una corrida abortada escribe `run.json` y no escribe fila de CSV.

## Riesgos del plan

- 3e es la subfase mas delicada: `dspy.GEPA` copia el programa por candidato y
  `bootstrap_trace_data` llama a `forward` directo (ver
  `dspy_gepa_poc/empty_response.py`); la atribucion y el conteo tienen que
  sobrevivir a esas copias.
- SC-006 depende de que sin fallas nada cambie: el cambio de reintentos (D3)
  altera la cantidad de llamadas solo ante errores, pero 5a debe confirmarlo en
  ambos subproyectos.
- Las reglas de capa 1 dependen de `litellm==1.108.5` + `openai==3.57.0`
  (D-023); `tests/test_litellm_failure_mapping.py` avisa si cambian.

## Detalle por subfase

Toda sesion de subfase lee antes `AGENTS.md`, la spec, este plan y los SSOT
que la subfase toca. "Archivos" es la lista que usa el control de salida: el
diff MUST NOT tocar otros (este plan siempre se puede editar, para marcar el
estado o anotar un bloqueo). Si hace falta tocar otro archivo, la sesion lo
anota como bloqueo y no commitea.

- 1a. Tests RED con payloads de `tests/litellm_failure_payloads.py`: clase de
  capa 1 de los 102 casos (campo de clase esperada), excepcion de DSPy envuelta,
  `FailureTracker` (conteo por clase y rol, `entrada_dato` por caso unico,
  umbrales con minimo de intentos, aborto por `configuracion`, `reset()`,
  concurrencia) y llamada comun (1 llamada HTTP si no es `infraestructura`,
  1 + reintentos si lo es; no llama al LLM si hay aborto). Archivos: tests
  nuevos en `tests/` (`test_failures.py`, `test_failure_call.py`).
- Nota de 1a para 1b (nombres que los tests RED asumieron, a confirmar o
  corregir): llamada comun `shared.llm.call.checked_completion(kwargs, messages,
  role, infra_retries=...)` que devuelve el texto; roles del contador `task` /
  `reflection` / `judge` (no los nombres en espanol de la spec);
  `FailureTracker.snapshot()` con `counts[clase][rol]` y `entrada_dato` (lista de
  `case_id`); `configure(thresholds={clase: {rol: tasa}}, min_attempts=int)`;
  `classify_response(None)` -> `configuracion`; `RunAborted` lo lanza tanto
  `check_abort()` como la llamada comun si el estado ya es abortado; `abort(
  failure, motivo)` y propiedad `aborted`. Los 214 tests nuevos son xfail
  estricto (`test_failures.py`, `test_failure_call.py`); algunos pueden fallar
  hoy solo por `ImportError`, y 1c debe verificar que pasen por la razon correcta
  al quitar la marca.
- Nota de 1b para 1c (D1 a D4 ya reescritas con el resultado; aca solo lo que
  pidio el supervisor y lo que queda para despues):
  - (a) `min_attempts`: un unico entero no expresa la tabla de la spec (20 en
    tarea y juez, 4 en reflexion). Se fija por rol, `{rol: int}` con mezcla
    parcial sobre los defaults (D2, D7). Test de 1a ajustado:
    `configure(..., min_attempts={"task": 2})`.
  - (b) Denominador de `entrada_dato`: la spec dice "0.10 de los casos unicos
    del split"; el test de 1a usaba los intentos de tarea, que con varios
    candidatos sobre los mismos casos diluyen la tasa (3 casos de 20 serian
    3/100). Se fija: casos unicos `entrada_dato` / `case_id` unicos intentados
    en `task` (`record_attempt(rol, case_id)`), con el minimo de 20 sobre casos
    unicos. "Del split" se lee como "casos, no intentos": el contador no conoce
    el split (el `case_id` de FR-013 no siempre lo lleva y ni el adapter ni
    `Evaluate` lo saben), y un caso pertenece a un solo split, asi que los casos
    unicos de la corrida son la union de los splits tocados. Consecuencia: un
    split chico (p. ej. test) no se evalua aislado. Si el usuario quiere tasa
    por split, hace falta pasar el split al contador desde el orquestador
    (cambio de 3b/4b); no bloquea 1c. Aprobado por el usuario el 2026-11-23:
    casos unicos de la corrida, sin tasa por split (spec ajustada). Tests de 1a ajustados
    (`test_entrada_dato_threshold_uses_unique_cases`) y agregados
    (`test_entrada_dato_min_attempts_counts_unique_cases`,
    `test_count_keys_carry_task_attribution`).
  - (c) Roles: identificadores en ingles (`task`, `judge`, `reflection`) en
    codigo, logs, `RunAborted`, `run.json` y YAML; la spec habla de tarea, juez
    y reflexion y 5b documenta la equivalencia. `judge` no se pliega en
    `reflection` (D2). Hoy `SimpleRAGAdapter` usa `"juez"` como rol de causa:
    2a lo pasa a `"judge"` al delegar en `checked_completion`.
  - 1c: `test_failure_call.py` necesita un fixture autouse que anule
    `shared.llm.call.time.sleep` (con 3 reintentos y backoff de 1 s cada caso de
    `infraestructura` tardaria 7 s). Al quitar los `xfail`, verificar que cada
    test pase por la razon correcta (no solo porque ahora existe el modulo).
  - Para 2a y 3e, hallazgo de la sonda de 1b (`dspy==3.2.1`): ante una excepcion
    del LM, `dspy.Predict` con `ChatAdapter` llama a `forward` 3 veces (fallback
    a `JSONAdapter`, que reintenta), salvo que la excepcion sea (o herede de)
    `dspy.utils.exceptions.ContextWindowExceededError`, que se propaga tras 1
    llamada. Consecuencias con D3 tal como esta: `configuracion` sigue en 1
    llamada HTTP (el aborto bloquea las siguientes con `RunAborted`); una falla
    no reintentable (`entrada`, 200 con falla) cuesta 3 llamadas por caso y una
    `infraestructura` persistente 3 x 4 = 12; y envolver el
    `ContextWindowExceededError` de DSPy en `LLMCallFailure` pasaria de 1 a 3
    llamadas. El conteo no cambia (D4), pero SC-009 ("exactamente 1 llamada
    HTTP si no es `infraestructura`... en ambos subproyectos") solo se cumple a
    nivel de `CheckedLM`, no por caso. Decidido por el usuario el 2026-11-23:
    SC-009 se mide por caso (spec ajustada). 2a MUST hacer que la falla que
    lanza `CheckedLM` corte el fallback: una subclase definida en
    `shared/llm/dspy_lm.py` que herede de `LLMCallFailure` (o
    `EmptyResponseError`) y de `dspy.utils.exceptions.ContextWindowExceededError`,
    con un test que cuente 1 llamada HTTP por caso (1 + reintentos si es
    `infraestructura`) a traves de `dspy.Predict`. 2a verifica por sonda que
    ningun modulo usado en el repo trate esa excepcion de forma especial
    (p. ej. truncado de trayectoria).
  - Hueco de la spec: la tabla de umbrales no lista `entrada` en juez (NE sin
    umbral), aunque la spec pide que todo NE quede acotado por umbrales. 1c
    implementa la tabla tal cual. Decidido por el usuario el 2026-11-23:
    `entrada` en juez con umbral 0.10 y minimo 20 (spec ajustada, default de D2
    actualizado); 1c lo implementa.
- 1b. Sin codigo de produccion: confirma o corrige D1 a D4 contra `shared/llm`,
  `dspy==3.2.1` (`dspy.LM.forward`, `_process_lm_response`) y los tests de 1a;
  fija nombres de modulo y funciones. Archivos: este plan; los tests de 1a solo
  si un nombre cambia.
- 1c. Implementa D1 a D4 y quita los `xfail` de 1a. Archivos:
  `shared/llm/failures.py` (nuevo), el modulo de la llamada comun que fije 1b
  (nuevo, en `shared/llm/`), `shared/llm/errors.py`, `shared/llm/__init__.py`,
  tests de 1a. Resultado: `checked_completion` ya fuerza `num_retries=0`;
  `CheckedLM` con `num_retries=0` (`dspy_lm.py`) queda para 2a, como fija D3 y
  la lista de archivos de 1c. Mismo caso: la fila FR-001/FR-006/FR-007/FR-011
  del Coverage mapping sigue `pendiente` hasta que los caminos de llamada usen
  el nucleo; solo FR-015 y SC-009 pasan a vigente.
- 2a. Ver la fila de la tabla y D3. Archivos: `shared/llm/config.py`,
  `shared/llm/dspy_lm.py`, `gepa_standalone/core/llm_factory.py`,
  `gepa_standalone/adapters/simple_rag_adapter.py`,
  `gepa_standalone/adapters/base_adapter.py`, `tests/test_empty_response.py`,
  `tests/test_empty_response_dspy.py`, `tests/test_anthropic_matrix.py`,
  `tests/test_sc006_azure_openai_paths.py`, `tests/test_gepa_adapters.py`,
  `tests/test_shared_llm.py`, test nuevo del punto unico de llamada,
  `tests/conftest.py`, `tests/test_functional_gepa.py`,
  `tests/test_litellm_failure_mapping.py` (ampliado tras el primer intento,
  aprobado por el usuario el 2026-11-23).
- Primer intento de 2a (sesion `-p`, 2026-11-23; sin commit). Resuelto por el
  usuario el 2026-11-23, ver "Resolucion" al final de este punto.
  Se implemento en el arbol (sin commitear): `complete_text` en
  `shared/llm/config.py` (delega en `checked_completion` y conserva el log
  SPEC-103 de respuesta sin texto) usado por `get_lm_function` y `call_llm`;
  `SimpleRAGAdapter._complete` (reemplaza `_call_llm_with_retry`, rol `judge`,
  `RunAborted` no se traga); `CheckedLM` con `num_retries=0`, `forward` por
  `call_with_infra_retry`, `_process_lm_response` por `raise_for_response`, y
  `DspyLLMCallFailure` / `DspyEmptyResponseError` (heredan tambien de
  `dspy.utils.exceptions.ContextWindowExceededError`, lo que corta el fallback
  de `ChatAdapter`). La suite completa dio 152 fallos; la parte que no se puede
  cerrar dentro de los "Archivos" de 2a es:
  1. Estado global del contador entre tests: una excepcion desconocida
     (`RuntimeError("boom")` de un mock de `litellm.completion`) se clasifica
     `configuracion` y fija el aborto del `FailureTracker` de modulo; los tests
     siguientes (p. ej. `test_litellm_regression.py`,
     `test_sc006_azure_openai_paths.py`, que pasan solos) fallan con
     `RunAborted`. Falta un fixture autouse con `get_failure_tracker().reset()`
     en `tests/conftest.py`, que no esta en la lista de 2a.
  2. `classify_response` trata como `filtro_salida` cualquier mensaje con
     `refusal` truthy; las respuestas `MagicMock` de la suite (fixture
     `mock_litellm` de `tests/conftest.py`, `tests/test_functional_gepa.py` y
     decenas de mocks de `tests/test_gepa_adapters.py`) tienen `refusal` como
     `MagicMock` y `finish_reason` sin fijar, asi que todo camino que pasa a
     `raise_for_response` falla. Decision que necesita el usuario: (a) endurecer
     `classify_response` (en `failures.py`, fuera de 2a) para exigir
     `isinstance(refusal, str)` y texto no vacio (los refusal reales son
     strings), o (b) corregir todos los mocks (`refusal=None`,
     `finish_reason="stop"`), incluidos `conftest.py` y `test_functional_gepa.py`.
  3. `tests/test_litellm_failure_mapping.py` (fuera de la lista) fija el
     comportamiento viejo de `CheckedLM`: `test_retry_counts_dspy_lm_default`
     (60 casos, espera 4 o 7 llamadas y `litellm.openai.APIError`) y
     `TestCheckedLMProcessResponse` deben pasar a 1 llamada (o 1 + reintentos si
     `infraestructura`) y `LLMCallFailure`; ese archivo debe entrar en la lista.
  Resolucion (usuario, 2026-11-23): los tests reflejan el comportamiento real,
  no al reves. Punto 2: opcion (b), sin tocar `failures.py` ni la spec: un
  helper unico en `tests/conftest.py` arma respuestas reales
  (`litellm.ModelResponse` con `content`, `finish_reason="stop"`, sin
  `refusal`, con `usage`) y los mocks de `conftest.py`,
  `test_functional_gepa.py` y `test_gepa_adapters.py` pasan a usarlo. Puntos 1
  y 3: se amplia la lista de Archivos (arriba). El relanzamiento continua sobre
  el arbol del primer intento (no lo descarta) y corre con Opus 5.5.
  Nota original del primer intento: agregar a "Archivos" de 2a `tests/conftest.py`,
  `tests/test_functional_gepa.py`, `tests/test_litellm_failure_mapping.py` (y
  `shared/llm/failures.py` si se elige 2.a), y resolver la decision 2. Faltan
  ademas los tests nuevos de 2a: `tests/test_single_call_point.py` (AST sin otra
  `litellm.completion` en produccion fuera de `shared/llm/call.py`, la sonda
  `validate_connection` y `check_deployments.py`; 1 llamada HTTP por caso via
  `dspy.Predict` sobre `RETRY_CASES` y las 200 con falla, con `drop_params=False`;
  `RunAborted` sin HTTP) y la migracion de los tests existentes
  (`test_empty_response*.py`, `test_gepa_adapters.py`, `test_anthropic_matrix.py`
  usan `_call_llm_with_retry`, rol `juez` o 3 llamadas por fallback).
- Cierre de 2a (relanzamiento Opus 5.5, 2026-11-23, d61de1c). Se continuo sobre
  el arbol del primer intento; la produccion se reviso contra D3 sin cambios de
  fondo (solo `noqa: N818` en `DspyLLMCallFailure` y el docstring de rol de
  `response_text`). Tests: `make_completion_response` en `tests/conftest.py`
  (`litellm.ModelResponse` real) y fixture autouse `reset_failure_tracker`; los
  mocks `MagicMock` de `conftest.py`, `test_functional_gepa.py`,
  `test_gepa_adapters.py` y `test_empty_response.py` pasan al helper; los casos
  vacios usan `finish_reason` normalizados reales (`length`, `stop`,
  `content_filter`) y verifican la clase. `test_litellm_failure_mapping.py`
  conserva la evidencia de `dspy.LM` por defecto (ahora con `dspy.LM` directo) y
  agrega `test_retry_counts_checked_lm`. `tests/test_single_call_point.py`: AST
  (solo `call.py::_call`, `validate_connection` y `check_deployments.py`),
  delegacion de los tres caminos con `num_retries=0`, 1 llamada HTTP por caso via
  `dspy.Predict` sobre los 99 payloads con falla (1 + 3 si `infraestructura`),
  control de que sin el corte el fallback repite la llamada, y `RunAborted` sin
  HTTP en los cuatro caminos. Sonda sobre `dspy==3.2.1`: solo `ChatAdapter`
  (corte deseado), `ReAct` e `infer_rules` tratan `ContextWindowExceededError`;
  el repo no usa los dos ultimos. Notas para fases siguientes:
  - Coverage mapping de la spec: la sesion tenia prohibido editar la spec. Queda
    para el supervisor (o el Cierre) pasar a vigente FR-011 (`shared/llm/call.py`,
    `shared/llm/dspy_lm.py`, `tests/test_single_call_point.py`,
    `test_retry_counts_checked_lm`) y ampliar SC-009 con la medicion por caso
    (`TestDspyPredictOneCallPerCase`). FR-001 sigue `pendiente` hasta 3c/3e (los
    adapters y envoltorios aun no reportan al contador).
  - Para 3c/4b: los adapters clasificador y SQL atrapan `RunAborted` como error
    del ejemplo (`test_*_unclassified_error_aborts_run` lo documenta: 1 llamada,
    contador abortado, `RuntimeError` del adapter). RAG ya lo propaga.
  - Para 3c/3e o 5a (SC-005): `complete_text` y `CheckedLM` siguen logueando a
    `WARNING` la respuesta sin texto (log SPEC-103 en la capa de llamada). Cuando
    los envoltorios llamen a `record` (que loguea a `WARNING` una vez por caso)
    habra dos `WARNING` por falla; hay que bajar el de la capa de llamada a
    `DEBUG` (FR-007) y ajustar los tests de `test_empty_response*.py` que lo
    miran.
  - `response_text` ya no tiene usos en produccion (solo su test); el Cierre lo
    elimina junto con `EmptyResponseError` si corresponde.
- 2b. Envoltorio de reflexion en ambos subproyectos (FR-005); verifica contra
  `gepa==0.0.27` como extrae la instruccion (bloque de codigo) y que la
  excepcion saltea la iteracion. Archivos: `shared/llm/config.py`,
  `shared/llm/dspy_lm.py`, `gepa_standalone/core/llm_factory.py`, test nuevo de
  reflexion, `shared/llm/reflection.py` (nuevo), `tests/test_empty_response_dspy.py`
  (ampliado tras el primer intento, aprobado por el usuario el 2026-11-23).
- Resolucion del primer intento de 2b (usuario, 2026-11-23). El relanzamiento
  continua sobre el arbol (no lo descarta), con Opus 5.5:
  1. `test_text_passes_through` refleja el comportamiento nuevo: una propuesta
     con bloque pasa; `"ok"` sin bloque en rol `reflection` se descarta como
     `formato`.
  2. FR-007: en 2b se baja a DEBUG el log de respuesta sin texto de la capa de
     llamada solo para el rol `reflection` (un unico WARNING, el de `record`),
     ajustando los tests de `test_empty_response_dspy.py`. Tarea y juez se
     resuelven cuando sus envoltorios cuenten (3c, 3e).
  3. `reflection_format_failure` y `ReflectionGuard` se mueven a
     `shared/llm/reflection.py`; `shared/llm/config.py` MUST quedar por debajo
     de 800 lineas.
  4. Cableado del callback de GEPA (`case_id` = iteracion) en 4b;
     `dspy_gepa_poc/optimizer.py` entra en la lista de Archivos de 4b.
- Cierre de 2b (relanzamiento Opus 5.5, 2026-11-23, bf346c1). Se continuo sobre el arbol
  del primer intento y se aplicaron los 4 puntos de la Resolucion:
  1. `test_text_passes_through` pasa una propuesta con bloque; nuevos
     `test_reflection_without_block_is_format_failure` (`"ok"` en reflexion es
     `formato` y cuenta) y `test_task_text_without_block_passes_through`.
  2. `log_empty_response(..., call_layer=True)` (desde `complete_text` y
     `CheckedLM`) va a DEBUG en rol `reflection`; queda un unico WARNING por
     falla, el de `record`. `response_text` (sin usos en produccion) no pasa
     `call_layer` y conserva el WARNING, asi `tests/test_empty_response.py`
     (fuera de la lista) no cambia; el Cierre lo elimina. Tests:
     `test_reflection_raises_with_cause` y `test_empty_reflection_skips_iteration`
     verifican el nivel; `_assert_single_warning` en `test_reflection_guard.py`
     lo verifica en ambos subproyectos.
  3. `reflection_format_failure` y `ReflectionGuard` en `shared/llm/reflection.py`
     (nuevo); `shared/llm/config.py` queda en 755 lineas.
  4. Sin cambios en 2b (ya registrado en Archivos de 4b).
  Coverage mapping de la spec: FR-005 y SC-003 vigentes; FR-007 parcial (rol
  `reflection`). La spec no esta en la lista de Archivos de 2b: se edito solo
  esa tabla, por pedido explicito del usuario en el lanzamiento.
- Primer intento de 2b (sesion `-p` Opus 5.5, 2026-11-23; sin commit, arbol sin
  commitear para relanzar sobre el). Implementado:
  - Verificacion contra `gepa==0.0.27` / `dspy==3.2.1`: ambos caminos
    (`ReflectiveMutationProposer.propose_new_texts` y
    `DspyAdapter.propose_new_texts`) extraen con
    `InstructionProposalSignature.output_extractor`, que nunca falla: sin bloque
    de triple backtick devuelve el texto entero (o lo salva si falta un cierre)
    y GEPA lo adopta como instruccion. `propose` atrapa cualquier excepcion y
    saltea la iteracion (candidato vigente sin cambios). Por eso el envoltorio
    detecta `formato` y lanza.
  - `shared/llm/config.py`: `reflection_format_failure(text)` (`formato` con
    causa `sin_bloque_instruccion` o `instruccion_vacia`, usando el extractor de
    GEPA con import diferido) y `ReflectionGuard` (D4: `check_abort` antes de
    llamar, `record_attempt("reflection", case_id)` una vez por propuesta,
    `record` de la falla de capa 1 o `formato` con su `case_id` y relanza;
    `RunAborted` no se registra). `gepa_standalone/core/llm_factory.py`:
    `create_reflection_lm_function` devuelve `ReflectionLM` (envuelve tambien el
    modo verbose). `shared/llm/dspy_lm.py`: `CheckedLM.__call__` con rol
    `reflection` pasa por el guard (salidas str o dict con `text`, como
    `stripped_lm_call`); la falla sigue cortando el fallback de adapters.
  - `case_id` (FR-013, D4): la iteracion de GEPA (`iteracion:<i>`) si el
    envoltorio recibe el callback `on_proposal_start` (`ReflectionLM` y
    `CheckedLM` lo implementan; un intento por iteracion aunque se actualicen
    varios componentes); si no, el numero de propuesta (`propuesta:<n>`). El
    cableado (`callbacks=[reflection_lm]` en `gepa.optimize` y
    `gepa_kwargs={"callbacks": [reflection_lm]}` en `dspy.GEPA`) queda para 4b;
    `dspy_gepa_poc/optimizer.py`, donde se arma `dspy.GEPA`, no esta en la lista
    de Archivos de 4b y deberia entrar.
  - `tests/test_reflection_guard.py` (250 tests, pasan): `formato` contrastado
    con el extractor de GEPA; los 99 payloads con falla en rol `reflection` en
    ambos subproyectos (clase, 1 llamada HTTP o 1 + reintentos, un conteo por
    propuesta, aborto por `configuracion`); 200 con falla via
    `make_completion_response`; `gepa.optimize` y `dspy.GEPA` reales: propuesta
    con falla no crea ni evalua candidato (SC-003), propuesta valida si;
    callback -> `case_id` = iteracion. Comportamiento real observado: con fallas
    persistentes, 3 propuestas fallan y el 4o intento alcanza el minimo de
    reflexion (4) y aborta por umbral (`presupuesto` 0.25 o `total` 0.50)
    antes de llamar; GEPA sigue iterando sin llamadas (`RunAborted` atrapado)
    hasta que el orquestador consulte el estado (4b).
  - `ci_local.sh`: lint, seguridad y cobertura OK; falla 1 test.
  Puntos que requirieron decision del usuario (resueltos arriba):
  1. `tests/test_empty_response_dspy.py::TestCheckedLM::test_text_passes_through`
     fija el comportamiento anterior: un `CheckedLM` de rol `reflection` que
     devuelve `"ok"` (sin bloque) lo deja pasar. Con FR-005 eso es `formato` y
     se descarta. El archivo no esta en la lista de 2b. Propuesta: agregar
     `tests/test_empty_response_dspy.py` a los Archivos de 2b y cambiar el
     contenido del test a una propuesta con bloque (o mover el caso a rol
     `task`).
  2. FR-007 en reflexion (decidir junto con 1): desde 2b el envoltorio de
     reflexion registra con `record` (WARNING una vez por propuesta), y la capa
     de llamada sigue logueando a WARNING la respuesta sin texto
     (`log_empty_response` en `complete_text` y `CheckedLM`): dos WARNING por
     falla sin texto de reflexion. Opciones: (a) en 2b bajar a DEBUG ese log
     solo para el rol `reflection` (unico rol cuyo envoltorio ya cuenta) y
     ajustar `test_empty_response_dspy.py` (`test_reflection_raises_with_cause`,
     `test_empty_reflection_skips_iteration`, que miran el WARNING
     `rol=reflection, finish_reason=...`); (b) dejarlo para 3c/3e/5a como ya
     anota el Cierre de 2a. Recomendacion: (a), asi 2b cumple FR-007 en su rol.
  Nota menor: `shared/llm/config.py` queda en 823 lineas (tope 800 de
  `coding-style`); el Cierre, al eliminar `response_text` (sin usos en
  produccion), lo devuelve bajo el tope.
- 3a. Archivos: `gepa_standalone/data/data_loader.py`,
  `dspy_gepa_poc/data_loader.py`, tests de loaders (existentes o uno nuevo).
- Cierre de 3a (Sonnet 5.5, 2026-11-23, 60b1ba2). `case_id` en cada ejemplo:
  clave `case_id` en el dict de `gepa_standalone` (excluida de las columnas de
  salida por defecto) y campo `case_id` del `dspy.Example` (label, no input).
  Valor: el del CSV (sin espacios) o `<split>:<fila>` si falta o esta vacio;
  la fila cuenta por split y no consume indice en filas descartadas (sin
  split). Tests: `tests/test_case_id_loaders.py`. Coverage mapping: FR-013
  vigente. Sin decisiones pendientes; ids duplicados en un CSV no se validan
  (la spec no lo pide).
- 3b. Sin codigo de produccion: fija D5 y D6 (donde vive el probe, como se
  reconoce el baseline, forma del resultado por caso en ambos subproyectos, como
  sobrevive a las copias de `dspy.GEPA`). Archivos: este plan.
- Cierre de 3b (Opus 5.5, 2026-11-23, 6d2dec1). D5 y D6 reescritas arriba; sin codigo.
  Verificado leyendo el fuente de `dspy==3.2.1` (`/datum1/dev/venvs/reflexio`):
  `Evaluate` llama `program(**example.inputs())` y despues `metric(example,
  prediction)` (`evaluate.py`), asi que `forward` no ve `case_id` y la metrica
  si; `bootstrap_trace_data` envuelve el `forward` de instancia y llama a la
  metrica una vez con `trace`; `DspyAdapter.build_program` hace `deepcopy` del
  `student` y cambia solo instrucciones; `make_reflective_dataset` llama a
  `feedback_fn` (metrica con `pred_name`) por predictor y trayectoria y saltea
  la trayectoria sin traza del predictor; `metric_fn` se guarda por referencia.
  `dspy.Example.__setattr__` deja fuera del store los atributos con `_`.
  Correcciones al plan que salen del diseno (a aprobar en la parada de 3b):
  - El probe lo crea el adapter (`set_baseline`) o la fabrica de la metrica
    DSPy, no el orquestador: solo ellos saben llamar a la tarea con los mismos
    parametros. El orquestador de `gepa_standalone` solo pasa el texto
    baseline.
  - `LLMFailure` gana `baseline_finish_reason` y `record` lo loguea: toca
    `shared/llm/failures.py`.
  - El log de respuesta sin texto de la capa de llamada
    (`log_empty_response(..., call_layer=True)`, desde `complete_text` y
    `CheckedLM`) pasa a DEBUG en todos los roles en 3c (nota de 2a): un unico
    WARNING por falla, el de `record`. Entre 3c y 3e la tarea de DSPy queda
    sin WARNING (aun no cuenta); 3e lo cierra.
  - 3e pasa a depender de 3c (Dependencias) y las listas de Archivos de 3c y
    3e se amplian (abajo).
  Parada de 3b (usuario, 2026-11-23): diseno y correcciones aprobados;
  `infraestructura` del probe NO se cachea (opcion b, FR-004 ajustado). Resto
  de decisiones aprobadas tal cual: en un programa DSPy de varios predictores el
  baseline del caso es el programa completo; `case_id` faltante es
  `ValueError`; sin baseline fijado, `entrada`/`presupuesto` de tarea en
  `gepa_standalone` es `RuntimeError`; un `formato` de DSPy
  (`AdapterParseError`) pasa a `FailedCallPrediction` y deja de contar para
  `max_errors` de `Evaluate`.
- 3c. Ver D5 y D6. Archivos: `gepa_standalone/adapters/*.py`,
  `shared/llm/attribution.py` (nuevo), `shared/llm/failures.py`
  (`baseline_finish_reason` y su log), `shared/llm/__init__.py`,
  `shared/llm/config.py` (solo `log_empty_response` de la capa de llamada a
  DEBUG), `gepa_standalone/universal_optimizer.py` (solo la llamada a
  `adapter.set_baseline(...)` tras `load_prompt()`), `tests/test_gepa_adapters.py`,
  `tests/test_empty_response.py` (SPEC-103 score 0 -> NE, `case_id`),
  `tests/test_empty_response_dspy.py` (solo los tests que miran el nivel del log
  de la capa de llamada), `tests/test_functional_gepa.py` (`case_id` en los
  lotes), `tests/test_failures.py` (si cambia la linea de log),
  `shared/llm/call.py` (solo una funcion nueva que devuelva texto y
  `finish_reason` de la respuesta sana, sin cambiar `checked_completion`;
  ampliado tras el primer intento, aprobado por el usuario el 2026-11-23),
  tests nuevos
  (`tests/test_attribution.py` y de adapters).
- Resolucion del primer intento de 3c (usuario, 2026-11-23): opcion (a).
  `shared/llm/call.py` entra en la lista de 3c para exponer el `finish_reason`
  del baseline sano (FR-004) con una funcion nueva; `checked_completion` no
  cambia. Relanzar sobre el arbol y quitar los 4 `xfail` haciendo pasar los
  tests.
- Primer intento de 3c (Sonnet 5.5, 2026-11-23, sin commit). Implementado y con
  `./shared/utils/ci_local.sh` en verde (2002 passed, 4 xfailed) en el arbol sin
  commitear: `shared/llm/attribution.py`, `baseline_finish_reason` y su log,
  log de la capa de llamada a DEBUG, los cuatro adapters (resultado por caso,
  atribucion, `formato`, `make_reflective_dataset` sin NE), `set_baseline` en
  `universal_optimizer.py` y los tests (`test_attribution.py`,
  `test_gepa_adapters_failures.py`, ajustes a los existentes). Falta un solo
  punto de FR-004 ("La atribucion MUST registrar el `finish_reason` de ambas
  llamadas"): cuando el baseline responde sano, `checked_completion` /
  `raise_for_response` devuelven solo el texto y el `finish_reason` de esa
  respuesta no llega al probe, asi que `baseline_finish_reason` queda None (si el
  baseline falla, si se registra). Cerrarlo exige tocar `shared/llm/call.py`
  (p. ej. que `checked_completion` exponga el `finish_reason` de la respuesta
  sana), archivo fuera de la lista de 3c. Los 4 tests
  `test_healthy_baseline_finish_reason_is_recorded` (`tests/test_gepa_adapters_failures.py`)
  son `xfail(strict=True)` con ese motivo; al resolverlo se les quita la marca.
  Decision pendiente del usuario: (a) ampliar la lista de archivos de 3c con
  `shared/llm/call.py` y relanzar (la sesion retoma el arbol tal como esta), o
  (b) aceptar que el `finish_reason` del baseline sano queda sin registrar y
  ajustar FR-004. Hasta entonces: sin commit, fila de 3c en `pendiente`, filas
  del Coverage mapping sin cambios.
- Cierre de 3c (Sonnet 5.5, relanzamiento, 2026-11-24). Opcion (a):
  `checked_completion_with_reason` en `shared/llm/call.py` devuelve texto y
  `finish_reason` de la respuesta sana y los publica en el bloque
  `capture_finish_reason()` (contextvar, seguro con hilos); `checked_completion`
  delega en ella sin cambiar su comportamiento. `BaseAdapter.set_baseline` envuelve
  la llamada baseline en ese bloque y `BaselineProbe` acepta un `BaselineOutcome`
  devuelto. Los 4 `xfail` quitados; `ci_local.sh` en verde (2006 passed).
- 3d. Archivos: `gepa_standalone/adapters/simple_rag_adapter.py`, tests de RAG.
  Cierre (Sonnet 5.5, 2026-11-23): el juez pide `{"puntaje", "razon"}` como JSON
  en el prompt (sin structured outputs), valida numero finito en [0.0, 1.0] y
  reintenta (`judge_retries`, default 2; el cableado desde el YAML es de 4c). Agotados
  los reintentos lanza `LLMCallFailure(formato, rol judge)`: el caso queda NE.
  Los intentos intermedios van a DEBUG. Tests nuevos en
  `tests/test_rag_judge_json.py`; los tests existentes de RAG pasan el puntaje
  como JSON y se elimino `test_rag_evaluate_with_judge_invalid_format` (fijaba
  score 0.0 ante un puntaje ilegible, contrario a FR-009). `ci_local.sh` en verde
  (2035 passed).
- 3e. Ver D5 y D6 (reutiliza `shared/llm/attribution.py` de 3c sin
  cambiarlo). Archivos: `dspy_gepa_poc/empty_response.py` (o el modulo que lo
  reemplace, segun D6), `dspy_gepa_poc/metrics.py`,
  `dspy_gepa_poc/reflexio_declarativa.py` (solo el armado de programa y
  metrica), `tests/test_empty_response_dspy.py`,
  `tests/test_dspy_metric_feedback.py`, tests nuevos.
- Cierre de 3e (Opus 5.5, 2026-11-23). D5 y D6 sin cambios de diseno;
  `shared/llm/attribution.py` sin tocar. `dspy_gepa_poc/empty_response.py` se
  reemplaza por `dspy_gepa_poc/call_failures.py`: `FailedCallPrediction`,
  `tolerate_call_failures` (mixin de `forward`: `LLMCallFailure` y
  `AdapterParseError` -> prediccion con la falla y el snapshot de instrucciones),
  `guard_metric` (la llamada de puntaje cuenta el intento, atribuye con el probe,
  registra y devuelve 0.0; la de feedback no cuenta y devuelve
  `dspy.Prediction(score=0.0, feedback=...)`: `dspy.GEPA` lee `feedback` con
  `hasattr`, un dict plano perderia el texto) y `guard_program_and_metric`, que
  usa `create_module_and_metric`. `finish_reason` del baseline sano:
  `capture_finish_reason` no aplica (solo lo publica `checked_completion_with_reason`
  y `CheckedLM` no pasa por ahi); se toma del historial del LM con un receptor
  agregado a `settings.caller_modules` dentro de `dspy.context` (thread-local:
  `BaseLM.update_history` agrega cada llamada del hilo al `history` de esos
  modulos, dspy 3.2.1). FR-007: el unico WARNING por caso es el de `record`; el
  aviso de `JSONAdapter` "Failed to use structured output format" (intento
  intermedio del fallback ante `formato`) se baja a DEBUG con un filtro sobre su
  logger. Tests: `tests/test_dspy_call_failures.py` (los 99 payloads con falla
  via `Evaluate`; atribucion candidato/externa/otra clase, cache por caso con
  hilos e `infraestructura` sin cache; formato; feedback; `dspy.GEPA` real con
  copias y `bootstrap_trace_data`, NE fuera del dataset reflexivo y feedback de
  falla externa con dos predictores) y `tests/test_empty_response_dspy.py`
  migrado (NE en vez de score 0; todo `presupuesto` aborta por umbral; error no
  clasificado aborta tras 1 llamada). `ci_local.sh` en verde (2147 passed).
  Notas para fases siguientes:
  - 5b / Cierre: quedan referencias al modulo viejo fuera de la lista de 3e: el
    docstring de `shared/llm/dspy_lm.py` (`tolerate_empty_responses`, "score
    0.0"), el de `log_empty_response` en `shared/llm/config.py` ("la tarea de
    `dspy_gepa_poc` queda sin WARNING hasta 3e") y `docs/GEPA_MANEJO_ERRORES.md`
    (linea 186).
  - 5a (SC-005): una falla `configuracion` deja un WARNING (`record`) y un ERROR
    (el aborto que fija la capa de llamada), en ambos subproyectos; el conteo de
    lineas de log >= WARNING debe distinguir el aborto de la falla.
  - Hallazgo previo, fuera de los FR de 3e: las metricas con feedback de
    `dspy_gepa_poc/metrics.py` devuelven un dict plano; `dspy.GEPA` 3.2.1
    (`feedback_fn`) lo envuelve y el Profesor recibe "This trajectory got a score
    of {...}" con el feedback dentro del repr. No se cambio (decision del
    usuario si se corrige, p. ej. devolver `dspy.Prediction`).
  - 4b: `baseline_only.py` usa `create_module_and_metric`; sus predicciones
    siempre son del baseline (atribucion `externa` sin llamar al probe).
- 4a. Archivos: modulo nuevo en `shared/scoring/`, `shared/scoring/__init__.py`,
  test nuevo.
- 4b. Archivos: `gepa_standalone/universal_optimizer.py`,
  `dspy_gepa_poc/reflexio_declarativa.py`,
  `dspy_gepa_poc/scripts/baseline_only.py`, `dspy_gepa_poc/optimizer.py`
  (cableado del callback de reflexion, decidido tras 2b),
  `shared/display/formatting.py` (solo si el reporte vive ahi), tests de los
  orquestadores.
- Cierre de 4b (Sonnet 5.5, 2026-11-24). Sin bloqueos. `ci_local.sh` en verde
  (2211 tests). Implementado:
  - `shared/display/formatting.py`: `print_summary` acepta `MetricSummary` y
    `delta` (`PairedDelta`: "Improvement (pareado)" con ambos scores y
    `n_pareados`); `format_metric_line` y `format_abort_error` (mensaje de
    `RunAborted` mas la sugerencia de effort solo si `resolve_anthropic_family`
    dice que el modelo del rol lo acepta).
  - Ambos orquestadores: `reset()` del contador al arrancar (`setup_models` en
    DSPy, junto al reset de uso en `gepa_standalone`), `check_abort()` tras
    baseline, optimizacion, val y test y antes de `save_results()`, metricas
    como `MetricSummary` (`self.metric_summaries`, `self.paired_delta`),
    `effective_delta` pareado, `main` captura `RunAborted` (mensaje y exit 1) y
    `abort_message(exc)` por orquestador. `gepa_standalone` pasa
    `callbacks=[reflection_lm]` a `gepa.optimize`; `dspy_gepa_poc/optimizer.py`
    pasa `gepa_kwargs={"callbacks": [reflection_lm]}` si el LM tiene
    `on_proposal_start` (`case_id` = iteracion de GEPA, FR-013).
  - FR-014: `_eval_repeated` de `gepa_standalone` devuelve tambien la ultima
    `EvaluationBatch` y `print_detailed_results` la reutiliza (se elimino la
    evaluacion extra de test).
  - `baseline_only.py`: val y test con `n_evaluados/n_total` (via
    `ReflexioDeclarativa.case_results`), estado consultado tras cada paso,
    `RunAborted` -> mensaje y codigo 1.
  - Tests nuevos: `tests/test_universal_optimizer_failures.py` (pipeline real con
    `litellm.completion` simulado con `make_completion_response`, GEPA real para
    el `case_id` de reflexion) y `tests/test_dspy_orchestrator_failures.py`
    (`Evaluate` y `dspy.GEPA` reales). Unica edicion a un test existente: una
    linea en `tests/test_gepa_adapters_failures.py` (el pipeline simulado de
    `TestOrchestratorSetsBaseline` fija `_summary_delta`).
  Decisiones tomadas dentro del plan (sin tocar la spec):
  - Unidades: en `dspy_gepa_poc` los `MetricSummary` quedan en fraccion (0-1) y
    al CSV / `save_results` van convertidos a la unidad de `Evaluate`
    (porcentaje, 2 decimales) para no cambiar la unidad historica (SC-006).
    `gepa_standalone` conserva fracciones, como antes.
  - Una metrica sin casos evaluados va al CSV como `"N/A"` (el marcador de
    faltante que ya usa `_prepare_row`; sin cambio de esquema) y como `None` en
    `results.json`. Con 0 intentos de test (DSPy sin test set) la metrica es
    `summarize([])` (0/0, "sin casos evaluados"), ya no 0.0.
  - `results.json` de `gepa_standalone` gana las claves `metrics` y
    `paired_delta`; el resto no cambia.
  Notas para fases siguientes:
  - 4c: `run()` propaga `RunAborted` sin escribir `run.json`; 4c debe escribirlo
    con estado `aborted` (en `run()`, antes de relanzar) y con `status` y
    `n_evaluados / n_total` desde `self.metric_summaries` (ya disponible en una
    corrida completada). La seccion `failures` del YAML llama a
    `FailureTracker.configure` tras el `reset()` de 4b.
  - 5a: `print_detailed_results` (tabla de test de `gepa_standalone`) muestra un
    caso NE como 0%; no se toco (fuera de FR-003).
  - `baseline_only.py` sigue ignorando `eval_repeats` (como antes).
- 4c. Archivos: `shared/validation/base_validator.py`,
  `gepa_standalone/config_schema.py`, `dspy_gepa_poc/config_schema.py`,
  `shared/logging/metadata.py`, `gepa_standalone/universal_optimizer.py` y
  `dspy_gepa_poc/reflexio_declarativa.py` (solo `save_results` y arranque del
  tracker), `tests/test_shared_metadata.py`, `tests/test_shared_validation.py`,
  `tests/test_universal_optimizer_configs.py`.
- Cierre de 4c (Sonnet 5.5, 2026-11-24). Sin bloqueos. `ci_local.sh` en verde (2248
  passed, cobertura 98%). Implementado:
  - `failures` (D7): `infra_retries`, `judge_retries` (nombre fijado aca; cierra el
    cableado pendiente de 3d), `min_attempts`, `thresholds`. Validada en
    `BaseConfigValidator._validate_failures` (estructura propia y valores con
    `FailureTracker().configure` sobre una instancia descartable, para no duplicar
    reglas); ambos `ConfigValidator` la heredan por `super().validate`.
  - `configure_failure_tracker()` en ambos orquestadores (`reset()` y despues
    `configure(...)`; en DSPy lo llama `setup_models`). `judge_retries` se pasa a
    `SimpleRAGAdapter` desde `initialize_adapter`; `infra_retries` lo lee la capa de
    llamada desde el contador.
  - D8: `MetadataManager.create_run(status, failures, metrics)` y
    `metrics_coverage`; `save_aborted_run()` en ambos orquestadores (solo `run.json`,
    sin CSV); un fallo al escribirlo se loguea y no tapa el `RunAborted`. En DSPy
    `run()` pasa a envolver `_run_pipeline()`. `save_results` de ambos escribe
    `status: completed`, conteos y metricas.
  - Desvio de lista de archivos: los tests de orquestadores de 4c (cableado y
    `run.json` de DSPy y `gepa_standalone`) quedaron en
    `tests/test_universal_optimizer_configs.py` para no agregar archivos fuera de la
    lista del plan.
  Notas para fases siguientes:
  - 5a (SC-005): `run.json` guarda `failures.counts` y `abort`; un caso `configuracion`
    cuenta en `counts` y fija el aborto (WARNING + ERROR en el log).
  - 5b: documentar `failures` (incl. `judge_retries`) en `docs/YAML_CONFIG_REFERENCE.md`
    y `status`, `abort`, `failures`, `metrics` en `docs/METADATA_REPRODUCIBILIDAD.md`.
  - `baseline_only.py` no escribe `run.json` (fuera del alcance de 4c).
- 5a. Solo tests (nuevos o existentes de los orquestadores) y este plan.
- Cierre de 5a (Opus 5.5, 2026-11-23). Sin bloqueos; produccion sin tocar.
  `ci_local.sh` en verde (2267 passed, cobertura 98%). La spec se edito solo en
  el Coverage mapping, por pedido del usuario en el lanzamiento.
  - `tests/orchestrator_e2e.py` (nuevo, auxiliar): `UniversalOptimizer.run()` y
    `ReflexioDeclarativa.run()` de punta a punta sobre YAML, CSV y prompt reales
    en `tmp_path`, GEPA y DSPy reales; solo se simula el transporte
    (`litellm.completion` y `dspy.clients.lm.litellm_completion`) con
    `make_completion_response` o excepciones reales de LiteLLM, y se anula la
    sonda `validate_connection`. Clasificador y RAG con juez en
    `gepa_standalone`, modulo dinamico en `dspy_gepa_poc`. Captura `run.json`,
    CSV maestro, `results.json`, llamadas por modelo y todo registro WARNING o
    superior del proceso.
  - SC-006 (`tests/test_sc006_no_failure_regression.py`, 10 tests). Oraculo: el
    comportamiento previo a SPEC-104 (commit 35c5b1c), leido con `git diff
    35c5b1c HEAD` (la sesion `-p` no puede crear un worktree ni correr scripts
    sueltos) y derivado a mano de respuestas fijas: scores = media de todos los
    casos, `effective_delta = optimizado - baseline`, rangos 0, unidad de
    `Evaluate` en DSPy; claves previas de `run.json` (`experiment_name`, `seed`,
    `models`, `created_at`, `usage`) con los mismos valores mas las de FR-008;
    esquema y valores del CSV; ningun WARNING. Sin regresion en ambos
    subproyectos. Sin fallas hay exactamente 1 llamada HTTP por caso evaluado
    (sin reintentos, sin fallback de `ChatAdapter`, sin llamadas de atribucion
    al baseline): confirma el riesgo "SC-006 depende de que sin fallas nada
    cambie". Unica diferencia, esperada: `gepa_standalone` hace `len(test)`
    llamadas de tarea menos (FR-014 quito la segunda evaluacion de test), y
    `usage` / `Tokens Task` bajan en esa medida.
  - SC-005 (`tests/test_sc005_logs_vs_run_json.py`, 9 tests). Corridas
    completadas con fallas de todas las clases de tarea (`infraestructura`,
    `entrada_dato`, `presupuesto_candidato`, `formato`), `formato` de reflexion
    y, en RAG, `formato` y `presupuesto` del juez; abortadas por
    `configuracion`, por umbral de tarea y por umbral de reflexion atrapado por
    GEPA; en ambos subproyectos (RAG solo en `gepa_standalone`). Se exige: conteo
    por (clave, rol) de las lineas WARNING de `record` igual a
    `run.json["failures"]["counts"]`, cada una con `case_id`; la linea ERROR del
    aborto se compara aparte con `run.json["abort"]` (nota de 3e y 4c: la
    `configuracion` deja su WARNING, que cuenta, y el ERROR del aborto, que no);
    ninguna otra linea WARNING o superior. Pasa sin cambios de produccion.
  - FR-007 en el juez (pendiente en el Coverage mapping): la corrida RAG
    verifica una falla por caso evaluado (1 + `judge_retries` llamadas por
    puntaje ilegible, un solo conteo), reintentos del puntaje a DEBUG y
    `presupuesto` del juez sin reintento. Fila FR-007 pasa a vigente.
  Notas para el Cierre (decision del usuario; ningun test fija estos
  comportamientos):
  - Hallazgo: tras una falla `configuracion`, `run.json["abort"]["conteo"]` y el
    mensaje de `RunAborted` dicen `conteo=0/N` aunque `counts.configuracion` del
    rol es 1: la capa de llamada fija el aborto (D4) antes de que el envoltorio
    registre la falla, y `_abort_locked` toma el conteo de ese momento. No rompe
    SC-005 tal como lo fija la nota de 3e (aborto comparado aparte), pero el
    error de FR-006 "nombra el conteo" con un 0 enganoso. Opciones: (a) que
    `record` actualice `conteo` del aborto si la falla registrada es de la misma
    clave y rol (toca `shared/llm/failures.py`); (b) aceptarlo y que 5b
    documente que el conteo del aborto es el del momento del corte.
  - Relacionado: tras un aborto por umbral, la metrica de DSPy puede registrar la
    falla del caso en curso (el `record_attempt` va despues de la llamada), asi
    que `counts` final puede superar `abort.conteo`. Es coherente con el log;
    5b deberia documentar que `abort.conteo` es el del momento del corte.
  - Nota de 4b sobre `print_detailed_results` (tabla de test de
    `gepa_standalone` muestra un caso NE como 0% / "NO"): no es log ni
    `run.json`, asi que queda fuera de SC-005 y SC-006, y no es una metrica
    reportada de FR-003 sino el detalle por caso. Sin cambios; si se quiere
    mostrar "NE (clase)", es un cambio de `shared/display/formatting.py` para el
    Cierre.
- 5b. Archivos: `docs/GEPA_MANEJO_ERRORES.md`,
  `docs/METADATA_REPRODUCIBILIDAD.md`, `docs/YAML_CONFIG_REFERENCE.md`.
- Cierre de 5b (Sonnet 5.5, 2026-11-24, 8d771ab). Sin bloqueos; solo docs y la
  fila FR-016 del Coverage mapping (por pedido del usuario). `ci_local.sh` en
  verde (2267 passed, 98.47%).
  - `docs/GEPA_MANEJO_ERRORES.md`: seccion "Estado vigente: fallas clasificadas
    (SPEC-104)" reemplaza la de SPEC-103 (clases, tratamiento por rol, atribucion,
    reintentos, aborto, equivalencia de roles `task`/`judge`/`reflection`); el
    descarte directo queda marcado como historico. Pendiente 2 de la parada de
    fin de fase 5: documentado que tras un aborto por umbral en DSPy `counts`
    final puede superar `abort.conteo`. Pendiente 4 (parte de 5b): referencias a
    `empty_response.py` reemplazadas por `call_failures.py`.
  - `docs/YAML_CONFIG_REFERENCE.md`: nueva seccion 3 `failures` (`infra_retries`,
    `judge_retries`, `min_attempts`, `thresholds`, defaults y ejemplo); "Campos
    Compartidos" pasa a la seccion 4.
  - `docs/METADATA_REPRODUCIBILIDAD.md`: `status`, `abort`, `failures` y `metrics`
    de `run.json`.
  - La documentacion del conteo 0 en el aborto por `configuracion` (pendiente 1)
    queda como "pendiente de decision": si el Cierre elige la opcion (a), hay que
    quitar esa viñeta de `GEPA_MANEJO_ERRORES.md`.
  - Siguen para el Cierre (no son de 5b): docstrings de `shared/llm/dspy_lm.py` y
    `log_empty_response` (`shared/llm/config.py`) con referencias al modulo viejo,
    y `response_text` sin usos.

## Lanzamiento por CLI (modo no interactivo)

Cada subfase de las fases 1 a 5 corre como una sesion `-p` aparte, con el
modelo de la tabla. La fase 6 y el Cierre van en sesion interactiva.

- Subfases Sonnet 5.5: `claude-e -p ... --model claude-sonnet-5-5` (perfil de
  empresa, API key propia).
- Subfases Opus 5.5: `claude -p ... --model claude-opus-5-5`.

```bash
SUB=1a   # subfase a ejecutar
mkdir -p "$HOME/spec104_logs"   # logs fuera del repo
claude-e -p "Implementar SPEC-104 subfase $SUB segun docs/plans/PLAN_SPEC-104_fallas_tecnicas_justas.md. \
Sesion no interactiva: si algo exige decision del usuario, no improvisar; \
registrarlo en el plan como bloqueo, no commitear y terminar." \
  --model claude-sonnet-5-5 \
  --permission-mode acceptEdits \
  --allowedTools "Bash(./shared/utils/ci_local.sh) Bash(.venv/bin/python -m pytest:*) Bash(git status) Bash(git diff:*) Bash(git add:*) Bash(git commit:*)" \
  | tee "$HOME/spec104_logs/$SUB.log"
```

Reglas:

- Una subfase por invocacion, en el orden de Dependencias.
- `--permission-mode acceptEdits` y `--allowedTools` son necesarios: sin ellos
  la sesion `-p` no puede editar ni correr `ci_local.sh`. No hay `python` en el
  PATH: siempre `.venv/bin/python`.
- Las subfases que verifican internals de librerias (2a, 2b, 3b, 3e) agregan
  `--add-dir /datum1/dev/venvs/reflexio`: `.venv` es un symlink a ese
  directorio, fuera del repo, y sin el flag la sesion `-p` no puede leer el
  fuente de dspy, gepa ni litellm (paso en 1b). Alternativa: sondas con pytest.
- Commits sin trailer `Co-Authored-By`, y sin mezclar `-n`/`-q` con
  `git commit` en el mismo comando (falso positivo del hook que bloquea saltear
  hooks).
- Si una subfase deja un bloqueo, se resuelve en una sesion interactiva y se
  relanza.

## Seguimiento

Una sesion interactiva de Opus 5.5 supervisa las fases 1 a 5. No implementa ni
guarda estado propio: el estado es la columna Estado de este plan. Si la sesion
se corta, otra retoma leyendo el plan.

Arranque: "Supervisar SPEC-104 segun la seccion Seguimiento de
docs/plans/PLAN_SPEC-104_fallas_tecnicas_justas.md".

Ciclo por subfase:

1. Tomar la primera subfase `pendiente` cuyas dependencias esten `hecho`.
2. Lanzarla con el comando de "Lanzamiento por CLI" en segundo plano, con el
   modelo de la tabla, y esperar el aviso de fin (sin polling).
3. Aplicar el control de salida. Si pasa, volver a 1. Si falla, detenerse e
   informar al usuario: no relanzar ni corregir por cuenta propia.

Control de salida (todos deben cumplirse):

- Hay un commit nuevo (`git log -1`) y el arbol queda limpio (`git status`).
- `./shared/utils/ci_local.sh` pasa.
- La subfase figura como `hecho` en la tabla, con el hash del commit.
- No quedo un bloqueo anotado en este plan.
- El diff (`git diff --stat HEAD~1`) toca solo los archivos del Detalle por
  subfase.
- El diff cumple los FR de la fila, contrastado con el texto de la spec y no
  con el resumen de la sesion (las sesiones `-p` tienden a "anotar un desvio"
  en vez de cumplir un MUST). Se revisa el diff completo en las fases 1 y 2, en
  3e y cuando un punto anterior falla.

Paradas obligatorias (la sesion se detiene y espera al usuario):

- Despues de 1b: el usuario aprueba el diseno del nucleo.
- Despues de 1c: el usuario aprueba el nucleo antes de tocar los caminos de
  llamada.
- Despues de 3b: el usuario aprueba el diseno de atribucion y de prediccion NE.
- Al terminar la fase 5: la fase 6 gasta API real y va en otra sesion.

Contexto: de cada log leer solo el final (`tail -n 40`); entrar al log completo
o al diff solo cuando un control falla.

## Proxima sesion

Estado al 2026-11-23 (sesion supervisora detenida por el usuario tras el
control de 5a). Fases 1 a 4 y 5a `hecho`; arbol limpio en `c19d87b`,
`ci_local.sh` verde (2267 passed). Arrancar con: "Supervisar SPEC-104 segun la
seccion Seguimiento de docs/plans/PLAN_SPEC-104_fallas_tecnicas_justas.md".
Siguiente subfase: 5b (Sonnet 5.5); al terminarla, parada obligatoria (fin de
fase 5).

Arreglo previo a 5b (2026-11-24, fuera de 5b): `5810d67` (filtro de loggers propios en `caplog` para pytest 9.1+) y `96b8743` (pin `openai==3.57.0` y `httpx==0.28.1`, D-023); `ci_local.sh` verde (2267 passed, 98.47%).

Practicas de lanzamiento que funcionaron (agregar al prompt de cada subfase):
- "Los tests MUST verificar el comportamiento deseado segun la spec, con
  respuestas reales via el helper de tests/conftest.py (ver
  docs/CONTRIBUTING.md)".
- "Al cerrar, actualizar las filas del Coverage mapping de la spec que
  correspondan. Registrar el hash en la tabla en un commit aparte de docs".
- Subfases que leen internals (y el Cierre): `--add-dir
  /datum1/dev/venvs/reflexio`.
- Un relanzamiento tras bloqueo continua sobre el arbol sin commitear y la
  resolucion se registra antes en este plan (commit solo del plan).

Decisiones del usuario (2026-11-24, tras 5b), resueltas en el commit
"fix(spec-104): conteo del aborto por configuracion, NE en la tabla de detalle y
limpieza de SPEC-103" (a2c0ce5): punto 1 corregido (el aborto que fija la
capa de llamada queda pendiente y `record` de la misma (clave, rol) completa
conteo, intentos y caso antes del ERROR; `snapshot` lo emite si nadie la
cuenta), punto 3 con opcion (a) (`print_detailed_results` muestra "NE" con la
clave de la falla) y punto 4 corregido (`response_text` eliminado,
`log_empty_response` siempre a DEBUG, docstring de `dspy_lm.py` al dia). Punto
7 hecho (login renovado). Quedan para el Cierre: code review, `[SDD-Check]`,
D-019, D-021 y spec a `active`.

Pendientes para la parada de fin de fase 5 / Cierre (decision del usuario):
1. Conteo 0 en el aborto por `configuracion`: `run.json["abort"]["conteo"]` y
   `RunAborted` dicen `conteo=0/N` aunque `counts.configuracion` vale 1 (la capa
   de llamada fija el aborto antes del `record`). Recomendacion del supervisor:
   que `record` actualice el conteo del aborto vigente (toca
   `shared/llm/failures.py`, en el Cierre), porque FR-006 pide nombrar el
   conteo y un 0 confunde.
2. En DSPy, tras un aborto por umbral, `counts` final puede superar
   `abort.conteo` (falla del caso en curso): documentar en 5b.
3. Tabla de detalle de test de `gepa_standalone` muestra un NE como 0% / "NO"
   (`shared/display/formatting.py`): decidir si se muestra "NE".
4. Referencias viejas a `empty_response.py` (docstrings de
   `shared/llm/dspy_lm.py` y `log_empty_response`) y `response_text` sin usos:
   limpiar en el Cierre; `docs/GEPA_MANEJO_ERRORES.md` en 5b.
5. Riesgo: el oraculo de SC-006 de 5a sale de leer el codigo previo a
   `35c5b1c`, no de correrlo; la fase 6 (API real) lo contrasta.
6. D-024 (`historial/sdd.md`, feedback de metricas DSPy como dict plano): se
   corrige despues del Cierre, aparte.
7. El login de `claude` (subfases Opus) vence entre 2026-11-25 y 2026-11-28:
   `claude auth login` antes del Cierre.
