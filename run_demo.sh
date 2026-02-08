#!/usr/bin/env bash
# Onboarding demo: ejecuta un experimento de email_urgency de punta a punta
# Uso:
#   ./run_demo.sh gepa       # Ejecuta GEPA standalone
#   ./run_demo.sh dspy       # Ejecuta DSPy + GEPA
#   ./run_demo.sh            # Ejecuta ambos
#   ./run_demo.sh --check    # Solo valida entorno, sin ejecutar

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Colores ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC} $*" >&2; }
ok()    { echo -e "${GREEN}[OK]${NC} $*" >&2; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*" >&2; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# --- Validaciones generales ---

check_python() {
    if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
        error "Python no encontrado. Instala Python >= 3.10"
        exit 1
    fi

    local py_cmd
    py_cmd=$(command -v python3 || command -v python)

    local py_version
    py_version=$("$py_cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    local major minor
    major=$(echo "$py_version" | cut -d. -f1)
    minor=$(echo "$py_version" | cut -d. -f2)

    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 10 ]; }; then
        error "Python >= 3.10 requerido (encontrado: $py_version)"
        exit 1
    fi
    ok "Python $py_version"
    echo "$py_cmd"
}

check_dependencies() {
    local py_cmd="$1"
    local project="$2"
    local missing=()

    if [ "$project" = "gepa" ] || [ "$project" = "both" ]; then
        if ! "$py_cmd" -c "import gepa" &>/dev/null; then
            missing+=("gepa")
        fi
    fi

    if [ "$project" = "dspy" ] || [ "$project" = "both" ]; then
        if ! "$py_cmd" -c "import dspy" &>/dev/null; then
            missing+=("dspy")
        fi
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        error "Dependencias faltantes: ${missing[*]}"
        echo "  Instala con: pip install ${missing[*]}" >&2
        echo "  O usando el entorno virtual: source .venv/bin/activate" >&2
        exit 1
    fi
    ok "Dependencias instaladas"
}

check_env() {
    local project_dir="$1"
    local project_name="$2"

    if [ -n "${LLM_API_KEY:-}" ]; then
        ok "LLM_API_KEY seteada en entorno"
        return 0
    fi

    if [ -f "$project_dir/.env" ]; then
        # Verificar que no tenga el placeholder por defecto
        if grep -q "your-api-key-here" "$project_dir/.env"; then
            error "LLM_API_KEY en $project_name/.env tiene el valor placeholder"
            echo "  Edita $project_dir/.env y configura tu API key" >&2
            exit 1
        fi
        ok "Archivo .env encontrado en $project_name/"
        return 0
    fi

    error "No se encontro LLM_API_KEY ni archivo .env en $project_name/"
    echo "  Opcion 1: export LLM_API_KEY=tu-api-key" >&2
    echo "  Opcion 2: cp $project_dir/.env.example $project_dir/.env && editar con tu key" >&2
    exit 1
}

# --- Validacion de archivos de entrada ---

check_gepa_files() {
    local base="$SCRIPT_DIR/gepa_standalone/experiments"
    local files=(
        "$base/configs/email_urgency.yaml"
        "$base/datasets/email_urgency.csv"
        "$base/prompts/email_urgency_v1.json"
    )
    for f in "${files[@]}"; do
        if [ ! -f "$f" ]; then
            error "Archivo faltante: $f"
            exit 1
        fi
    done
    ok "Archivos GEPA verificados (${#files[@]}/${#files[@]})"
}

check_dspy_files() {
    local files=(
        "$SCRIPT_DIR/dspy_gepa_poc/configs/dynamic_email_urgency.yaml"
        "$SCRIPT_DIR/dspy_gepa_poc/datasets/email_urgency.csv"
    )
    for f in "${files[@]}"; do
        if [ ! -f "$f" ]; then
            error "Archivo faltante: $f"
            exit 1
        fi
    done
    ok "Archivos DSPy verificados (${#files[@]}/${#files[@]})"
}

# --- Ejecucion ---

run_gepa() {
    local py_cmd="$1"

    echo ""
    info "=== GEPA Standalone: email_urgency ==="
    echo ""

    check_env "$SCRIPT_DIR/gepa_standalone" "gepa_standalone"
    check_gepa_files

    info "Ejecutando optimizacion GEPA..."
    echo ""

    (cd "$SCRIPT_DIR" && "$py_cmd" gepa_standalone/universal_optimizer.py \
        --config gepa_standalone/experiments/configs/email_urgency.yaml)

    echo ""
    ok "GEPA standalone completado"
}

run_dspy() {
    local py_cmd="$1"

    echo ""
    info "=== DSPy + GEPA: email_urgency ==="
    echo ""

    check_env "$SCRIPT_DIR/dspy_gepa_poc" "dspy_gepa_poc"
    check_dspy_files

    info "Ejecutando optimizacion DSPy + GEPA..."
    echo ""

    (cd "$SCRIPT_DIR" && "$py_cmd" dspy_gepa_poc/reflexio_declarativa.py \
        --config dspy_gepa_poc/configs/dynamic_email_urgency.yaml)

    echo ""
    ok "DSPy + GEPA completado"
}

# --- Main ---

main() {
    local mode="${1:-both}"
    local check_only=false

    # Manejar flags antes de validaciones
    case "$mode" in
        -h|--help)
            echo "Uso: $0 [gepa|dspy|both|--check]"
            echo ""
            echo "  gepa      Ejecuta GEPA standalone con email_urgency"
            echo "  dspy      Ejecuta DSPy + GEPA con email_urgency"
            echo "  both      Ejecuta ambos (default)"
            echo "  --check   Solo valida entorno, sin ejecutar"
            echo ""
            echo "Requisitos:"
            echo "  - Python >= 3.10 con dependencias instaladas"
            echo "  - LLM_API_KEY configurada (variable de entorno o .env)"
            echo "  - Ver docs/LLM_CONFIG.md para configuracion de modelos"
            exit 0
            ;;
        --check)
            check_only=true
            mode="both"
            ;;
        gepa|dspy|both) ;;
        *)
            error "Modo desconocido: $mode"
            echo "Uso: $0 [gepa|dspy|both|--check]" >&2
            exit 1
            ;;
    esac

    echo ""
    info "Reflexio Dicta - Demo de onboarding"
    info "Experimento: email_urgency (clasificador de urgencia, 3 clases)"
    echo ""

    # Validaciones generales
    local py_cmd
    py_cmd=$(check_python)

    check_dependencies "$py_cmd" "$mode"

    if [ "$check_only" = true ]; then
        # Solo validar archivos y .env de ambos proyectos
        echo ""
        info "=== GEPA Standalone: email_urgency ==="
        echo ""
        check_env "$SCRIPT_DIR/gepa_standalone" "gepa_standalone"
        check_gepa_files

        echo ""
        info "=== DSPy + GEPA: email_urgency ==="
        echo ""
        check_env "$SCRIPT_DIR/dspy_gepa_poc" "dspy_gepa_poc"
        check_dspy_files

        echo ""
        ok "Validacion completa. Entorno listo para ejecutar."
        return 0
    fi

    case "$mode" in
        gepa)
            run_gepa "$py_cmd"
            ;;
        dspy)
            run_dspy "$py_cmd"
            ;;
        both)
            run_gepa "$py_cmd"
            run_dspy "$py_cmd"
            ;;
    esac

    echo ""
    info "=== Resumen ==="
    echo ""
    case "$mode" in
        gepa)
            echo "  Resultados GEPA: gepa_standalone/results/"
            ;;
        dspy)
            echo "  Resultados DSPy: dspy_gepa_poc/results/"
            ;;
        both)
            echo "  Resultados GEPA: gepa_standalone/results/"
            echo "  Resultados DSPy: dspy_gepa_poc/results/"
            ;;
    esac
    echo ""
    echo "  Para ver el leaderboard: ./analyze leaderboard"
    echo ""
    ok "Demo completada"
}

main "$@"
