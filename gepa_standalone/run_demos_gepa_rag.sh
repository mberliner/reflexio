#!/bin/bash

# --- CONFIGURACIÓN ---
# Define cuántas veces quieres que se ejecuten los demos
NUM_RUNS=7
HOME_PRUEBA=./gepa_standalone/demos

# ---------------------

echo "Iniciando ejecución de demos de GEPA ($NUM_RUNS iteraciones)..."

for i in $(seq 1 $NUM_RUNS)
do
    echo ""
    echo "############################################################"
    echo "  ITERACIÓN $i de $NUM_RUNS"
    echo "############################################################"
    echo ""

    echo ">>> Ejecutando iteracion $i - Demo 4: RAG..."
    python $HOME_PRUEBA/demo4_rag_optimization.py

    echo ""
    echo "Iteración $i finalizada con éxito."
done

echo ""
echo "Todas las ejecuciones han terminado."
