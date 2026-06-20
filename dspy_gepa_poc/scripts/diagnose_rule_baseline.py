"""Diagnostico por-caso del baseline rule_derived de fast_gate (SIN GEPA).

Para D-017: identifica QUE casos del val y del test falla el modelo y POR QUE
juicio (p1..p5 / alto_impacto), para sembrar un VAL representativo del TEST.

Uso (desde la raiz del repo):
    python -m dspy_gepa_poc.scripts.diagnose_rule_baseline --config <ruta_yaml>
    python -m dspy_gepa_poc.scripts.diagnose_rule_baseline --config <yaml> --splits test
    LLM_MODEL_TASK=azure/gpt-4.1-mini python -m dspy_gepa_poc.scripts.diagnose_rule_baseline \
        --config <yaml>

Reutiliza ReflexioDeclarativa (mismo student rule_derived + few-shot que la corrida
real, SIN optimizar con GEPA). Para cada caso imprime esperado vs obtenido (color
derivado) y, cuando falla, los juicios p1..p5/alto_impacto gold vs pred. Cierra con
la matriz de confusion y el accuracy por split. Hace llamadas reales al LLM
(una por caso, x N repeticiones).

NOTA: el modelo se lee de la .env del subproyecto; sobreescribir solo para esta
corrida con LLM_MODEL_TASK=... inline (no toca la .env).
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

from dspy_gepa_poc.reflexio_declarativa import ReflexioDeclarativa
from shared.display import log_info, print_header, print_section

_FIELDS = ("p1", "p2", "p3", "p4", "p5", "alto_impacto")


def _diagnose_split(student, dataset, split_name: str, repeats: int) -> tuple[int, int]:
    """Evalua un split por caso. Devuelve (aciertos_acumulados, total_evaluado)."""
    print_section(f"SPLIT {split_name.upper()} (n={len(dataset)}, repeats={repeats})")
    conf: Counter = Counter()
    ok_total = 0
    n_total = 0
    # Para detectar inestabilidad de muestreo: cuenta aciertos por caso sobre repeats.
    per_case_ok: dict[str, int] = {}
    # Diagnostico aislado de alto_impacto SOLO donde decide el color (gold P5=Si:
    # Negro = P5 y alto). ai_conf cuenta sub-escala (si->no) y sobre-escala (no->si).
    ai_ok = 0
    ai_total = 0
    ai_conf: Counter = Counter()
    print(f"{'caso':12} {'esperado':9} {'obtenido':9}  ok   (juicios pred si difieren del gold)")
    print("-" * 90)
    for ex in dataset:
        cid = getattr(ex, "case_id", "?")
        exp = str(ex.clasificacion).strip()
        p5_gold = str(getattr(ex, "p5", "") or "").strip().lower()
        ai_gold = str(getattr(ex, "alto_impacto", "") or "").strip().lower()
        for _ in range(repeats):
            pred = student(ficha=ex.ficha)
            got = str(pred.clasificacion).strip()
            hit = exp == got
            ok_total += hit
            n_total += 1
            per_case_ok[cid] = per_case_ok.get(cid, 0) + int(hit)
            if p5_gold == "si":
                ai_pred = str(getattr(pred, "alto_impacto", "") or "").strip().lower()
                ai_ok += ai_gold == ai_pred
                ai_total += 1
                if ai_gold != ai_pred:
                    ai_conf[(ai_gold, ai_pred)] += 1
            if not hit:
                conf[(exp, got)] += 1
                diffs = []
                for f in _FIELDS:
                    gold = str(getattr(ex, f, "") or "").strip().lower()
                    pv = str(getattr(pred, f, "") or "").strip().lower()
                    if gold and gold != pv:
                        diffs.append(f"{f}:{gold}->{pv}")
                detail = "  " + ", ".join(diffs) if diffs else ""
                print(f"{cid:12} {exp:9} {got:9}  X {detail}")
    print("-" * 90)
    acc = ok_total / n_total if n_total else 0.0
    print(f"Accuracy {split_name} (color): {ok_total}/{n_total} = {acc:.1%}")
    # Casos inestables (ni 0 ni full): senal de muestreo, no de criterio.
    if repeats > 1:
        unstable = [c for c, k in per_case_ok.items() if 0 < k < repeats]
        if unstable:
            print(f"Casos inestables entre repeats ({len(unstable)}): {sorted(unstable)}")
    if conf:
        print("Confusiones color (esperado -> obtenido):")
        for (e, g), n in conf.most_common():
            print(f"  {e} -> {g}: {n}")
    # Reporte aislado de alto_impacto (donde decide Negro vs Rojo).
    if ai_total:
        ai_acc = ai_ok / ai_total
        print(
            f"\nalto_impacto sobre casos P5=Si (decide Negro/Rojo): "
            f"{ai_ok}/{ai_total} = {ai_acc:.1%}"
        )
        for (g, p), n in ai_conf.most_common():
            etiqueta = "sub-escala (Negro->Rojo)" if g == "si" else "sobre-escala (Rojo->Negro)"
            print(f"  alto {g}->{p}: {n}  [{etiqueta}]")
    return ok_total, n_total


def run(config_path: Path, splits: list[str], repeats: int) -> int:
    orchestrator = ReflexioDeclarativa(str(config_path))
    orchestrator.setup_models()
    orchestrator.load_data()
    orchestrator.create_module_and_metric()

    case_name = orchestrator.config.raw_config["case"]["name"]
    print_header(f"[DIAGNOSTICO BASELINE rule_derived] {case_name}")
    log_info(f"Command: {' '.join(sys.argv)}")

    available = {"val": orchestrator.valset, "test": orchestrator.testset}
    for sp in splits:
        ds = available.get(sp)
        if not ds:
            print(f"(split {sp} vacio, salteado)")
            continue
        _diagnose_split(orchestrator.student, ds, sp, repeats)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Diagnostico por-caso del baseline rule_derived.")
    parser.add_argument("--config", required=True, help="Ruta al YAML de configuracion")
    parser.add_argument(
        "--splits",
        default="val,test",
        help="Splits a diagnosticar, separados por coma (default: val,test)",
    )
    parser.add_argument("--repeats", type=int, default=1, help="Repeticiones por caso (default: 1)")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(f"config no existe: {config_path}", file=sys.stderr)
        sys.exit(1)

    splits = [s.strip() for s in args.splits.split(",") if s.strip()]
    sys.exit(run(config_path, splits, args.repeats))


if __name__ == "__main__":
    main()
