#!/bin/bash
#
# Script para ejecutar pruebas de DSPy POC
# Itera sobre todos los archivos YAML de configuracion en configs/
# Limpia cache de DSPy antes de cada ejecucion
#

set -e

# ==============================================================================
# CONFIGURACION
# ==============================================================================

# Numero de veces que se ejecutara cada configuracion YAML
NUM_RUNS=5

# Directorio de configuraciones
CONFIGS_DIR="$(dirname "$0")/configs"

# Cache de DSPy
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

    # Paso 1: Limpiar cache
    echo ">>> PASO 1: Limpiando cache de DSPy"
    limpiar_cache_dspy
    echo ""

    # Paso 2: Ejecutar prueba
    echo ">>> PASO 2: Ejecutando prueba"
    echo "    Comando: python reflexio_declarativa.py --config $config_file"
    echo ""
    echo "--- INICIO OUTPUT PRUEBA ---"
    python "$(dirname "$0")/reflexio_declarativa.py" --config "$config_file"
    echo "--- FIN OUTPUT PRUEBA ---"
    echo ""
}

# ==============================================================================
# MAIN
# ==============================================================================

clear
echo "=============================================="
echo "        DSPy POC Test Runner"
echo "=============================================="
echo ""
echo "  Configuracion:"
echo "    - Runs por config:  $NUM_RUNS"
echo "    - Dir configs:      $CONFIGS_DIR"
echo "    - Cache DSPy:       $DSPY_CACHE_DIR"
echo ""

# Verificar que existe el directorio de configs
if [ ! -d "$CONFIGS_DIR" ]; then
    echo "ERROR: No se encuentra el directorio de configs: $CONFIGS_DIR"
    exit 1
fi

# Obtener lista de archivos YAML
yaml_files=($(ls "$CONFIGS_DIR"/*.yaml 2>/dev/null))

if [ ${#yaml_files[@]} -eq 0 ]; then
    echo "ERROR: No se encontraron archivos YAML en $CONFIGS_DIR"
    exit 1
fi

echo "  Archivos YAML encontrados: ${#yaml_files[@]}"
echo ""
idx=1
for f in "${yaml_files[@]}"; do
    echo "    [$idx] $(basename "$f")"
    idx=$((idx + 1))
done
echo ""

# Contadores
total_tests=$((${#yaml_files[@]} * NUM_RUNS))
current_test=0
failed_tests=0
failed_list=()

echo "  Total de pruebas a ejecutar: $total_tests"
echo ""
echo "=============================================="
echo "  Iniciando ejecucion..."
echo "=============================================="

# Loop principal
for ((run=1; run<=NUM_RUNS; run++)); do
    for config_file in "${yaml_files[@]}"; do
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
    echo "  Todas las pruebas completadas exitosamente!"
    echo ""
fi
