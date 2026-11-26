# ARCHITECTURE — Patrones e invariantes

SSOT de los patrones de diseno del repo y las invariantes que MUST respetar
cualquier cambio. Para setup y comandos ver `docs/DEVELOPMENT.md`; para workflow
y convenciones ver `docs/CONTRIBUTING.md`.

## Patrones de arquitectura

- **Factory**: `DynamicModuleFactory` (`dspy_gepa_poc/dynamic_factory.py`) crea
  signatures y modules DSPy desde config YAML. Punto central de extension para
  nuevas tareas. Tipos: `dynamic` (predictor unico), `rule_derived` (ver abajo),
  `pipeline` (N etapas con routing).
- **Rule-Derived**: para tareas con **regla explicita y deterministica**
  (conteo/umbral/formula), el LLM NO produce el resultado final: emite los
  **juicios atomicos** (binarios) y una **funcion pura** aplica la regla. Hace el
  resultado deterministico, AUDITABLE y fiel a la regla, y aisla el error por
  componente. Implementacion: `create_rule_derived_module` (el `forward()` corre el
  predictor y agrega el campo derivado al `dspy.Prediction`, mismo patron de
  composicion que `create_pipeline_module`). Caso vigente: fast_gate de
  `flujo-intents` (`module.type: rule_derived`), donde el LLM responde 5 preguntas
  Si/No + `alto_impacto` y `flujo_intents/fast_gate_rule.derive_color` deriva el
  color (0-1 Verde / 2-3 Amarillo / 4-5 Rojo; Negro = P5 + alto impacto). Supera al
  enfoque end-to-end y lo hace auditable. Lecciones y veredicto (incl. por que GEPA
  no aporta aqui) en `historial/sdd.md` (D-013) y `docs/LECCIONES_APRENDIDAS.md` s11.
- **Adapter**: `BaseAdapter` (`gepa_standalone/adapters/base_adapter.py`) con 4
  implementaciones concretas (classifier, extractor, sql, rag). Cada adapter
  define como evaluar una tarea contra el LLM.
- **BasePaths**: `BasePaths` (`shared/paths/base_paths.py`) con subclases
  `GEPAPaths` y `DSPyPaths`. Gestion centralizada de rutas con fallback a
  ubicaciones legacy. MUST NOT hardcodear paths.
- **LLM unificado**: `shared/llm/` via LiteLLM. Configuracion en el `.env` de
  cada subproyecto. Variables: `LLM_API_KEY`, `LLM_MODEL_TASK`,
  `LLM_MODEL_REFLECTION`. Ver `docs/LLM_CONFIG.md`.
- **Validacion temprana**: `BaseConfigValidator` y `CSVValidator`
  (`shared/validation/`) validan configs YAML y datasets CSV antes de ejecutar.
  Fallos antes de gastar tokens.
- **Logger compartido**: `BaseCSVLogger` (`shared/logging/csv_writer.py`) para
  registro consistente de metricas.
- **MetadataManager**: `MetadataManager` (`shared/logging/metadata.py`) escribe
  metadata de reproducibilidad en 3 niveles: `environment.json` (frameworks),
  `experiment.meta.json` (dataset hash, contador), `run.json` (seed, modelos).
  Integracion automatica en entry points. Ver `docs/METADATA_REPRODUCIBILIDAD.md`.

## Agnosticismo de framework (DSPy y GEPA)

Principio: DSPy y GEPA son **motores intercambiables**, no el lugar donde vive lo
que define un experimento. Todo lo que determina el resultado de una
optimizacion (prompts, parseo, deteccion de fallas, medicion, reglas de negocio)
MUST ser del repo; de las librerias se usa solo su API publica. Asi un upgrade
no cambia la optimizacion en silencio y una incompatibilidad falla en CI, no en
una corrida paga. Origen: D-018 en `historial/sdd.md`; requisitos y criterios en
`specs/SPEC-105-punto-llamada-desacoplado.md`.

Reglas para cualquier construccion nueva:

- MUST: usar solo API publica de `dspy`, `gepa` y `litellm`. MUST NOT
  sobrescribir metodos ni importar simbolos privados (prefijo `_`) o no
  documentados (verificado por `tests/test_lib_contracts.py`).
- MUST: toda superficie publica que se empiece a usar entra al inventario de
  contratos (`SURFACES` en `tests/test_lib_contracts.py`) con al menos una
  mutacion que lo ponga rojo.
- MUST: toda llamada al LLM, en cualquier rol, pasa por el punto de llamada
  propio de `shared/llm/` (`call.py`; en DSPy via el engine `CheckedEngine` de
  `dspy_lm.py`). Ningun otro modulo llama a LiteLLM
  (`tests/test_single_call_point.py`).
- MUST NOT depender de defaults de la libreria que afecten la optimizacion: el
  repo fija los suyos. Vigentes: reflexion propia (`shared/llm/reflection.py`,
  `ReflectionProposer`, comun a los dos subproyectos), adapter de tarea
  (`configure_dspy` fija `ChatAdapter`) y tipo de `reasoning` de CoT
  (`chain_of_thought`). Un default nuevo que aparezca tras un upgrade se
  inventaria y se fija igual.
- MUST: la deteccion de fallas, el uso de tokens y el `finish_reason` se toman en
  el punto de llamada, sobre la respuesta cruda; MUST NOT leerse de estructuras
  internas del framework (p. ej. `dspy.LM.history`).
- SHOULD: la logica de dominio (reglas, metricas, derivaciones) se escribe como
  funciones puras sin importar `dspy`/`gepa`, y el framework solo la invoca. Ej.:
  `flujo_intents/fast_gate_rule.derive_color` en el patron Rule-Derived. Hoy en
  `shared/` solo `shared/llm/dspy_lm.py` importa `dspy`; mantenerlo asi.
- MUST: cambiar un componente fijado (plantilla de reflexion, adapter, version
  de libreria) es un **cambio de optimizacion**, no un ajuste: id/version nueva
  registrada y medicion con N seeds (`docs/PROTOCOLO_N_SEEDS.md`, comparabilidad
  por versiones de SPEC-100 FR-009). Se verifica con golden contra lo historico
  (SC-007 y SC-008 de SPEC-105: `tests/test_reflection_prompt.py`,
  `tests/test_dspy_call_failures.py`).
- MUST: versiones exactas (`==`) de `dspy`, `gepa`, `litellm` y `openai` en
  `requirements.txt`.

Limites conocidos del desacople (traduccion del engine solo texto, prompt de
reflexion como variable de experimento) en la Deuda arrastrada de
`historial/sdd.md` (D-026, D-027). Hallazgo que lo motivo: seccion "Los defaults
de la libreria son parte del experimento" de `docs/LECCIONES_APRENDIDAS.md`.

## Invariantes

- MUST: cada subproyecto (`dspy_gepa_poc/`, `gepa_standalone/`) tiene su propio
  `.env` para configuracion LLM independiente.
- MUST: inputs versionados en git: configs YAML, datasets CSV y prompts JSON.
- MUST NOT versionar outputs: todo bajo `**/results/` esta gitignoreado (runs,
  leaderboards, metricas). Son regenerables. Artefactos por corrida (local):
  `results/runs/<caso>_<ts>/` (`run.json`, `candidates.json`,
  `optimized_program.json`, `config_snapshot.yaml`; + `predictions_{test,val}.csv` si
  `optimization.save_predictions: true`), `results/experiments/metricas_optimizacion.csv`
  (una fila por corrida). El script `scripts/diagnose_fast_gate_rule.py` genera
  dumps por-ficha: con `--run-dir` los escribe dentro del run dir; sin el flag
  caen en `results/audits/` (diagnostico sobre programa base). El harness solo persiste
  prompts y scores agregados; las respuestas por-ejemplo requieren `save_predictions`
  o el dump.
- MUST: los datasets CSV requieren columna `split` con valores `train`/`val`/`test`
  (definido en `shared/validation/csv_validator.py`, `VALID_SPLITS`).
- MUST: un CSV con el mismo nombre en `dspy_gepa_poc/datasets/` y
  `gepa_standalone/experiments/datasets/` es un **espejo** (copia identica; se
  edita en los dos a la vez) o una **divergencia intencional** declarada. La lista
  y la verificacion viven en `tests/test_dataset_mirrors.py`; un par nuevo sin
  clasificar hace fallar el CI.
- MUST: invocar los entry points con `python -m` desde la raiz del repo. Si se
  ejecuta el script directo, Python pone el dir del script en `sys.path` y
  `import shared` falla. Detalle y comandos en `docs/DEVELOPMENT.md`.
