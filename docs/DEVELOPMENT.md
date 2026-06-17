# DEVELOPMENT — Setup, comandos y ejecucion

SSOT de como preparar el entorno, correr el proyecto localmente e invocar los
entry points. Si un comando no esta aqui, no es canonico.

## Requisitos

- Python >= 3.10 (minimo en `pyproject.toml`, `requires-python`); el CI corre en
  3.13. Con las dependencias de `requirements.txt` instaladas.
- Entorno virtual en `.venv/` (Unix: `.venv/bin/`, Windows: `.venv/Scripts/`).
  RECOMENDADO pero no obligatorio: el pipeline local detecta el `.venv` y, si no
  existe, cae al `python` del SO con un warning (ver `shared/utils/ci_local.sh`).
  El `.venv` se vuelve NECESARIO cuando el python del sistema no cumple los
  requisitos (es < 3.10 o le faltan las dependencias).
- Cada subproyecto (`dspy_gepa_poc/`, `gepa_standalone/`) tiene su propio `.env`
  para configuracion LLM independiente. Ver `docs/LLM_CONFIG.md`.

## Setup inicial

```bash
python -m venv .venv             # opcional; necesario si el python del SO no cumple
source .venv/bin/activate        # Unix/macOS
# .venv\Scripts\Activate.ps1     # Windows (PowerShell)
pip install -r requirements.txt
```

## Pipeline de verificacion local (OBLIGATORIO tras cualquier modificacion)

MUST: antes de dar por cerrado cualquier cambio de codigo, ejecutar el pipeline
local que replica el CI (orden `lint -> security -> tests`, mismos comandos y
cobertura minima 85%):

```bash
./shared/utils/ci_local.sh                 # CI local completo (lint + security + tests)
./shared/utils/ci_local.sh --skip-security # Variante rapida (omite bandit + pip-audit)
```

En Windows invocarlo via git-bash; el script detecta `.venv/Scripts/python.exe` y,
si no hay venv, usa el python del SO. Pasar el CI local equivale a pasar
`.github/workflows/ci.yml`. MUST NOT sustituirlo por `pytest`/`ruff check` sueltos:
eso omite `ruff format --check`, la fase de security y el umbral de cobertura.

## Comandos sueltos (uso puntual)

```bash
pytest tests/ -v                 # suite completa (segundos)
ruff check .                     # Lint (config en pyproject.toml)
ruff format --check .            # Formato (lo valida el CI; suele olvidarse)
./run_demo.sh --check            # Validar entorno sin ejecutar experimentos
./run_demo.sh gepa               # Demo GEPA standalone
./run_demo.sh dspy               # Demo DSPy + GEPA
```

## Invocacion de entry points

MUST: los entry points se ejecutan SIEMPRE como modulos (`python -m`) desde la
raiz del repo. Esto evita hacks de `sys.path` y mantiene `dspy_gepa_poc/` y
`gepa_standalone/` como paquetes hermanos independientes que comparten `shared/`.

```bash
# Desde la raiz del repo:
python -m gepa_standalone.universal_optimizer --config gepa_standalone/experiments/configs/<caso>.yaml
python -m dspy_gepa_poc.reflexio_declarativa  --config dspy_gepa_poc/configs/<caso>.yaml
python -m dspy_gepa_poc.scripts.dryrun_config --config <yaml>
python -m dspy_gepa_poc.scripts.baseline_only --config <yaml>
python -m shared.utils.check_deployments
```

MUST NOT invocar directamente como `python gepa_standalone/universal_optimizer.py`:
Python pondria el directorio del script en `sys.path` y `import shared` fallaria.
Los shell scripts del repo (`run_demo.sh`, `run_cv_cases.sh`, etc.) ya invocan con
`python -m` desde la raiz.

- Punto de entrada GEPA: `python -m gepa_standalone.universal_optimizer --config <yaml>`.
- Punto de entrada DSPy: `python -m dspy_gepa_poc.reflexio_declarativa --config <yaml>`
  (`--config` es obligatorio).

## Fast Gate determinista (rule_derived): auditoria y regeneracion de datos

La etapa fast_gate de flujo-intents usa `module.type: rule_derived` (ver
`docs/ARCHITECTURE.md` y `YAML_CONFIG_REFERENCE.md`): el LLM responde 5 preguntas
Si/No + `alto_impacto` y `derive_color` deriva el color. Scripts asociados:

```bash
# Regenerar el dataset: anotar P1..P5+alto_impacto en train/val (desde make_variations)
# y en el test (desde fast_gate_v1.csv). Idempotente.
python -m dspy_gepa_poc.flujo_intents.make_variations          # reescribe variations/*_var.csv
python -m dspy_gepa_poc.scripts.enrich_fast_gate_questions     # puebla el CSV de la etapa

# Diagnostico per-pregunta + DUMP AUDITABLE por-ficha (gold vs pred de las 6
# respuestas + color). Hace llamadas LLM (una por caso).
PYTHONUTF8=1 LLM_MODEL_TASK=azure/gpt-4.1-mini \
  python -m dspy_gepa_poc.scripts.diagnose_fast_gate_rule [--run-dir <run>] [--split test]
```

- Sin `--run-dir` audita el programa base del YAML y escribe el dump en
  `results/audits/`; con `--run-dir <results/runs/...>` carga
  `optimized_program.json` y escribe el dump dentro del run dir.
- El dump RE-EJECUTA el LLM (GEPA no guarda predicciones por-ejemplo): cada corrida
  puede variar por la varianza del LLM (temp 0.1). Para congelar las predicciones
  dentro del run, usar `optimization.save_predictions: true` (deja
  `predictions_{test,val}.csv` en el run dir).
- `gold` sale del dataset (`flujo_intents_fast_gate.csv`); `pred` del LLM con el prompt
  del run elegido. Detalle del caso en `historial/sdd.md` (D-013) y `SPEC-102`.

## Flujo de trabajo tipico (nueva tarea)

Todo es declarativo: una tarea nueva NO requiere escribir codigo Python, solo
dataset + config YAML.

1. Crear el dataset CSV con columna `split` (`train`/`val`/`test`) en
   `dspy_gepa_poc/datasets/` o `gepa_standalone/experiments/datasets/`.
2. Crear el config YAML del caso: en `dspy_gepa_poc/configs/` (modulo `dynamic` o
   `pipeline`, con la `signature` definida en el YAML) o en
   `gepa_standalone/experiments/configs/` (mas el prompt JSON inicial en
   `experiments/prompts/`). Referencia de campos: `docs/YAML_CONFIG_REFERENCE.md`.
3. Validar sin gastar tokens (lado DSPy):
   `python -m dspy_gepa_poc.scripts.dryrun_config --config <yaml>`.
4. Medir el baseline antes de optimizar:
   `python -m dspy_gepa_poc.scripts.baseline_only --config <yaml>`.
5. Correr la optimizacion con el entry point del subproyecto (ver arriba) y
   analizar resultados con `./analyze leaderboard` (`docs/ANALISIS_UTILIDADES.md`).
   Para validar mejoras con N seeds, ver `docs/PROTOCOLO_N_SEEDS.md`.

## CI

`.github/workflows/ci.yml` ejecuta lint (`ruff check` + `ruff format --check`),
security (`bandit` + `pip-audit`) y tests con cobertura en cada push/PR. La
replica local es `./shared/utils/ci_local.sh` (ver arriba).
