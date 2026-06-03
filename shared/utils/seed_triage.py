"""
Triaje de casos para el protocolo de N seeds: que vale la pena re-correr.

A diferencia de los runners que listan YAML a ciegas, este modulo MIRA los
resultados previos del CSV y clasifica cada caso en RESUELTO / DUDOSO / SIN DATOS,
verifica los prerequisitos manuales (dataset, gold, modelo) y propone para
seleccion solo los casos "con dudas". Reusa las primitivas de
``shared.utils.seed_protocol`` (ConfigInfo, read_rows, aggregate, _models).

Uso (siempre como modulo desde la raiz del repo):

    python -m shared.utils.seed_triage            # tablero + seleccion interactiva
    python -m shared.utils.seed_triage --list      # solo tablero, no pregunta

Capacidad: SPEC-101-triaje-casos-nseeds. Criterios de "duda" y prerequisitos:
docs/PROTOCOLO_N_SEEDS.md (seccion "Triaje de casos").
"""

import argparse
import csv as _csv
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from shared.utils.seed_protocol import (
    CEILING_BASELINE_PTS,
    COL_OPT,
    NOISE_EPS_PTS,
    ConfigInfo,
    _models,
    aggregate,
    parse_float,
    read_rows,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directorios de configs por engine (cross-engine: el triaje cubre ambos).
CONFIG_DIRS = {
    "dspy": REPO_ROOT / "dspy_gepa_poc" / "configs",
    "gepa": REPO_ROOT / "gepa_standalone" / "experiments" / "configs",
}

# Umbrales del triaje (escala 0-100). SSOT: docs/PROTOCOLO_N_SEEDS.md.
TRIAGE_VARIANCE_RANGE_PTS = 5.0  # rango de Robustez por encima -> medicion poco fiable.
TRIAGE_MIN_REFERENCE_ROWS = 3  # menos filas comparables -> poca evidencia.


@dataclass
class Diagnosis:
    """Estado de un caso de cara a decidir si re-correr N seeds."""

    name: str
    framework: str
    config_path: str
    status: str  # RESUELTO | DUDOSO | SIN DATOS
    n_comparable: int
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)  # impiden correr (dataset)
    warnings: list[str] = field(default_factory=list)  # gold, etc. (no bloquean)

    @property
    def selectable(self) -> bool:
        """Solo se puede correr si no hay bloqueantes duros (dataset ausente)."""
        return not self.blockers


def _matches(row_models: tuple[str, str], target: tuple[str, str]) -> bool:
    """Una fila es comparable si su par (tarea, profesor) iguala al objetivo.

    Un componente vacio en el objetivo actua como comodin (p. ej. si el .env no
    declara el modelo de reflexion, no se filtra por el).
    """
    rt, rr = row_models
    tt, tr = target
    if tt and rt != tt:
        return False
    if tr and rr != tr:
        return False
    return True


def _scale_for(rows: list[dict[str, str]]) -> float:
    """100 si los scores vienen 0-1 (GEPA), 1 si vienen 0-100 (DSPy)."""
    opt = [parse_float(r.get(COL_OPT)) for r in rows]
    opt = [v for v in opt if v is not None]
    return 100.0 if (opt and max(opt) <= 1.0) else 1.0


def target_models(framework: str) -> tuple[str, str]:
    """(modelo tarea, modelo profesor) que usaria una corrida nueva.

    Precedencia: variable de entorno gana sobre el .env del subproyecto (igual
    que dotenv con override=False). Componente ausente -> '' (comodin al matchear).
    """
    from dotenv import dotenv_values

    sub = "gepa_standalone" if framework == "gepa" else "dspy_gepa_poc"
    env_path = REPO_ROOT / sub / ".env"
    vals = dotenv_values(env_path) if env_path.exists() else {}
    task = os.environ.get("LLM_MODEL_TASK") or vals.get("LLM_MODEL_TASK") or ""
    refl = os.environ.get("LLM_MODEL_REFLECTION") or vals.get("LLM_MODEL_REFLECTION") or ""
    return (task.strip(), refl.strip())


def gold_is_unverified(dataset_path: Path | None) -> bool:
    """True si el dataset trae columna gold_verificado con algun valor 'no'."""
    if dataset_path is None or not dataset_path.exists():
        return False
    text = dataset_path.read_text(encoding="utf-8", errors="replace")
    first = text.splitlines()[0] if text else ""
    delim = ";" if first.count(";") >= first.count(",") else ","
    reader = _csv.DictReader(text.splitlines(), delimiter=delim)
    if "gold_verificado" not in (reader.fieldnames or []):
        return False
    return any((row.get("gold_verificado") or "").strip().lower() == "no" for row in reader)


def diagnose(
    name: str,
    framework: str,
    config_path: str,
    rows: list[dict[str, str]],
    target: tuple[str, str],
    dataset_exists: bool,
    gold_unverified: bool,
) -> Diagnosis:
    """Clasifica un caso (funcion pura). Status y razones segun los criterios.

    DUDOSO si: (a) hay mejora sin confirmar (rob < techo y Opt-Base > eps),
    (b) alta varianza o pocas filas comparables, o (c) no hay referencia
    comparable (filas previas con otro modelo). RESUELTO si esta en techo y
    estable. SIN DATOS si el caso nunca se corrio.
    """
    reasons: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []

    if not dataset_exists:
        blockers.append("dataset ausente: la corrida haria [SKIP]")
    if gold_unverified:
        warnings.append("gold_verificado=no (D-001): conclusion no confiable hasta revisar")

    comparable = [r for r in rows if _matches(_models(r), target)]
    n_comp = len(comparable)
    n_other = len(rows) - n_comp

    if not rows:
        return Diagnosis(
            name,
            framework,
            config_path,
            "SIN DATOS",
            0,
            reasons=["nunca corrido (sin filas en el CSV)"],
            blockers=blockers,
            warnings=warnings,
        )

    if n_comp == 0:
        reasons.append(
            f"sin referencia comparable: {n_other} fila(s) previa(s) usan otro modelo "
            f"(objetivo {target[0] or '?'}/{target[1] or '?'})"
        )
        return Diagnosis(
            name,
            framework,
            config_path,
            "DUDOSO",
            0,
            reasons=reasons,
            blockers=blockers,
            warnings=warnings,
        )

    scale = _scale_for(comparable)
    agg = aggregate(comparable)
    base_m = (agg["baseline"].get("media") or 0.0) * scale
    opt_m = (agg["optimizado"].get("media") or 0.0) * scale
    rob = agg["robustez"]
    rob_m = (rob.get("media") or 0.0) * scale
    rob_rng = (rob.get("rango") or 0.0) * scale
    delta_ob = opt_m - base_m

    dudoso = False
    if n_other:
        warnings.append(f"{n_other} fila(s) previa(s) de otro modelo se ignoran")
    if rob_rng > TRIAGE_VARIANCE_RANGE_PTS:
        reasons.append(
            f"alta varianza: rango Rob {rob_rng:.1f} > {TRIAGE_VARIANCE_RANGE_PTS:.0f} pts"
        )
        dudoso = True
    if n_comp < TRIAGE_MIN_REFERENCE_ROWS:
        reasons.append(f"poca evidencia: n={n_comp} < {TRIAGE_MIN_REFERENCE_ROWS}")
        dudoso = True

    at_ceiling = rob_m >= CEILING_BASELINE_PTS and delta_ob <= NOISE_EPS_PTS
    if at_ceiling and not dudoso:
        reasons.append(
            f"techo: Rob {rob_m:.1f} >= {CEILING_BASELINE_PTS:.0f} y Opt-Base {delta_ob:+.1f} plano"
        )
        return Diagnosis(
            name,
            framework,
            config_path,
            "RESUELTO",
            n_comp,
            reasons=reasons,
            blockers=blockers,
            warnings=warnings,
        )

    if not at_ceiling and delta_ob > NOISE_EPS_PTS:
        reasons.append(f"mejora sin confirmar: Opt-Base {delta_ob:+.1f}, Rob {rob_m:.1f} < techo")
        dudoso = True

    status = "DUDOSO" if dudoso else "RESUELTO"
    if status == "RESUELTO" and not reasons:
        reasons.append(f"estable: Rob {rob_m:.1f}, rango {rob_rng:.1f}, sin margen aparente")
    return Diagnosis(
        name,
        framework,
        config_path,
        status,
        n_comp,
        reasons=reasons,
        blockers=blockers,
        warnings=warnings,
    )


def collect_diagnoses() -> list[Diagnosis]:
    """Recorre los configs de ambos engines y diagnostica cada caso."""
    out: list[Diagnosis] = []
    for cfg_dir in CONFIG_DIRS.values():
        if not cfg_dir.exists():
            continue
        for path in sorted(cfg_dir.glob("*.yaml")):
            try:
                info = ConfigInfo(str(path))
            except Exception as exc:  # config invalido: lo saltamos sin romper el tablero
                print(f"  [WARN] {path.name}: no se pudo leer ({exc})", file=sys.stderr)
                continue
            rows = read_rows(info.summary_csv, info.case_names)
            target = target_models(info.framework)
            dataset_exists = info.dataset_path is None or info.dataset_path.exists()
            gold_unv = gold_is_unverified(info.dataset_path)
            out.append(
                diagnose(
                    name=path.stem,
                    framework=info.framework,
                    config_path=str(path),
                    rows=rows,
                    target=target,
                    dataset_exists=dataset_exists,
                    gold_unverified=gold_unv,
                )
            )
    return out


_STATUS_ORDER = {"DUDOSO": 0, "SIN DATOS": 1, "RESUELTO": 2}


def print_board(diags: list[Diagnosis]) -> list[Diagnosis]:
    """Imprime el tablero ordenado (dudosos primero). Devuelve el orden mostrado."""
    ordered = sorted(diags, key=lambda d: (_STATUS_ORDER.get(d.status, 9), d.name))
    print("\n=== Triaje de casos (N seeds) ===\n")
    print(f"  {'#':>2}  {'ESTADO':<10} {'ENGINE':<5} {'N':>3}  CASO")
    print("  " + "-" * 60)
    for i, d in enumerate(ordered, 1):
        mark = "" if d.selectable else " (BLOQUEADO)"
        print(f"  {i:>2}  {d.status:<10} {d.framework:<5} {d.n_comparable:>3}  {d.name}{mark}")
        for r in d.reasons:
            print(f"        - {r}")
        for w in d.warnings:
            print(f"        ! {w}")
        for b in d.blockers:
            print(f"        x {b}")
    print()
    return ordered


def _prompt(text: str) -> str:
    """input() tolerante: sin terminal (EOF) o Ctrl-C devuelve '' (= sin seleccion)."""
    try:
        return input(text).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Triaje de casos N seeds: clasifica por resultados previos y prerequisitos."
    )
    parser.add_argument(
        "--list", action="store_true", help="Solo muestra el tablero; no pregunta ni corre."
    )
    parser.add_argument(
        "-n", "--seeds", type=int, default=5, help="Seeds por caso al lanzar (default 5)."
    )
    parser.add_argument(
        "-j", "--jobs", type=int, default=1, help="Corridas en paralelo al lanzar (default 1)."
    )
    args = parser.parse_args()

    diags = collect_diagnoses()
    if not diags:
        print("No se encontraron configs.", file=sys.stderr)
        return 1
    ordered = print_board(diags)

    if args.list:
        return 0

    dudosos = [d for d in ordered if d.status == "DUDOSO" and d.selectable]
    if not dudosos:
        print("No hay casos DUDOSOS seleccionables. Nada que re-correr.")
        return 0

    print("Casos DUDOSOS seleccionables:")
    for i, d in enumerate(dudosos, 1):
        print(f"  [{i}] {d.name} ({d.framework})")
    raw = _prompt("\nSeleccion (numeros separados por espacio/coma, 'all' o vacio para ninguno): ")
    if not raw:
        print("Sin seleccion. Fin.")
        return 0

    if raw.lower() in {"all", "todos"}:
        chosen = dudosos
    else:
        chosen = []
        for tok in raw.replace(",", " ").split():
            if not tok.isdigit() or not (1 <= int(tok) <= len(dudosos)):
                print(f"ERROR: seleccion invalida: '{tok}'", file=sys.stderr)
                return 1
            chosen.append(dudosos[int(tok) - 1])

    # Confirmacion extra si algun elegido tiene gold sin verificar.
    if any(d.warnings for d in chosen):
        print("\n[ATENCION] casos elegidos con advertencias:")
        for d in chosen:
            for w in d.warnings:
                print(f"  - {d.name}: {w}")
        if _prompt("Continuar igual? [s/N]: ").lower() not in {"s", "si", "y", "yes"}:
            print("Cancelado.")
            return 0

    cmd = [
        sys.executable,
        "-m",
        "shared.utils.seed_protocol",
        "-n",
        str(args.seeds),
        "-j",
        str(args.jobs),
    ]
    for d in chosen:
        cmd += ["--config", d.config_path]
    print(f"\n>>> Lanzando: {' '.join(cmd)}\n")
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(cmd, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
