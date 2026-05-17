#!/usr/bin/env bash
# Replica local del pipeline CI de GitHub Actions.
# Uso: ./shared/utils/ci_local.sh [--skip-security]
#
# Orden: lint -> security -> tests (igual que CI)

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

# --- Detectar Python/venv ---
if [[ -f ".venv/bin/python" ]]; then
    PYTHON=".venv/bin/python"
    VENV_BIN=".venv/bin"
else
    error "No se encontro .venv. Ejecuta: python -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

ERRORS=0

step_header() { echo -e "\n${BLUE}==== $* ====${NC}"; }

# ---- 1. LINT ----------------------------------------------------------------
step_header "LINT"

info "ruff check ..."
if "$VENV_BIN/ruff" check .; then
    ok "ruff check OK"
else
    error "ruff check FALLO"
    ERRORS=$((ERRORS + 1))
fi

info "ruff format --check ..."
if "$VENV_BIN/ruff" format --check .; then
    ok "ruff format OK"
else
    error "ruff format FALLO  (ejecuta: ruff format .)"
    ERRORS=$((ERRORS + 1))
fi

# ---- 2. SECURITY ------------------------------------------------------------
if [[ "$SKIP_SECURITY" == false ]]; then
    step_header "SECURITY"

    if ! command -v "$VENV_BIN/bandit" &>/dev/null; then
        warn "bandit no instalado. Ejecuta: pip install bandit pip-audit"
        SKIP_SECURITY=true
    fi
fi

if [[ "$SKIP_SECURITY" == false ]]; then
    info "bandit ..."
    if "$VENV_BIN/bandit" -r . \
        --exclude ./.venv,./tests,./docs \
        --severity-level medium \
        --confidence-level medium \
        -f txt; then
        ok "bandit OK"
    else
        error "bandit FALLO"
        ERRORS=$((ERRORS + 1))
    fi

    info "pip-audit ..."
    if "$VENV_BIN/pip-audit" -r requirements.txt --ignore-vuln CVE-2025-69872; then
        ok "pip-audit OK"
    else
        error "pip-audit FALLO"
        ERRORS=$((ERRORS + 1))
    fi
else
    warn "Security omitida (--skip-security)"
fi

# ---- 3. TESTS + COBERTURA ---------------------------------------------------
step_header "TESTS"

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

# ---- RESUMEN ----------------------------------------------------------------
echo ""
if [[ $ERRORS -eq 0 ]]; then
    ok "CI local PASO (0 errores)"
    exit 0
else
    error "CI local FALLO ($ERRORS paso(s) con error)"
    exit 1
fi
