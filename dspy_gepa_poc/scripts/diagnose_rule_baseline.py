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

from dotenv import load_dotenv

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


def _diagnose_alto_impacto_pilot(student, dataset, split_name: str, repeats: int) -> None:
    """Pilot D-015a: mide alto_impacto DERIVADO de sub-hechos sobre casos P5=Si.

    El student emite sub-hechos objetivos (acotado, reversible, escala_masiva, ...);
    `derive_alto_impacto_from_row` aplica la PRECEDENCIA del Marco. Compara contra el gold
    de alto_impacto donde decide el color (P5=Si: Negro<=>alto, Rojo<=>no-alto). Si la
    precision supera la del baseline directo (historial), el error era de precedencia.
    """
    from dspy_gepa_poc.flujo_intents.fast_gate_rule import (
        ALTO_IMPACTO_SUBHECHO_FIELDS,
        derive_alto_impacto_from_row,
    )

    print_section(f"PILOT alto_impacto DERIVADO -- SPLIT {split_name.upper()} (repeats={repeats})")
    print(f"{'caso':12} {'gold':5} {'der':5}  ok   sub-hechos pred (Si)")
    print("-" * 90)
    ai_ok = 0
    ai_total = 0
    conf: Counter = Counter()
    for ex in dataset:
        cid = getattr(ex, "case_id", "?")
        p5_gold = str(getattr(ex, "p5", "") or "").strip().lower()
        if p5_gold != "si":
            continue  # alto_impacto solo decide el color cuando P5=Si
        ai_gold = str(getattr(ex, "alto_impacto", "") or "").strip().lower()
        for _ in range(repeats):
            pred = student(ficha=ex.ficha)
            sub = {f: getattr(pred, f, "") for f in ALTO_IMPACTO_SUBHECHO_FIELDS}
            der = "si" if derive_alto_impacto_from_row(sub) else "no"
            hit = ai_gold == der
            ai_ok += hit
            ai_total += 1
            if not hit:
                conf[(ai_gold, der)] += 1
            activos = ",".join(
                f for f, v in sub.items() if str(v).strip().lower() in ("si", "true", "1")
            )
            mark = "ok" if hit else "X "
            print(f"{cid:12} {ai_gold:5} {der:5}  {mark}  {activos}")
    print("-" * 90)
    if ai_total:
        print(f"alto_impacto DERIVADO (P5=Si): {ai_ok}/{ai_total} = {ai_ok / ai_total:.1%}")
        for (g, p), n in conf.most_common():
            etiqueta = "sub-escala (alto si->no)" if g == "si" else "sobre-escala (alto no->si)"
            print(f"  alto {g}->{p}: {n}  [{etiqueta}]")
    else:
        print("(sin casos P5=Si en el split)")


def _run_pilot(config_path: Path, splits: list[str], repeats: int) -> int:
    """Pilot D-015a autocontenido: NO usa AppConfig (los sub-hechos aun no tienen columna
    gold en el CSV; eso es Fase 2). Construye el predictor desde el YAML crudo, configura el
    LM de la .env y lee el TEST del CSV. Solo necesita el gold de alto_impacto (que SI existe).
    """
    import csv as _csv

    import dspy
    import yaml

    from dspy_gepa_poc import DynamicModuleFactory, LLMConfig
    from shared.paths import get_dspy_paths

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    case_name = raw["case"]["name"]
    print_header(f"[DIAGNOSTICO PILOT alto_impacto] {case_name}")
    log_info(f"Command: {' '.join(sys.argv)}")

    project_dir = Path(__file__).resolve().parents[1]
    env_path = project_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    task_config = LLMConfig.from_env("task")
    # Mismo override que ReflexioDeclarativa.setup_models: aplica models.* del config
    # (temperature/max_tokens/cache). Para reasoning models (gpt-5.4) get_dspy_lm fuerza
    # temperature=1.0 y max_tokens>=16000 por su cuenta.
    models_cfg = raw.get("models", {})
    if "temperature" in models_cfg:
        task_config.temperature = models_cfg["temperature"]
    if "max_tokens" in models_cfg:
        task_config.max_tokens = models_cfg["max_tokens"]
    if "cache" in models_cfg:
        task_config.cache = models_cfg["cache"]
    dspy.configure(lm=task_config.get_dspy_lm())
    log_info(f"Task LM: {task_config.describe()} | zero-shot (sin few-shot)")

    student = DynamicModuleFactory.create_module(raw["signature"], predictor_type="cot")

    csv_path = get_dspy_paths().datasets / raw["data"]["csv_filename"]
    rows = list(_csv.DictReader(csv_path.open(encoding="utf-8")))
    for sp in splits:
        ds = [_PilotCase(r) for r in rows if r.get("split", "").strip() == sp]
        if not ds:
            print(f"(split {sp} vacio, salteado)")
            continue
        _diagnose_alto_impacto_pilot(student, ds, sp, repeats)
    return 0


class _PilotCase:
    """Adaptador minimo fila-CSV -> objeto con .ficha/.case_id/.p5/.alto_impacto."""

    def __init__(self, row: dict):
        self.ficha = row.get("ficha", "")
        self.case_id = row.get("case_id", "?")
        self.p5 = row.get("p5", "")
        self.alto_impacto = row.get("alto_impacto", "")


def run(config_path: Path, splits: list[str], repeats: int, pilot: bool = False) -> int:
    if pilot:
        return _run_pilot(config_path, splits, repeats)

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
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="Modo pilot D-015a: mide alto_impacto DERIVADO de sub-hechos (config pilot).",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(f"config no existe: {config_path}", file=sys.stderr)
        sys.exit(1)

    splits = [s.strip() for s in args.splits.split(",") if s.strip()]
    sys.exit(run(config_path, splits, args.repeats, pilot=args.pilot))


if __name__ == "__main__":
    main()
