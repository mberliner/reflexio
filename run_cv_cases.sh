#!/usr/bin/env bash
set -euo pipefail

RUNS=10
JOBS=${JOBS:-4}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --jobs|-j)
            if [[ $# -lt 2 ]]; then
                echo "Error: --jobs requiere un entero positivo." >&2
                exit 1
            fi
            value="$2"
            if ! [[ "$value" =~ ^[0-9]+$ ]] || (( value <= 0 )); then
                echo "Error: --jobs debe recibir un entero positivo." >&2
                exit 1
            fi
            JOBS="$value"
            shift 2
            ;;
        *)
            echo "Uso: $0 [--jobs N]" >&2
            exit 1
            ;;
    esac
done
CONFIGS=(
    "dspy_gepa_poc/configs/dynamic_cv_profile.yaml"
    "dspy_gepa_poc/configs/dynamic_cv_triage.yaml"
)

for config in "${CONFIGS[@]}"; do
    echo "=== Caso: $config ==="
    running=0

    for i in $(seq 1 $RUNS); do
        echo "--- Run $i/$RUNS (config: $config) ---"

        (
            echo "[config:$config][run:$i] inicio"
            python dspy_gepa_poc/reflexio_declarativa.py --config "$config"
            echo "[config:$config][run:$i] fin"
        ) &

        running=$((running + 1))
        if (( running >= JOBS )); then
            wait -n
            running=$((running - 1))
        fi
    done

    wait
done

echo "Completado: $RUNS runs x ${#CONFIGS[@]} casos."
