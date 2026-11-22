# SPEC-104-roles-intercambiables — Profesor y estudiante intercambiables entre proveedores

Estado: draft
Iteracion: 1 (rev. 2026-11-22)
Relacionada con: [[SPEC-103-proveedor-anthropic]], [[SPEC-100-veredicto-senal-ruido]], docs/LLM_CONFIG.md

## User Story (prioridad)

Como persona que experimenta con DSPy y GEPA, quiero asignar a cada rol
(estudiante, profesor, juez) un modelo de cualquier proveedor soportado, de forma
independiente, en los dos subproyectos, para medir cuanto aporta cambiar un solo
rol (por ejemplo, profesor Claude con el mismo estudiante Azure) y que combinacion
resuelve los casos de prueba al menor costo real.
Prioridad: P1

## Contexto (estado al 2026-11-22)

Cada rol ya elige su modelo (`LLM_MODEL_TASK`, `LLM_MODEL_REFLECTION`), pero la
credencial y el endpoint son unicos (`LLM_API_KEY`, `LLM_API_BASE`,
`LLM_API_VERSION`): hoy los dos roles deben ser del mismo proveedor. El juez
(LLM-as-judge, `gepa_standalone/adapters/simple_rag_adapter.py`) usa la
configuracion del profesor. El uso real de tokens ya se mide por rol
(`shared/llm/usage.py`) en ambos subproyectos.

## Alcance

Incluye: resolucion de modelo, credencial, endpoint y version por rol;
validacion de cada rol al arrancar; registro del proveedor por rol; medicion del
costo por resolucion sobre los casos de prueba. Ambos subproyectos.

Excluye: restricciones de parametros de un proveedor concreto (las de Anthropic
son [[SPEC-103-proveedor-anthropic]]); balanceo, fallback o reintentos entre
proveedores; seleccion automatica de la mejor combinacion.

## Requisitos funcionales

- FR-001 Cada rol MUST resolver su propia conexion: `LLM_API_KEY_<ROL>`,
  `LLM_API_BASE_<ROL>` y `LLM_API_VERSION_<ROL>`, con fallback a la variable
  global correspondiente cuando la del rol no esta definida. Aplica a todo rol
  que use `LLMConfig.from_env` (task, reflection y los adicionales).
- FR-002 Un `.env` sin variables por rol MUST comportarse exactamente igual que
  hoy (compatibilidad hacia atras).
- FR-003 Los valores globales MUST NOT filtrarse a un rol de otro proveedor de
  forma que rompa la llamada (ejemplo: un `LLM_API_BASE` global de Azure no MUST
  aplicarse a un rol `anthropic/` u `openai/` que no define el suyo).
  [NEEDS CLARIFICATION: si un rol no-Azure no define `LLM_API_BASE_<ROL>`, se
  ignora el global siempre, o solo cuando el proveedor del rol difiere del
  proveedor "global"? La primera es mas simple y predecible.]
- FR-004 El juez MUST ser un rol configurable (`LLM_MODEL_JUDGE` y su conexion),
  con fallback a la configuracion del profesor si no se define, y su uso MUST
  seguir contando en el bucket de reflexion.
- FR-005 Al arrancar, cada subproyecto MUST validar configuracion y conexion de
  todos los roles que la corrida va a usar, y los errores MUST indicar rol,
  proveedor y modelo.
- FR-006 El registro de cada corrida (CSV y `run.json`) MUST guardar proveedor y
  modelo de cada rol, de modo que [[SPEC-100-veredicto-senal-ruido]] y
  [[SPEC-101-triaje-casos-nseeds]] solo comparen corridas con la misma
  combinacion.
  [NEEDS CLARIFICATION: `azure/gpt-4o` y `openai/gpt-4o` cuentan como el mismo
  modelo a efectos de comparabilidad? Hoy `normalize_model` los iguala.]
- FR-007 La evaluacion economica de una combinacion MUST basarse en uso real
  sobre los casos de prueba, no en el precio por token. Por corrida MUST
  reportarse, con tokens reales y precios por rol:
  - costo de optimizacion (estudiante + profesor + juez durante la optimizacion);
  - costo por llamada del estudiante en la evaluacion de test (incluye el prompt
    optimizado y los tokens de razonamiento);
  - costo por resolucion correcta en test = costo de evaluacion de test /
    casos resueltos correctamente.
  Para eso el uso de la evaluacion de test MUST medirse separado del uso de la
  optimizacion.
- FR-008 El calculo de ROI y el leaderboard MUST usar esas magnitudes medidas
  cuando existan, y caer a las estimaciones por caso solo para corridas antiguas
  sin medicion (indicandolo).
- FR-009 `docs/LLM_CONFIG.md` MUST documentar las variables por rol y un ejemplo
  de combinacion entre proveedores.

## Criterios de exito (medibles, agnosticos a tecnologia)

- SC-001 Una corrida con estudiante `azure/gpt-4.1-mini` y profesor Claude
  completa de punta a punta en cada subproyecto, con cada rol llamando a su
  propio endpoint (verificable en el log y en el uso por rol).
- SC-002 Con el mismo caso, dataset y estudiante, cambiar solo el profesor de
  proveedor produce filas que SPEC-100 compara entre si y no contra la
  combinacion anterior.
- SC-003 El 100% de las corridas nuevas reportan los tres costos de FR-007, y el
  costo por resolucion correcta coincide con el calculado a mano desde el uso
  por rol, las predicciones de test y la tabla de precios.
- SC-004 Los tests y corridas existentes pasan sin cambios en sus `.env`
  (sin regresion).
- SC-005 Un error de credenciales en un solo rol se reporta antes de la primera
  llamada de optimizacion, nombrando ese rol.

## Escenarios (Given/When/Then)

- Given `LLM_MODEL_TASK=azure/gpt-4.1-mini` con `LLM_API_KEY`/`LLM_API_BASE`
  globales de Azure, y `LLM_MODEL_REFLECTION=anthropic/claude-opus-5-5` con
  `LLM_API_KEY_REFLECTION`, When arranca una corrida, Then el estudiante usa
  Azure, el profesor usa Anthropic sin `api_base` de Azure y ambos se validan.
- Given un `.env` actual sin variables por rol, When arranca una corrida, Then
  los parametros enviados son identicos a los de antes del cambio.
- Given `LLM_API_KEY_REFLECTION` invalida, When arranca la corrida, Then falla en
  la validacion con un mensaje que nombra el rol `reflection` y su proveedor.
- Given una corrida terminada, When se consulta su registro, Then muestra
  proveedor y modelo por rol, costo de optimizacion, costo por llamada en test y
  costo por resolucion correcta.
- Given dos combinaciones con el mismo caso, When una tiene precio por token mas
  bajo pero resuelve menos casos o consume mas tokens por llamada, Then el costo
  por resolucion correcta lo refleja y puede ser mayor.

## Coverage mapping (requisito -> derivado)

| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | `shared/llm/config.py::LLMConfig.from_env`; `tests/test_shared_llm.py` (pendiente) |
| FR-002 | test de regresion con `.env` actual (pendiente) |
| FR-003 | `LLMConfig.from_env`; test (pendiente) |
| FR-004 | `gepa_standalone/adapters/simple_rag_adapter.py`, `gepa_standalone/core/llm_factory.py`; test (pendiente) |
| FR-005 | `gepa_standalone/universal_optimizer.py::validate_llm_connections`, `dspy_gepa_poc/reflexio_declarativa.py::setup_models`; test (pendiente) |
| FR-006 | `shared/logging/csv_writer.py`, `shared/utils/seed_protocol.py`, `shared/analysis/roi_calculator.py::normalize_model` (pendiente) |
| FR-007 | `shared/llm/usage.py` (uso por fase), `shared/analysis/roi_calculator.py`, registro de corrida en ambos subproyectos (pendiente) |
| FR-008 | `shared/analysis/roi_calculator.py`, `shared/analysis/leaderboard.py` (pendiente) |
| FR-009 | `docs/LLM_CONFIG.md` |
| SC-001 | corrida manual con API real por subproyecto (pendiente) |
| SC-002 | `seed_triage` / `seed_protocol` sobre las filas resultantes (pendiente) |
| SC-003 | test con uso y predicciones sinteticas + verificacion sobre una corrida real (pendiente) |
| SC-004 | `./shared/utils/ci_local.sh` |
| SC-005 | test de validacion con credencial invalida por rol (pendiente) |
