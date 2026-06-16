"""Builder de datasets por etapa para flujo-intents.

Genera un CSV por etapa (`intake`, `triage_solidez`, `triage_factibilidad`,
`fast_gate`) con columnas `id`, `ficha`, `<label>`, `split`, listo para el harness
existente (`CSVDataLoader`).

Hygiene de datos (decision del plan):
- Los 42 casos ORIGINALES del proyecto (`intake_clasificacion.csv` 32 positivos +
  `triage_rechazos.csv` 10 rechazos) van SOLO a `split=test` (holdout independiente).
- El `train`/`val` se arma con variaciones a mano (mismo formato de ficha) ubicadas en
  `dspy_gepa_poc/datasets/variations/flujo_intents_<etapa>_var.csv`. Si no existen, el
  CSV de etapa queda solo con test (util para inspeccionar el holdout).

El mapeo rechazo -> etapa terminal es EXPLICITO por id (autoritativo, desde
`triage_rechazos.md`), porque la columna `marcadores` del CSV original esta desalineada
en algunas filas por `;` sin comillas. `triage_paso`/`triage_accion` se parsean bien
pero no distinguen campo-ausente/contradiccion (intake) de invalidez de contenido
(solidez); por eso se fija a mano.
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

from shared.paths import get_dspy_paths

from .ficha import normalize_color, serialize_ficha

# Fuente del holdout de test: los casos originales del proyecto de gobierno. Es data
# externa al repo (no versionada), por eso su ubicacion se resuelve por entorno y NO se
# hardcodea: variable `FLUJO_INTENTS_ORIGINALS_DIR`. Si no esta definida o el directorio
# no existe, las etapas que dependen de originales para el test (intake, solidez,
# fast_gate) no se regeneran (se dejan intactas); las que traen test propio en sus
# variaciones (p.ej. factibilidad, con holdout balanceado a mano) si se regeneran.
_ORIGINALS_ENV = "FLUJO_INTENTS_ORIGINALS_DIR"


def _originals_dir() -> Path | None:
    raw = os.environ.get(_ORIGINALS_ENV, "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


# Orden canonico de las etapas LLM y el nombre de su campo de salida (label).
STAGE_LABEL_FIELD: dict[str, str] = {
    "intake": "admision",
    "triage_solidez": "solidez",
    "triage_factibilidad": "factibilidad",
    "fast_gate": "clasificacion",
}
STAGE_ORDER: tuple[str, ...] = ("intake", "triage_solidez", "triage_factibilidad", "fast_gate")

# Todas las columnas de output de la signature de cada etapa (el harness exige que
# existan en el CSV aunque esten en ignore_in_metric). El label se rellena; el resto
# queda vacio (razonamiento, p1..p5 son diagnosticos ignorados por la metrica).
STAGE_OUTPUT_COLUMNS: dict[str, list[str]] = {
    "intake": ["admision", "razonamiento"],
    "triage_solidez": ["solidez", "razonamiento"],
    "triage_factibilidad": ["factibilidad", "razonamiento"],
    "fast_gate": ["p1", "p2", "p3", "p4", "p5", "clasificacion", "razonamiento"],
}

# Valor "pasa" de cada etapa-gate (lo que permite avanzar a la siguiente).
PASS_LABEL: dict[str, str] = {
    "intake": "admitida",
    "triage_solidez": "solido",
    "triage_factibilidad": "avanza_fast_gate",
}

# Mapeo explicito rechazo original -> (etapa terminal, label en esa etapa).
# Derivado de triage_rechazos.md. Codifica la decomposicion de 5 etapas adoptada.
REJ_STAGE_MAP: dict[str, tuple[str, str]] = {
    "TC-REJ-01": ("intake", "incompleta"),  # campo obligatorio ausente
    "TC-REJ-05": ("intake", "incompleta"),  # contradiccion irreconciliable
    "TC-REJ-02": ("triage_solidez", "devolucion_reformulacion"),  # tecnologia, no resultado
    "TC-REJ-03": ("triage_solidez", "devolucion_reformulacion"),  # sin sponsor individual
    "TC-REJ-04": ("triage_solidez", "devolucion_reformulacion"),  # metricas no medibles
    "TC-REJ-07": ("triage_factibilidad", "no_avanza"),  # factibilidad insuficiente
    "TC-REJ-08": ("triage_factibilidad", "avanza_con_redisenio"),  # autonomia reducible
    # Sin etapa hasta crear las etapas nuevas (diferido, D-014):
    # - TC-REJ-06 (no requiere IA): "devolucion_no_ia" no es criterio de solidez del Marco.
    # - TC-REJ-09 (§9.2 uso prohibido) y TC-REJ-10 (§7.4 duplicado): admisibilidad
    #   (atributos protegidos / deduplicacion) no es factibilidad tecnica.
    # Ver historial/sdd.md y SPEC-102.
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def _stage_rows_for_positive(row: Mapping[str, str]) -> dict[str, str]:
    """Labels de un positivo (alcanza todas las etapas; color en fast_gate)."""
    return {
        "intake": PASS_LABEL["intake"],
        "triage_solidez": PASS_LABEL["triage_solidez"],
        "triage_factibilidad": PASS_LABEL["triage_factibilidad"],
        "fast_gate": normalize_color(row["clasificacion_esperada"]),
    }


def _stage_rows_for_rejection(case_id: str) -> dict[str, str]:
    """Labels de un rechazo: 'pasa' en etapas previas, su label en la terminal,
    ausente en las posteriores."""
    terminal_stage, terminal_label = REJ_STAGE_MAP[case_id]
    terminal_idx = STAGE_ORDER.index(terminal_stage)
    labels: dict[str, str] = {}
    for idx, stage in enumerate(STAGE_ORDER):
        if idx < terminal_idx:
            labels[stage] = PASS_LABEL[stage]
        elif idx == terminal_idx:
            labels[stage] = terminal_label
        # idx > terminal_idx: el caso no llega a esa etapa -> no se incluye
    return labels


# Tamano del test por etapa (holdout). Los originales (~32-42) se recortan a este
# numero de forma estratificada (round-robin por clase) para honrar el ratio
# 40/20/40 (train 30 / val 15 / test 30) sin perder las clases minoritarias.
TEST_TARGET = 30


def build_originals_rows() -> dict[str, list[dict[str, str]]]:
    """Construye, por etapa, TODAS las filas derivadas de los 42 originales.

    Si la fuente externa no esta disponible (`FLUJO_INTENTS_ORIGINALS_DIR` sin definir
    o inexistente), devuelve listas vacias por etapa: las etapas sin test propio en sus
    variaciones quedaran sin test y `build_stage_csv` las omite para no pisar el CSV.
    """
    per_stage: dict[str, list[dict[str, str]]] = {s: [] for s in STAGE_ORDER}

    originals_dir = _originals_dir()
    if originals_dir is None:
        return per_stage

    for row in _read_csv(originals_dir / "intake_clasificacion.csv"):
        case_id = row["id"].strip()
        if not case_id:
            continue
        ficha = serialize_ficha(row)
        for stage, label in _stage_rows_for_positive(row).items():
            per_stage[stage].append({"id": case_id, "ficha": ficha, "label": label})

    for row in _read_csv(originals_dir / "triage_rechazos.csv"):
        case_id = row["id"].strip()
        if case_id not in REJ_STAGE_MAP:
            continue
        ficha = serialize_ficha(row)
        for stage, label in _stage_rows_for_rejection(case_id).items():
            per_stage[stage].append({"id": case_id, "ficha": ficha, "label": label})

    return per_stage


def _stratified_cap(rows: list[dict[str, str]], target: int) -> list[dict[str, str]]:
    """Recorta a `target` filas con round-robin por clase (deterministico por id).

    Mantiene presentes las clases minoritarias: itera las clases por turnos tomando
    una fila de cada una hasta llegar a `target`. Si ya hay <= target, devuelve todo.
    """
    if len(rows) <= target:
        return sorted(rows, key=lambda r: r["id"])
    by_label: dict[str, list[dict[str, str]]] = {}
    for r in sorted(rows, key=lambda r: r["id"]):
        by_label.setdefault(r["label"], []).append(r)
    queues = list(by_label.values())
    selected: list[dict[str, str]] = []
    idx = 0
    while len(selected) < target:
        queue = queues[idx % len(queues)]
        if queue:
            selected.append(queue.pop(0))
        idx += 1
        if all(not q for q in queues):
            break
    return selected


def _read_variations(stage: str, variations_dir: Path) -> list[dict[str, str]]:
    """Lee variaciones a mano (train/val) para una etapa, si existen.

    Formato esperado: columnas de ficha (las 21) + columna `label` + columna `split`
    (train|val). Devuelve filas {id, ficha, label, split}.
    """
    path = variations_dir / f"flujo_intents_{stage}_var.csv"
    if not path.exists():
        return []
    out: list[dict[str, str]] = []
    for row in _read_csv(path):
        split = (row.get("split") or "train").strip()
        out.append(
            {
                "id": (row.get("id") or "").strip(),
                "ficha": serialize_ficha(row),
                "label": (row.get("label") or "").strip(),
                "razonamiento": (row.get("razonamiento") or "").strip(),
                "split": split,
            }
        )
    return out


def build_stage_csv(
    stage: str, variations_dir: Path, out_dir: Path, originals: dict[str, list[dict[str, str]]]
) -> Path | None:
    """Escribe el CSV final de una etapa.

    - test: variaciones con split=test si existen; si no, originales recortados a
      TEST_TARGET (estratificado).
    - train/val: variaciones a mano (la columna `split` del archivo de variaciones).
    Orden de columnas alineado al resto del repo: `split` primero, luego `case_id`.

    Devuelve `None` (omite la etapa, sin pisar el CSV) si no hay test disponible: ni
    variaciones con split=test ni originales (fuente externa ausente).
    """
    label_field = STAGE_LABEL_FIELD[stage]
    output_cols = STAGE_OUTPUT_COLUMNS[stage]
    var_rows = _read_variations(stage, variations_dir)
    # Las variaciones pueden aportar su propio split=test (holdout balanceado a mano,
    # p.ej. factibilidad para macro-F1). Si lo hacen, ese test reemplaza al recorte de
    # originales en esa etapa; el resto de etapas sigue usando los originales.
    var_train_val = [r for r in var_rows if r["split"] in {"train", "val"}]
    var_test = [r for r in var_rows if r["split"] == "test"]
    test_rows = var_test if var_test else _stratified_cap(originals[stage], TEST_TARGET)
    if not test_rows:
        return None

    def _row(r: dict[str, str], split: str) -> list[str]:
        cells = dict.fromkeys(output_cols, "")
        cells[label_field] = r["label"]
        # Razonamiento de demos (few-shot rico): solo lo traen las variaciones que lo
        # definieron; los originales (test) lo dejan vacio (ignore_in_metric igual).
        if r.get("razonamiento") and "razonamiento" in cells:
            cells["razonamiento"] = r["razonamiento"]
        return [split, r["id"], r["ficha"], *[cells[col] for col in output_cols]]

    # El harness (CSVDataLoader/CSVValidator) lee CSV con coma. La ficha contiene
    # comas y saltos de linea: csv.writer la entrecomilla automaticamente.
    out_path = out_dir / f"flujo_intents_{stage}.csv"
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["split", "case_id", "ficha", *output_cols])
        for r in var_train_val:
            writer.writerow(_row(r, r["split"]))
        for r in test_rows:
            writer.writerow(_row(r, "test"))
    return out_path


def build_all(variations_dir: Path, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    originals = build_originals_rows()
    built: dict[str, Path] = {}
    for stage in STAGE_ORDER:
        path = build_stage_csv(stage, variations_dir, out_dir, originals)
        if path is not None:
            built[stage] = path
    return built


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera datasets por etapa de flujo-intents")
    parser.add_argument(
        "--out-dir",
        default=str(get_dspy_paths().datasets),
        help="Directorio de salida (default: DSPyPaths.datasets)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    variations_dir = out_dir / "variations"

    paths = build_all(variations_dir, out_dir)
    for stage, path in paths.items():
        # El CSV de salida es coma-delimitado (lo consume el harness); se relee asi.
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        splits = Counter(r["split"] for r in rows)
        labels = Counter(r[STAGE_LABEL_FIELD[stage]] for r in rows)
        print(f"[{stage}] {path}")
        print(f"   splits={dict(splits)} labels={dict(labels)}")

    skipped = [s for s in STAGE_ORDER if s not in paths]
    if skipped:
        print(
            f"[omitidas] {', '.join(skipped)}: sin test disponible "
            f"(definir {_ORIGINALS_ENV} para regenerarlas). CSV existentes intactos."
        )


if __name__ == "__main__":
    main()
