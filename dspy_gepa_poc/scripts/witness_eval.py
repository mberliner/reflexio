"""Evalua el programa base de fast_gate (prompt pilot + few-shot, SIN GEPA) sobre
el set de casos testigo externo.

Uso (desde la raiz del repo):
    python -m dspy_gepa_poc.scripts.witness_eval
    LLM_MODEL_TASK=azure/gpt-4.1-mini python -m dspy_gepa_poc.scripts.witness_eval

Reconstruye el student tal como lo arma `ReflexioDeclarativa` (modulo dinamico +
`LabeledFewShot` desde el train), pero apuntando al CSV testigo
(`flujo_intents_fast_gate_witness.csv`). No optimiza con GEPA: mide la
generalizacion fuera de distribucion. Imprime esperado vs obtenido por caso y la
matriz de confusion. Hace llamadas reales al LLM (una por caso testigo).

NOTA: el modelo se lee de la `.env` del subproyecto; se puede sobreescribir solo
para esta corrida con `LLM_MODEL_TASK=...` inline (no toca la `.env`).
"""

import sys
from collections import Counter
from pathlib import Path

import dspy
import yaml
from dotenv import load_dotenv
from dspy.teleprompt import LabeledFewShot

from dspy_gepa_poc import CSVDataLoader, DynamicModuleFactory, LLMConfig

_CONFIG = (
    Path(__file__).resolve().parent.parent
    / "configs"
    / "flujo_intents_fast_gate_fewshot_rico_prompt_v1.yaml"
)
_WITNESS_CSV = "flujo_intents_fast_gate_witness.csv"


def run() -> int:
    cfg = yaml.safe_load(open(_CONFIG, encoding="utf-8"))
    project_dir = Path(__file__).resolve().parent.parent
    env_path = project_dir / ".env"
    load_dotenv(env_path if env_path.exists() else None)
    task = LLMConfig.from_env("task")
    dspy.configure(lm=task.get_dspy_lm())
    print(f"Task LM: {task.model}")

    sig = cfg["signature"]
    ptype = cfg["optimization"].get("predictor_type", "cot")
    module = DynamicModuleFactory.create_module(sig, predictor_type=ptype)

    loader = CSVDataLoader()
    train, _val, test = loader.load_dataset(filename=_WITNESS_CSV, input_keys=["ficha"])
    k = cfg["optimization"].get("few_shot_count", 8)
    student = LabeledFewShot(k=k).compile(module, trainset=train)
    print(f"few-shot k={k}; testigo n={len(test)}\n")

    conf: Counter = Counter()
    ok = 0
    print(f"{'caso':6} {'esperado':9} {'obtenido':9}  ok")
    print("-" * 40)
    for ex in test:
        pred = student(ficha=ex.ficha)
        exp = str(ex.clasificacion).strip()
        got = str(pred.clasificacion).strip()
        hit = exp == got
        ok += hit
        cid = getattr(ex, "case_id", "?")
        if not hit:
            conf[(exp, got)] += 1
        print(f"{cid:6} {exp:9} {got:9}  {'OK' if hit else 'X'}")
    print("-" * 40)
    print(f"\nAccuracy testigo: {ok}/{len(test)} = {ok / len(test):.1%}")
    if conf:
        print("Confusiones:")
        for (e, g), n in conf.most_common():
            print(f"  {e} -> {g}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
