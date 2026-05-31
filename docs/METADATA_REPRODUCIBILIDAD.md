# Metadata de Reproducibilidad

## Proposito

Sistema de metadata incremental en 3 niveles para rastrear:
- Versiones de frameworks (global)
- Datasets y configuraciones base (por experimento)
- Seeds, modelos y overrides (por run individual)

Permite comparar runs, detectar cambios de dataset, y documentar condiciones de ejecucion sin duplicar info en cada run.

## Arquitectura de 3 Niveles

```
results/
├── .metadata/
│   └── environment.json              # Nivel 1: Versiones de frameworks
├── experiments/
│   ├── email_urgency.meta.json       # Nivel 2: Hash dataset, contador runs
│   └── metricas_optimizacion.csv     # (CSV master, no metadata)
└── runs/
    └── email_urgency_20260208_143022/
        ├── run.json                  # Nivel 3: Seed, modelos, timestamp
        ├── config_snapshot.yaml      # (Snapshot YAML completo)
        └── optimized_program.json    # (Artefactos de salida)
```

### Nivel 1: Environment (Global)

**Ubicacion:** `results/.metadata/environment.json`

**Frecuencia:** Se actualiza solo cuando cambian versiones de frameworks.

**Contenido:**
```json
{
  "frameworks": {
    "dspy": "2.5.3",
    "litellm": "1.52.15",
    "gepa": "0.1.0"
  },
  "updated_at": "2026-02-08T14:30:22"
}
```

**Comportamiento idempotente:** Si las versiones actuales coinciden con el archivo existente, no se reescribe.

### Nivel 2: Experiment (Por Caso de Uso)

**Ubicacion:** `results/experiments/<experiment_name>.meta.json`

**Frecuencia:** Se actualiza en cada run del experimento.

**Contenido:**
```json
{
  "experiment_name": "email_urgency",
  "dataset_hash": "a3f9b2c1d4e5f6...",
  "dataset_path": "/path/to/email_urgency.csv",
  "base_config": {
    "module_type": "dynamic",
    "optimization": {
      "max_metric_calls": 50,
      "predictor_type": "cot"
    }
  },
  "total_runs": 12,
  "created_at": "2026-02-01T10:00:00",
  "last_run_at": "2026-02-08T14:30:22",
  "dataset_hash_changed": true,
  "previous_dataset_hash": "b4e8c7a2f1..."
}
```

**Deteccion de cambios:** Si el SHA-256 del dataset CSV cambia entre runs, se marca `dataset_hash_changed: true` y se guarda el hash anterior.

### Nivel 3: Run (Individual)

**Ubicacion:** `results/runs/<run_dir>/run.json`

**Frecuencia:** Se crea una vez por run.

**Contenido:**
```json
{
  "experiment_name": "email_urgency",
  "seed": 1844674407,
  "models": {
    "task": {
      "model": "azure/gpt-4o",
      "temperature": 0.0,
      "max_tokens": 1000
    },
    "reflection": {
      "model": "azure/gpt-4o-mini",
      "temperature": 0.7,
      "max_tokens": 2000
    }
  },
  "created_at": "2026-02-08T14:30:22"
}
```

**Nota sobre seed:** El seed se registra para documentacion, pero **no se aplica** al LLM ni a GEPA internamente. La reproducibilidad depende de caches del LLM y condiciones de API.

## Uso de MetadataManager

### API Publica

```python
from shared.logging import MetadataManager, collect_model_info, generate_seed
from shared.paths import get_dspy_paths

# Inicializar
mgr = MetadataManager(get_dspy_paths().results)

# Generar seed (solo para registro)
seed = generate_seed()

# Nivel 1: Environment
mgr.ensure_environment()

# Nivel 2: Experiment
mgr.ensure_experiment(
    experiment_name="email_urgency",
    dataset_path=Path("datasets/email_urgency.csv"),
    base_config={
        "module_type": "dynamic",
        "optimization": {...}
    }
)

# Nivel 3: Run
mgr.create_run(
    run_dir=Path("results/runs/email_urgency_20260208_143022"),
    experiment_name="email_urgency",
    seed=seed,
    models=collect_model_info(task_config, reflection_config)
)
```

### Integracion Automatica

Los entry points principales (`reflexio_declarativa.py`, `universal_optimizer.py`) llaman automaticamente a `MetadataManager` en `save_results()`.

**No es necesario** llamar manualmente a menos que crees un nuevo entry point.

## Funciones Helper

### `generate_seed()`

```python
def generate_seed() -> int:
    """Genera un entero aleatorio para rastreo (no se aplica al LLM)."""
```

Rango: `0` a `2^31 - 1` (int32 maximo).

### `collect_model_info(task_config, reflection_config)`

```python
def collect_model_info(task_config, reflection_config) -> dict:
    """Extrae model, temperature, max_tokens de LLMConfig instances."""
```

Retorna dict con claves `"task"` y `"reflection"`, cada una con subcampos `model`, `temperature`, `max_tokens`.

## Relacion con Otros Artefactos

| Artefacto | Tipo | Proposito |
|-----------|------|-----------|
| `environment.json` | Metadata L1 | Versiones de frameworks |
| `<exp>.meta.json` | Metadata L2 | Hash dataset, contador |
| `run.json` | Metadata L3 | Seed, modelos, timestamp |
| `config_snapshot.yaml` | Config completo | YAML usado en el run |
| `metricas_optimizacion.csv` | Resultados | Scores, budget, modelo |
| `optimized_program.json` | Modelo DSPy | Prompt optimizado |

**Complementarios:** `run.json` **no reemplaza** `config_snapshot.yaml`. El YAML tiene configuracion completa, `run.json` tiene solo metadata de reproducibilidad.

## Limitaciones

1. **Seed no se aplica:** Solo se registra. LLMs pueden dar respuestas diferentes en runs consecutivos con mismo seed debido a caches, load balancing, y no-determinismo del servidor.

2. **Hash de dataset:** Detecta cambios binarios, no cambios semanticos (ej: reordenar filas da hash diferente aunque contenido sea equivalente).

3. **Versiones de frameworks:** Se lee via `importlib.metadata`. Si un framework no esta instalado, se marca `null`.

## Conciliacion historica (artefactos previos a la persistencia de run dirs)

Al conciliar `metricas_optimizacion.csv` contra los run dirs en disco
(2026-05-30) se detectaron filas cuyo `Run Directory` no existe. No es perdida
de datos: corresponden a corridas **anteriores a que existiera la persistencia
de artefactos por-run**. En esa etapa el sistema solo escribia la fila de scores
en el CSV; aun no se creaba el directorio de run con `results.json`/`run.json`.

**Corte temporal:**

- **GEPA:** 234 filas sin run dir, todas en el rango **2025-12-22 a 2026-01-12**
  (fase prototipo, anterior al primer commit del repo del 2026-02-07). Casos
  afectados: CV Extraction, Email Urgency, Text-to-SQL, RAG Optimization. Los
  scores sobreviven en el CSV; no hay prompts ni `results.json` por-run.
- **A partir de febrero 2026** (cuando ya existia git y, desde el `2026-05-17`
  con `save_run_artifacts`, la persistencia consolidada) **no falta ningun
  artefacto**: 100% de las filas tienen su run dir.
- **DSPy:** sin filas faltantes (rango 2026-02-06 en adelante).

**Implicancia:** las filas previas a ~2026-01-12 son legitimamente
**archivables** (conciliacion de scores: OK; auditoria de prompts: no disponible),
no candidatas a re-correr.

**Nota de portabilidad:** parte del CSV restaurado desde otra maquina guarda
`Run Directory` con separador Windows (`\`). Cualquier tooling que resuelva la
ruta de forma literal en Linux (incl. `seed_protocol.py` si une rutas) debe
normalizar `\`->`/` o matchear por basename. Ver `shared/utils/seed_protocol.py`.

## Casos de Uso

### Comparar dos runs del mismo experimento

```bash
# Ver metadata de run antiguo
cat results/runs/email_urgency_20260201_100000/run.json

# Ver metadata de run nuevo
cat results/runs/email_urgency_20260208_143022/run.json

# Comparar seeds, modelos, temperaturas
```

### Detectar si el dataset cambio

```bash
cat results/experiments/email_urgency.meta.json | jq '.dataset_hash_changed'
# true = dataset fue modificado entre runs
```

### Verificar versiones de frameworks

```bash
cat results/.metadata/environment.json
```

## Ver Tambien

- `docs/DSPY_ARTEFACTOS_SALIDA.md` - Persistencia de modulos DSPy (Prediction, JSON, Pickle)
- `docs/LLM_CONFIG.md` - Configuracion de modelos task/reflection
- `shared/logging/metadata.py` - Implementacion completa de `MetadataManager`
