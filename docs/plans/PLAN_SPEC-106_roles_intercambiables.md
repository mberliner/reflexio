# Plan de implementacion — SPEC-106 roles intercambiables

Fuente del plan de ejecucion de [[SPEC-106-roles-intercambiables]]. La spec
define que debe cumplirse (FR/SC); este documento define en que orden se
implementa, con que modelo de agente, que decisiones de diseno ya estan tomadas
y en que estado esta cada subfase. Si cambia un requisito, se edita la spec y
aca solo se ajusta la referencia.

Creado: 2026-11-27. Base: `8aa6ff7` (SPEC-106 iteracion 2). Dependencias
cumplidas: SPEC-103, SPEC-104 y SPEC-105 `active`.

## Criterio de modelo

"Modelo" es el modelo del agente de codigo que ejecuta cada subfase.

- Opus 5.5 (`claude -p`): cambios que cruzan el punto de llamada y la
  clasificacion de fallas (SPEC-104/105), revision integral y cierre.
- Sonnet 5.5 (`claude-e -p`): implementacion guiada por la spec, por las
  decisiones D1 a D11 de este plan y por tests ya escritos.

Las decisiones de diseno se fijaron al escribir este plan, leyendo el codigo
(no hay subfases de diseno aparte): asi cada sesion Sonnet arranca con el
diseno resuelto y no gasta tokens en explorarlo. Si una decision choca con el
codigo, la sesion lo anota como bloqueo (ver Reglas) y no improvisa.

## Reglas de ejecucion

- La spec queda en `draft` hasta el Cierre. Ninguna subfase la pasa a
  `active` ni toca su fila en `specs/SPECS_REGISTRY.md` (misma convencion que
  SPEC-103 y SPEC-104).
- Tests primero. Cuando RED y GREEN van en la misma subfase, la sesion escribe
  primero los tests, verifica que fallan por la razon correcta y despues
  implementa. Cuando van en subfases distintas, los tests RED se marcan
  `@pytest.mark.xfail(strict=True, reason="SPEC-106 <subfase que los cierra>")`
  para que `ci_local.sh` quede verde; la subfase GREEN quita la marca.
- Los tests verifican la spec, no el codigo actual (`docs/ARCHITECTURE.md`,
  Invariantes). Respuestas de LLM con `litellm.ModelResponse` via el helper de
  `tests/conftest.py`; excepciones de proveedor desde
  `tests/litellm_failure_payloads.py`. Sin red: ningun test llama a una API.
- Cada subfase cierra con `./shared/utils/ci_local.sh` verde y un commit
  `feat(spec-106): <subfase> <resumen>` (o `test(...)`, `docs(...)`). Commits
  sin trailer `Co-Authored-By`. Sin mezclar `-n`/`-q` con `git commit` en el
  mismo comando.
- Al cerrar una subfase: marcarla `hecho (<hash>)` en la tabla y pasar a
  vigente la fila del Coverage mapping de la spec que corresponda, en un commit
  aparte `docs(spec-106): estado de <subfase>`.
- "Archivos" del Detalle es la lista cerrada que usa el control de salida: el
  diff MUST NOT tocar otros (este plan siempre se puede editar). Si hace falta
  otro archivo, la sesion lo anota como bloqueo en "Bloqueos" y no commitea.
- Arquitectura (`docs/ARCHITECTURE.md`): toda llamada al LLM pasa por
  `shared/llm/call.py`; `shared/` no importa `gepa_standalone` ni
  `dspy_gepa_poc`; en `shared/` solo `dspy_lm.py` importa `dspy`; solo API
  publica de `dspy`, `gepa` y `litellm`. Sin emoticones. Un doc, un proposito.

## Consumo de tokens (aplica a toda sesion `-p`)

- Leer solo: la spec, de este plan las secciones "Reglas de ejecucion",
  "Consumo de tokens", las decisiones que nombra la fila y el "Detalle" de la
  subfase. `AGENTS.md` ya llega por `CLAUDE.md`. No leer otros planes, ni
  `historial/sdd.md`, ni docs que la subfase no edita.
- Archivos de mas de 300 lineas: ubicar con Grep el simbolo y leer solo ese
  rango (`offset`/`limit`). Los rangos de "Puntos de entrada" del Detalle son
  orientativos al `8aa6ff7`.
- Durante el trabajo, pytest dirigido (`-q -x` sobre los tests de la subfase).
  `ci_local.sh` una vez al final, con la salida recortada (`| tail -n 40`); se
  repite solo si fallo.
- No explorar librerias instaladas: ninguna subfase de este plan lo necesita.
  Si una lo necesita, es un bloqueo.
- Resumen final de la sesion: maximo 15 lineas (subfase, commit, tests nuevos,
  desvios o bloqueos). El detalle va al plan, no a la salida.

## Fases

| Fase | Subfase | Requisitos | Decisiones | Modelo | Estado |
|---|---|---|---|---|---|
| 1 Conexion por rol (`shared/llm`) | 1a Tests: golden de regresion de parametros (verde hoy) y tests RED de resolucion por rol, no fuga y validacion local | FR-001, FR-002, FR-003, SC-003, SC-004 | D1, D2, D3, D4 | Sonnet 5.5 | hecho (404af1d) |
| | 1b Funcion de proveedor, resolucion por rol con proveedor ancla, `api_base` explicito en `anthropic/`, validacion local por rol, `LLM_ENV_FILE`, `endpoint_host` y `connection_summary` (GREEN) | FR-001, FR-002, FR-003, FR-005 (ultimo punto), FR-007 (metodo) | D1 a D4, D7 | Sonnet 5.5 | pendiente |
| 2 Validacion al arrancar | 2a Sonda por el punto de llamada comun, clasificacion de SPEC-104 y `LLMConnectionError` con rol y variable; quitar la excepcion de `test_single_call_point.py` | FR-005 | D5 | Opus 5.5 | pendiente |
| | 2b Entry points: validar solo los roles usados e imprimir rol, proveedor, modelo y host | FR-005, FR-007, SC-005 (tarea y profesor) | D6, D7 | Sonnet 5.5 | pendiente |
| 3 Juez como rol | 3a Bucket `judge` en `UsageTracker`, `Tokens Reflection` = reflexion + juez, juez tarifado con su modelo | FR-004 (uso), H1 | D9 | Sonnet 5.5 | pendiente |
| | 3b `LLM_MODEL_JUDGE`, configuracion del juez en `build_llm_configs`, validacion en el Step 2 e inyeccion al adapter RAG | FR-004, FR-005, SC-005 (juez) | D8 | Sonnet 5.5 | pendiente |
| 4 Registro y comparabilidad | 4a `run.json` con proveedor y host por rol; columna `Modelo Juez`; logger sobre CSV sin migrar; migracion | FR-006, SC-006 | D7, D10 | Sonnet 5.5 | pendiente |
| | 4b Terna de comparabilidad en `seed_protocol` y `seed_triage` (`target_models` con juez en RAG) | FR-006, SC-002 (sin red) | D11 | Sonnet 5.5 | pendiente |
| 5 Herramientas y docs | 5a `check_deployments.py` por rol y carga de `LLM_ENV_FILE` | FR-005 (ultimo punto), FR-008 | D2, D7 | Sonnet 5.5 | pendiente |
| | 5b Documentacion y `.env.example` | FR-009 | todas | Sonnet 5.5 | pendiente |
| 6 Revision | 6 Revision integral sin red contra la spec (diff `8aa6ff7..HEAD`); hallazgos al plan | todos, SC-003 a SC-006 | todas | Opus 5.5 | pendiente |
| 7 Verificacion real (sesion interactiva, gasta API) | Corridas cortas Azure + Claude en ambos subproyectos | SC-001, SC-002 | - | Sonnet 5.5 | pendiente |
| Cierre (sesion interactiva) | `[SDD-Check]`, estado de D-028 y D-029, spec y registro a `active`, plan cerrado | todos | - | Opus 5.5 | pendiente |

## Dependencias

- 1a -> 1b. Todo lo demas requiere 1b.
- 2a requiere 1b. 2b requiere 2a.
- 3a requiere 1b. 3b requiere 2b y 3a.
- 4a requiere 3b. 4b requiere 4a.
- 5a requiere 2a. 5b requiere 4b y 5a.
- 6 requiere 5b. 7 requiere 6 (y sus correcciones). Cierre requiere 7.

Orden lineal recomendado: 1a, 1b, 2a, 2b, 3a, 3b, 4a, 4b, 5a, 5b, 6, 7, Cierre.

## Huecos de la spec

- H1 (antes de 3a). La spec separa el bucket `judge` (FR-004) pero no dice con
  que precio se tarifa. Hoy `roi_calculator.cost_from_usage(usage, task_model,
  reflection_model)` tarifa `reflection` (que incluye al juez) con el modelo
  del profesor. Con un juez de otro proveedor, `Costo Real USD` quedaria mal.
  Propuesta: agregar a FR-004 "El costo del bucket `judge` MUST tarifarse con
  el modelo del juez; `Costo Real USD` conserva su semantica (total de la
  corrida)". No adelanta SPEC-107: es mantener correcto el total vigente.
  Estado: resuelta (2026-11-27, aprobada por el usuario): FR-004 de la spec
  agrega que cada bucket se tarifa con el modelo de su rol.

## Decisiones de diseno

D1. Proveedor de un modelo. Funcion publica `provider_of(model: str) -> str` en
`shared/llm/config.py`: el prefijo antes de la primera `/`, en minusculas; sin
`/` devuelve `"openai"` (convencion de LiteLLM). Unica fuente del proveedor:
la usan `CheckedEngine._provider` (`shared/llm/dspy_lm.py`), `validate()`,
`validate_connection()`, `LLMConfigError` y `LLMConnectionError` (hoy
`"unknown"` en `config.py`/`errors.py` y `"openai"` en `dspy_lm.py`). Cada
prefijo distinto es un proveedor distinto (`azure`, `openai`, `anthropic` y
cualquier otro). `_is_anthropic` se conserva (decide la rama de
`apply_constraints` por prefijo).

D2. Resolucion de la conexion en `LLMConfig.from_env(model_name)`:
- `_env(name)`: `os.getenv` con `strip()`; vacio cuenta como no definido
  (FR-001, mismo criterio que SPEC-103 FR-008).
- `ROL = model_name.upper()`. Modelo: `LLM_MODEL_<ROL>` con el default vigente
  (`azure/gpt-4.1-mini`).
- Proveedor ancla: `provider_of` del modelo de `task`, leido con la misma regla
  y default (para `task` es el propio).
- `hereda = provider_of(model) == ancla`.
- `api_key = LLM_API_KEY_<ROL>`, si no, `LLM_API_KEY` solo si `hereda`.
- `api_base = LLM_API_BASE_<ROL>`, si no, `LLM_API_BASE` solo si `hereda` y el
  proveedor no es `anthropic`.
- `api_version = LLM_API_VERSION_<ROL>`, si no, `LLM_API_VERSION` o el default
  `2024-02-15-preview` solo si `hereda` y el proveedor no es `anthropic`; en
  otro caso `None`. El campo pasa a `str | None`; el default del dataclass no
  cambia (construcciones directas y tests vigentes).
- Campo nuevo `env_sources: dict[str, str]` (`compare=False`, `repr=False`):
  para `api_key`, `api_base` y `api_version`, el nombre de la variable de la que
  salio el valor (`LLM_API_KEY_REFLECTION`, `LLM_API_KEY` o `default`). Nunca el
  valor. Los overrides de `from_env(**overrides)` se aplican despues, como hoy.
- `LLM_ENV_FILE` se carga si no hay ninguna credencial definida: ni
  `LLM_API_KEY` ni ninguna variable `LLM_API_KEY_*` no vacia (FR-005).
- Con un `.env` sin variables por rol y todos los roles del mismo proveedor,
  `hereda` es siempre verdadero y los kwargs son los de hoy (FR-002). El golden
  de 1a lo verifica.

D3. `anthropic/` (enmienda a SPEC-103 FR-007). `apply_constraints` quita
siempre `api_version` y conserva `api_base` si la config lo tiene: por D2,
`from_env` solo lo pone desde `LLM_API_BASE_<ROL>`, asi que es explicito. El
aviso de `_warn_once` "LLM_API_BASE is ignored" se reemplaza por uno solo
cuando `LLM_API_BASE` global esta definido, el rol es `anthropic/` y no define
`LLM_API_BASE_<ROL>` ("el global no se hereda"). Con `LLM_API_BASE_<ROL>` no hay
aviso. `tests/test_anthropic_matrix.py`: el caso de `api_base` pasa a probar
por `from_env` (global no enviado, por rol enviado).

D4. Validacion local (`validate()`), antes de cualquier llamada:
- Falta credencial: `LLMConnectionError` que nombra rol, proveedor y la
  variable esperada: `LLM_API_KEY_<ROL>` si el rol no hereda; `LLM_API_KEY_<ROL>
  o LLM_API_KEY` si hereda. Igual para `api_base` en `azure/`.
- `LLMConnectionError` gana campos opcionales `role`, `failure_class` y
  `variable`, que `format_error()` muestra (`Role:`, `Class:`, `Variable:`).
  Las sugerencias nombran la variable concreta segun `env_sources`
  (`LLM_API_KEY_REFLECTION` si la credencial salio de ella).
- Ningun mensaje incluye el valor de una credencial.

D5. Sonda de conexion (FR-005), en `shared/llm/call.py`:
- `_raw_completion(kwargs, messages)`: unico sitio de `litellm.completion` en
  produccion, con `num_retries=0`. Lo usan `checked_response` y la sonda.
- `probe_completion(kwargs, role) -> None`: un intento, sin reintento propio
  (igual que la sonda de hoy), sin `record_usage` (la sonda no es uso de la
  corrida; hoy tampoco se registra) y sin tocar el `FailureTracker` (no fija
  aborto: todavia no hay corrida). Una excepcion se clasifica con
  `classify_exception` (capa 1, sin leer el texto) y sale como
  `LLMCallFailure` con su `failure.clase`. Una respuesta `None` es
  `configuracion`. Una respuesta sin texto (`sin_texto`, `presupuesto`,
  `filtro_salida`) cuenta como conexion valida con `[WARN]`: el endpoint y la
  credencial respondieron.
- `LLMConfig.validate_connection()` llama a `probe_completion` y traduce
  `LLMCallFailure` a `LLMConnectionError` con `role`, `failure_class` y
  `variable`. Mensaje por clase: `configuracion` -> credencial, endpoint o
  modelo invalido; `infraestructura` -> 429, timeout o red, reintentar mas
  tarde (no "credencial invalida"); otras -> la clase. Se eliminan las ramas
  por subcadena (`"401"`, `"404"`, `"429"`, `"VNet"`). Se conservan los
  `extra_details` diagnosticos.
- `tests/test_single_call_point.py`: se quita la excepcion
  `("shared/llm/config.py", "validate_connection")`; la de
  `shared/utils/check_deployments.py` se conserva (herramienta de diagnostico,
  fuera de FR-005).

D6. Roles por entry point (FR-005):
- `gepa_standalone/universal_optimizer.py`: `validate_llm_connections` recorre
  `task`, `reflection` y, en RAG, `judge` (`self.judge_config`, D8). Primero
  `validate()` de todos (sin red) y despues `validate_connection()` de cada uno,
  asi un error local de cualquier rol sale sin llamadas.
- `dspy_gepa_poc/reflexio_declarativa.py`: `setup_models(roles=("task",
  "reflection"))`. Con `roles=("task",)` no construye ni valida la reflexion
  (`self.reflection_config = None`, `self.reflection_lm = None`).
  `scripts/baseline_only.py` lo llama asi. `abort_message` y
  `collect_model_info` toleran `reflection_config is None`.
- Una falla de validacion sale como `LLMConnectionError` antes de la primera
  llamada de optimizacion y no escribe `run.json` (hoy `run.json` se escribe
  despues; 2b lo fija con tests).

D7. Endpoint efectivo (FR-006, FR-007):
- Propiedad `LLMConfig.endpoint_host -> str | None`: `hostname` de `api_base`
  si se envia (tras `apply_constraints`); si no, default del proveedor
  (`openai` -> `api.openai.com`, `anthropic` -> `api.anthropic.com`); si no se
  conoce, `None`.
- `LLMConfig.connection_summary() -> str`: una linea `rol | proveedor | modelo
  | host`. Nunca la credencial ni el `api_base` completo.
- `effective_params()` agrega las claves `provider` y `endpoint_host` (4a): asi
  `collect_model_info` las deja en `run.json` sin otro cambio.

D8. Juez (FR-004), solo en el adapter RAG de `gepa_standalone`:
- `resolve_judge_config(reflection_config: LLMConfig) -> LLMConfig` en
  `shared/llm/config.py`. Sin `LLM_MODEL_JUDGE`:
  `dataclasses.replace(reflection_config, role="judge")` (configuracion resuelta
  del profesor, incluidos los overrides del YAML) y `[WARN]` si esta definida
  alguna de `LLM_API_KEY_JUDGE`, `LLM_API_BASE_JUDGE`, `LLM_API_VERSION_JUDGE`,
  `LLM_EFFORT_JUDGE`, `LLM_THINKING_JUDGE`. Con `LLM_MODEL_JUDGE`:
  `LLMConfig.from_env("judge")` (D2, effort y thinking de SPEC-103).
- `build_llm_configs`: si `adapter.type == "rag"`, arma `self.judge_config` con
  los mismos overrides del YAML que el profesor (`temperature` si el YAML lo
  fija, `max_tokens` si el YAML lo fija, `cache`), sin el
  `_REFLECTION_DEFAULT_MAX_TOKENS` (el juez fija `judge_max_tokens` por
  llamada). Fuera de RAG, `self.judge_config = None` y `LLM_MODEL_JUDGE` se
  ignora (log DEBUG).
- `SimpleRAGAdapter.__init__` recibe `judge_config: LLMConfig` (obligatorio) y
  deja de importar `get_reflection_config`. `abort_message` y `_run_models` usan
  `self.judge_config`.
- FR-002: el unico YAML RAG (`gepa_standalone/experiments/configs/
  rag_optimization.yaml`) no tiene `models:`, asi que el juez sin
  `LLM_MODEL_JUDGE` envia lo mismo que hoy. El golden de 1a lo cubre.

D9. Uso y costo (FR-004, H1):
- `UsageTracker` con buckets `task`, `reflection` y `judge`; `judge` deja de
  plegarse en `reflection`. `snapshot()` agrega la clave `judge` (misma forma) y
  `total_tokens` suma los tres. Un rol desconocido sigue cayendo en `task`.
- `reflection_tokens_for_csv(usage) -> int` en `shared/llm/usage.py`:
  reflexion + juez. La usan los dos orquestadores para `Tokens Reflection`.
- `cost_from_usage(usage, task_model, reflection_model, pricing=None,
  judge_model=None)`: `judge` se tarifa con `judge_model` o, si es None, con
  `reflection_model`. Sin dimension de fase: la agrega SPEC-107 sobre esta
  forma plana por rol.
- Sin juez, `snapshot()["judge"]` queda en ceros. FR-004 ("los casos sin juez
  MUST NOT registrar un rol `judge`") se cumple en `models` de `run.json` y en
  `Modelo Juez` del CSV; el bucket en ceros no es un rol registrado.

D10. CSV maestro (FR-006):
- `STANDARD_COLUMN_MAPPING` agrega `"judge_model": "Modelo Juez"` despues de
  `reflection_model`. `log_experiment_result` recibe `judge_model` (default
  `""`); `gepa_standalone` pasa el modelo del juez en RAG.
- `_sync_active_keys_to_file`: si el archivo no tiene columnas del mapeo, lo
  reescribe (archivo temporal y reemplazo) agregando esas columnas en el orden
  del mapeo, vacias en las filas existentes, y emite `[WARN]` que pide correr
  `migrate_metrics_csv.py` para completar `Modelo Juez` en filas RAG previas.
  Las columnas del archivo que el mapeo no conoce se conservan (como hoy).
- `migrate_metrics_csv.py`: completa `Modelo Juez` vacio con `Modelo Profesor`
  en filas RAG. Una fila es RAG si su `run.json` tiene `models.judge` o, sin
  eso, si `config_snapshot.yaml` del run tiene `adapter.type: rag`. Sin forma
  de saberlo, la deja vacia y la cuenta en el reporte.

D11. Comparabilidad (FR-006, enmienda a SPEC-100 FR-008 y SPEC-101 FR-002):
- `seed_protocol._models(row)` devuelve la terna (`Modelo Tarea`,
  `Modelo Profesor`, `Modelo Juez`) con la cadena cruda (sin normalizar).
- `seed_triage.target_models(framework, adapter_type)` devuelve la terna:
  juez = `LLM_MODEL_JUDGE` o, si falta, el profesor, solo si `adapter_type ==
  "rag"`; si no, `""`. `_matches` compara tres componentes (vacio en el
  objetivo = comodin, como hoy).
- Una fila RAG sin `Modelo Juez` (CSV sin migrar) no es comparable con una
  corrida nueva; el mensaje de "sin referencia comparable" sugiere migrar.
- D-028 (effort y thinking) queda fuera: SC-002 con profesor Claude se
  verifica en la fase 7 con effort y thinking constantes.

## Riesgos del plan

- FR-002 es el riesgo mayor: un cambio en `from_env` altera en silencio los
  kwargs de corridas que hoy funcionan. Mitigacion: el golden de 1a se escribe
  y queda verde ANTES de tocar `from_env`, con dicts literales.
- 2a cambia el sitio unico de `litellm.completion`. Mitigacion: `_raw_completion`
  conserva el `num_retries=0` y `test_single_call_point.py` lo verifica.
- 4a reescribe el CSV maestro en disco. Mitigacion: los tests trabajan sobre
  copias en `tmp_path`; la reescritura es atomica (temporal y reemplazo).
- La fase 7 gasta API real y exige credenciales de dos proveedores.

## Detalle por subfase

Toda sesion de subfase lee antes la spec y, de este plan, lo indicado en
"Consumo de tokens". "Archivos" es la lista cerrada del control de salida.

### 1a Tests (golden verde y RED) — Sonnet 5.5

- `tests/test_role_connection_golden.py` (nuevo, VERDE con el codigo de hoy):
  con `monkeypatch` del entorno y `from_env(..., load_env=False)`, dicts
  literales de `to_kwargs()`, de los kwargs de la sonda (`_base_kwargs` con
  `max_tokens=5` y `apply_constraints`) y de `get_dspy_lm().engine` (los
  `params` que lleva) para `task`, `reflection` y el juez de hoy
  (`from_env("reflection")` con rol `judge`) en tres `.env`: (a) todo `azure/`
  con globales; (b) todo `openai/` con `LLM_API_BASE` de proxy; (c) todo
  `anthropic/` con `LLM_API_KEY` y un `LLM_API_BASE` global (hoy quitado). Los
  valores esperados se escriben literales en el test, no se calculan.
- `tests/test_role_connection.py` (nuevo, RED con `xfail(strict=True,
  reason="SPEC-106 1b")`): `provider_of` (D1); variables por rol y vacio = no
  definido (FR-001); no fuga: rol `anthropic/` con `LLM_API_KEY` global de
  Azure falla en `validate()` nombrando `reflection`, `anthropic` y
  `LLM_API_KEY_REFLECTION`, con `litellm.completion` parcheado para fallar si
  se llama, y la clave global no esta en sus kwargs (SC-003); `api_version` y
  su default no se heredan a otro proveedor; `anthropic/` con
  `LLM_API_BASE_REFLECTION` lo envia sin aviso y sin `api_version`; aviso
  cuando hay `LLM_API_BASE` global y el rol `anthropic/` no lo hereda (D3);
  `env_sources`; `LLM_ENV_FILE` se carga sin credenciales y no se carga con
  solo `LLM_API_KEY_TASK` definida; `endpoint_host` y `connection_summary` sin
  credencial (D7).
- Archivos: los dos tests nuevos.
- Puntos de entrada: `shared/llm/config.py` (`from_env` ~L451,
  `apply_constraints` ~L299, `validate` ~L611), `tests/conftest.py`.

### 1b Conexion por rol (GREEN) — Sonnet 5.5

- Implementa D1 a D4 y D7 (sin las claves nuevas de `effective_params`, que van
  en 4a). Quita el `xfail` de `tests/test_role_connection.py`. El golden sigue
  verde sin editarlo (si hay que editarlo, es un bloqueo: FR-002).
- Archivos: `shared/llm/config.py`, `shared/llm/dspy_lm.py`,
  `shared/llm/errors.py`, `shared/llm/__init__.py` (exportar `provider_of`),
  `tests/test_role_connection.py`, `tests/test_anthropic_matrix.py` (caso
  `api_base`, D3), `tests/test_shared_llm.py` (solo si un test fija el
  `"unknown"` o el aviso viejo).
- Parada obligatoria al terminar: el usuario revisa el nucleo.

### 2a Sonda por el punto comun — Opus 5.5

- Tests primero en la misma sesion: `tests/test_role_probe.py` (nuevo) con
  payloads de `tests/litellm_failure_payloads.py`: 401 y 404 -> `configuracion`;
  429 y timeout -> `infraestructura` y el mensaje no dice credencial invalida;
  el error nombra rol, proveedor, modelo y `LLM_API_KEY_REFLECTION` cuando la
  credencial salio de ella; la sonda no registra uso ni fija aborto; una
  llamada HTTP con `num_retries=0`; respuesta sin texto = conexion valida con
  aviso.
- Implementa D5. `test_single_call_point.py` sin la excepcion de
  `validate_connection`.
- Archivos: `shared/llm/call.py`, `shared/llm/config.py`,
  `shared/llm/errors.py`, `tests/test_role_probe.py`,
  `tests/test_single_call_point.py`, `tests/test_shared_llm.py` (tests de
  `validate_connection` por subcadena que contradigan D5).
- Parada obligatoria al terminar: el usuario revisa la sonda.

### 2b Entry points — Sonnet 5.5

- Implementa D6 y la impresion de FR-007 con `connection_summary()` en el log
  de arranque de ambos subproyectos.
- Tests (`tests/test_role_startup.py`, nuevo): SC-005 para tarea y profesor en
  ambos subproyectos (credencial invalida -> `LLMConnectionError` antes de la
  primera llamada de optimizacion, sin `run.json` en `tmp_path`); validacion
  local de todos los roles antes de la primera sonda; `baseline_only.py` con el
  profesor mal configurado no falla (escenario 10).
- Archivos: `gepa_standalone/universal_optimizer.py`,
  `gepa_standalone/core/llm_factory.py` (`validate_llm_connection`),
  `dspy_gepa_poc/reflexio_declarativa.py`,
  `dspy_gepa_poc/scripts/baseline_only.py`, `tests/test_role_startup.py` y los
  tests existentes de esos modulos que fijen el orden viejo de validacion.
- Puntos de entrada: `validate_llm_connections` (~L324),
  `setup_models` (~L183).

### 3a Bucket del juez y costo — Sonnet 5.5

- Implementa D9 (FR-004, costo por bucket con el modelo de su rol).
- Tests: bucket `judge` separado; `Tokens Reflection` = reflexion + juez;
  `cost_from_usage` con juez de otro modelo; sin juez, total igual al de hoy.
- Archivos: `shared/llm/usage.py`, `shared/analysis/roi_calculator.py`,
  `gepa_standalone/universal_optimizer.py` (`save_results`,
  `save_aborted_run`), `dspy_gepa_poc/reflexio_declarativa.py` (tokens del
  CSV), tests de uso y de `roi_calculator`.

### 3b Juez como rol — Sonnet 5.5

- Implementa D8; el juez entra en la validacion de D6.
- Tests (`tests/test_judge_role.py`, nuevo): escenarios 7 a 9 de la spec; SC-005
  para el juez; `[WARN]` con `LLM_*_JUDGE` sin `LLM_MODEL_JUDGE`; overrides del
  YAML aplicados al juez; el adapter no lee el entorno para el juez.
- Archivos: `shared/llm/config.py` (`resolve_judge_config`),
  `gepa_standalone/universal_optimizer.py`,
  `gepa_standalone/adapters/simple_rag_adapter.py`,
  `gepa_standalone/core/llm_factory.py` (solo si `get_reflection_config` queda
  sin uso), `tests/test_judge_role.py` y los tests que construyen
  `SimpleRAGAdapter`.

### 4a Registro — Sonnet 5.5

- Implementa D7 (claves `provider` y `endpoint_host` en `effective_params`) y
  D10.
- Tests: `run.json` con proveedor y host por rol y sin credencial; `Modelo
  Juez` en RAG y vacia en el resto; SC-006 sobre una copia sintetica del CSV
  (con y sin migracion previa); migracion de filas RAG por `run.json` y por
  `config_snapshot.yaml`.
- Archivos: `shared/llm/config.py`, `shared/logging/csv_writer.py`, el modulo
  que define `log_experiment_result` (ubicarlo con Grep),
  `shared/utils/migrate_metrics_csv.py`,
  `gepa_standalone/universal_optimizer.py`, tests de esos modulos.

### 4b Comparabilidad — Sonnet 5.5

- Implementa D11.
- Tests: `azure/gpt-4o` y `openai/gpt-4o` no comparables; cambiar solo el juez
  separa las filas; terna en `target_models` para RAG y no RAG; fila RAG sin
  migrar no comparable y el mensaje sugiere migrar.
- Archivos: `shared/utils/seed_protocol.py`, `shared/utils/seed_triage.py`,
  sus tests.

### 5a `check_deployments` — Sonnet 5.5

- FR-008: cada rol (`task`, `reflection`, `judge` si `LLM_MODEL_JUDGE`) contra
  su propio endpoint y credencial (D2); un rol no Azure se informa "no aplica".
  Carga de `LLM_ENV_FILE` con la regla de D2.
- Archivos: `shared/utils/check_deployments.py`, su test.

### 5b Documentacion — Sonnet 5.5

- FR-009: `docs/LLM_CONFIG.md` (variables por rol, proveedor ancla, ejemplo
  Azure + Claude, juez), `docs/METADATA_REPRODUCIBILIDAD.md` (proveedor y host
  por rol, bucket `judge`), `docs/PROTOCOLO_N_SEEDS.md` (terna),
  `gepa_standalone/.env.example`, `dspy_gepa_poc/.env.example`. Enlazar, no
  duplicar (SSOT).
- Archivos: esos cinco y las filas del Coverage mapping de la spec.

### 6 Revision integral — Opus 5.5

- Diff `8aa6ff7..HEAD` contra el texto de cada FR y SC (no contra los
  resumenes de las sesiones). Verifica SC-003 a SC-006 sin red y las reglas de
  arquitectura.
- Salida: seccion "Hallazgos de la revision" en este plan, cada uno con
  severidad, archivo y FR. No corrige: cada hallazgo aprobado por el usuario se
  resuelve en una subfase `6-fix-N` (Sonnet 5.5, test RED previo).
- Archivos: solo este plan.

### 7 Verificacion real — sesion interactiva

- `gepa_standalone` con `rag_optimization.yaml` (ejercita el juez) y un caso
  corto de `dspy_gepa_poc`, presupuesto minimo, estudiante
  `azure/gpt-4.1-mini` y profesor `anthropic/claude-sonnet-5-5` con
  `LLM_API_KEY_REFLECTION`. Effort y thinking constantes en todo el lote
  (precondicion de SC-002 mientras D-028 siga abierta).
- Registrar en este plan: log de arranque por rol, `models` y `usage` de
  `run.json`, filas del CSV y el resultado de `seed_triage` sobre ellas.

### Cierre — sesion interactiva, Opus 5.5

- `[SDD-Check]` en `historial/sdd.md`; estado de D-028 y D-029 (a); Coverage
  mapping vigente; spec y `specs/SPECS_REGISTRY.md` a `active`; plan marcado
  cerrado.

## Lanzamiento por CLI (modo no interactivo)

Cada subfase de las fases 1 a 6 corre como una sesion `-p` aparte, desde Git
Bash en la raiz del repo, con el modelo de la tabla. La fase 7 y el Cierre van
en sesion interactiva.

- Subfases Opus 5.5: `claude -p ... --model claude-opus-5-5`.
- Subfases Sonnet 5.5: `claude-e -p ... --model claude-sonnet-5-5` (perfil de
  empresa; ver la referencia de los wrappers en la memoria del proyecto).

```bash
SUB=1a                                   # subfase a ejecutar
CLI=claude-e; MODEL=claude-sonnet-5-5    # Opus: CLI=claude; MODEL=claude-opus-5-5
export PYTHONUTF8=1                      # salida redirigida en Windows (cp1252)
mkdir -p "$HOME/spec106_logs"            # logs fuera del repo
"$CLI" -p "Implementar SPEC-106 subfase $SUB segun docs/plans/PLAN_SPEC-106_roles_intercambiables.md. \
Leer solo lo indicado en 'Consumo de tokens' del plan. \
Los tests MUST verificar el comportamiento de la spec, con respuestas reales via el helper de tests/conftest.py. \
Al cerrar: ci_local.sh verde, commit de la subfase y, en commit aparte de docs, estado en la tabla del plan y Coverage mapping de la spec. \
No pasar la spec a active. \
Sesion no interactiva: si algo exige decision del usuario o un archivo fuera de la lista, no improvisar; \
anotarlo en 'Bloqueos' del plan, no commitear y terminar." \
  --model "$MODEL" \
  --permission-mode acceptEdits \
  --allowedTools "Bash(./shared/utils/ci_local.sh:*) Bash(.venv/Scripts/python.exe -m pytest:*) Bash(git status) Bash(git diff:*) Bash(git log:*) Bash(git add:*) Bash(git commit:*)" \
  | tee "$HOME/spec106_logs/$SUB.log"
```

Reglas:

- Una subfase por invocacion, en el orden de Dependencias.
- En este equipo el interprete es `.venv/Scripts/python.exe` (Windows); en
  Unix, `.venv/bin/python`, y se ajusta `--allowedTools`.
- Un relanzamiento tras bloqueo continua sobre el arbol sin commitear; la
  resolucion se registra antes en este plan (commit solo del plan).

## Seguimiento

Una sesion interactiva de Opus 5.5 supervisa las fases 1 a 6. No implementa ni
guarda estado propio: el estado es la columna Estado de este plan.

Arranque: "Supervisar SPEC-106 segun la seccion Seguimiento de
docs/plans/PLAN_SPEC-106_roles_intercambiables.md".

Ciclo por subfase:

1. Tomar la primera subfase `pendiente` cuyas dependencias esten `hecho`.
2. Lanzarla con el comando de "Lanzamiento por CLI" en segundo plano y esperar
   el aviso de fin (sin polling).
3. Aplicar el control de salida. Si pasa, volver a 1. Si falla, detenerse e
   informar al usuario: no relanzar ni corregir por cuenta propia.

Control de salida (todos deben cumplirse):

- Commit nuevo (`git log -1`) y arbol limpio (`git status`).
- `./shared/utils/ci_local.sh` verde.
- La subfase figura `hecho` con el hash y no hay bloqueo nuevo en "Bloqueos".
- `git diff --stat` del commit toca solo los "Archivos" de la subfase.
- El diff cumple los FR de la fila, contrastado con el texto de la spec. Diff
  completo en 1b, 2a y 3b, y cuando otro punto falla.
- La spec sigue en `draft`.

Paradas obligatorias (la sesion se detiene y espera al usuario):

- Despues de 1b (nucleo) y despues de 2a (sonda).
- Despues de 6: el usuario aprueba los hallazgos que se corrigen.
- Antes de la fase 7: gasta API real.

Contexto del supervisor: de cada log leer solo el final (`tail -n 40`); abrir el
log completo o el diff solo cuando un control falla.

## Bloqueos

(ninguno)

## Proxima sesion

Plan aprobado por el usuario el 2026-11-27, con H1 resuelta. 1a hecha
(404af1d). Siguiente subfase: 1b (Sonnet 5.5). Arrancar con: "Supervisar SPEC-106 segun la seccion
Seguimiento de docs/plans/PLAN_SPEC-106_roles_intercambiables.md".
