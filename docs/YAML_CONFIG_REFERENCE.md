# Referencia de Configuracion YAML

> **SSOT** para todos los campos de configuracion YAML de ambos proyectos.
> Fuente: `config_schema.py` de cada proyecto.

---

## Criterio unificado `case`

Ambos subproyectos comparten la misma estructura y uso de la seccion `case:`:

| Campo | Requerido | Uso |
|-------|-----------|-----|
| `case.name` | MUST | Slug corto. Alimenta el nombre del directorio de runs y el `experiment_name` de metadata |
| `case.title` | MUST | Titulo semantico. Alimenta la columna `Caso` del CSV maestro y del leaderboard |
| `case.description` | SHOULD | Descripcion del caso |

Los titulos se mantienen distintos por engine (no se normalizan entre DSPy y
GEPA) para que el leaderboard combinado no mezcle ambos motores. El consumo de
la columna `Caso` esta en `shared/logging/csv_writer.py` (`case_name -> Caso`).

---

## 1. DSPy + GEPA (`dspy_gepa_poc/configs/`)

### Secciones Requeridas

| Seccion | Campo | Tipo | Descripcion |
|---------|-------|------|-------------|
| `case` | `name` | string | Slug corto del caso (ver [Criterio unificado `case`](#criterio-unificado-case)) |
| `case` | `title` | string | Titulo semantico del caso |
| `module` | `type` | string | Tipo de modulo: `dynamic`, `rule_derived`, `rule_derived_alto`, `pipeline` (cualquier otro valor es error de validacion) |
| `data` | `csv_filename` | string | Archivo CSV en `datasets/` |
| `data` | `input_column` o `input_columns` | string / list | Columna(s) de entrada del CSV. `input_column` (string, single) o `input_columns` (lista, multi-input); al menos uno requerido |
| `optimization` | `max_metric_calls` o `auto_budget` | int / string | Al menos uno requerido |

### Signature (requerida si `module.type: "dynamic"` o `"rule_derived"`)

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `signature.instruction` | string | Prompt base para la tarea |
| `signature.inputs` | list | Lista de `{name, desc}` |
| `signature.outputs` | list | Lista de `{name, desc}` |

### Optimization (opcionales)

| Campo | Tipo | Default | Descripcion |
|-------|------|---------|-------------|
| `optimization.max_metric_calls` | int | - | Budget de llamadas a metrica (prioritario) |
| `optimization.auto_budget` | string | - | `light`, `medium`, `heavy` (fallback si no hay max_metric_calls) |
| `optimization.predictor_type` | string | `cot` | `cot` o `predict` |
| `optimization.use_few_shot` | bool | false | Habilitar inyeccion de ejemplos few-shot |
| `optimization.few_shot_count` | int | 3 | Numero de ejemplos few-shot |
| `optimization.ignore_in_metric` | list | [] | Campos de output a ignorar en evaluacion |
| `optimization.match_mode` | string | `exact` | `exact`, `normalized`, `fuzzy` (ver `docs/DSPY_GUIA_DISENO.md` seccion 5) |
| `optimization.fuzzy_threshold` | float | 0.85 | Umbral de similitud para modo fuzzy (0.0-1.0) |
| `optimization.metric_feedback` | bool | false | Si `true`, la metrica emite diagnostico textual para el reflection_lm de GEPA |
| `optimization.field_configs` | dict | {} | Overrides por campo: `{nombre: {mode: exact\|normalized\|fuzzy\|set, fuzzy_threshold?: float, separators?: str}}`. Implica `metric_feedback=true` |
| `optimization.eval_repeats` | int | 1 | Repeticiones de evaluacion por prompt (k) para reducir varianza del LLM |
| `optimization.num_threads` | int | 1 | Threads para evaluacion paralela |
| `optimization.save_predictions` | bool | false | Si `true`, al cerrar el run vuelca `predictions_test.csv` y `predictions_val.csv` en el run dir: por cada ejemplo, `gold_*` vs `pred_*` de cada output (auditabilidad). Generico para modulos con `signature`. Agrega una llamada LLM por ejemplo |

### Models (opcionales)

| Campo | Tipo | Default | Descripcion |
|-------|------|---------|-------------|
| `models.temperature` | float | (del .env) | Override de temperatura |
| `models.max_tokens` | int | 1000 | Override de max tokens. Requerido >= 16000 para reasoning models (gpt-5, o1, o3) |
| `models.cache` | bool | false | Cache de respuestas DSPy; hoy solo `false` (ver `LLM_CACHE` en `docs/LLM_CONFIG.md`) |

### Seccion `adapter`: no soportada

La seccion `adapter` es de `gepa_standalone`. En DSPy el validador la rechaza
(`dspy.GEPA` 3.2.1 y 3.4.1 no aceptan `max_text_length` ni `max_positive_examples`, asi que
nunca tuvieron efecto; D-025). Los ejemplos en el prompt se controlan con
`optimization.use_few_shot` / `few_shot_count`.

### Parametros de GEPA no configurables por YAML

`GEPAConfig` (`config.py`) fija defaults que el YAML no puede cambiar:
`skip_perfect_score: true`, `reflection_minibatch_size: 3`,
`candidate_selection_strategy: pareto`, `use_merge: true`,
`max_merge_invocations: 5`, `track_stats: true`. Para modificarlos hay que
cambiar el codigo.

### Campos por Tipo de Modulo

| Tipo | Campos Adicionales Requeridos |
|------|-------------------------------|
| `dynamic` | Seccion `signature` completa |
| `rule_derived` | Seccion `signature` completa; outputs DEBEN incluir las preguntas + el campo derivado (ver abajo) |
| `rule_derived_alto` | Seccion `signature` completa; el LLM responde sub-hechos y `derive_alto_impacto` deriva `alto_impacto` antes del color (ver `docs/LECCIONES_APRENDIDAS.md`, D-015a) |
| `pipeline` | Secciones `stages` (lista, >=2 etapas con `name` + `signature`) y `routing` |

Cualquier otro tipo (incluidos los heredados `sentiment`, `extractor`, `qa`) es
error de validacion.

### Pipeline (requerida si `module.type: "pipeline"`)

Compone N etapas en serie con routing condicional: la etapa-gate decide si las posteriores se ejecutan. Ver `DynamicModuleFactory.create_pipeline_module` (`dynamic_factory.py`).

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `stages` | list | Lista de >=2 etapas; cada una con `name` (unico) y `signature` (estructura completa) |
| `routing.gate_stage` | string | Nombre de la etapa cuyo output dispara el gate |
| `routing.gate_field` | string | Campo de output de `gate_stage` a evaluar (debe existir en sus outputs) |
| `routing.gate_value` | string | Valor que abre las etapas posteriores |
| `routing.skip_outputs_when_gated` | dict | Opcional: `{campo: valor}` asignado a outputs de etapas posteriores cuando el gate no abre |

### Rule_derived (requerida si `module.type: "rule_derived"`)

El LLM NO produce el resultado final: emite **juicios atomicos** y una **funcion pura**
deriva el resultado de forma deterministica. Hoy especifico de fast_gate (Marco de
Gobierno de IA): el LLM responde 5 preguntas Si/No + `alto_impacto`, y
`flujo_intents/fast_gate_rule.derive_color` calcula el color. Ver `ARCHITECTURE.md`
(patron Rule-Derived) y `DynamicModuleFactory.create_rule_derived_module`.

| Aspecto | Detalle |
|---------|---------|
| `signature.outputs` | DEBE incluir `p1..p5`, `alto_impacto` y el campo derivado `clasificacion`. El factory crea el predictor con todos los outputs MENOS `clasificacion` (el LLM no lo decide); el `forward()` lo agrega derivado |
| Metrica | Evaluar el campo derivado (`clasificacion`) y opcionalmente el cuello (`alto_impacto`). NO evaluar las 5 preguntas si ya estan altas: infla el baseline al techo y diluye la senal (ver `historial/sdd.md`, fix de metrica 2026-06-16) |
| Dataset | Las preguntas (`p1..p5`, `alto_impacto`) son gold y deben ser conteo-consistentes: `derive_color(p1..p5, alto_impacto) == clasificacion` en todas las filas |

---

## 2. GEPA Standalone (`gepa_standalone/experiments/configs/`)

### Secciones Requeridas

| Seccion | Campo | Tipo | Descripcion |
|---------|-------|------|-------------|
| `case` | `name` | string | Slug corto del caso (ver [Criterio unificado `case`](#criterio-unificado-case)) |
| `case` | `title` | string | Titulo semantico del caso |
| `adapter` | `type` | string | Tipo de adaptador: `classifier`, `extractor`, `sql`, `rag` |
| `data` | `csv_filename` | string | Archivo CSV en `experiments/datasets/` |
| `optimization` | `max_metric_calls` | int | Budget de llamadas a metrica (10-500) |

### Case (opcionales)

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `case.description` | string | Descripcion del caso |

### Data (opcionales)

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `data.input_column` | string | Columna de entrada (default: `text`) |
| `data.output_columns` | list | Columnas de salida a validar contra el CSV |

### Adapter (campos por tipo)

| Tipo | Campos Requeridos | Campos Opcionales |
|------|-------------------|-------------------|
| `classifier` | `valid_classes` (list) | (ninguno) |
| `extractor` | `required_fields` (list) | `extractor_max_positive_examples` |
| `sql` | - | (ninguno) |
| `rag` | - | `max_positive_examples` (prioritario sobre `rag_max_positive_examples`) |

Limites de longitud y ejemplos positivos: se fijan en la seccion `adapter` del
YAML. Los limites truncan el texto que recibe el Profesor en el dataset de
reflexion, no la entrada de la tarea. `Config.apply_yaml_config` (`gepa_standalone/config.py`) los aplica sobre
defaults del codigo; NO se leen de variables de entorno. Los campos
`extractor_max_positive_examples` (extractor) y `max_positive_examples` (rag)
ademas se pasan directo al adapter y tienen prioridad.

| Campo | Default | Pisa en `Config` |
|-------|---------|------------------|
| `adapter.max_text_length` | 1000 | `CLASSIFIER_TEXT_MAX_LENGTH` y `EXTRACTOR_TEXT_MAX_LENGTH` |
| `adapter.rag_context_max_length` | 1500 | `RAG_CONTEXT_MAX_LENGTH` |
| `adapter.rag_max_positive_examples` | 2 | `RAG_MAX_POSITIVE_EXAMPLES` |
| `adapter.extractor_max_positive_examples` | 0 | `EXTRACTOR_MAX_POSITIVE_EXAMPLES` |

### Prompt (opcional)

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `prompt.filename` | string | Archivo JSON en `experiments/prompts/` |

### Optimization (opcionales)

| Campo | Tipo | Default | Descripcion |
|-------|------|---------|-------------|
| `optimization.skip_perfect_score` | bool | true | Omitir ejemplos con score perfecto en reflexion |
| `optimization.display_progress_bar` | bool | true | Mostrar barra de progreso |
| `optimization.ignore_in_metric` | list | [] | Campos de output a ignorar en la evaluacion de la metrica |
| `optimization.eval_repeats` | int | 1 | Repeticiones de evaluacion por prompt (k) en val/test para reducir varianza del LLM |
| `optimization.match_mode` | string | `exact` | Solo `extractor`: `exact`, `normalized`, `fuzzy` |
| `optimization.fuzzy_threshold` | float | 0.85 | Solo `extractor`: umbral del modo fuzzy |
| `optimization.field_configs` | dict | - | Solo `extractor`: overrides de matching por campo (mismo formato que en DSPy) |
| `optimization.list_separators` | string | `,;` | Solo `extractor`: separadores para campos de tipo lista |

### Models (opcionales)

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `models.temperature` | float | Override de temperatura (tarea y reflexion). Sin el campo, la tarea usa 0.0 |
| `models.max_tokens` | int | Override de max tokens de tarea y reflexion. `classifier`, `sql` y `rag` fijan su propio maximo por llamada; `extractor` lo usa como maximo de respuesta. Sin el campo, la reflexion usa el default de `universal_optimizer.py` |
| `models.cache` | bool | Sin efecto: se guarda en la config pero la llamada de `gepa_standalone` (`shared/llm/call.py`) no usa cache |

---

## 3. Seccion `failures` (opcional, ambos subproyectos)

Configura el contador de fallas y los umbrales de aborto (SPEC-104 FR-006).
Validada en `BaseConfigValidator` antes de gastar tokens: claves, roles y rangos
invalidos son error de configuracion. Sin la seccion (o sin un campo) rigen los
defaults. La mezcla es parcial: solo se pisan las entradas indicadas. Que es cada
clase y que hace el aborto: `docs/GEPA_MANEJO_ERRORES.md`.

| Campo | Tipo | Default | Descripcion |
|-------|------|---------|-------------|
| `failures.infra_retries` | int >= 0 | 3 | Reintentos (con backoff exponencial) solo ante `infraestructura`; 3 = 4 intentos |
| `failures.judge_retries` | int >= 0 | 2 | Reintentos del juez de RAG ante un puntaje ilegible o fuera de [0, 1], antes de clasificarlo `formato`. Solo aplica al adapter `rag` |
| `failures.min_attempts.<rol>` | int >= 0 | `task: 20`, `judge: 20`, `reflection: 4` | Intentos minimos del rol antes de evaluar umbrales (para `entrada_dato`, casos unicos) |
| `failures.thresholds.<clave>.<rol>` | float [0, 1] | ver tabla | Aborta si `fallas / intentos > umbral` |

Roles validos: `task`, `judge`, `reflection`. Claves de umbral validas y defaults:

| Clave | task | judge | reflection |
|-------|------|-------|------------|
| `presupuesto` | 0.05 | 0.05 | 0.25 |
| `infraestructura` | 0.10 | 0.10 | - |
| `sin_texto` | 0.10 | 0.10 | - |
| `filtro_salida` | 0.10 | 0.10 | - |
| `entrada_dato` | 0.10 | - | - |
| `entrada` | - | 0.10 | - |
| `formato` | - | 0.10 | - |
| `total` (suma de todas las claves del rol) | - | - | 0.50 |

`configuracion` aborta siempre (sin umbral). `formato`, `entrada_candidato` y
`presupuesto_candidato` en `task` no tienen umbral: son score del candidato.

```yaml
failures:
  infra_retries: 3
  judge_retries: 2
  min_attempts:
    task: 30
  thresholds:
    presupuesto:
      task: 0.10
    total:
      reflection: 0.60
```

El estado resultante (conteos, aborto) queda en `run.json`
(`docs/METADATA_REPRODUCIBILIDAD.md`).

---

## 4. Campos Compartidos

Ambos proyectos comparten esta estructura base:

```yaml
case:
  name: "..."          # Requerido en ambos

data:
  csv_filename: "..."  # Requerido en ambos

models:
  temperature: 0.1     # Opcional en ambos (tambien max_tokens y cache)

optimization:
  max_metric_calls: 50 # Requerido en GEPA, opcional (con auto_budget) en DSPy
```

Las variables de entorno para modelos LLM (API keys, endpoints) se documentan en `docs/LLM_CONFIG.md`.
