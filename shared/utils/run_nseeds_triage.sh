#!/bin/bash
#
# Runner de triaje para el protocolo de N seeds.
# Muestra el tablero de casos (clasificados por resultados previos y
# prerequisitos) y delega en shared.utils.seed_triage la seleccion interactiva
# y el lanzamiento de seed_protocol sobre los casos elegidos.
#
# Es un wrapper fino: toda la logica (diagnostico, criterios de "duda",
# verificacion de prerequisitos, seleccion) vive en Python y esta testeada en
# tests/test_seed_triage.py. Capacidad: SPEC-101-triaje-casos-nseeds.
#
# Uso:
#   ./shared/utils/run_nseeds_triage.sh           # tablero + seleccion + corrida
#   ./shared/utils/run_nseeds_triage.sh --list     # solo tablero
#   LLM_MODEL_TASK=azure/gpt-5-mini ./shared/utils/run_nseeds_triage.sh
#

set -e

# Salida ordenada cuando stdout NO es terminal (igual que run_demos_gepa.sh).
export PYTHONUNBUFFERED=1
export PYTHONUTF8=1
if [ -z "${_RUN_LINEBUF:-}" ] && command -v stdbuf >/dev/null 2>&1; then
    export _RUN_LINEBUF=1
    exec stdbuf -oL -eL bash "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Python: venv (Unix o Windows) o python del SO (misma deteccion que ci_local.sh).
if [ -f "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON="$REPO_ROOT/.venv/bin/python"
elif [ -f "$REPO_ROOT/.venv/Scripts/python.exe" ]; then
    PYTHON="$REPO_ROOT/.venv/Scripts/python.exe"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
else
    PYTHON="python3"
fi

# winpty da un pty real a python.exe nativo bajo mintty cuando stdout es terminal
# (sin esto la seleccion interactiva con input() puede no verse). Si esta
# redirigido, se ejecuta directo.
cd "$REPO_ROOT"
if [ -t 1 ] && command -v winpty >/dev/null 2>&1; then
    winpty "$PYTHON" -m shared.utils.seed_triage "$@"
else
    "$PYTHON" -m shared.utils.seed_triage "$@"
fi
