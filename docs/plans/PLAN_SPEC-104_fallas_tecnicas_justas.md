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
| | 1b Diseno: confirmar D1 a D4 contra el codigo (API de `failures.py`, destino de `EmptyResponseError`, punto de reintento en `CheckedLM`, conteo una vez por caso) | FR-001, FR-007, FR-011 | Opus 5.5 | hecho |
| | 1c Clasificador, `FailureTracker` y llamada con reintento propio; `num_retries=0` en LiteLLM y `CheckedLM` (GREEN) | FR-001, FR-006, FR-007, FR-011, FR-015 | Sonnet 5.5 | pendiente |
| 2 Caminos de llamada | 2a Los tres lugares que hoy llaman a `litellm.completion` delegan en la llamada comun: `get_lm_function`, `call_llm` (queda como fachada en `gepa_standalone/core/llm_factory.py`) y `SimpleRAGAdapter._call_llm_with_retry` (se elimina, con su reintento por `content_filter`); `CheckedLM` con `num_retries=0`; `ContextWindowExceededError` de DSPy por `__cause__`; test de que no hay otra llamada a `litellm.completion` en produccion | FR-001, FR-011, FR-015 | Sonnet 5.5 | pendiente |
| | 2b Reflexion: descarte en el envoltorio (clase de capa 1 y `formato` sin bloque de instruccion) en ambos subproyectos; verificacion contra GEPA 0.0.27 y `dspy.GEPA` | FR-005, SC-003 | Opus 5.5 | pendiente |
| 3 Casos y atribucion | 3a Identificador canonico de caso en ambos loaders | FR-013 | Sonnet 5.5 | pendiente |
| | 3b Diseno de la atribucion contra el baseline (D5) y de la prediccion NE en DSPy (D6) | FR-004, FR-012 | Opus 5.5 | pendiente |
| | 3c Adapters de `gepa_standalone`: resultado por caso (evaluado / NE / score 0 por clase), atribucion, `make_reflective_dataset` sin NE, `formato` por adapter | FR-002, FR-004, FR-010, FR-011, FR-012, SC-001, SC-008 | Sonnet 5.5 | pendiente |
| | 3d Juez de RAG con JSON en el prompt, validacion de rango y reintentos | FR-009 | Sonnet 5.5 | pendiente |
| | 3e `dspy_gepa_poc`: generaliza `empty_response.py` a fallas clasificadas, atribucion, feedback de falla externa, conteo una vez por caso pese al fallback de adapters | FR-002, FR-004, FR-007, FR-010, FR-012, SC-001, SC-008 | Opus 5.5 | pendiente |
| 4 Metricas y orquestacion | 4a Agregacion sobre casos evaluados y delta pareado en `shared/scoring` (incluye `eval_repeats` y `n_evaluados == 0`) | FR-003, SC-002, SC-007 | Sonnet 5.5 | pendiente |
| | 4b Orquestadores: aborto por estado tras cada paso y antes de `save_results()`; reporte `n_evaluados / n_total`; sin segunda evaluacion de test (FR-014); `baseline_only.py` | FR-003, FR-006, FR-014, SC-004 | Sonnet 5.5 | pendiente |
| | 4c Seccion `failures` del YAML validada en `BaseConfigValidator`; `run.json` con estado, conteos y casos `entrada_dato`; corrida abortada sin fila de CSV | FR-006, FR-008, SC-004, SC-005 | Sonnet 5.5 | pendiente |
| 5 Regresion y docs | 5a Regresion sin fallas (SC-006) y logs vs `run.json` (SC-005) en ambos subproyectos con LLM simulado | SC-005, SC-006 | Opus 5.5 | pendiente |
| | 5b `docs/GEPA_MANEJO_ERRORES.md`, `docs/METADATA_REPRODUCIBILIDAD.md`, `docs/YAML_CONFIG_REFERENCE.md` | FR-016 | Sonnet 5.5 | pendiente |
| 6 Verificacion real (sesion aparte, opcional) | Corrida corta con API real por proveedor disponible: sin fallas (SC-006) y con `max_tokens` forzado bajo (presupuesto y aborto) | SC-004, SC-006 | Sonnet 5.5 | pendiente |
| Cierre | Code review integral, `[SDD-Check]`, cierre de D-019 y D-021, spec a `active` | todos | Opus 5.5 | pendiente |

## Dependencias

- 1a -> 1b -> 1c. Todo lo demas requiere la fase 1.
- 2a requiere 1c. 2b requiere 2a.
- 3a es independiente de la fase 2. 3b requiere 2a y 3a. 3c y 3e requieren 3b;
  3c y 3e son independientes entre si. 3d requiere 3c.
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
  "entrada_dato": {"task": .10}, "formato": {"judge": .10},
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

D5. Atribucion contra el baseline (FR-004): un `BaselineProbe` por corrida, con
cache `case_id -> resultado de la llamada baseline` (clase de capa 1 o "ok" y
`finish_reason`). Lo crea el orquestador con el prompt/programa baseline y se lo
pasa al adapter o al envoltorio DSPy. Un prompt es "el baseline" si su texto (o
el snapshot de instrucciones en DSPy) es igual al inicial. 3b define donde vive
el probe (shared o por subproyecto) y como evitar que la llamada de atribucion
cuente como intento del candidato.

D6. Resultado por caso. `gepa_standalone`: cada elemento de `outputs` lleva
`failure` (dict del `LLMFailure` o None); el score es 0.0 tecnico si el caso es
NE. `dspy_gepa_poc`: una `FailedCallPrediction` (generaliza
`EmptyResponsePrediction`) que lleva el `LLMFailure`; la metrica puntua 0.0
tecnico y devuelve feedback de falla externa (FR-012). En ambos, la agregacion
de 4a lee el flag NE de cada caso desde `outputs` o desde
`EvaluationResult.results`; no recalcula llamando al modelo.

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
    (cambio de 3b/4b); no bloquea 1c. Tests de 1a ajustados
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
    nivel de `CheckedLM`, no por caso. [NEEDS CLARIFICATION: ¿SC-009 se mide
    por llamada al LM o por caso de DSPy? Si es por caso, 2a debe hacer que
    `CheckedLM` lance una excepcion que corte el fallback (p. ej. que
    `LLMCallFailure` de `CheckedLM` herede del `ContextWindowExceededError` de
    DSPy, o que el envoltorio de 3e memorice la falla del caso).] No bloquea
    1c, que no toca `CheckedLM`; se decide en la parada posterior a 1b o en 2a.
  - Hueco de la spec: la tabla de umbrales no lista `entrada` en juez (NE sin
    umbral), aunque la spec pide que todo NE quede acotado por umbrales. 1c
    implementa la tabla tal cual. [NEEDS CLARIFICATION: ¿umbral para `entrada`
    del juez (p. ej. 0.10 / 20 como las otras NE)?]
- 1b. Sin codigo de produccion: confirma o corrige D1 a D4 contra `shared/llm`,
  `dspy==3.2.1` (`dspy.LM.forward`, `_process_lm_response`) y los tests de 1a;
  fija nombres de modulo y funciones. Archivos: este plan; los tests de 1a solo
  si un nombre cambia.
- 1c. Implementa D1 a D4 y quita los `xfail` de 1a. Archivos:
  `shared/llm/failures.py` (nuevo), el modulo de la llamada comun que fije 1b
  (nuevo, en `shared/llm/`), `shared/llm/errors.py`, `shared/llm/__init__.py`,
  tests de 1a.
- 2a. Ver la fila de la tabla y D3. Archivos: `shared/llm/config.py`,
  `shared/llm/dspy_lm.py`, `gepa_standalone/core/llm_factory.py`,
  `gepa_standalone/adapters/simple_rag_adapter.py`,
  `gepa_standalone/adapters/base_adapter.py`, `tests/test_empty_response.py`,
  `tests/test_empty_response_dspy.py`, `tests/test_anthropic_matrix.py`,
  `tests/test_sc006_azure_openai_paths.py`, `tests/test_gepa_adapters.py`,
  `tests/test_shared_llm.py`, test nuevo del punto unico de llamada.
- 2b. Envoltorio de reflexion en ambos subproyectos (FR-005); verifica contra
  `gepa==0.0.27` como extrae la instruccion (bloque de codigo) y que la
  excepcion saltea la iteracion. Archivos: `shared/llm/config.py`,
  `shared/llm/dspy_lm.py`, `gepa_standalone/core/llm_factory.py`, test nuevo de
  reflexion.
- 3a. Archivos: `gepa_standalone/data/data_loader.py`,
  `dspy_gepa_poc/data_loader.py`, tests de loaders (existentes o uno nuevo).
- 3b. Sin codigo de produccion: fija D5 y D6 (donde vive el probe, como se
  reconoce el baseline, forma del resultado por caso en ambos subproyectos, como
  sobrevive a las copias de `dspy.GEPA`). Archivos: este plan.
- 3c. Archivos: `gepa_standalone/adapters/*.py`, `tests/test_gepa_adapters.py`,
  tests nuevos de adapters.
- 3d. Archivos: `gepa_standalone/adapters/simple_rag_adapter.py`, tests de RAG.
- 3e. Archivos: `dspy_gepa_poc/empty_response.py` (o el modulo que lo
  reemplace, segun D6), `dspy_gepa_poc/metrics.py`,
  `dspy_gepa_poc/reflexio_declarativa.py` (solo el armado de programa y
  metrica), `tests/test_empty_response_dspy.py`,
  `tests/test_dspy_metric_feedback.py`, tests nuevos.
- 4a. Archivos: modulo nuevo en `shared/scoring/`, `shared/scoring/__init__.py`,
  test nuevo.
- 4b. Archivos: `gepa_standalone/universal_optimizer.py`,
  `dspy_gepa_poc/reflexio_declarativa.py`,
  `dspy_gepa_poc/scripts/baseline_only.py`, `shared/display/formatting.py`
  (solo si el reporte vive ahi), tests de los orquestadores.
- 4c. Archivos: `shared/validation/base_validator.py`,
  `gepa_standalone/config_schema.py`, `dspy_gepa_poc/config_schema.py`,
  `shared/logging/metadata.py`, `gepa_standalone/universal_optimizer.py` y
  `dspy_gepa_poc/reflexio_declarativa.py` (solo `save_results` y arranque del
  tracker), `tests/test_shared_metadata.py`, `tests/test_shared_validation.py`,
  `tests/test_universal_optimizer_configs.py`.
- 5a. Solo tests (nuevos o existentes de los orquestadores) y este plan.
- 5b. Archivos: `docs/GEPA_MANEJO_ERRORES.md`,
  `docs/METADATA_REPRODUCIBILIDAD.md`, `docs/YAML_CONFIG_REFERENCE.md`.

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
- Las subfases que verifican internals de librerias (1b, 2b, 3b, 3e) pueden
  necesitar leer `.venv/lib/...`; eso entra en las herramientas de lectura y no
  requiere permisos extra.
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

Plan aprobado el 2026-11-23. Arrancar con: "Supervisar SPEC-104 segun la
seccion Seguimiento de docs/plans/PLAN_SPEC-104_fallas_tecnicas_justas.md".
Primera subfase: 1a.
