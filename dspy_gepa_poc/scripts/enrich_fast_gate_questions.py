"""Enriquece `flujo_intents_fast_gate.csv` con las preguntas P1..P5 y alto_impacto.

Iteracion 1 de la arquitectura determinista (D-013): el color se DERIVA de las 5
preguntas Si/No del Marco. El holdout (los TC del split=test) ya tiene P1..P5 anotadas
en `fast_gate_v1.csv`; aqui se unen por `case_id`. La columna `alto_impacto` se deriva
del color gold (Si sii el caso es Negro; todos los Negro tienen P5=Si). El train/val
(VAR-FG) se anota por construccion en `make_variations.py` (Iteracion 2): aqui quedan
con P1..P5 vacias y `alto_impacto` derivado del color.

Idempotente y reproducible. Uso (desde la raiz del repo):
    python -m dspy_gepa_poc.scripts.enrich_fast_gate_questions
"""

import csv
from pathlib import Path

_DATASETS = Path(__file__).resolve().parent.parent / "datasets"
_MAIN = _DATASETS / "flujo_intents_fast_gate.csv"
_SRC = _DATASETS / "fast_gate_v1.csv"
_QCOLS = ("p1", "p2", "p3", "p4", "p5")
_COLS = ["split", "case_id", "ficha", *_QCOLS, "alto_impacto", "clasificacion", "razonamiento"]


def enrich() -> Path:
    src_rows = list(csv.DictReader(open(_SRC, encoding="utf-8")))
    q_by_id = {r["case_id"]: {c: r[c] for c in _QCOLS} for r in src_rows}

    main_rows = list(csv.DictReader(open(_MAIN, encoding="utf-8")))
    enriched_test = 0
    for r in main_rows:
        q = q_by_id.get(r["case_id"])
        if q is not None:
            r.update(q)
            if r["split"] == "test":
                enriched_test += 1
        # alto_impacto consistente con el color: Si sii Negro (todos los Negro tienen P5=Si).
        r["alto_impacto"] = "si" if r["clasificacion"].strip() == "Negro" else "No"

    with open(_MAIN, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_COLS)
        writer.writeheader()
        for r in main_rows:
            writer.writerow({c: r.get(c, "") for c in _COLS})

    print(f"[enrich] {_MAIN}")
    print(f"  test enriquecidos con P1..P5: {enriched_test}")
    print(f"  filas totales: {len(main_rows)}")
    return _MAIN


if __name__ == "__main__":
    enrich()
