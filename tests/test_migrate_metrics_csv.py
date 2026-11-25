"""Tests de shared.utils.migrate_metrics_csv: schema actual y backfill desde run.json."""

import csv
import json

from shared.logging.csv_writer import STANDARD_COLUMN_MAPPING
from shared.utils.migrate_metrics_csv import migrate_csv

LEGACY_HEADER = (
    "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;Baseline Score;Optimizado Score;"
    "Robustez Score;Run Directory;Reflexion Positiva;Budget;Tokens Task;"
    "Tokens Reflection;Costo Real USD;Notas"
)


def _write_legacy(tmp_path, rows):
    csv_path = tmp_path / "results" / "experiments" / "metricas_optimizacion.csv"
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text("\n".join([LEGACY_HEADER, *rows]) + "\n", encoding="utf-8")
    return csv_path


def _read(csv_path):
    with csv_path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def test_agrega_columna_de_versiones_y_la_rellena_desde_run_json(tmp_path):
    run_dir = tmp_path / "results" / "runs" / "demo" / "r1"
    run_dir.mkdir(parents=True)
    frameworks = {"dspy": "3.2.1", "gepa": "0.0.27", "litellm": "1.108.5", "openai": "3.57.0"}
    (run_dir / "run.json").write_text(json.dumps({"frameworks": frameworks}), encoding="utf-8")
    csv_path = _write_legacy(
        tmp_path,
        [
            "r1;2026-11-20;Demo;m;p;60;80;79;runs/demo/r1;No;30;1;1;0,1;",
            "r0;2026-01-01;Demo;m;p;60;80;79;runs/demo/sin_run_json;No;30;1;1;0,1;",
        ],
    )

    result = migrate_csv(csv_path)

    assert result["backup"] is not None and result["rows"] == 2
    rows = _read(csv_path)
    assert list(rows[0]) == list(STANDARD_COLUMN_MAPPING.values())
    assert rows[0]["Versiones Librerias"] == "dspy=3.2.1 gepa=0.0.27 litellm=1.108.5 openai=3.57.0"
    # Corrida legacy sin run.json: versiones desconocidas, nunca adivinadas.
    assert rows[1]["Versiones Librerias"] == ""
    assert rows[1]["Robustez Score"] == "79"


def test_idempotente_si_ya_esta_en_schema_actual(tmp_path):
    csv_path = _write_legacy(tmp_path, [])
    migrate_csv(csv_path)
    assert migrate_csv(csv_path)["already_current"] is True
