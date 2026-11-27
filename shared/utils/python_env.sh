#!/usr/bin/env bash
#
# Helper compartido por los runners (run_*.sh): resuelve el Python del .venv del
# repo y verifica el entorno ANTES de lanzar nada.
#
# Por que existe: invocar `python` a secas usa el del PATH, que puede ser un
# interprete global con otras versiones (p.ej. dspy 3.2.1 sin `dspy.lm15`). El
# batch fallaba en cada corrida con un ModuleNotFoundError. Aqui el fallo es
# inmediato, unico y claro, y detiene el runner.
#
# Uso (desde un runner, con REPO_ROOT definido):
#   source "$REPO_ROOT/shared/utils/python_env.sh"
#   python_env_require "$REPO_ROOT"     # fija $PYTHON o aborta con exit 1
#
# No hay fallback al python del sistema (a diferencia de ci_local.sh, que es un
# pipeline y avisa): un batch de pruebas con costo LLM MUST correr en el entorno
# alineado con requirements.txt.
#
# Variables:
#   SKIP_ENV_CHECK=1   omite solo el chequeo de dependencias (no la deteccion
#                      del .venv). Util si ya se verifico a mano.

python_env_die() {
    echo "" >&2
    echo "[ERROR] $1" >&2
    shift
    for line in "$@"; do
        echo "        $line" >&2
    done
    echo "" >&2
    exit 1
}

python_env_require() {
    local repo_root="$1"

    if [ -f "$repo_root/.venv/Scripts/python.exe" ]; then
        PYTHON="$repo_root/.venv/Scripts/python.exe"
    elif [ -f "$repo_root/.venv/bin/python" ]; then
        PYTHON="$repo_root/.venv/bin/python"
    else
        python_env_die "No se encontro el entorno virtual en $repo_root/.venv" \
            "El batch no usa el python del sistema para no correr con versiones distintas a requirements.txt." \
            "Crear el entorno:" \
            "  python -m venv .venv" \
            "  .venv/Scripts/python.exe -m pip install -r requirements.txt   (Windows)" \
            "  .venv/bin/python -m pip install -r requirements.txt           (Unix/macOS)"
    fi
    export PYTHON

    if [ "${SKIP_ENV_CHECK:-0}" = "1" ]; then
        echo "[ENV] chequeo de dependencias omitido (SKIP_ENV_CHECK=1); python: $PYTHON"
        return 0
    fi

    # check_env_deps compara el entorno con requirements.txt (pins, transitivas,
    # imports y huerfanos): sale !=0 con el detalle de lo que no alinea.
    local out
    if ! out="$(cd "$repo_root" && "$PYTHON" -m shared.utils.check_env_deps 2>&1)"; then
        # Primero lo que rompe corridas (pin/transitiva/import); los huerfanos
        # son ruido para este diagnostico y solo se cuentan.
        local relevant orphans
        relevant="$(printf '%s\n' "$out" | grep -v -E '^\s*- huerfano:' || true)"
        orphans="$(printf '%s\n' "$out" | grep -c -E '^\s*- huerfano:' || true)"
        echo "" >&2
        echo "[ERROR] El entorno de $PYTHON no coincide con requirements.txt." >&2
        printf '%s\n' "$relevant" | head -n 15 | sed 's/^/        /' >&2
        if [ "${orphans:-0}" -gt 0 ]; then
            echo "        (+ $orphans paquetes huerfanos; detalle: $PYTHON -m shared.utils.check_env_deps)" >&2
        fi
        python_env_die "Corrida cancelada antes de ejecutar pruebas." \
            "Alinear el entorno:  $PYTHON -m pip install -r requirements.txt" \
            "(o SKIP_ENV_CHECK=1 para omitir este chequeo bajo tu responsabilidad)"
    fi
    echo "[ENV] python: $PYTHON (alineado con requirements.txt)"
}
