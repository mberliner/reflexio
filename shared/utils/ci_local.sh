#!/usr/bin/env bash
# Replica local del pipeline CI de GitHub Actions.
# Uso: ./shared/utils/ci_local.sh [--skip-security]
#
# Orden: lint -> security -> tests (igual que CI)
#
# Un paso obligatorio que no puede correr (herramienta no instalada) cuenta como
# error: el pipeline nunca termina en "PASO" sin haber corrido todos los pasos.
# La unica omision admitida es --skip-security, explicita, y el resumen la marca
# como PASO PARCIAL.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

SKIP_SECURITY=false
for arg in "$@"; do
    [[ "$arg" == "--skip-security" ]] && SKIP_SECURITY=true
done

# --- Detectar Python: venv (Unix o Windows) o python del SO ---
if [[ -f ".venv/bin/python" ]]; then
    PYTHON=".venv/bin/python"          # venv Unix/macOS
elif [[ -f ".venv/Scripts/python.exe" ]]; then
    PYTHON=".venv/Scripts/python.exe"  # venv Windows
elif command -v python &>/dev/null; then
    PYTHON="python"                    # fallback: python del SO
    warn "No se encontro .venv; usando python del sistema ($(command -v python))"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
    warn "No se encontro .venv; usando python3 del sistema ($(command -v python3))"
else
    error "No se encontro .venv ni python en el SO. Instala Python o crea el venv: python -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

# Todas las herramientas se invocan como "python -m <tool>" para funcionar
# tanto con venv como con el interprete del SO.

ERRORS=0

step_header() { echo -e "\n${BLUE}==== $* ====${NC}"; }

# require_tool <modulo> <argumento de pip install>: 0 si el modulo esta
# instalado; si falta, registra el error (el paso no corrio) y devuelve 1.
require_tool() {
    if "$PYTHON" -m "$1" --version &>/dev/null; then
        return 0
    fi
    error "$1 no instalado: el paso NO corrio. Ejecuta: $PYTHON -m pip install $2"
    ERRORS=$((ERRORS + 1))
    return 1
}

# ---- 1. LINT ----------------------------------------------------------------
step_header "LINT"

if require_tool ruff "-r requirements.txt"; then
    info "ruff check ..."
    if "$PYTHON" -m ruff check .; then
        ok "ruff check OK"
    else
        error "ruff check FALLO"
        ERRORS=$((ERRORS + 1))
    fi

    info "ruff format --check ..."
    if "$PYTHON" -m ruff format --check .; then
        ok "ruff format OK"
    else
        error "ruff format FALLO  (ejecuta: ruff format .)"
        ERRORS=$((ERRORS + 1))
    fi
fi

# ---- 2. SECURITY ------------------------------------------------------------
if [[ "$SKIP_SECURITY" == false ]]; then
    step_header "SECURITY"

    if require_tool bandit bandit; then
        info "bandit ..."
        if "$PYTHON" -m bandit -r . \
            --exclude ./.venv,./tests,./docs \
            --severity-level medium \
            --confidence-level medium \
            -f txt; then
            ok "bandit OK"
        else
            error "bandit FALLO"
            ERRORS=$((ERRORS + 1))
        fi
    fi

    if require_tool pip_audit pip-audit; then
        info "pip-audit ..."
        if "$PYTHON" -m pip_audit -r requirements.txt --ignore-vuln CVE-2025-69872; then
            ok "pip-audit OK"
        else
            error "pip-audit FALLO"
            ERRORS=$((ERRORS + 1))
        fi
    fi
else
    warn "Security omitida a pedido (--skip-security): no equivale al CI completo"
fi

# ---- 3. TESTS + COBERTURA ---------------------------------------------------
step_header "TESTS"

if require_tool pytest "-r requirements.txt" && require_tool coverage "-r requirements.txt"; then
    info "pytest con cobertura ..."
    if "$PYTHON" -m pytest tests/ -v \
        --cov=shared/llm --cov=shared/validation --cov=shared/paths \
        --cov-fail-under=85 \
        --cov-report=term-missing; then
        ok "tests OK"
    else
        error "tests FALLARON"
        ERRORS=$((ERRORS + 1))
    fi
fi

# ---- RESUMEN ----------------------------------------------------------------
echo ""
if [[ $ERRORS -ne 0 ]]; then
    error "CI local FALLO ($ERRORS paso(s) con error)"
    exit 1
elif [[ "$SKIP_SECURITY" == true ]]; then
    warn "CI local PASO PARCIAL (0 errores; security omitida con --skip-security)"
    exit 0
else
    ok "CI local PASO (0 errores)"
    exit 0
fi
