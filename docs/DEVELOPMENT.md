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

## Flujo de trabajo tipico (nueva tarea)

1. Definir/modificar una `Signature` en `dspy_gepa_poc/modules.py`.
2. Crear un `Module` en `dspy_gepa_poc/modules.py` que use la `Signature`.
3. Crear datos de ejemplo en `dspy_gepa_poc/data.py`.
4. Definir una metrica en `dspy_gepa_poc/metrics.py`.
5. Crear un script en `examples/` que use los componentes para ejecutar la tarea
   o un flujo de optimizacion.

## CI

`.github/workflows/ci.yml` ejecuta lint (`ruff check` + `ruff format --check`),
security (`bandit` + `pip-audit`) y tests con cobertura en cada push/PR. La
replica local es `./shared/utils/ci_local.sh` (ver arriba).
