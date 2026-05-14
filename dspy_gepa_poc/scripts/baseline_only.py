"""Evalua el prompt baseline (sin optimizar con GEPA) sobre val y test.

Uso:
    python dspy_gepa_poc/scripts/baseline_only.py --config <ruta_yaml>

Util para medir el punto de partida antes de invertir tokens en GEPA.
Reutiliza ReflexioDeclarativa.setup_models / load_data / create_module_and_metric
y luego ejecuta solo dspy.evaluate.Evaluate (sin optimizacion).
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dspy.evaluate import Evaluate  # noqa: E402

from dspy_gepa_poc.reflexio_declarativa import ReflexioDeclarativa  # noqa: E402
from shared.display import print_header, print_section  # noqa: E402


def run_baseline(config_path: Path) -> int:
    orchestrator = ReflexioDeclarativa(str(config_path))
    orchestrator.setup_models()
    orchestrator.load_data()
    orchestrator.create_module_and_metric()

    case_name = orchestrator.config.raw_config["case"]["name"]
    print_header(f"BASELINE ONLY: {case_name}")

    num_threads = orchestrator.config.raw_config.get("optimization", {}).get("num_threads", 1)

    print_section("BASELINE EN VAL SET")
    print(f">> Evaluando prompt inicial sobre {len(orchestrator.valset)} ejemplos de val...")
    evaluator_val = Evaluate(
        devset=orchestrator.valset,
        metric=orchestrator.metric,
        num_threads=num_threads,
        display_progress=True,
    )
    baseline_val = ReflexioDeclarativa._to_float_score(evaluator_val(orchestrator.student))
    print(f"\n>>> Baseline VAL: {ReflexioDeclarativa._format_score(baseline_val)}")

    print_section("BASELINE EN TEST SET")
    if not orchestrator.testset:
        print("Test set vacio, salteando.")
        return 0

    print(f">> Evaluando prompt inicial sobre {len(orchestrator.testset)} ejemplos de test...")
    evaluator_test = Evaluate(
        devset=orchestrator.testset,
        metric=orchestrator.metric,
        num_threads=num_threads,
        display_progress=True,
    )
    baseline_test = ReflexioDeclarativa._to_float_score(evaluator_test(orchestrator.student))
    print(f"\n>>> Baseline TEST: {ReflexioDeclarativa._format_score(baseline_test)}")

    print_section("RESUMEN")
    print(f"Val:  {ReflexioDeclarativa._format_score(baseline_val)}")
    print(f"Test: {ReflexioDeclarativa._format_score(baseline_test)}")
    print("\nResultados NO se guardan en results/ (modo baseline-only).")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Evaluar baseline sin GEPA.")
    parser.add_argument("--config", required=True, help="Ruta al YAML de configuracion")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(f"Error: config no existe: {config_path}", file=sys.stderr)
        sys.exit(1)

    sys.exit(run_baseline(config_path))


if __name__ == "__main__":
    main()
