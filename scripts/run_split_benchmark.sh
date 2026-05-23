#!/usr/bin/env bash
# Benchmark de los casos segmentados triage_v1 y fast_gate_v1.
# Por cada subproblema corre N iteraciones; en cada iteracion lanza GEPA
# standalone y DSPy EN PARALELO (prefijando la salida por motor) y guarda logs.
# Subproblemas secuenciales entre si (triage primero, fast_gate despues).
#
# Uso (desde la raiz del repo):
#   bash scripts/run_split_benchmark.sh
#   N=5 bash scripts/run_split_benchmark.sh   # override de iteraciones

set -u
# pipefail: el exit code de "python | sed | tee" toma el de tee (siempre 0)
# si no se activa; con pipefail, propaga el primer fallo de la pipeline ->
# wait $pid captura el rc real del python, no del tee.
set -o pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$REPO_ROOT/scripts/benchmark_logs"
mkdir -p "$LOG_DIR"
cd "$REPO_ROOT"

N="${N:-3}"

run_case() {
    local case_name="$1" gepa_config="$2" dspy_config="$3"
    echo ""
    echo "########################################################"
    echo "# Caso: $case_name  (N=$N)"
    echo "########################################################"
    for i in $(seq 1 "$N"); do
        local ts gepa_log dspy_log gepa_pid dspy_pid gepa_rc dspy_rc gepa_status dspy_status
        ts="$(date +%Y%m%d_%H%M%S)"
        gepa_log="$LOG_DIR/${case_name}_gepa_run${i}_${ts}.log"
        dspy_log="$LOG_DIR/${case_name}_dspy_run${i}_${ts}.log"
        echo ""
        echo "=== $case_name iteracion $i / $N ==="

        ( python -u -m gepa_standalone.universal_optimizer --config "$gepa_config" 2>&1 \
            | sed -u 's/^/[GEPA] /' | tee "$gepa_log" ) &
        gepa_pid=$!

        ( python -u -m dspy_gepa_poc.reflexio_declarativa --config "$dspy_config" 2>&1 \
            | sed -u 's/^/[DSPY] /' | tee "$dspy_log" ) &
        dspy_pid=$!

        wait "$gepa_pid"; gepa_rc=$?
        wait "$dspy_pid"; dspy_rc=$?

        gepa_status=$([ "$gepa_rc" -eq 0 ] && echo "OK" || echo "FAIL($gepa_rc)")
        dspy_status=$([ "$dspy_rc" -eq 0 ] && echo "OK" || echo "FAIL($dspy_rc)")
        echo "=== $case_name iteracion $i: GEPA=$gepa_status | DSPy=$dspy_status ==="
    done
}

run_case "triage_v1" \
    "gepa_standalone/experiments/configs/triage_v1.yaml" \
    "dspy_gepa_poc/configs/triage_v1.yaml"

run_case "fast_gate_v1" \
    "gepa_standalone/experiments/configs/fast_gate_v1.yaml" \
    "dspy_gepa_poc/configs/fast_gate_v1.yaml"

echo ""
echo "=== Listo. Inspeccionar metricas en: ==="
echo "  gepa_standalone/results/experiments/metricas_optimizacion.csv"
echo "  dspy_gepa_poc/results/experiments/metricas_optimizacion.csv"
