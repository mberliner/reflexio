"""Generador modular y reproducible de CVs extensos estilo modelos_cv.

Una sola fuente de verdad por candidato (CandidateSpec) -> tres salidas
derivadas: prosa (render), gold de extraccion (gold) y label de triage (rubric).
El gold es correcto por construccion (no requiere revision humana posterior).

Entry point: python -m shared.cv_synth.build_datasets
"""

from .builder import make_candidate
from .catalog import CANDIDATES, build_catalog
from .gold import extraction_gold
from .render import render
from .rubric import triage_label
from .spec import CandidateSpec

__all__ = [
    "CANDIDATES",
    "CandidateSpec",
    "build_catalog",
    "extraction_gold",
    "make_candidate",
    "render",
    "triage_label",
]
