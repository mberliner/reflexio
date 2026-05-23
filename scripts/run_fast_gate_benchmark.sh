#!/usr/bin/env bash
# Corre 3 iteraciones del benchmark Fast Gate.
# En cada iteracion lanza GEPA standalone y DSPy pipeline EN PARALELO
# y muestra la salida en pantalla (prefijada por motor) mientras tambien
# la guarda en logs.
#
# Uso (desde la raiz del repo):
#   bash scripts/run_fast_gate_benchmark.sh

set -u
# pipefail: el exit code de "python | sed | tee" toma el de tee (siempre 0)
# si no se activa; con pipefail, propaga el primer fallo de la pipeline →
# wait $pid captura el rc real del python, no del tee.
set -o pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$REPO_ROOT/scripts/benchmark_logs"
mkdir -p "$LOG_DIR"

GEPA_CONFIG="gepa_standalone/experiments/configs/fast_gate.yaml"
DSPY_CONFIG="dspy_gepa_poc/configs/intake_pipeline.yaml"

cd "$REPO_ROOT"

for i in 1 2 3; do
    ts="$(date +%Y%m%d_%H%M%S)"
    gepa_log="$LOG_DIR/gepa_run${i}_${ts}.log"
    dspy_log="$LOG_DIR/dspy_run${i}_${ts}.log"

    echo ""
    echo "=== Iteracion $i / 3 (logs: $LOG_DIR) ==="

    # Cada proceso: prefija sus lineas con [GEPA]/[DSPY] y tee a pantalla + log
    ( python -u -m gepa_standalone.universal_optimizer --config "$GEPA_CONFIG" 2>&1 \
        | sed -u 's/^/[GEPA] /' | tee "$gepa_log" ) &
    gepa_pid=$!

    ( python -u -m dspy_gepa_poc.reflexio_declarativa --config "$DSPY_CONFIG" 2>&1 \
        | sed -u 's/^/[DSPY] /' | tee "$dspy_log" ) &
    dspy_pid=$!

    wait "$gepa_pid"; gepa_rc=$?
    wait "$dspy_pid"; dspy_rc=$?

    gepa_status=$([ "$gepa_rc" -eq 0 ] && echo "OK" || echo "FAIL($gepa_rc)")
    dspy_status=$([ "$dspy_rc" -eq 0 ] && echo "OK" || echo "FAIL($dspy_rc)")
    echo "=== Iteracion $i: GEPA=$gepa_status | DSPy=$dspy_status ==="
done

echo ""
echo "=== Listo. Inspeccionar metricas en: ==="
echo "  gepa_standalone/results/experiments/metricas_optimizacion.csv"
echo "  dspy_gepa_poc/results/experiments/metricas_optimizacion.csv"
