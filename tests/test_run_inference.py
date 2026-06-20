"""Tests de `build_inference_module`: respeta `module.type` en produccion (D-015b).

Deterministas y sin LLM: se reemplaza el predictor interno por uno falso para
verificar que el modulo `rule_derived` DERIVA el color con la regla del Marco y que
el modulo `dynamic` no lo toca.
"""

from __future__ import annotations

import dspy
import pytest

from dspy_gepa_poc.run_inference import build_inference_module


def _signature_config() -> dict:
    """Signature minima del Fast Gate: p1..p5 + alto_impacto + clasificacion."""
    return {
        "instruction": "Responde las preguntas del Fast Gate.",
        "inputs": [{"name": "ficha", "desc": "Ficha de Intent."}],
        "outputs": [
            {"name": "p1", "desc": "Si/No"},
            {"name": "p2", "desc": "Si/No"},
            {"name": "p3", "desc": "Si/No"},
            {"name": "p4", "desc": "Si/No"},
            {"name": "p5", "desc": "Si/No"},
            {"name": "alto_impacto", "desc": "Si/No"},
            {"name": "razonamiento", "desc": "Justificacion."},
            {"name": "clasificacion", "desc": "Color derivado."},
        ],
    }


class _FakePredictor:
    """Predictor falso: devuelve respuestas fijas sin llamar al LLM."""

    def __init__(self, **answers: str):
        self._answers = answers

    def __call__(self, **_kwargs):
        return dspy.Prediction(**self._answers)


def test_rule_derived_config_uses_rule_derived_module():
    """Un config `rule_derived` deriva `clasificacion` con la regla, no la emite el LLM."""
    raw_config = {
        "module": {"type": "rule_derived"},
        "signature": _signature_config(),
        "optimization": {"predictor_type": "cot"},
    }

    module = build_inference_module(raw_config)
    # P5=Si + alto_impacto=Si -> Negro (override del conteo).
    module.predictor = _FakePredictor(
        p1="No", p2="No", p3="No", p4="No", p5="si", alto_impacto="si", razonamiento="x"
    )

    pred = module(ficha="cualquiera")

    assert pred.clasificacion == "Negro"


def test_rule_derived_counts_for_color():
    """Sin alto impacto, el color sale del conteo de Si (2 -> Amarillo)."""
    raw_config = {
        "module": {"type": "rule_derived"},
        "signature": _signature_config(),
        "optimization": {"predictor_type": "cot"},
    }

    module = build_inference_module(raw_config)
    module.predictor = _FakePredictor(
        p1="si", p2="si", p3="No", p4="No", p5="No", alto_impacto="No", razonamiento="x"
    )

    pred = module(ficha="cualquiera")

    assert pred.clasificacion == "Amarillo"


def test_dynamic_config_does_not_derive_color():
    """Un config `dynamic` devuelve lo que emite el predictor, sin derivar."""
    raw_config = {
        "module": {"type": "dynamic"},
        "signature": _signature_config(),
        "optimization": {"predictor_type": "cot"},
    }

    module = build_inference_module(raw_config)
    module.predictor = _FakePredictor(clasificacion="Verde")

    pred = module(ficha="cualquiera")

    # El generico no toca el output: refleja lo que dio el predictor.
    assert pred.clasificacion == "Verde"


def test_default_module_type_is_dynamic():
    """Sin seccion `module`, se asume `dynamic` (comportamiento previo preservado)."""
    raw_config = {
        "signature": _signature_config(),
        "optimization": {"predictor_type": "cot"},
    }

    module = build_inference_module(raw_config)
    module.predictor = _FakePredictor(clasificacion="Rojo")

    pred = module(ficha="cualquiera")

    assert pred.clasificacion == "Rojo"


def test_rule_derived_requires_question_fields():
    """`rule_derived` exige p1..p5 + alto_impacto en los outputs."""
    bad_config = {
        "module": {"type": "rule_derived"},
        "signature": {
            "instruction": "x",
            "inputs": [{"name": "ficha"}],
            "outputs": [{"name": "clasificacion", "desc": "color"}],
        },
    }

    with pytest.raises(ValueError, match="rule_derived requiere"):
        build_inference_module(bad_config)
