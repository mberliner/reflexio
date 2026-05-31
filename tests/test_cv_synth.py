"""Tests del generador modular de CVs (shared.cv_synth).

Verifican: reproducibilidad byte a byte, consistencia rubric/intencion, que el
gold derivado refleje el spec y que los hechos decisivos aparezcan en la prosa.
"""

from __future__ import annotations

import pytest

from shared.cv_synth import (
    CANDIDATES,
    build_catalog,
    extraction_gold,
    make_candidate,
    render,
    triage_label,
)

VALID_LABELS = {"fit_alto", "fit_medio", "no_fit"}


def _sample_spec():
    return make_candidate(
        idx=0, split="train", discipline="backend", primary_language="Python",
        years_total=7, years_relevant=7, frameworks=("Django", "FastAPI"),
        databases=("PostgreSQL", "Redis"), english="c1", city="Buenos Aires",
        seniority="senior", industria="Fintech", extra_skills=("Docker", "AWS"),
    )


def test_render_is_reproducible():
    spec = _sample_spec()
    assert render(spec) == render(spec)


def test_catalog_is_reproducible():
    a = build_catalog()
    b = build_catalog()
    assert [s.nombre for s in a] == [s.nombre for s in b]
    assert [render(s) for s in a] == [render(s) for s in b]


def test_catalog_balanced_and_consistent():
    # 57 candidatos, balanceados por clase dentro de cada split.
    assert len(CANDIDATES) == 57
    for spec in CANDIDATES:
        label, _ = triage_label(spec)
        assert label in VALID_LABELS


@pytest.mark.parametrize("label", ["fit_alto", "fit_medio", "no_fit"])
def test_each_label_present(label):
    labels = [triage_label(s)[0] for s in CANDIDATES]
    assert label in labels


def test_gold_reflects_spec():
    spec = _sample_spec()
    g = extraction_gold(spec)
    assert g["nombre"] == spec.nombre
    assert g["email"] == spec.email
    assert g["años_experiencia"] == "7"
    assert g["ubicacion"] == "Buenos Aires, Argentina"
    assert g["industria_previa"] == "Fintech"
    assert "ingles:c1" in g["idiomas"]
    assert g["stack_principal"].startswith("Python:7")


def test_decisive_facts_appear_in_prose():
    spec = _sample_spec()
    text = render(spec)
    assert "Buenos Aires" in text
    assert "Django" in text or "FastAPI" in text
    assert "PostgreSQL" in text


def test_rubric_fit_alto():
    spec = _sample_spec()
    label, _ = triage_label(spec)
    assert label == "fit_alto"


def test_rubric_single_fail_is_medio():
    # Mismo perfil pero ingles A2 -> falla un solo eje -> fit_medio.
    spec = make_candidate(
        idx=1, split="val", discipline="backend", primary_language="Python",
        years_total=7, years_relevant=7, frameworks=("Django",),
        databases=("PostgreSQL",), english="a2", city="Lima",
        seniority="senior", industria="Fintech",
    )
    assert triage_label(spec)[0] == "fit_medio"


def test_rubric_misaligned_language_is_no_fit():
    spec = make_candidate(
        idx=2, split="test", discipline="backend", primary_language="Java",
        years_total=8, years_relevant=8, frameworks=("Spring Boot",),
        databases=("PostgreSQL",), english="c1", city="Bogota",
        seniority="senior", industria="Backend",
    )
    assert triage_label(spec)[0] == "no_fit"


def test_qa_with_python_is_no_fit():
    # Trampa: QA que usa Python para scripting NO es backend Python.
    spec = make_candidate(
        idx=3, split="test", discipline="qa", primary_language="Python",
        years_total=6, years_relevant=6, frameworks=("Selenium",),
        databases=("PostgreSQL",), english="c1", city="Santiago",
        seniority="senior", industria="QA", extra_skills=("Python", "Jira"),
    )
    assert triage_label(spec)[0] == "no_fit"
