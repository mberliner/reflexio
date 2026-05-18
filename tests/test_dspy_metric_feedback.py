"""
Tests para create_dynamic_metric_with_feedback (metrica con scoring por campo
y feedback textual para GEPA).
"""

import dspy
import pytest

from dspy_gepa_poc.metrics import (
    _normalize_text,
    _score_set,
    _tokenize_list,
    create_dynamic_metric_with_feedback,
)


class TestHelpers:
    def test_normalize_strips_accents_and_punct(self):
        assert _normalize_text("México, D.F.") == "mexico d f"
        assert _normalize_text("  Año  Nuevo!  ") == "ano nuevo"

    def test_tokenize_list_handles_separators(self):
        assert _tokenize_list("Python, Django; AWS") == {"python", "django", "aws"}

    def test_tokenize_list_strips_value_after_colon(self):
        # 'Python:5' -> 'python' (la clave es lo que cuenta)
        tokens = _tokenize_list("Python:5; Django:3")
        assert tokens == {"python", "django"}

    def test_tokenize_list_empty(self):
        assert _tokenize_list("") == set()
        assert _tokenize_list("   ;  , ") == set()

    def test_score_set_partial(self):
        score, missing, extra = _score_set("a, b, c, d", "a, b")
        assert score == 0.5
        assert missing == {"c", "d"}
        assert extra == set()

    def test_score_set_extras_dont_inflate(self):
        score, missing, extra = _score_set("a, b", "a, b, c, d")
        assert score == 1.0  # cubrimos todo lo esperado
        assert extra == {"c", "d"}

    def test_score_set_both_empty(self):
        score, missing, extra = _score_set("", "")
        assert score == 1.0
        assert missing == set() and extra == set()

    def test_score_set_expected_empty_actual_not(self):
        score, _, extra = _score_set("", "x, y")
        assert score == 0.0
        assert extra == {"x", "y"}


class TestMetricWithFeedback:
    def _ex(self, **kw):
        return dspy.Example(**kw).with_inputs("text")

    def test_returns_float_when_no_pred_name(self):
        metric = create_dynamic_metric_with_feedback(["a"], default_mode="normalized")
        ex = self._ex(text="t", a="hola")
        pred = dspy.Prediction(a="HOLA!")
        result = metric(ex, pred)
        assert result == 1.0

    def test_returns_dict_when_pred_name_set(self):
        metric = create_dynamic_metric_with_feedback(["a"], default_mode="exact")
        ex = self._ex(text="t", a="x")
        pred = dspy.Prediction(a="y")
        result = metric(ex, pred, pred_name="predictor1")
        assert isinstance(result, dict)
        assert result["score"] == 0.0
        assert "a [exact]" in result["feedback"]

    def test_per_field_mode_overrides(self):
        metric = create_dynamic_metric_with_feedback(
            ["skills", "nombre"],
            field_configs={
                "skills": {"mode": "set", "separators": ",;"},
                "nombre": {"mode": "normalized"},
            },
        )
        ex = self._ex(text="t", skills="Python, Django, AWS", nombre="Juan Pérez")
        # 2/3 skills correctos, nombre normalizado match
        pred = dspy.Prediction(skills="python; aws", nombre="JUAN PEREZ")
        result = metric(ex, pred)
        # skills score = 2/3, nombre = 1.0 -> avg = (0.6667 + 1.0) / 2
        assert result == pytest.approx((2 / 3 + 1.0) / 2, rel=1e-3)

    def test_perfect_extraction_feedback(self):
        metric = create_dynamic_metric_with_feedback(["a", "b"], default_mode="normalized")
        ex = self._ex(text="t", a="x", b="y")
        pred = dspy.Prediction(a="X", b="Y")
        result = metric(ex, pred, pred_name="p")
        assert result["score"] == 1.0
        assert "perfecta" in result["feedback"].lower()

    def test_feedback_lists_missing_and_extra(self):
        metric = create_dynamic_metric_with_feedback(
            ["skills"],
            field_configs={"skills": {"mode": "set"}},
        )
        ex = self._ex(text="t", skills="a, b, c")
        pred = dspy.Prediction(skills="a, d")
        result = metric(ex, pred, pred_name="p")
        fb = result["feedback"]
        assert "faltan" in fb and "sobran" in fb
        assert "b" in fb and "c" in fb and "d" in fb

    def test_invalid_default_mode_raises(self):
        with pytest.raises(ValueError):
            create_dynamic_metric_with_feedback(["a"], default_mode="bogus")

    def test_invalid_field_mode_raises(self):
        with pytest.raises(ValueError):
            create_dynamic_metric_with_feedback(["a"], field_configs={"a": {"mode": "weird"}})

    def test_empty_eval_fields_returns_zero(self):
        metric = create_dynamic_metric_with_feedback([])
        ex = self._ex(text="t")
        pred = dspy.Prediction()
        assert metric(ex, pred) == 0.0
