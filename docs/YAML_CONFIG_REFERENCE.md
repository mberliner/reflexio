# Referencia de Configuracion YAML

> **SSOT** para todos los campos de configuracion YAML de ambos proyectos.
> Fuente: `config_schema.py` de cada proyecto.

---

## 1. DSPy + GEPA (`dspy_gepa_poc/configs/`)

### Secciones Requeridas

| Seccion | Campo | Tipo | Descripcion |
|---------|-------|------|-------------|
| `case` | `name` | string | Nombre del experimento |
| `module` | `type` | string | Tipo de modulo: `dynamic`, `sentiment`, `extractor`, `qa` |
| `data` | `csv_filename` | string | Archivo CSV en `datasets/` |
| `data` | `input_column` | string | Columna de entrada del CSV |
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
| `optimization.num_threads` | int | 1 | Threads para evaluacion paralela |

### Models (opcionales)

| Campo | Tipo | Default | Descripcion |
|-------|------|---------|-------------|
| `models.temperature` | float | (del .env) | Override de temperatura |
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
| `sentiment` | Ninguno |
| `extractor` | `output_columns` (en `module` o `data`) |
| `qa` | `input_column_context`, `input_column_question` |

---

## 2. GEPA Standalone (`gepa_standalone/experiments/configs/`)

### Secciones Requeridas

| Seccion | Campo | Tipo | Descripcion |
|---------|-------|------|-------------|
| `case` | `name` | string | Nombre del caso |
| `adapter` | `type` | string | Tipo de adaptador: `classifier`, `extractor`, `sql`, `rag` |
| `data` | `csv_filename` | string | Archivo CSV en `experiments/datasets/` |
| `optimization` | `max_metric_calls` | int | Budget de llamadas a metrica (10-500) |

### Case (opcionales)

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `case.title` | string | Titulo legible del caso |
| `case.description` | string | Descripcion del caso |

### Data (opcionales)

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `data.input_column` | string | Columna de entrada (default: `text`) |
| `data.output_columns` | list | Columnas de salida a validar contra el CSV |

### Adapter (campos por tipo)

| Tipo | Campos Requeridos | Campos Opcionales |
|------|-------------------|-------------------|
| `classifier` | `valid_classes` (list) | `max_text_length`, `max_positive_examples` |
| `extractor` | `required_fields` (list) | `max_positive_examples`, `max_text_length` |
| `sql` | - | `max_text_length` |
| `rag` | - | `max_positive_examples`, `max_text_length` |

### Prompt (opcional)

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `prompt.filename` | string | Archivo JSON en `experiments/prompts/` |

### Optimization (opcionales)

| Campo | Tipo | Default | Descripcion |
|-------|------|---------|-------------|
| `optimization.skip_perfect_score` | bool | true | Omitir ejemplos con score perfecto en reflexion |
| `optimization.display_progress_bar` | bool | false | Mostrar barra de progreso |

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
