"""Enriquece `flujo_intents_fast_gate.csv` con las preguntas P1..P5 y alto_impacto.

Arquitectura determinista (D-013): el color se DERIVA de las 5 preguntas Si/No del
Marco + alto_impacto. Esta herramienta materializa los gold de esas columnas en el CSV
de la etapa, desde dos fuentes por `case_id`:

- TEST (los TC del split=test): P1..P5 desde `fast_gate_v1.csv` (anotacion previa que
  coincide con el holdout). `alto_impacto` se deriva del color (Si sii Negro; todos los
  Negro tienen P5=Si).
- TRAIN/VAL (los VAR-FG): P1..P5 + alto_impacto desde
  `variations/flujo_intents_fast_gate_var.csv` (anotados a mano, conteo-consistentes;
  ver `make_variations._FG_PREGUNTAS`).

Idempotente y reproducible. Uso (desde la raiz del repo):
    python -m dspy_gepa_poc.scripts.enrich_fast_gate_questions
"""

import csv
from pathlib import Path

_DATASETS = Path(__file__).resolve().parent.parent / "datasets"
_MAIN = _DATASETS / "flujo_intents_fast_gate.csv"
_SRC_TEST = _DATASETS / "fast_gate_v1.csv"
_SRC_VAR = _DATASETS / "variations" / "flujo_intents_fast_gate_var.csv"
_QCOLS = ("p1", "p2", "p3", "p4", "p5")
_COLS = ["split", "case_id", "ficha", *_QCOLS, "alto_impacto", "clasificacion", "razonamiento"]


def enrich() -> Path:
    test_q = {
        r["case_id"]: {c: r[c] for c in _QCOLS}
        for r in csv.DictReader(open(_SRC_TEST, encoding="utf-8"))
    }
    var_q = {
        r["id"]: {c: r[c] for c in (*_QCOLS, "alto_impacto")}
        for r in csv.DictReader(open(_SRC_VAR, encoding="utf-8"), delimiter=";")
    }

    main_rows = list(csv.DictReader(open(_MAIN, encoding="utf-8")))
    n_test = n_var = 0
    for r in main_rows:
        cid = r["case_id"]
        es_negro = r["clasificacion"].strip() == "Negro"
        if cid in var_q:  # VAR (train/val): preguntas + alto_impacto anotados a mano
            r.update(var_q[cid])
            n_var += 1
        elif cid in test_q:  # TC (test): preguntas de fast_gate_v1, alto_impacto derivado
            r.update(test_q[cid])
            r["alto_impacto"] = "si" if es_negro else "No"
            n_test += 1
        else:
            r["alto_impacto"] = r.get("alto_impacto") or ("si" if es_negro else "No")

    with open(_MAIN, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_COLS)
        writer.writeheader()
        for r in main_rows:
            writer.writerow({c: r.get(c, "") for c in _COLS})

    print(f"[enrich] {_MAIN}")
    print(f"  train/val (VAR) enriquecidos: {n_var}")
    print(f"  test (TC) enriquecidos: {n_test}")
    print(f"  filas totales: {len(main_rows)}")
    return _MAIN


if __name__ == "__main__":
    enrich()
