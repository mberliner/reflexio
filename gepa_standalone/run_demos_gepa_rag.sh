#!/bin/bash

# --- CONFIGURACIÓN ---
# Define cuántas veces quieres que se ejecuten los demos
NUM_RUNS=7
CONFIG_DIR=gepa_standalone/experiments/configs
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# ---------------------

echo "Iniciando ejecución de GEPA RAG Optimizer ($NUM_RUNS iteraciones)..."

for i in $(seq 1 $NUM_RUNS)
do
    echo ""
    echo "############################################################"
    echo "  ITERACIÓN $i de $NUM_RUNS"
    echo "############################################################"
    echo ""

    echo ">>> Ejecutando iteracion $i - RAG Optimization..."
    (cd "$SCRIPT_DIR" && python -m gepa_standalone.universal_optimizer --config "$CONFIG_DIR/rag_optimization.yaml")

    if [ $? -ne 0 ]; then
        echo "ERROR: Falló la ejecución de rag_optimization.yaml"
        exit 1
    fi

    echo ""
    echo "Iteración $i finalizada con éxito."
done

echo ""
echo "Todas las ejecuciones han terminado."
