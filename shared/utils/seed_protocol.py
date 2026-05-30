"""
Protocolo de N seeds para reconocer mejoras reales (senal vs ruido).

Corre cada config N veces (seed nuevo por corrida, autogenerado por el entry
point) y agrega las filas resultantes de ``metricas_optimizacion.csv`` en
media +/- rango por caso, comparando contra las filas previas (la "vara").

Por que: una corrida unica no distingue mejora real de suerte. Este protocolo
reporta media, rango y desvio sobre N corridas, y senala el gap val-test
(indicador de sobreajuste) para decidir si una intervencion funciono.

Uso (siempre como modulo desde la raiz del repo):

    python -m shared.utils.seed_protocol \
        --config dspy_gepa_poc/configs/dynamic_cv_profile_v2.yaml \
        --config dspy_gepa_poc/configs/dynamic_cv_triage_v2.yaml \
        --config gepa_standalone/experiments/configs/cv_extraction_v2.yaml \
        --seeds 5

    # Solo agregar lo ya corrido (p. ej. tras run_cv_cases.sh), sin ejecutar:
    python -m shared.utils.seed_protocol --config <yaml> --report-only

El framework (DSPy vs GEPA) y el CSV de metricas se infieren de la ruta del config.
"""

import argparse
import os
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from shared.paths import get_dspy_paths, get_gepa_paths

# Columnas del CSV compartido (ver shared/logging/csv_writer.py).
COL_RUN_ID = "Run ID"
COL_CASO = "Caso"
COL_BASE = "Baseline Score"
COL_OPT = "Optimizado Score"
COL_ROB = "Robustez Score"


class ConfigInfo:
    """Metadatos de un config necesarios para correr y agregar su protocolo."""

    def __init__(self, config_path: str):
        self.path = Path(config_path)
        if not self.path.exists():
            raise FileNotFoundError(f"Config no encontrado: {self.path}")

        raw = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        case = raw.get("case", {})
        opt = raw.get("optimization", {})
        data = raw.get("data", {})

        norm = self.path.as_posix()
        if "gepa_standalone" in norm:
            self.framework = "gepa"
            self.module = "gepa_standalone.universal_optimizer"
            paths = get_gepa_paths()
            # GEPA registra el 'title' en la columna Caso; aceptamos ambos por las dudas.
            self.case_names = {case.get("title"), case.get("name")} - {None}
        elif "dspy_gepa_poc" in norm:
            self.framework = "dspy"
            self.module = "dspy_gepa_poc.reflexio_declarativa"
            paths = get_dspy_paths()
            self.case_names = {case.get("name")} - {None}
        else:
            raise ValueError(
                f"No puedo inferir framework desde la ruta: {self.path} "
                "(esperaba 'dspy_gepa_poc' o 'gepa_standalone')."
            )

        self.summary_csv = paths.summary_csv
        self.eval_repeats = int(opt.get("eval_repeats", 1))
        csv_filename = data.get("csv_filename")
        self.dataset_path = (paths.datasets / csv_filename) if csv_filename else None

    def label(self) -> str:
        return " / ".join(sorted(self.case_names)) or self.path.name


def parse_float(value: str | None) -> float | None:
    """Convierte '93,0100' (coma decimal) a float; None si no parsea."""
    if value is None:
        return None
    txt = str(value).strip().replace(",", ".")
    if not txt:
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def read_rows(csv_path: Path, case_names: set[str]) -> list[dict[str, str]]:
    """Filas del CSV que pertenecen al caso (matcheando contra case_names)."""
    if not csv_path.exists():
        return []
    import csv as _csv

    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = _csv.DictReader(fh, delimiter=";")
        return [
            row
            for row in reader
            if row.get(COL_CASO) in case_names and row.get(COL_RUN_ID) not in (None, "", "PROMEDIO")
        ]


def summarize(values: list[float]) -> dict[str, Any]:
    """media, min, max, rango y desvio de una lista de scores."""
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "media": statistics.mean(values),
        "min": min(values),
        "max": max(values),
        "rango": max(values) - min(values),
        "desvio": statistics.pstdev(values) if len(values) > 1 else 0.0,
    }


def aggregate(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Agrega Baseline/Optimizado/Robustez sobre un conjunto de filas."""
    cols = {"baseline": COL_BASE, "optimizado": COL_OPT, "robustez": COL_ROB}
    out: dict[str, dict[str, Any]] = {}
    for key, col in cols.items():
        vals = [v for v in (parse_float(r.get(col)) for r in rows) if v is not None]
        out[key] = summarize(vals)
    return out


def run_seeds(info: ConfigInfo, seeds: int, jobs: int) -> int:
    """Lanza ``seeds`` invocaciones del entry point. Devuelve cuantas fallaron."""
    cmd_base = [sys.executable, "-m", info.module, "--config", str(info.path)]
    # Forzar UTF-8 en el subprocess: en Windows el entry point imprime caracteres
    # Unicode (p. ej. '->') y stdout heredado en cp1252 crashea con UnicodeEncodeError.
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    failures = 0
    procs: list[subprocess.Popen] = []

    def drain(pool: list[subprocess.Popen]) -> int:
        fails = 0
        for p in pool:
            if p.wait() != 0:
                fails += 1
        return fails

    for i in range(1, seeds + 1):
        print(f"  [{info.label()}] seed {i}/{seeds} ...", flush=True)
        if jobs <= 1:
            if subprocess.run(cmd_base, env=env).returncode != 0:
                failures += 1
        else:
            procs.append(subprocess.Popen(cmd_base, env=env))
            if len(procs) >= jobs:
                failures += drain(procs)
                procs = []
    failures += drain(procs)
    return failures


def fmt(stats: dict[str, Any], scale: float) -> str:
    """Formatea un resumen como 'media +/- rango (min..max), n=N'."""
    if not stats.get("n"):
        return "sin datos"
    return (
        f"{stats['media'] * scale:6.2f} +/- {stats['rango'] * scale:5.2f} "
        f"({stats['min'] * scale:6.2f}..{stats['max'] * scale:6.2f})  "
        f"desvio={stats['desvio'] * scale:5.2f}  n={stats['n']}"
    )


def report(info: ConfigInfo, before: list[dict], after: list[dict]) -> None:
    """Imprime resumen del caso: vara previa, lote nuevo y diagnostico de gap."""
    before_ids = {r[COL_RUN_ID] for r in before}
    new_rows = [r for r in after if r[COL_RUN_ID] not in before_ids]

    # Escala: GEPA guarda 0-1; DSPy guarda 0-100. Normalizamos a 0-100 al mostrar.
    sample = new_rows or after or before
    scale = 100.0
    if sample:
        opt_vals = [parse_float(r.get(COL_OPT)) for r in sample]
        opt_vals = [v for v in opt_vals if v is not None]
        if opt_vals and max(opt_vals) <= 1.0:
            scale = 100.0  # ya viene 0-1 -> *100
        else:
            scale = 1.0  # ya viene 0-100

    print(f"\n=== {info.label()} ({info.framework}, eval_repeats={info.eval_repeats}) ===")

    if new_rows:
        agg = aggregate(new_rows)
        print(f"  Lote nuevo (N={len(new_rows)}):")
        print(f"    Baseline   : {fmt(agg['baseline'], scale)}")
        print(f"    Optimizado : {fmt(agg['optimizado'], scale)}")
        print(f"    Robustez   : {fmt(agg['robustez'], scale)}")
        om = agg["optimizado"].get("media")
        rm = agg["robustez"].get("media")
        if om is not None and rm is not None:
            gap = (om - rm) * scale
            flag = "  <- posible sobreajuste" if gap > 3 else ""
            print(f"    Gap val-test (opt-rob): {gap:+.2f} pts{flag}")

    if before:
        agg_b = aggregate(before)
        print(f"  Vara previa (N={len(before)}):")
        print(f"    Optimizado : {fmt(agg_b['optimizado'], scale)}")
        print(f"    Robustez   : {fmt(agg_b['robustez'], scale)}")
        if new_rows:
            d_rob = (aggregate(new_rows)["robustez"]["media"] - agg_b["robustez"]["media"]) * scale
            print(
                f"    Delta robustez vs vara: {d_rob:+.2f} pts "
                "(media; chequear solapamiento de rangos)"
            )

    if not new_rows and not before:
        print("  Sin filas en el CSV todavia.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Protocolo de N seeds: corre y agrega media +/- rango por caso."
    )
    parser.add_argument(
        "--config",
        action="append",
        required=True,
        dest="configs",
        help="Ruta a config YAML (repetible).",
    )
    parser.add_argument(
        "-n", "--seeds", type=int, default=5, help="Corridas por config (default 5)."
    )
    parser.add_argument(
        "-j", "--jobs", type=int, default=1, help="Corridas en paralelo (default 1)."
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="No ejecuta; solo agrega las filas ya presentes en el CSV.",
    )
    args = parser.parse_args()

    if args.seeds < 1:
        parser.error("--seeds debe ser >= 1")

    infos = [ConfigInfo(c) for c in args.configs]

    for info in infos:
        before = read_rows(info.summary_csv, info.case_names)

        if not args.report_only:
            if info.dataset_path is not None and not info.dataset_path.exists():
                print(
                    f"\n[SKIP] {info.label()}: falta el dataset {info.dataset_path}. "
                    "Es un PREREQUISITO (curar datos reales). No se ejecuta este caso.",
                    file=sys.stderr,
                )
                report(info, before, before)
                continue
            print(f"\n>>> Corriendo {args.seeds} seeds: {info.label()}")
            fails = run_seeds(info, args.seeds, max(1, args.jobs))
            if fails:
                print(f"  [WARN] {fails}/{args.seeds} corridas fallaron.", file=sys.stderr)

        after = read_rows(info.summary_csv, info.case_names)
        report(info, before, after)

    print(
        "\nReconocer exito: el rango del lote nuevo NO debe solaparse con la vara previa, "
        "y el gap val-test debe ser <= 3 pts. Una sola mejor corrida no cuenta."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
