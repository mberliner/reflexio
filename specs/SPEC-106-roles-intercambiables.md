# SPEC-106-roles-intercambiables — Profesor, estudiante y juez intercambiables entre proveedores

Estado: draft
Iteracion: 2 (rev. 2026-11-26)
Depende de: [[SPEC-104-fallas-tecnicas-justas]] (clasificacion de fallas), [[SPEC-105-punto-llamada-desacoplado]] (punto de llamada comun y sonda de conexion)
Enmienda: [[SPEC-103-proveedor-anthropic]] FR-007 (FR-003 de esta spec), [[SPEC-100-veredicto-senal-ruido]] FR-007 y FR-008, [[SPEC-101-triaje-casos-nseeds]] FR-002 (FR-006 de esta spec)
Relacionada con: [[SPEC-107-costo-real-por-resolucion]] (evaluacion economica de cada combinacion, separada en la iteracion 2), docs/LLM_CONFIG.md, docs/METADATA_REPRODUCIBILIDAD.md
Plan de implementacion: docs/plans/PLAN_SPEC-106_roles_intercambiables.md

## User Story (prioridad)

Como persona que experimenta con DSPy y GEPA, quiero asignar a cada rol
(estudiante, profesor y, donde exista, juez) un modelo de cualquier proveedor
soportado, de forma independiente y en los dos subproyectos, para medir cuanto
aporta cambiar un solo rol (por ejemplo, profesor Claude con el mismo estudiante
Azure) sin que la configuracion de un rol contamine a otro.
Prioridad: P1

El juez existe solo en el adapter RAG de `gepa_standalone`; `dspy_gepa_poc` no
tiene rol juez. Cuanto cuesta cada combinacion es [[SPEC-107-costo-real-por-resolucion]].

## Contexto (estado al 2026-11-26)

- Cada rol elige su modelo (`LLM_MODEL_TASK`, `LLM_MODEL_REFLECTION`) y, desde
  SPEC-103, su effort y razonamiento (`LLM_EFFORT_<ROL>`, `LLM_THINKING_<ROL>`).
  La conexion es unica: `LLMConfig.from_env` lee `LLM_API_KEY`, `LLM_API_BASE` y
  `LLM_API_VERSION` (default `2024-02-15-preview`) globales para todos los roles
  (`shared/llm/config.py`). Hoy todos los roles deben ser del mismo proveedor.
- Consecuencia hoy: un rol `anthropic/` con un `LLM_API_KEY` global de Azure
  recibe esa clave y la envia a Anthropic en la sonda de conexion.
- `apply_constraints` quita `api_base` y `api_version` a todo modelo `anthropic/`
  (SPEC-103 FR-007) y `_warn_once` avisa siempre que haya un `api_base`.
- El juez del RAG toma la configuracion del profesor
  (`SimpleRAGAdapter._judge_config = get_reflection_config()`), se construye en el
  Step 4, despues de la validacion de conexiones (Step 2), y no se valida aparte.
  Su uso se suma al bucket `reflection` (`shared/llm/usage.py::_REFLECTION_ROLES`).
  `run.json` ya registra `models.judge` en RAG (docs/METADATA_REPRODUCIBILIDAD.md).
- La sonda de conexion (`LLMConfig.validate_connection`) llama a
  `litellm.completion` directo (excepcion en `tests/test_single_call_point.py`),
  sin `num_retries=0`, y clasifica errores buscando subcadenas del mensaje
  (`"401"`, `"404"`, `"429"`); `LLMConnectionError` no lleva el rol y los
  mensajes nombran `LLM_API_KEY` / `LLM_API_BASE` aunque el rol use otra variable.
- `dspy_gepa_poc/scripts/baseline_only.py` valida tambien el rol de reflexion
  aunque no lo usa.
- La comparabilidad de SPEC-100 FR-008 y SPEC-101 FR-002 compara el par
  (`Modelo Tarea`, `Modelo Profesor`) por la cadena cruda del CSV: `azure/gpt-4o`
  y `openai/gpt-4o` ya son modelos distintos. `normalize_model` solo interviene
  en precios y en ROI, no en comparabilidad.
- La deteccion de proveedor sin prefijo difiere: `shared/llm/config.py` devuelve
  `unknown` y `shared/llm/dspy_lm.py` devuelve `openai`.
- `shared/utils/check_deployments.py` asume que tarea y reflexion comparten el
  endpoint Azure.

## Alcance

Incluye: resolucion de modelo, credencial, endpoint y version por rol; regla de
no fuga entre proveedores; juez como rol configurable con su bucket de uso;
validacion de cada rol al arrancar, por el punto de llamada comun; registro del
proveedor y modelo por rol y su comparabilidad; documentacion. Ambos
subproyectos (el juez solo donde existe).

Excluye: evaluacion economica por combinacion (costos medidos por fase, costo por
resolucion, ROI y leaderboard con magnitudes medidas):
[[SPEC-107-costo-real-por-resolucion]]. Restricciones de parametros de un
proveedor concreto ([[SPEC-103-proveedor-anthropic]]). Balanceo, fallback o
reintentos entre proveedores. Seleccion automatica de la mejor combinacion.
Variables nativas de LiteLLM (`ANTHROPIC_API_KEY`, `AZURE_API_KEY`, ...) como
fuente de credenciales.

Deuda a revisar (`historial/sdd.md`):
- D-028 (comparabilidad sin effort/thinking): fuera de alcance, pero MUST
  cerrarse antes de verificar SC-002 con un profesor Claude (ver SC-002).
- D-029 (a) (`run_inference.py` arma la configuracion desde el `.env` vigente):
  fuera de alcance. FR-006 deja en `run.json` lo necesario (proveedor, modelo y
  host del endpoint por rol) para que la reconstruccion o el `[WARN]` sean
  posibles.

## Requisitos funcionales

- FR-001 Cada rol que use `LLMConfig.from_env` (task, reflection, judge y los
  adicionales) MUST resolver su conexion desde `LLM_API_KEY_<ROL>`,
  `LLM_API_BASE_<ROL>` y `LLM_API_VERSION_<ROL>`. Cuando la variable del rol no
  esta definida, MAY usarse la global correspondiente solo si FR-003 lo permite.
  Una variable presente pero vacia (`VAR=`) MUST tratarse como no definida (mismo
  criterio que SPEC-103 FR-008).
  El modelo de un rol (`LLM_MODEL_<ROL>`) MUST NOT tener default: si no esta
  definido (ausente o vacio), la validacion local del rol MUST fallar antes de
  cualquier llamada, nombrando el rol y la variable `LLM_MODEL_<ROL>`. No aplica al
  juez sin `LLM_MODEL_JUDGE`, que usa la configuracion del profesor (FR-004).
- FR-002 Un `.env` sin variables por rol y con todos los roles del mismo
  proveedor (unica configuracion posible hoy) MUST producir exactamente los
  mismos parametros de llamada que antes del cambio, incluido `openai/` con un
  `LLM_API_BASE` global hacia un endpoint compatible.
- FR-003 Regla de no fuga. Las variables globales (`LLM_API_KEY`,
  `LLM_API_BASE`, `LLM_API_VERSION` y su default) forman la conexion por defecto,
  que pertenece al proveedor del rol `task` (proveedor ancla).
  - Un rol cuyo proveedor coincide con el ancla MAY heredar cada variable global
    que no define.
  - Un rol de otro proveedor MUST NOT heredar ninguna de las tres ni el default de
    `LLM_API_VERSION`. Si le falta la credencial, la validacion local MUST fallar
    antes de cualquier llamada, nombrando el rol, el proveedor y la variable
    esperada (`LLM_API_KEY_<ROL>`).
  - `azure`, `openai` y `anthropic` MUST contarse como proveedores distintos.
  - El proveedor de un rol MUST salir de una sola funcion compartida por
    `shared/llm/config.py` y `shared/llm/dspy_lm.py`. Un modelo sin prefijo MUST
    contarse como `openai` (convencion de LiteLLM).
  - Enmienda a SPEC-103 FR-007: en `anthropic/`, un `LLM_API_BASE_<ROL>`
    explicito MUST enviarse (proxy o gateway) y no debe generar aviso. El global
    sigue sin enviarse, y ahora tampoco se hereda. `api_version` sigue sin
    enviarse a `anthropic/`.
- FR-004 El juez MUST ser un rol configurable (`LLM_MODEL_JUDGE` y sus
  variables por rol), solo en el adapter RAG de `gepa_standalone`:
  - Sin `LLM_MODEL_JUDGE`, el juez MUST usar la configuracion resuelta del
    profesor completa (modelo, conexion, effort, razonamiento), como hoy. Las
    variables `LLM_*_JUDGE` MUST ignorarse en ese caso, con un `[WARN]` si alguna
    esta definida. Como su conexion es la del profesor, la sonda del profesor la
    cubre: el juez heredado MUST NOT sondearse aparte, y sus mensajes de
    validacion MUST nombrar las variables del profesor, no las `LLM_*_JUDGE`
    (aclaracion del 2026-11-27, hallazgo R2 de la revision).
  - Con `LLM_MODEL_JUDGE`, el juez MUST resolverse como un rol mas (FR-001,
    FR-003; `LLM_EFFORT_JUDGE` y `LLM_THINKING_JUDGE` segun SPEC-103). Los
    overrides del YAML (`models:`) MUST aplicarse al juez igual que hoy se
    aplican al profesor.
  - La configuracion del juez MUST construirse junto a las de tarea y profesor
    (`build_llm_configs`), validarse en el mismo paso e inyectarse al adapter. El
    adapter MUST NOT reconstruirla desde el entorno.
  - El uso del juez MUST registrarse en un bucket propio `judge` en
    `UsageTracker`. Por compatibilidad, la columna `Tokens Reflection` del CSV
    MUST seguir mostrando reflexion + juez, y el detalle por bucket MUST quedar
    en `run.json`.
  - El costo de cada bucket (`task`, `reflection`, `judge`) MUST tarifarse con
    el modelo de su rol. `Costo Real USD` conserva su semantica (total de la
    corrida).
  - Los casos sin juez MUST NOT registrar un rol `judge` (ni en `run.json` ni en
    el CSV).
- FR-005 Al arrancar, cada entry point MUST validar la configuracion y la
  conexion de los roles que esa corrida usa, y solo de esos: el optimizador usa
  tarea y profesor, mas el juez en RAG; `baseline_only.py` usa solo tarea. Ademas:
  - La sonda de conexion MUST pasar por el punto de llamada comun de SPEC-105
    (sin la excepcion de `test_single_call_point.py`), con `num_retries=0`.
  - Su falla MUST clasificarse con las reglas de SPEC-104 (capa 1, sin depender
    del texto del mensaje, SPEC-104 FR-015): credencial o modelo invalido es
    `configuracion`; 429 o timeout es `infraestructura`.
  - `LLMConnectionError` MUST llevar el rol y mostrarlo junto al proveedor, el
    modelo y la variable concreta del rol (`LLM_API_KEY_REFLECTION`, no
    `LLM_API_KEY`) cuando la credencial salio de ella.
  - La falla al arrancar MUST abortar antes de la primera llamada de
    optimizacion y MUST NOT escribir `run.json` (todavia no hay corrida). La
    clasificacion de SPEC-104 se usa aca solo para el diagnostico, y su FR-008
    (abortar con `status: "aborted"`) rige solo durante la corrida.
  - La carga de `LLM_ENV_FILE` MUST dispararse cuando no hay ninguna credencial
    definida (ni global ni por rol), no solo cuando falta `LLM_API_KEY`
    (`shared/llm/config.py`, `shared/utils/check_deployments.py`).
- FR-006 Registro y comparabilidad:
  - `run.json` MUST guardar, por cada rol usado, el modelo con prefijo de
    proveedor, el proveedor y el host del endpoint efectivo (nunca la credencial).
  - El CSV maestro MUST agregar la columna `Modelo Juez`: modelo efectivo del juez
    en RAG, vacia en los demas casos.
  - Enmienda a SPEC-100 FR-007 y FR-009: segunda excepcion al formato congelado
    del CSV, agregada por el logger y no por el veredicto.
  - `migrate_metrics_csv.py` MUST completar `Modelo Juez` en filas previas de
    casos RAG con el valor de `Modelo Profesor` (antes el juez era el profesor) y
    dejarla vacia en el resto.
  - El logger MUST escribir la columna nueva tambien sobre un CSV existente sin
    migrar (hoy `_sync_active_keys_to_file` descarta columnas nuevas en silencio),
    o fallar con un mensaje que pida migrar. Nunca descartarla en silencio.
  - Enmienda a SPEC-100 FR-008 y SPEC-101 FR-002: la clave de comparabilidad
    MUST ser la terna (`Modelo Tarea`, `Modelo Profesor`, `Modelo Juez`), con la
    cadena cruda: `azure/gpt-4o` y `openai/gpt-4o` MUST contar como modelos
    distintos (pueden diferir en version de despliegue y filtros).
    `seed_triage.target_models` MUST incluir el juez en casos RAG.
- FR-007 El arranque MUST imprimir, por cada rol usado, rol, proveedor, modelo y
  host del endpoint (nunca la credencial), para que el endpoint de cada rol sea
  verificable en el log.
- FR-008 `shared/utils/check_deployments.py` MUST verificar cada rol contra su
  propio endpoint. Un rol no Azure MUST informarse como "no aplica", no como
  error.
- FR-009 MUST documentarse:
  - `docs/LLM_CONFIG.md`: variables por rol, regla de proveedor ancla y un ejemplo
    de combinacion entre proveedores;
  - `docs/METADATA_REPRODUCIBILIDAD.md`: proveedor y host por rol, bucket `judge`;
  - `docs/PROTOCOLO_N_SEEDS.md`: terna de comparabilidad;
  - los `.env.example` de ambos subproyectos.

## Decisiones

- Proveedor ancla en lugar de "ignorar siempre los globales" (opcion 1 de la
  iteracion 1): ignorar siempre rompe FR-002 para `openai/` con proxy en
  `LLM_API_BASE`. Tampoco hacia falta un "proveedor global" nuevo: el ancla es el
  proveedor de `task`, que hoy coincide con el de todos los roles. La regla cubre
  clave, endpoint y version a la vez, que es donde estaba la fuga real.
- `azure/X` y `openai/X` son modelos distintos para la comparabilidad
  (cierra el `[NEEDS CLARIFICATION]` de FR-006 de la iteracion 1, cuya premisa,
  que `normalize_model` los igualaba, era falsa).
- El proveedor va en el prefijo del modelo, que ya esta en el CSV: no hace falta
  una columna de proveedor. La unica columna nueva es `Modelo Juez`.
- Sin modelo por defecto (2026-11-27, decision del usuario tras revisar 1b): un
  `LLM_MODEL_<ROL>` ausente o vacio frena la corrida en la validacion local. Un
  default silencioso (`azure/gpt-4.1-mini`) puede gastar API con un modelo que
  nadie eligio y, con roles de proveedores distintos, fija un proveedor ancla
  equivocado.
- Sin variables nativas de LiteLLM: la credencial de cada rol es explicita en
  `LLM_*`, para que la validacion local pueda nombrar lo que falta.
- La iteracion 1 incluia la evaluacion economica (FR-007 y FR-008). Paso a
  [[SPEC-107-costo-real-por-resolucion]]: es otro dominio (uso por fase, formula
  de costo con metricas continuas y `eval_repeats`, ROI) y sus decisiones
  abiertas no deben bloquear la conexion por rol.

## Criterios de exito (medibles, agnosticos a tecnologia)

- SC-001 Una corrida con estudiante `azure/gpt-4.1-mini` y profesor Claude con
  acceso real (`anthropic/claude-sonnet-5-5`) completa de punta a punta en cada
  subproyecto. El log de arranque (FR-007) y el `run.json` muestran un endpoint
  distinto por rol, y el uso por bucket muestra llamadas de los dos roles.
- SC-002 Con el mismo caso, dataset y estudiante, cambiar solo el proveedor del
  profesor (o solo el juez en RAG) produce filas que SPEC-100 y SPEC-101 comparan
  entre si y no contra la combinacion anterior. Precondicion para un profesor
  Claude: D-028 cerrada o el lote con effort/thinking constantes.
- SC-003 Un rol `anthropic/` sin `LLM_API_KEY_<ROL>`, con un `LLM_API_KEY`
  global de Azure, falla en la validacion local sin ninguna llamada de red, y la
  clave global no aparece en los parametros de ese rol.
- SC-004 Los tests y corridas existentes pasan sin cambios en sus `.env`, con
  parametros de llamada identicos por rol (sin regresion);
  `./shared/utils/ci_local.sh` verde.
- SC-005 Un error de credenciales en un solo rol (tarea, profesor o juez) se
  reporta antes de la primera llamada de optimizacion, nombrando ese rol y su
  variable, y sin crear `run.json`.
- SC-006 Sobre una copia del CSV maestro actual, la primera corrida RAG tras el
  cambio deja `Modelo Juez` escrito (con o sin migracion previa) y las filas
  RAG previas migradas siguen siendo comparables con una corrida nueva cuyo juez
  es el profesor.

## Escenarios (Given/When/Then)

- Given `LLM_MODEL_TASK=azure/gpt-4.1-mini` con `LLM_API_KEY`/`LLM_API_BASE`
  globales de Azure y `LLM_MODEL_REFLECTION=anthropic/claude-sonnet-5-5` con
  `LLM_API_KEY_REFLECTION`, When arranca una corrida, Then el estudiante usa
  Azure, el profesor usa Anthropic sin `api_base`, sin `api_version` y sin aviso
  de `LLM_API_BASE` ignorado, y ambos se validan.
- Given la misma combinacion sin `LLM_API_KEY_REFLECTION`, When arranca, Then
  falla en la validacion local nombrando `reflection`, `anthropic` y
  `LLM_API_KEY_REFLECTION`, sin llamada de red.
- Given un `.env` actual sin variables por rol (todos `azure/`, o todos `openai/`
  con `LLM_API_BASE` de proxy), When arranca, Then los parametros enviados son
  identicos a los de antes del cambio.
- Given `LLM_MODEL_REFLECTION=anthropic/...` con
  `LLM_API_BASE_REFLECTION=https://gateway.interno`, When arranca, Then el
  profesor envia ese `api_base`.
- Given `LLM_API_KEY_REFLECTION` invalida, When arranca, Then falla en la
  validacion con clase `configuracion`, un mensaje que nombra `reflection` y su
  proveedor, y sin `run.json`.
- Given la sonda de un rol recibe 429, When arranca, Then el error se reporta
  como `infraestructura` del rol, no como credencial invalida.
- Given un caso RAG sin `LLM_MODEL_JUDGE`, When corre, Then el juez usa la
  configuracion del profesor, su uso cae en el bucket `judge`, `Tokens Reflection`
  suma reflexion + juez y `Modelo Juez` = `Modelo Profesor`.
- Given un caso RAG con `LLM_MODEL_JUDGE` distinto del profesor, When corre,
  Then el juez se valida en el Step 2 y llama a su propio endpoint.
- Given un caso no RAG con `LLM_MODEL_JUDGE` definido, When corre, Then el juez
  no se valida ni se registra.
- Given `baseline_only.py` con el profesor mal configurado, When corre, Then no
  falla por el profesor.

## Coverage mapping (requisito -> derivado)

| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | `shared/llm/config.py::LLMConfig.from_env`; `tests/test_role_connection.py` (vigente, verde desde 1b); modelo sin default: `LLMConfig.validate`, `tests/test_role_connection.py::TestModelWithoutDefault` (vigente, verde desde 1b-fix-1) |
| FR-002 | `tests/test_role_connection_golden.py` (vigente, verde) |
| FR-003 | `shared/llm/config.py` (`from_env`, `apply_constraints`, `_warn_once`, `provider_of`), `shared/llm/dspy_lm.py`; `tests/test_anthropic_matrix.py` (caso `api_base` ajustado); `tests/test_role_connection.py` (no fuga, vigente desde 1b); `from_env` rechaza overrides de conexion: `tests/test_role_connection.py::TestConnectionOverridesRejected` (vigente desde 6-fix-3) |
| FR-004 | `shared/llm/usage.py`, `shared/analysis/roi_calculator.py::cost_from_usage`, `shared/llm/config.py`, `gepa_standalone/universal_optimizer.py::build_llm_configs`, `gepa_standalone/adapters/simple_rag_adapter.py`, `gepa_standalone/core/llm_factory.py`; bucket `judge`, `Tokens Reflection` y costo por rol: `tests/test_shared_usage.py`, `tests/test_shared_analysis.py` (vigente desde 3a); configuracion del juez como rol: `shared/llm/config.py::resolve_judge_config`, `tests/test_judge_role.py` (vigente desde 3b); juez heredado sin sonda propia y con mensajes del profesor (`LLMConfig.env_role`): `tests/test_judge_role.py::TestJudgeWithoutOwnModel` (vigente desde 6-fix-2) |
| FR-005 | `shared/llm/config.py::validate_connection`, `shared/llm/errors.py::LLMConnectionError`, `shared/llm/call.py`, `gepa_standalone/universal_optimizer.py::validate_llm_connections`, `dspy_gepa_poc/reflexio_declarativa.py::setup_models`, `dspy_gepa_poc/scripts/baseline_only.py`, `tests/test_single_call_point.py`; sonda por el punto comun (`shared/llm/call.py::probe_completion`), clase de SPEC-104 y `LLMConnectionError` con rol y variable: `tests/test_role_probe.py` y `tests/test_single_call_point.py` sin la excepcion de `validate_connection` (vigente desde 2a); validacion de solo los roles usados en entry points: `gepa_standalone/universal_optimizer.py::validate_llm_connections`, `dspy_gepa_poc/reflexio_declarativa.py::setup_models(roles=...)`, `tests/test_role_startup.py` (vigente desde 2b); el juez en RAG: `tests/test_judge_role.py` (vigente desde 3b) |
| FR-006 | `shared/logging/metadata.py`, `shared/logging/csv_writer.py` (`STANDARD_COLUMN_MAPPING`, `_sync_active_keys_to_file`), `shared/utils/migrate_metrics_csv.py`, `shared/utils/seed_protocol.py`, `shared/utils/seed_triage.py`; `run.json` con proveedor y host por rol, columna `Modelo Juez`, logger sobre CSV sin migrar y migracion: `tests/test_judge_registry.py` (vigente desde 4a); terna de comparabilidad en `seed_protocol`/`seed_triage`: `tests/test_seed_protocol.py`, `tests/test_seed_triage.py` (vigente desde 4b) |
| FR-007 | `shared/llm/config.py::LLMConfig.endpoint_host` y `connection_summary` (vigente desde 1b, `tests/test_role_connection.py::TestEndpointAndSummary`); impresion en entry points: `tests/test_role_startup.py::TestStartupPrintsEndpointPerRole` (vigente desde 2b) |
| FR-008 | `shared/utils/check_deployments.py`; `tests/test_check_deployments.py` (vigente desde 5a); carga de `LLM_ENV_FILE` sin credenciales (FR-005, ultimo punto): `check_deployments.main` y `tests/test_check_deployments.py::TestEnvFileTrigger` (vigente desde 5a) |
| FR-009 | `docs/LLM_CONFIG.md`, `docs/METADATA_REPRODUCIBILIDAD.md`, `docs/PROTOCOLO_N_SEEDS.md`, `.env.example` de ambos subproyectos (vigente desde 5b) |
| SC-001 | corrida manual con API real por subproyecto (vigente desde fase 7, 2026-11-27: GEPA `rag_optimization` run `235a07e5`, DSPy `dynamic_sentiment_hard` run `3182b393`; registro en el plan) |
| SC-002 | `seed_protocol` / `seed_triage` sobre las filas resultantes (vigente desde fase 7, 2026-11-27: las filas nuevas solo se comparan entre si; las previas con profesor `azure/gpt-4o` quedan excluidas) |
| SC-003 | `tests/test_role_connection.py::TestNoLeakBetweenProviders` (vigente desde 1b, sin red) |
| SC-004 | `./shared/utils/ci_local.sh`; `tests/test_role_connection_golden.py` |
| SC-005 | `tests/test_role_startup.py::TestInvalidCredentialByRole` (tarea y profesor, ambos subproyectos; vigente desde 2b); juez: `tests/test_judge_role.py::TestInvalidJudgeCredential` (vigente desde 3b) |
| SC-006 | `tests/test_judge_registry.py::TestSC006` sobre copia sintetica del CSV, con y sin migracion (vigente desde 4a; migracion sin `run.json`: `tests/test_judge_registry.py::TestMigrationOfJudgeModel` (vigente desde 6-fix-1)) |
