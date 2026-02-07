#!/bin/bash

# --- CONFIGURACIÓN ---
# Define cuántas veces quieres que se ejecuten los demos
NUM_RUNS=10
OPTIMIZER=./universal_optimizer.py
CONFIG_DIR=./experiments/configs

# Configuraciones a ejecutar
CONFIGS=(
    "email_urgency.yaml"
    "cv_extraction.yaml"
    "text_to_sql.yaml"
)

TITLES=(
    "Email Urgency Classification"
    "CV Data Extraction"
    "Text-to-SQL Generation"
)

# ---------------------

echo "Iniciando ejecución de GEPA Universal Optimizer ($NUM_RUNS iteraciones)..."

for i in $(seq 1 $NUM_RUNS)
do
    echo ""
    echo "############################################################"
    echo "  ITERACIÓN $i de $NUM_RUNS"
    echo "############################################################"
    echo ""

    for idx in "${!CONFIGS[@]}"
    do
        CONFIG="${CONFIGS[$idx]}"
        TITLE="${TITLES[$idx]}"

        echo ">>> Ejecutando iteracion $i - ${TITLE}..."
        python $OPTIMIZER --config $CONFIG_DIR/$CONFIG

        if [ $? -ne 0 ]; then
            echo "ERROR: Falló la ejecución de ${CONFIG}"
            exit 1
        fi

        echo ""
    done

    echo "Iteración $i finalizada con éxito."
done

echo ""
echo "Todas las ejecuciones han terminado."
