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
| `module` | `type` | string | Tipo de modulo: `dynamic`, `pipeline`, `sentiment`, `extractor`, `qa` |
| `data` | `csv_filename` | string | Archivo CSV en `datasets/` |
| `data` | `input_column` o `input_columns` | string / list | Columna(s) de entrada del CSV. `input_column` (string, single) o `input_columns` (lista, multi-input); al menos uno requerido |
| `optimization` | `max_metric_calls` o `auto_budget` | int / string | Al menos uno requerido |

### Signature (requerida si `module.type: "dynamic"`)

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

### Models (opcionales)

| Campo | Tipo | Default | Descripcion |
|-------|------|---------|-------------|
| `models.temperature` | float | (del .env) | Override de temperatura |
| `models.max_tokens` | int | 1000 | Override de max tokens. Requerido >= 16000 para reasoning models (gpt-5, o1, o3) |
| `models.cache` | bool | false | Cache de respuestas DSPy (ver `docs/LLM_CONFIG.md`) |

### Adapter (opcionales)

| Campo | Tipo | Default | Descripcion |
|-------|------|---------|-------------|
| `adapter.max_text_length` | int | 1000 | Longitud maxima de texto para el adaptador |
| `adapter.max_positive_examples` | int | 2 | Ejemplos positivos en prompt |
| `adapter.extractor_max_positive_examples` | int | 0 | Ejemplos positivos para extractor |

### Campos por Tipo de Modulo

| Tipo | Campos Adicionales Requeridos |
|------|-------------------------------|
| `dynamic` | Seccion `signature` completa |
| `pipeline` | Secciones `stages` (lista, >=2 etapas con `name` + `signature`) y `routing` |
| `sentiment` | Ninguno |
| `extractor` | `output_columns` (en `module` o `data`) |
| `qa` | `input_column_context`, `input_column_question` |

### Pipeline (requerida si `module.type: "pipeline"`)

Compone N etapas en serie con routing condicional: la etapa-gate decide si las posteriores se ejecutan. Ver `DynamicModuleFactory.create_pipeline_module` (`dynamic_factory.py`).

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `stages` | list | Lista de >=2 etapas; cada una con `name` (unico) y `signature` (estructura completa) |
| `routing.gate_stage` | string | Nombre de la etapa cuyo output dispara el gate |
| `routing.gate_field` | string | Campo de output de `gate_stage` a evaluar (debe existir en sus outputs) |
| `routing.gate_value` | string | Valor que abre las etapas posteriores |
| `routing.skip_outputs_when_gated` | dict | Opcional: `{campo: valor}` asignado a outputs de etapas posteriores cuando el gate no abre |

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
| `rag` | - | `max_positive_examples` |

Los limites de longitud de texto/contexto NO son campos del YAML: se configuran
por variable de entorno en el `.env` del subproyecto (`CLASSIFIER_TEXT_MAX_LENGTH`,
`EXTRACTOR_TEXT_MAX_LENGTH`, `RAG_CONTEXT_MAX_LENGTH`). Ver `docs/LLM_CONFIG.md`.

### Prompt (opcional)

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `prompt.filename` | string | Archivo JSON en `experiments/prompts/` |

### Optimization (opcionales)

| Campo | Tipo | Default | Descripcion |
|-------|------|---------|-------------|
| `optimization.skip_perfect_score` | bool | true | Omitir ejemplos con score perfecto en reflexion |
| `optimization.display_progress_bar` | bool | false | Mostrar barra de progreso |
| `optimization.ignore_in_metric` | list | [] | Campos de output a ignorar en la evaluacion de la metrica |
| `optimization.eval_repeats` | int | 1 | Repeticiones de evaluacion por prompt (k) en val/test para reducir varianza del LLM |

### Models (opcionales)

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `models.temperature` | float | Override de temperatura |

---

## 3. Campos Compartidos

Ambos proyectos comparten esta estructura base:

```yaml
case:
  name: "..."          # Requerido en ambos

data:
  csv_filename: "..."  # Requerido en ambos

models:
  temperature: 0.1     # Opcional en ambos

optimization:
  max_metric_calls: 50 # Requerido en GEPA, opcional (con auto_budget) en DSPy
```

Las variables de entorno para modelos LLM (API keys, endpoints) se documentan en `docs/LLM_CONFIG.md`.
