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
| | 1b Diseno: confirmar D1 a D4 contra el codigo (API de `failures.py`, destino de `EmptyResponseError`, punto de reintento en `CheckedLM`, conteo una vez por caso) | FR-001, FR-007, FR-011 | Opus 5.5 | pendiente |
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

D1. Modulo `shared/llm/failures.py` (sin importar `dspy`, `gepa_standalone` ni
`dspy_gepa_poc`):
- `FailureClass` (enum de texto): `configuracion`, `entrada`, `infraestructura`,
  `filtro_salida`, `presupuesto`, `sin_texto`, `formato`.
- `LLMFailure` (dataclass `frozen`): `clase`, `rol`, `causa` (tipo de error o
  `finish_reason`), `finish_reason`, `case_id` (None en la capa de llamada),
  `atribucion` (`candidato` | `externa` | None).
- `LLMCallFailure(Exception)`: lleva un `LLMFailure`. Es lo que lanza la capa de
  llamada; no cuenta nada.
- `classify_exception(exc) -> FailureClass` y
  `classify_response(response) -> FailureClass | None`: funciones puras con las
  reglas de la capa 1 de la spec, en ese orden. Leen `exc.body` y
  `getattr(message, "refusal", None)` en forma defensiva.
- Destino de `EmptyResponseError` (lo decide 1b): opcion preferida, que pase a
  ser subclase de `LLMCallFailure` con clase `sin_texto` mientras se migran sus
  usos, y se elimine al cierre si nada la usa.

D2. `FailureTracker` en `failures.py`, mismo patron que `shared/llm/usage.py`
(`threading.Lock`, `reset()` por corrida, instancia de modulo con
`get_failure_tracker()`):
- `record_attempt(rol)` y `record(failure)`: intentos y fallas por (clase, rol);
  `entrada_dato` por `case_id` unico.
- `configure(thresholds, min_attempts)` desde el YAML (4c); defaults de la spec.
- Estado de aborto: `abort(failure, motivo)` lo fija `configuracion` en la capa
  de llamada y la superacion de umbral en `record`. `check_abort()` lanza
  `RunAborted` con clase, rol, conteo y causa probable; `aborted` lo consulta la
  capa de llamada antes de llamar al LLM.
- `snapshot()`: dict serializable para `run.json` (4c).

D3. Llamada comun con reintento propio en `shared/llm` (nombre a fijar en 1b,
p. ej. `checked_completion(kwargs, messages, role)`): verifica `aborted`, llama
a `litellm.completion` con `num_retries=0`, clasifica la excepcion o la
respuesta, reintenta solo `infraestructura` con backoff exponencial (reintentos
desde la config, default 3; intentos intermedios a `DEBUG`), y devuelve el texto
o lanza `LLMCallFailure`. Ante `configuracion` fija el aborto antes de lanzar.
Registra el uso de tokens como hoy (`record_usage`).
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
En DSPy, `CheckedLM` se construye con `num_retries=0`; el reintento va en
`forward` (envuelve `super().forward`) y la clasificacion de la respuesta en
`_process_lm_response`. 1b verifica que `forward` sea el punto correcto en
dspy 3.2.1 y como se ve la excepcion envuelta de `ContextWindowExceededError`.

D4. Conteo una vez por caso (FR-007): la capa de llamada nunca llama a
`record`; solo lanza. Cuenta quien conoce el caso: los adapters de
`gepa_standalone`, el envoltorio de programa/metrica de `dspy_gepa_poc` y, para
reflexion, el envoltorio del `reflection_lm` (una vez por propuesta). Asi el
fallback `ChatAdapter` -> `JSONAdapter` de DSPy no multiplica el conteo.
Excepcion: `configuracion` fija el aborto en la capa de llamada (no cuenta, solo
corta), porque `Evaluate` y GEPA pueden tragarse la excepcion.

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
`failures: {infra_retries, min_attempts, thresholds: {<clase>: {<rol>: tasa}}}`.
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
