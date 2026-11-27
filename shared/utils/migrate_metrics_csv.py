"""
Migrate a legacy metrics CSV to the current column schema.

A metrics CSV created before token tracking has the old header (no
``Tokens Task`` / ``Tokens Reflection`` / ``Costo Real USD`` columns, and the
accented ``Reflexion Positiva`` variant). Appending new rows to it keeps the
old layout (see BaseCSVLogger alignment), so the real cost columns never show
up. This one-shot migration rewrites the file to the current header while:

- preserving every existing row (matched by accent-insensitive column name),
- backfilling token/cost columns from each run's ``run.json`` when available,
- backfilling ``Versiones Librerias`` from ``run.json`` (empty for legacy runs
  that did not record them: versions unknown, never guessed),
- backfilling ``Modelo Juez`` in RAG rows with ``Modelo Profesor`` (before
  SPEC-106 the judge was the teacher); empty elsewhere (SPEC-106 FR-006),
- writing a timestamped ``.bak`` backup first.

Usage (from repo root):
    python -m shared.utils.migrate_metrics_csv            # both project CSVs
    python -m shared.utils.migrate_metrics_csv <csv_path> # a specific file
"""

import csv
import json
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import yaml

from shared.logging.csv_writer import EUROPEAN_CSV_CONFIG, STANDARD_COLUMN_MAPPING
from shared.logging.metadata import format_framework_versions


def _norm(text: str) -> str:
    """Accent/case-insensitive key for matching display headers."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return ascii_only.lower().strip()


def _run_json(results_dir: Path, run_dir_value: str) -> dict | None:
    """Load a row's run.json, or None if unavailable."""
    if not run_dir_value or run_dir_value.strip() in ("", "N/A"):
        return None
    rel = run_dir_value.replace("\\", "/")
    run_json = results_dir / rel / "run.json"
    if not run_json.exists():
        return None
    try:
        data = json.loads(run_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _usage_from_run_json(results_dir: Path, run_dir_value: str) -> dict | None:
    """Load the usage block from a row's run.json, or None if unavailable."""
    data = _run_json(results_dir, run_dir_value)
    return data.get("usage") if data else None


def _versions_from_run_json(results_dir: Path, run_dir_value: str) -> str:
    """Canonical library versions from a row's run.json; '' if not recorded.

    Legacy run.json files (before SPEC-100 FR-009) carry no versions: the row
    stays empty, i.e. "versions unknown", never a guessed value.
    """
    data = _run_json(results_dir, run_dir_value)
    frameworks = data.get("frameworks") if data else None
    return format_framework_versions(frameworks) if isinstance(frameworks, dict) else ""


def _is_rag_run(results_dir: Path, run_dir_value: str) -> bool | None:
    """Whether a row is a RAG run: True, False, or None when it cannot be known.

    RAG if its ``run.json`` has ``models.judge``; without that (or without
    ``run.json``), if its ``config_snapshot.yaml`` has ``adapter.type: rag``
    (SPEC-106 D10). A snapshot with a ``module`` section and no ``adapter.type``
    is a DSPy run (``module`` exists only in DSPy, which has no RAG): not RAG.
    """
    data = _run_json(results_dir, run_dir_value)
    models = data.get("models") if data else None
    if isinstance(models, dict) and "judge" in models:
        return True
    snapshot = results_dir / run_dir_value.replace("\\", "/") / "config_snapshot.yaml"
    if not snapshot.exists():
        return None
    try:
        config = yaml.safe_load(snapshot.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(config, dict):
        return None
    adapter = config.get("adapter")
    if isinstance(adapter, dict) and "type" in adapter:
        return adapter["type"] == "rag"
    if "module" in config:
        return False
    return None


def _backfill_judge(new_row: dict, results_dir: Path) -> bool | None:
    """Fill an empty ``judge_model`` of a RAG row with the teacher.

    Returns True if filled, None if the row's kind is unknown (reported), False otherwise.
    """
    if new_row.get("judge_model"):
        return False
    kind = _is_rag_run(results_dir, new_row.get("run_dir", ""))
    if kind is None:
        return None
    if kind and new_row.get("reflection_model"):
        new_row["judge_model"] = new_row["reflection_model"]
        return True
    return False


def _backfill_judge_only(csv_path: Path, results_dir: Path, rows: list[list[str]]) -> dict:
    """File already at the current header: complete only an empty ``Modelo Juez``.

    The logger adds the column to an unmigrated file leaving earlier rows empty
    (SPEC-106 D10); this fills them. Idempotent: with nothing to fill, the file
    is not touched and no backup is made.
    """
    header, data_rows = rows[0], rows[1:]
    keys = list(STANDARD_COLUMN_MAPPING)
    judge_filled = 0
    judge_unknown = 0
    out_rows = [header]
    for raw in data_rows:
        padded = [*raw, *[""] * (len(keys) - len(raw))]
        new_row = dict(zip(keys, padded, strict=False))
        filled = _backfill_judge(new_row, results_dir)
        judge_filled += filled is True
        judge_unknown += filled is None
        out_rows.append([*(str(new_row[k]) for k in keys), *padded[len(keys) :]])

    result = {
        "backup": None,
        "rows": len(data_rows),
        "backfilled": 0,
        "already_current": True,
        "judge_filled": judge_filled,
        "judge_unknown": judge_unknown,
    }
    if not judge_filled:
        return result

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = csv_path.with_name(f"{csv_path.name}.bak-{stamp}")
    shutil.copy2(csv_path, backup)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, **EUROPEAN_CSV_CONFIG).writerows(out_rows)
    result.update(backup=backup, already_current=False)
    return result


def migrate_csv(csv_path: Path) -> dict:
    """Rewrite csv_path to the current schema, backfilling from run.json.

    Returns a summary dict: {backup, rows, backfilled, already_current,
    judge_filled, judge_unknown}. ``judge_unknown`` counts rows whose kind (RAG
    or not) could not be determined; they keep ``Modelo Juez`` empty.
    """
    csv_path = Path(csv_path)
    # <project>/results/experiments/metricas_optimizacion.csv -> results dir
    results_dir = csv_path.parent.parent

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f, **EUROPEAN_CSV_CONFIG))

    if not rows:
        return {
            "backup": None,
            "rows": 0,
            "backfilled": 0,
            "already_current": False,
            "judge_filled": 0,
            "judge_unknown": 0,
        }

    new_headers = list(STANDARD_COLUMN_MAPPING.values())
    old_header = rows[0]
    data_rows = rows[1:]

    if old_header == new_headers:
        return _backfill_judge_only(csv_path, results_dir, rows)

    # Backup before touching anything.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = csv_path.with_name(f"{csv_path.name}.bak-{stamp}")
    shutil.copy2(csv_path, backup)

    backfilled = 0
    judge_filled = 0
    judge_unknown = 0
    out_rows = [new_headers]
    for raw in data_rows:
        by_norm = {
            _norm(old_header[i]): (raw[i] if i < len(raw) else "") for i in range(len(old_header))
        }
        new_row = {
            key: by_norm.get(_norm(display), "") for key, display in STANDARD_COLUMN_MAPPING.items()
        }

        # Backfill token/cost from run.json when the row lacks a real cost.
        if not new_row.get("cost_real_usd"):
            usage = _usage_from_run_json(results_dir, new_row.get("run_dir", ""))
            if usage:
                task = usage.get("task", {})
                reflection = usage.get("reflection", {})
                new_row["tokens_task"] = task.get("prompt_tokens", 0) + task.get(
                    "completion_tokens", 0
                )
                new_row["tokens_reflection"] = reflection.get("prompt_tokens", 0) + reflection.get(
                    "completion_tokens", 0
                )
                cost = usage.get("cost_usd")
                if cost is not None:
                    new_row["cost_real_usd"] = f"{cost:.6f}".replace(".", ",")
                backfilled += 1

        if not new_row.get("lib_versions"):
            new_row["lib_versions"] = _versions_from_run_json(
                results_dir, new_row.get("run_dir", "")
            )

        filled = _backfill_judge(new_row, results_dir)
        judge_filled += filled is True
        judge_unknown += filled is None

        out_rows.append([str(new_row.get(key, "")) for key in STANDARD_COLUMN_MAPPING])

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, **EUROPEAN_CSV_CONFIG)
        writer.writerows(out_rows)

    return {
        "backup": backup,
        "rows": len(data_rows),
        "backfilled": backfilled,
        "already_current": False,
        "judge_filled": judge_filled,
        "judge_unknown": judge_unknown,
    }


def _default_csv_paths() -> list[Path]:
    """The two project metrics CSVs, relative to the repo root."""
    root = Path(__file__).resolve().parent.parent.parent
    rel = Path("results") / "experiments" / "metricas_optimizacion.csv"
    candidates = [root / "dspy_gepa_poc" / rel, root / "gepa_standalone" / rel]
    return [p for p in candidates if p.exists()]


def main(argv: list[str]) -> int:
    targets = [Path(argv[0])] if argv else _default_csv_paths()
    if not targets:
        print("No se encontraron CSVs de metricas para migrar.")
        return 1

    for csv_path in targets:
        result = migrate_csv(csv_path)
        print(f"\n{csv_path}")
        if result["already_current"]:
            print(f"  Ya esta en el schema actual ({result['rows']} filas). Sin cambios.")
            continue
        if result["backup"] is None:
            print("  Archivo vacio. Sin cambios.")
            continue
        print(f"  Backup:    {result['backup'].name}")
        print(f"  Filas:     {result['rows']}")
        print(f"  Backfill:  {result['backfilled']} fila(s) con costo real desde run.json")
        print(
            f"  Juez:      {result['judge_filled']} fila(s) RAG con Modelo Juez = Modelo Profesor"
        )
        if result["judge_unknown"]:
            print(
                f"  Sin saber si son RAG: {result['judge_unknown']} fila(s) "
                "(ni run.json con juez ni config_snapshot.yaml con adapter.type o "
                "module); Modelo Juez queda vacio."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
