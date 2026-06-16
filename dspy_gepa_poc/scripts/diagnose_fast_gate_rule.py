"""Diagnostico per-pregunta del fast_gate determinista (rule_derived) sobre el test.

Corre el modulo rule_derived (sin few-shot ni GEPA) sobre el split=test y compara,
por caso, cada pregunta P1..P5 + alto_impacto predicha contra el gold, y el color
derivado contra el gold. Reporta accuracy por pregunta, matriz de confusion del color
y, para cada error de color, que preguntas difirieron (la causa del fallo).

Hace llamadas reales al LLM (una por caso de test). Uso (desde la raiz del repo):
    PYTHONUTF8=1 LLM_MODEL_TASK=azure/gpt-4.1-mini \
        python -m dspy_gepa_poc.scripts.diagnose_fast_gate_rule
"""

import sys
from collections import Counter
from pathlib import Path

import dspy
import yaml
from dotenv import load_dotenv

from dspy_gepa_poc import CSVDataLoader, DynamicModuleFactory, LLMConfig
from dspy_gepa_poc.flujo_intents.ficha import _is_true

_CONFIG = (
    Path(__file__).resolve().parent.parent / "configs" / "flujo_intents_fast_gate_rule_v1.yaml"
)
_QUESTIONS = ("p1", "p2", "p3", "p4", "p5", "alto_impacto")


def run() -> int:
    cfg = yaml.safe_load(open(_CONFIG, encoding="utf-8"))
    project_dir = Path(__file__).resolve().parent.parent
    env_path = project_dir / ".env"
    load_dotenv(env_path if env_path.exists() else None)
    task = LLMConfig.from_env("task")
    dspy.configure(lm=task.get_dspy_lm())
    print(f"Task LM: {task.model}\n")

    sig = cfg["signature"]
    ptype = cfg["optimization"].get("predictor_type", "cot")
    student = DynamicModuleFactory.create_rule_derived_module(sig, predictor_type=ptype)

    loader = CSVDataLoader()
    _train, _val, test = loader.load_dataset(
        filename=cfg["data"]["csv_filename"], input_keys=["ficha"]
    )

    q_ok = Counter()
    color_ok = 0
    color_conf: Counter = Counter()
    error_lines: list[str] = []

    print(f"{'caso':12}{'gold':9}{'pred':9}  {'preguntas mal'}")
    print("-" * 60)
    for ex in test:
        pred = student(ficha=ex.ficha)
        cid = getattr(ex, "case_id", "?")
        gold_color = str(ex.clasificacion).strip()
        pred_color = str(pred.clasificacion).strip()
        if pred_color == gold_color:
            color_ok += 1
        else:
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
        line = f"{cid:12}{gold_color:9}{pred_color:9}  {', '.join(mal)}{flag}"
        print(line)
        if pred_color != gold_color:
            error_lines.append(line)

    n = len(test)
    print("-" * 60)
    print(f"\nAccuracy color: {color_ok}/{n} = {color_ok / n:.1%}")
    print("\nAccuracy por pregunta:")
    for q in _QUESTIONS:
        print(f"  {q:14} {q_ok[q]}/{n} = {q_ok[q] / n:.1%}")
    if color_conf:
        print("\nConfusiones de color (gold -> pred):")
        for (g, p), c in color_conf.most_common():
            print(f"  {g} -> {p}: {c}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
