#!/bin/bash
#
# Comparacion Email Urgency: DSPy vs GEPA Standalone
#
# Ejecuta las dos variantes (zero-shot y few-shot) del caso Email Urgency
# para comparar con los resultados existentes de gepa_standalone.
#

set -e

# ==============================================================================
# CONFIGURACION
# ==============================================================================

NUM_RUNS=15

SCRIPT_DIR="$(dirname "$0")"
CONFIGS=(
    "$SCRIPT_DIR/configs/dynamic_email_urgency.yaml"
    "$SCRIPT_DIR/configs/dynamic_email_urgency_fewshot.yaml"
)

DSPY_CACHE_DIR="$HOME/.dspy_cache"

# ==============================================================================
# FUNCIONES
# ==============================================================================

limpiar_cache_dspy() {
    if [ -d "$DSPY_CACHE_DIR" ]; then
        echo "    [CACHE] Limpiando: $DSPY_CACHE_DIR"
        rm -rf "$DSPY_CACHE_DIR"/*
    else
        echo "    [CACHE] No existe, nada que limpiar"
    fi
}

ejecutar_prueba() {
    local config_file="$1"
    local run_num="$2"
    local total_runs="$3"
    local test_num="$4"
    local total_tests="$5"
    local config_name=$(basename "$config_file" .yaml)

    echo ""
    echo "##############################################################################"
    echo "#"
    echo "#  PRUEBA $test_num de $total_tests"
    echo "#"
    echo "#  Archivo:    $config_name.yaml"
    echo "#  Iteracion:  $run_num de $total_runs"
    echo "#  Ruta:       $config_file"
    echo "#"
    echo "##############################################################################"
    echo ""

    echo ">>> PASO 1: Limpiando cache de DSPy"
    limpiar_cache_dspy
    echo ""

    echo ">>> PASO 2: Ejecutando prueba"
    echo "    Comando: python reflexio_declarativa.py --config $config_file"
    echo ""
    echo "--- INICIO OUTPUT PRUEBA ---"
    python "$SCRIPT_DIR/reflexio_declarativa.py" --config "$config_file"
    echo "--- FIN OUTPUT PRUEBA ---"
    echo ""
}

# ==============================================================================
# MAIN
# ==============================================================================

clear
echo "=============================================="
echo "  Email Urgency: DSPy vs Standalone"
echo "=============================================="
echo ""
echo "  Configuracion:"
echo "    - Runs por config:  $NUM_RUNS"
echo "    - Cache DSPy:       $DSPY_CACHE_DIR"
echo ""
echo "  Configs a ejecutar:"
for f in "${CONFIGS[@]}"; do
    echo "    - $(basename "$f")"
done
echo ""

# Verificar que existen los configs
for config_file in "${CONFIGS[@]}"; do
    if [ ! -f "$config_file" ]; then
        echo "ERROR: Config no encontrado: $config_file"
        exit 1
    fi
done

total_tests=$(( ${#CONFIGS[@]} * NUM_RUNS ))
current_test=0
failed_tests=0
failed_list=()

echo "  Total de pruebas: $total_tests"
echo ""
echo "=============================================="
echo "  Iniciando ejecucion..."
echo "=============================================="

for ((run=1; run<=NUM_RUNS; run++)); do
    for config_file in "${CONFIGS[@]}"; do
        current_test=$((current_test + 1))
        config_name=$(basename "$config_file" .yaml)

        if ejecutar_prueba "$config_file" "$run" "$NUM_RUNS" "$current_test" "$total_tests"; then
            echo ">>> RESULTADO: OK"
        else
            echo ">>> RESULTADO: FALLO"
            failed_tests=$((failed_tests + 1))
            failed_list+=("$config_name (run $run)")
        fi
    done
done

# Resumen final
echo ""
echo "##############################################################################"
echo "#"
echo "#                         RESUMEN FINAL"
echo "#"
echo "##############################################################################"
echo ""
echo "  Total de pruebas ejecutadas: $total_tests"
echo "  Exitosas:                    $((total_tests - failed_tests))"
echo "  Fallidas:                    $failed_tests"
echo ""

if [ $failed_tests -gt 0 ]; then
    echo "  Pruebas fallidas:"
    for failed in "${failed_list[@]}"; do
        echo "    - $failed"
    done
    echo ""
    exit 1
else
    echo "  Todas las pruebas completadas!"
    echo ""
    echo "  Para ver resultados comparados:"
    echo "    ./analyze leaderboard"
    echo ""
fi
