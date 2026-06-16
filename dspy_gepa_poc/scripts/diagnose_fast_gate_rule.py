"""Diagnostico per-pregunta del fast_gate determinista (rule_derived) + dump auditable.

Corre el modulo rule_derived sobre un split y compara, por caso, cada pregunta
P1..P5 + alto_impacto predicha contra el gold, y el color derivado contra el gold.
Reporta accuracy por pregunta y matriz de confusion del color.

Ademas GUARDA un CSV auditable por ficha (gold vs pred de las 6 respuestas +
razonamiento + color) en `results/audits/`: es el artefacto que materializa la
trazabilidad de la arquitectura A (por que cada ficha recibio su color). El harness
de GEPA solo persiste prompts y scores agregados, no las respuestas por ejemplo.

Hace llamadas reales al LLM (una por caso). Uso (desde la raiz del repo):
    PYTHONUTF8=1 LLM_MODEL_TASK=azure/gpt-4.1-mini \
        python -m dspy_gepa_poc.scripts.diagnose_fast_gate_rule [--run-dir RUN] [--split test]

--run-dir: carga `optimized_program.json` de un run de GEPA para auditar el programa
optimizado (sin el flag, audita el programa base del YAML).
"""

import argparse
import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import dspy
import yaml
from dotenv import load_dotenv

from dspy_gepa_poc import CSVDataLoader, DynamicModuleFactory, LLMConfig
from dspy_gepa_poc.flujo_intents.ficha import _is_true
from shared.paths import get_dspy_paths

_CONFIG = (
    Path(__file__).resolve().parent.parent / "configs" / "flujo_intents_fast_gate_rule_v1.yaml"
)
_QUESTIONS = ("p1", "p2", "p3", "p4", "p5", "alto_impacto")
_DUMP_FIELDS = (*_QUESTIONS, "razonamiento", "clasificacion")


def run(run_dir: str | None = None, split: str = "test") -> int:
    cfg = yaml.safe_load(open(_CONFIG, encoding="utf-8"))
    project_dir = Path(__file__).resolve().parent.parent
    env_path = project_dir / ".env"
    load_dotenv(env_path if env_path.exists() else None)
    task = LLMConfig.from_env("task")
    dspy.configure(lm=task.get_dspy_lm())
    print(f"Task LM: {task.model}")

    sig = cfg["signature"]
    ptype = cfg["optimization"].get("predictor_type", "cot")
    student = DynamicModuleFactory.create_rule_derived_module(sig, predictor_type=ptype)
    if run_dir:
        prog = Path(run_dir) / "optimized_program.json"
        student.load(str(prog))
        print(f"Programa optimizado cargado: {prog}")
    print()

    loader = CSVDataLoader()
    train, val, test = loader.load_dataset(
        filename=cfg["data"]["csv_filename"], input_keys=["ficha"]
    )
    examples = {"train": train, "val": val, "test": test}[split]

    q_ok: Counter = Counter()
    color_ok = 0
    color_conf: Counter = Counter()
    dump_rows: list[dict[str, str]] = []

    print(f"{'caso':12}{'gold':9}{'pred':9}  {'preguntas mal'}")
    print("-" * 60)
    for ex in examples:
        pred = student(ficha=ex.ficha)
        cid = getattr(ex, "case_id", "?")
        gold_color = str(ex.clasificacion).strip()
        pred_color = str(pred.clasificacion).strip()
        color_ok += pred_color == gold_color
        if pred_color != gold_color:
            color_conf[(gold_color, pred_color)] += 1

        mal = []
        for q in _QUESTIONS:
            g = _is_true(getattr(ex, q, ""))
            p = _is_true(getattr(pred, q, ""))
            if g == p:
                q_ok[q] += 1
            else:
                mal.append(f"{q}(g={'Si' if g else 'No'},p={'Si' if p else 'No'})")
        flag = "" if pred_color == gold_color else "  <-- COLOR"
        print(f"{cid:12}{gold_color:9}{pred_color:9}  {', '.join(mal)}{flag}")

        row = {"case_id": cid, "ficha": ex.ficha}
        for field in _DUMP_FIELDS:
            row[f"gold_{field}"] = str(getattr(ex, field, "")).strip()
            row[f"pred_{field}"] = str(getattr(pred, field, "")).strip()
        row["color_ok"] = str(pred_color == gold_color)
        dump_rows.append(row)

    n = len(examples)
    print("-" * 60)
    print(f"\nAccuracy color: {color_ok}/{n} = {color_ok / n:.1%}")
    print("\nAccuracy por pregunta:")
    for q in _QUESTIONS:
        print(f"  {q:14} {q_ok[q]}/{n} = {q_ok[q] / n:.1%}")
    if color_conf:
        print("\nConfusiones de color (gold -> pred):")
        for (g, p), c in color_conf.most_common():
            print(f"  {g} -> {p}: {c}")

    audits_dir = get_dspy_paths().results / "audits"
    audits_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = "optimized" if run_dir else "base"
    out_path = audits_dir / f"fast_gate_rule_{tag}_{split}_{ts}.csv"
    cols = [
        "case_id",
        "color_ok",
        *[f"gold_{f}" for f in _DUMP_FIELDS],
        *[f"pred_{f}" for f in _DUMP_FIELDS],
        "ficha",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for r in dump_rows:
            writer.writerow({c: r.get(c, "") for c in cols})
    print(f"\n[audit] dump por-ficha guardado en: {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnostico + dump auditable de fast_gate")
    parser.add_argument("--run-dir", default=None, help="Run de GEPA: carga optimized_program.json")
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    args = parser.parse_args()
    return run(run_dir=args.run_dir, split=args.split)


if __name__ == "__main__":
    sys.exit(main())
