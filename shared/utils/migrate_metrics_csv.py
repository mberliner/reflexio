"""
Migrate a legacy metrics CSV to the current column schema.

A metrics CSV created before token tracking has the old header (no
``Tokens Task`` / ``Tokens Reflection`` / ``Costo Real USD`` columns, and the
accented ``Reflexion Positiva`` variant). Appending new rows to it keeps the
old layout (see BaseCSVLogger alignment), so the real cost columns never show
up. This one-shot migration rewrites the file to the current header while:

- preserving every existing row (matched by accent-insensitive column name),
- backfilling token/cost columns from each run's ``run.json`` when available,
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

from shared.logging.csv_writer import EUROPEAN_CSV_CONFIG, STANDARD_COLUMN_MAPPING


def _norm(text: str) -> str:
    """Accent/case-insensitive key for matching display headers."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return ascii_only.lower().strip()


def _usage_from_run_json(results_dir: Path, run_dir_value: str) -> dict | None:
    """Load the usage block from a row's run.json, or None if unavailable."""
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
    return data.get("usage")


def migrate_csv(csv_path: Path) -> dict:
    """Rewrite csv_path to the current schema, backfilling from run.json.

    Returns a summary dict: {backup, rows, backfilled, already_current}.
    """
    csv_path = Path(csv_path)
    # <project>/results/experiments/metricas_optimizacion.csv -> results dir
    results_dir = csv_path.parent.parent

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f, **EUROPEAN_CSV_CONFIG))

    if not rows:
        return {"backup": None, "rows": 0, "backfilled": 0, "already_current": False}

    new_headers = list(STANDARD_COLUMN_MAPPING.values())
    old_header = rows[0]
    data_rows = rows[1:]

    if old_header == new_headers:
        return {
            "backup": None,
            "rows": len(data_rows),
            "backfilled": 0,
            "already_current": True,
        }

    # Backup before touching anything.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = csv_path.with_name(f"{csv_path.name}.bak-{stamp}")
    shutil.copy2(csv_path, backup)

    backfilled = 0
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

        out_rows.append([str(new_row.get(key, "")) for key in STANDARD_COLUMN_MAPPING])

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, **EUROPEAN_CSV_CONFIG)
        writer.writerows(out_rows)

    return {
        "backup": backup,
        "rows": len(data_rows),
        "backfilled": backfilled,
        "already_current": False,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
