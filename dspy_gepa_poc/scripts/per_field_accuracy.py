"""Evalua un run optimizado calculando accuracy por campo sobre val y test.

Uso (desde la raiz del repo):
    python -m dspy_gepa_poc.scripts.per_field_accuracy --run-dir <ruta_run>

El script carga `config_snapshot.yaml` + `optimized_program.json` de un run,
ejecuta inferencia sobre val + test, y muestra el score promedio por campo
(usando los `field_configs` de la metrica con feedback). Sirve para detectar
en que campos vive el error residual y decidir si conviene `ignore_in_metric`
o suavizar el comparador de un campo concreto.

NOTA: hace llamadas reales al LLM (una por ejemplo de val + test).
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import dspy
import yaml
from dotenv import load_dotenv

from dspy_gepa_poc import CSVDataLoader, DynamicModuleFactory, LLMConfig
from dspy_gepa_poc.metrics import _score_field


def _resolve_eval_fields(raw_config: dict) -> tuple[list[str], dict, dict]:
    """Devuelve (eval_fields, field_configs_resueltos, defaults)."""
    sig = raw_config["signature"]
    outputs = [o["name"] for o in sig["outputs"]]
    opt = raw_config.get("optimization", {})
    ignored = set(opt.get("ignore_in_metric", []))
    eval_fields = [f for f in outputs if f not in ignored]

    raw_fc = opt.get("field_configs", {}) or {}
    default_mode = opt.get("match_mode", "normalized")
    if default_mode == "exact":
        # Mantener paridad con reflexio_declarativa: default elevado a normalized
        # cuando se usa feedback metric.
        default_mode = "normalized"
    defaults = {
        "mode": default_mode,
        "fuzzy_threshold": opt.get("fuzzy_threshold", 0.85),
        "separators": ",;",
    }

    field_cfg = {}
    for f in eval_fields:
        cfg = dict(defaults)
        if f in raw_fc:
            cfg.update(raw_fc[f])
        field_cfg[f] = cfg

    return eval_fields, field_cfg, defaults


def evaluate(run_dir: Path) -> int:
    print("=" * 70)
    print(f"PER-FIELD ACCURACY: {run_dir.name}")
    print("=" * 70)

    config_path = run_dir / "config_snapshot.yaml"
    model_path = run_dir / "optimized_program.json"
    if not config_path.exists() or not model_path.exists():
        print(f"[ERROR] Faltan artefactos en {run_dir}", file=sys.stderr)
        return 1

    with open(config_path, encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    # LLM
    project_dir = Path(__file__).resolve().parent.parent
    env_path = project_dir / ".env"
    load_dotenv(env_path if env_path.exists() else None)
    task_config = LLMConfig.from_env("task")
    dspy.configure(lm=task_config.get_dspy_lm())
    print(f"  Task LM: {task_config.model}")

    # Module
    sig = raw_config["signature"]
    predictor_type = raw_config.get("optimization", {}).get("predictor_type", "cot")
    module = DynamicModuleFactory.create_module(sig, predictor_type=predictor_type)
    module.load(str(model_path))

    # Dataset
    data_cfg = raw_config["data"]
    input_keys = data_cfg.get("input_columns") or [data_cfg["input_column"]]
    if not isinstance(input_keys, list):
        input_keys = [input_keys]
    loader = CSVDataLoader()
    _, val, test = loader.load_dataset(filename=data_cfg["csv_filename"], input_keys=input_keys)

    eval_fields, field_cfg, defaults = _resolve_eval_fields(raw_config)
    print(f"  Eval fields ({len(eval_fields)}): {eval_fields}")
    print(f"  Default mode: {defaults['mode']}")

    for split_name, split in [("VAL", val), ("TEST", test)]:
        if not split:
            print(f"\n[{split_name}] vacio, salteando.")
            continue
        print(f"\n[{split_name}] {len(split)} ejemplos. Ejecutando inferencia...")
        sums: dict[str, float] = defaultdict(float)
        perfects: dict[str, int] = defaultdict(int)
        examples_by_field: dict[str, list[tuple[str, str]]] = defaultdict(list)

        for i, ex in enumerate(split, 1):
            try:
                pred = module(**{k: getattr(ex, k) for k in input_keys})
            except Exception as exc:
                print(f"    [WARN] ejemplo {i} fallo: {exc}")
                continue
            for f in eval_fields:
                cfg = field_cfg[f]
                exp = getattr(ex, f, "")
                act = getattr(pred, f, "")
                score, diag = _score_field(
                    exp, act, cfg["mode"], cfg["fuzzy_threshold"], cfg["separators"]
                )
                sums[f] += score
                if score == 1.0:
                    perfects[f] += 1
                elif len(examples_by_field[f]) < 3:
                    examples_by_field[f].append((str(exp)[:80], str(act)[:80]))

        n = len(split)
        print(f"\n  {'campo':25s} {'mode':12s} {'avg':>7s} {'perfect':>10s}")
        print("  " + "-" * 60)
        rows = []
        for f in eval_fields:
            avg = sums[f] / n
            rows.append((f, field_cfg[f]["mode"], avg, perfects[f], n))
        rows.sort(key=lambda r: r[2])  # peor primero
        for f, mode, avg, p, total in rows:
            print(f"  {f:25s} {mode:12s} {avg:>6.1%} {p:>5d}/{total}")

        # Mostrar 3 ejemplos de fallo para los 3 peores campos
        print("\n  Top 3 fallos (campos peor evaluados):")
        for f, mode, avg, _p, _total in rows[:3]:
            if not examples_by_field[f]:
                continue
            print(f"  [{f} - {mode} - avg {avg:.1%}]")
            for exp, act in examples_by_field[f]:
                print(f"    esperado: {exp!r}")
                print(f"    obtenido: {act!r}")
                print()

    return 0


def main():
    p = argparse.ArgumentParser(description="Accuracy por campo de un run optimizado.")
    p.add_argument("--run-dir", required=True, help="Ruta al directorio del run")
    args = p.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        print(f"Error: no existe {run_dir}", file=sys.stderr)
        sys.exit(1)
    sys.exit(evaluate(run_dir))


if __name__ == "__main__":
    main()
