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

## Invariantes

- MUST: cada subproyecto (`dspy_gepa_poc/`, `gepa_standalone/`) tiene su propio
  `.env` para configuracion LLM independiente.
- MUST: inputs versionados en git: configs YAML, datasets CSV y prompts JSON.
- MUST NOT versionar outputs: todo bajo `**/results/` esta gitignoreado (runs,
  leaderboards, metricas). Son regenerables. Artefactos por corrida (local):
  `results/runs/<caso>_<ts>/` (`run.json`, `candidates.json`,
  `optimized_program.json`, `config_snapshot.yaml`; + `predictions_{test,val}.csv` si
  `optimization.save_predictions: true`), `results/experiments/metricas_optimizacion.csv`
  (una fila por corrida) y `results/audits/` (dumps por-ficha generados a mano con
  `scripts/diagnose_fast_gate_rule.py --run-dir`). El harness GEPA solo persiste
  prompts y scores agregados; las respuestas por-ejemplo requieren `save_predictions`
  o el dump.
- MUST: los datasets CSV requieren columna `split` con valores `train`/`val`/`test`
  (definido en `shared/validation/csv_validator.py`, `VALID_SPLITS`).
- MUST: invocar los entry points con `python -m` desde la raiz del repo. Si se
  ejecuta el script directo, Python pone el dir del script en `sys.path` y
  `import shared` falla. Detalle y comandos en `docs/DEVELOPMENT.md`.
