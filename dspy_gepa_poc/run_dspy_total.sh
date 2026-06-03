#!/bin/bash
#
# Script para ejecutar pruebas de DSPy POC
# Itera sobre todos los archivos YAML de configuracion en configs/
# Limpia cache de DSPy antes de cada ejecucion
#

set -e

# Salida en orden y en tiempo real cuando stdout NO es una terminal (p.ej.
# ./run_dspy_total.sh > log 2>&1 o | tee). Conviven dos buffers distintos:
#   1) Python bufferea su stdout -> se cubre con PYTHONUNBUFFERED.
#   2) El propio shell bufferea por bloque los 'echo' de las cabeceras -> sin
#      esto las cabeceras salen tarde, intercaladas con el log de litellm.
# Re-ejecutamos bajo 'stdbuf -oL' para forzar line-buffering del shell.
export PYTHONUNBUFFERED=1
if [ -z "${_RUN_LINEBUF:-}" ] && command -v stdbuf >/dev/null 2>&1; then
    export _RUN_LINEBUF=1
    exec stdbuf -oL -eL bash "$0" "$@"
fi

# ==============================================================================
# CONFIGURACION
# ==============================================================================

# Numero de veces que se ejecutara cada configuracion YAML (valor por defecto;
# se puede sobrescribir interactivamente al inicio)
DEFAULT_NUM_RUNS=5

# Rutas absolutas (independientes del directorio desde el que se invoque)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Helper multiplataforma para evitar suspension/hibernacion durante el batch.
source "$REPO_ROOT/shared/utils/keep_awake.sh"

# Directorio de configuraciones
CONFIGS_DIR="$SCRIPT_DIR/configs"

# ==============================================================================
# FUNCIONES
# ==============================================================================

# Ejecuta un programa Python nativo de Windows bajo mintty (Git Bash) a traves
# de winpty, que le da un pty real. Sin esto, el puente pipe de Git Bash
# reordena/retiene la salida de python.exe y la mezcla con los echo del shell:
# las lineas se pisan (texto garabateado). Solo se aplica cuando stdout es una
# terminal interactiva; si esta redirigido a archivo/pipe se ejecuta directo
# (winpty romperia la redireccion y ahi la salida ya sale ordenada).
run_py() {
    if [ -t 1 ] && command -v winpty >/dev/null 2>&1; then
        winpty "$@"
    else
        "$@"
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

    # Ejecutar prueba (cache deshabilitado via config: cache: false; no hay
    # cache en disco que limpiar, ver get_dspy_lm en shared/llm/config.py).
    echo ">>> Ejecutando prueba"
    echo "    Comando: python -m dspy_gepa_poc.reflexio_declarativa --config $config_file"
    echo ""
    echo "--- INICIO OUTPUT PRUEBA ---"
    local exit_code=0
    (cd "$REPO_ROOT" && run_py python -m dspy_gepa_poc.reflexio_declarativa --config "$config_file") || exit_code=$?
    echo "--- FIN OUTPUT PRUEBA ---"
    echo ""
    return $exit_code
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
echo "    - Dir configs:      $CONFIGS_DIR"
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

# Seleccion interactiva de configuraciones a ejecutar
echo "  Seleccione las configuraciones a ejecutar."
echo "  Indique los numeros separados por espacio o coma (ej: 1 3 4),"
echo "  o deje vacio / escriba 'all' para ejecutar todas."
read -r -p "  Seleccion [all]: " seleccion

selected_files=()
if [ -z "$seleccion" ] || [ "$seleccion" = "all" ] || [ "$seleccion" = "todos" ]; then
    selected_files=("${yaml_files[@]}")
else
    # Normalizar comas a espacios y recorrer cada token
    for token in ${seleccion//,/ }; do
        if ! [[ "$token" =~ ^[0-9]+$ ]] || [ "$token" -lt 1 ] || [ "$token" -gt ${#yaml_files[@]} ]; then
            echo "ERROR: Seleccion invalida: '$token' (rango valido: 1-${#yaml_files[@]})"
            exit 1
        fi
        selected_files+=("${yaml_files[$((token - 1))]}")
    done
fi

if [ ${#selected_files[@]} -eq 0 ]; then
    echo "ERROR: No se selecciono ninguna configuracion"
    exit 1
fi
echo ""

# Numero de runs por configuracion
read -r -p "  Numero de runs por config [$DEFAULT_NUM_RUNS]: " num_runs_input
NUM_RUNS="${num_runs_input:-$DEFAULT_NUM_RUNS}"
if ! [[ "$NUM_RUNS" =~ ^[0-9]+$ ]] || [ "$NUM_RUNS" -lt 1 ]; then
    echo "ERROR: El numero de runs debe ser un entero positivo (recibido: '$NUM_RUNS')"
    exit 1
fi
echo ""

# Resumen de la seleccion
echo "  Seleccion confirmada:"
echo "    - Configs a ejecutar: ${#selected_files[@]}"
for f in "${selected_files[@]}"; do
    echo "        - $(basename "$f")"
done
echo "    - Runs por config:    $NUM_RUNS"
echo ""

# Contadores
total_tests=$((${#selected_files[@]} * NUM_RUNS))
current_test=0
failed_tests=0
failed_list=()

echo "  Total de pruebas a ejecutar: $total_tests"
echo ""
echo "=============================================="
echo "  Iniciando ejecucion..."
echo "=============================================="

# Evitar que la PC entre en suspension/hibernacion durante las pruebas.
keep_awake_start
trap keep_awake_stop EXIT INT TERM

# Loop principal
for ((run=1; run<=NUM_RUNS; run++)); do
    for config_file in "${selected_files[@]}"; do
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
