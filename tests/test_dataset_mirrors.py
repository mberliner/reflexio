"""
Datasets espejo entre subproyectos (D-010).

Convencion (SSOT: `docs/ARCHITECTURE.md`, Invariantes): un CSV con el mismo nombre
en `dspy_gepa_poc/datasets/` y `gepa_standalone/experiments/datasets/` MUST ser
una copia identica del otro (espejo), salvo que figure como divergente
intencional. Todo par nuevo con el mismo nombre MUST clasificarse aqui; si no,
el test falla y obliga a decidir.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DSPY_DIR = ROOT / "dspy_gepa_poc" / "datasets"
GEPA_DIR = ROOT / "gepa_standalone" / "experiments" / "datasets"

# Copias deliberadas: el mismo caso medido con ambos motores.
MIRRORED = {
    "cv_extraction_v3.csv",
    "cv_profile_v3.csv",
    "email_urgency.csv",
    "fast_gate_v1.csv",
    "triage_v1.csv",
}

# Mismo nombre, esquema distinto a proposito (no sincronizar).
# cv_triage_v3: DSPy usa `cv_text` + `job_description` (multi-input) y
# `gold_verificado`; GEPA usa `text` con la JD embebida en el prompt.
INTENTIONALLY_DIVERGENT = {
    "cv_triage_v3.csv",
}


def _content(path: Path) -> bytes:
    # Normaliza fin de linea: en Windows con autocrlf el checkout puede diferir.
    return path.read_bytes().replace(b"\r\n", b"\n")


def _shared_names() -> set[str]:
    return {p.name for p in DSPY_DIR.glob("*.csv")} & {p.name for p in GEPA_DIR.glob("*.csv")}


def test_every_shared_name_is_classified():
    unclassified = _shared_names() - MIRRORED - INTENTIONALLY_DIVERGENT
    assert not unclassified, (
        f"CSV con el mismo nombre en ambos subproyectos sin clasificar: {sorted(unclassified)}. "
        "Agregarlos a MIRRORED (copia identica) o INTENTIONALLY_DIVERGENT."
    )


def test_classification_lists_are_disjoint_and_present():
    assert not MIRRORED & INTENTIONALLY_DIVERGENT
    missing = (MIRRORED | INTENTIONALLY_DIVERGENT) - _shared_names()
    assert not missing, f"Clasificados pero ausentes en algun subproyecto: {sorted(missing)}"


@pytest.mark.parametrize("name", sorted(MIRRORED))
def test_mirrored_datasets_are_identical(name):
    assert _content(DSPY_DIR / name) == _content(GEPA_DIR / name), (
        f"{name} diverge entre subproyectos: actualizar ambas copias juntas."
    )


@pytest.mark.parametrize("name", sorted(INTENTIONALLY_DIVERGENT))
def test_divergent_datasets_differ(name):
    assert _content(DSPY_DIR / name) != _content(GEPA_DIR / name), (
        f"{name} quedo identico: moverlo a MIRRORED."
    )
