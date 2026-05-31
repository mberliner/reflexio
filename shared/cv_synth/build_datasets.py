"""Entry point: genera los datasets v3 (triage, profile, extraction) del catalogo.

Uso (desde la raiz del repo):
    python -m shared.cv_synth.build_datasets

Los TRES datasets salen del MISMO catalogo de CandidateSpec, asi quedan alineados
candidato a candidato:
  - cv_triage_v3.csv   (DSPy)  -> dspy_gepa_poc/datasets/
  - cv_profile_v3.csv  (DSPy)  -> dspy_gepa_poc/datasets/
  - cv_extraction_v3.csv (GEPA standalone, subset de 5 campos)
                               -> gepa_standalone/experiments/datasets/
El gold se deriva del spec (correcto por construccion): gold_verificado="derivado".
"""

from __future__ import annotations

import csv
from collections import Counter

from shared.paths import get_dspy_paths, get_gepa_paths

from .catalog import CANDIDATES
from .gold import extraction_gold
from .render import render
from .rubric import JOB_DESCRIPTION, triage_label

TRIAGE_HEADER = [
    "split", "cv_text", "job_description", "fit_label", "justificacion", "gold_verificado",
]
PROFILE_HEADER = [
    "split", "text", "nombre", "email", "años_experiencia", "skills",
    "educacion_principal", "seniority_declarado", "stack_principal", "idiomas",
    "ubicacion", "industria_previa",
]
# Subset de 5 campos para el caso GEPA standalone (paridad con cv_extraction_v2).
EXTRACTION_HEADER = [
    "split", "text", "nombre", "email", "años_experiencia", "skills",
    "educacion_principal", "gold_verificado",
]


def _write(path, header, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        w.writerow(header)
        w.writerows(rows)
    print(f"Escrito: {path} ({len(rows)} filas)")


def main() -> int:
    dspy_datasets = get_dspy_paths().datasets
    gepa_datasets = get_gepa_paths().datasets

    triage_rows = []
    profile_rows = []
    extraction_rows = []
    for spec in CANDIDATES:
        cv_text = render(spec)
        label, justificacion = triage_label(spec)
        triage_rows.append(
            [spec.split, cv_text, JOB_DESCRIPTION, label, justificacion, "derivado"]
        )
        g = extraction_gold(spec)
        profile_rows.append([spec.split, cv_text] + [g[k] for k in PROFILE_HEADER[2:]])
        extraction_rows.append(
            [spec.split, cv_text, *[g[k] for k in EXTRACTION_HEADER[2:-1]], "derivado"]
        )

    _write(dspy_datasets / "cv_triage_v3.csv", TRIAGE_HEADER, triage_rows)
    _write(dspy_datasets / "cv_profile_v3.csv", PROFILE_HEADER, profile_rows)
    _write(gepa_datasets / "cv_extraction_v3.csv", EXTRACTION_HEADER, extraction_rows)

    for name, rows in [
        ("triage", triage_rows),
        ("profile", profile_rows),
        ("extraction", extraction_rows),
    ]:
        by_split = Counter(r[0] for r in rows)
        print(f"  {name}: {dict(by_split)} (total {len(rows)})")
    label_by_split = {}
    for r in triage_rows:
        label_by_split.setdefault(r[0], Counter())[r[3]] += 1
    for split, c in label_by_split.items():
        print(f"  triage labels {split}: {dict(c)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
