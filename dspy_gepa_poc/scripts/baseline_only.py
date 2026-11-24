"""Evalua el prompt baseline (sin optimizar con GEPA) sobre val y test.

Uso (desde la raiz del repo):
    python -m dspy_gepa_poc.scripts.baseline_only --config <ruta_yaml>

Util para medir el punto de partida antes de invertir tokens en GEPA.
Reutiliza ReflexioDeclarativa.setup_models / load_data / create_module_and_metric
y luego ejecuta solo dspy.evaluate.Evaluate (sin optimizacion).
"""

import argparse
import sys
from pathlib import Path

from dspy.evaluate import Evaluate

from dspy_gepa_poc.call_failures import run_evaluate
from dspy_gepa_poc.reflexio_declarativa import ReflexioDeclarativa
from shared.display import (
    log_error,
    log_info,
    log_warn,
    print_header,
    print_kv,
    print_section,
)
from shared.display.formatting import format_metric_line
from shared.llm import RunAborted, get_failure_tracker
from shared.scoring import MetricSummary, summarize


def _evaluate(evaluator, student) -> MetricSummary:
    """Baseline sobre sus casos evaluados, con `n_evaluados/n_total` (SPEC-104 FR-003)."""
    result = run_evaluate(evaluator, student)
    summary = summarize([ReflexioDeclarativa.case_results(result)])
    # FR-006: tras cada paso se consulta el estado del contador.
    get_failure_tracker().check_abort()
    return summary


def run_baseline(config_path: Path) -> int:
    orchestrator = ReflexioDeclarativa(str(config_path))
    try:
        return _run_baseline(orchestrator)
    except RunAborted as e:
        # SPEC-104 FR-006: corrida abortada por el contador de fallas.
        get_failure_tracker().flush_abort()
        log_error(orchestrator.abort_message(e))
        return 1


def _run_baseline(orchestrator: ReflexioDeclarativa) -> int:
    orchestrator.setup_models()
    orchestrator.load_data()
    orchestrator.create_module_and_metric()

    case_name = orchestrator.config.raw_config["case"]["name"]
    print_header(f"[DSPY+GEPA / BASELINE-ONLY] {case_name}")
    log_info(f"Command: {' '.join(sys.argv)}")

    num_threads = orchestrator.config.raw_config.get("optimization", {}).get("num_threads", 1)

    print_section("BASELINE EN VAL SET")
    log_info(f"Evaluando prompt inicial sobre {len(orchestrator.valset)} ejemplos de val...")
    evaluator_val = Evaluate(
        devset=orchestrator.valset,
        metric=orchestrator.metric,
        num_threads=num_threads,
        display_progress=True,
    )
    baseline_val = _evaluate(evaluator_val, orchestrator.student)
    print_kv("Baseline VAL", format_metric_line(baseline_val, 0.0))

    print_section("BASELINE EN TEST SET")
    if not orchestrator.testset:
        log_warn("Test set vacio, salteando.")
        return 0

    log_info(f"Evaluando prompt inicial sobre {len(orchestrator.testset)} ejemplos de test...")
    evaluator_test = Evaluate(
        devset=orchestrator.testset,
        metric=orchestrator.metric,
        num_threads=num_threads,
        display_progress=True,
    )
    baseline_test = _evaluate(evaluator_test, orchestrator.student)
    print_kv("Baseline TEST", format_metric_line(baseline_test, 0.0))

    print_section("RESUMEN")
    print_kv("Val", f"{baseline_val.format_score()} ({baseline_val.ratio_label()})")
    print_kv("Test", f"{baseline_test.format_score()} ({baseline_test.ratio_label()})")
    log_info("Resultados NO se guardan en results/ (modo baseline-only).")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Evaluar baseline sin GEPA.")
    parser.add_argument("--config", required=True, help="Ruta al YAML de configuracion")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        log_error(f"config no existe: {config_path}")
        sys.exit(1)

    sys.exit(run_baseline(config_path))


if __name__ == "__main__":
    main()
