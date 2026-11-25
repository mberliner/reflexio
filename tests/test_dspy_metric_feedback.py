"""
Tests para metricas con feedback textual de `dspy_gepa_poc/metrics.py` y su
integracion con `dspy.GEPA` 3.4.1 (D-024; antes 3.2.1).
"""

import logging

import dspy
import pytest

from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory
from dspy_gepa_poc.flujo_intents.ficha import _is_true
from dspy_gepa_poc.metrics import (
    _normalize_text,
    _score_set,
    _tokenize_list,
    create_dynamic_metric_with_feedback,
    create_pipeline_metric_with_feedback,
    create_rule_derived_metric_with_feedback,
    extraction_with_feedback_metric,
    sentiment_with_feedback_metric,
)
from shared.llm import LLMConfig
from tests.conftest import make_completion_response, patch_litellm_completion, repo_dspy_gepa


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

    def test_tokenize_list_multiword_tech_matches_with_or_without_years(self):
        # Vue.js:5 y Vue.js deben producir el mismo token (bug fix: no truncar a primera palabra)
        assert _tokenize_list("Vue.js:5") == _tokenize_list("Vue.js")
        assert _tokenize_list("Ruby on Rails:6") == _tokenize_list("Ruby on Rails")
        assert _tokenize_list("Next.js; TypeScript") == {"next js", "typescript"}

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
        assert type(result) is float
        assert result == 1.0

    def test_returns_prediction_when_pred_name_set(self):
        metric = create_dynamic_metric_with_feedback(["a"], default_mode="exact")
        ex = self._ex(text="t", a="x")
        pred = dspy.Prediction(a="y")
        result = metric(ex, pred, pred_name="predictor1")
        assert isinstance(result, dspy.Prediction)
        assert hasattr(result, "feedback")
        assert type(result["score"]) is float
        assert result["score"] == 0.0
        assert "a [exact]" in result.feedback

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


class TestRuleDerivedMetricWithFeedback:
    """La metrica rule_derived puntua igual que la dinamica pero el feedback explica
    la derivacion del color (caso real del audit: Rojo->Negro por alto_impacto)."""

    EVAL = ["alto_impacto", "clasificacion"]

    def _metric(self, **kw):
        return create_rule_derived_metric_with_feedback(
            self.EVAL,
            is_true_fn=_is_true,
            field_configs={"alto_impacto": {"mode": "exact"}, "clasificacion": {"mode": "exact"}},
            **kw,
        )

    def _ex(self, **kw):
        return dspy.Example(**kw).with_inputs("ficha")

    def test_returns_float_when_no_pred_name(self):
        metric = self._metric()
        ex = self._ex(ficha="f", alto_impacto="No", clasificacion="Rojo")
        pred = dspy.Prediction(alto_impacto="No", clasificacion="Rojo")
        assert metric(ex, pred) == 1.0

    def test_score_matches_field_average(self):
        # alto_impacto mal, clasificacion mal -> 0/2
        metric = self._metric()
        ex = self._ex(ficha="f", alto_impacto="No", clasificacion="Rojo")
        pred = dspy.Prediction(alto_impacto="si", clasificacion="Negro")
        assert metric(ex, pred) == 0.0

    def test_rojo_to_negro_feedback_points_at_alto_impacto(self):
        # Caso TC-R-02: gold Rojo (p5=si, alto_impacto=No), pred Negro (alto_impacto=si).
        metric = self._metric()
        ex = self._ex(
            ficha="f",
            p1="si",
            p2="si",
            p3="No",
            p4="si",
            p5="si",
            alto_impacto="No",
            clasificacion="Rojo",
        )
        pred = dspy.Prediction(
            p1="si",
            p2="si",
            p3="No",
            p4="si",
            p5="si",
            alto_impacto="si",
            clasificacion="Negro",
        )
        result = metric(ex, pred, pred_name="predictor")
        assert isinstance(result, dspy.Prediction)
        fb = result.feedback
        assert result.score == 0.0
        # Explica la derivacion y senala el juicio a corregir.
        assert "DERIVADO" in fb
        assert "override Negro" in fb
        assert "alto_impacto" in fb
        assert "Rojo" in fb and "Negro" in fb

    def test_perfect_feedback(self):
        metric = self._metric()
        ex = self._ex(ficha="f", alto_impacto="si", clasificacion="Negro")
        pred = dspy.Prediction(alto_impacto="si", clasificacion="Negro")
        result = metric(ex, pred, pred_name="p")
        assert isinstance(result, dspy.Prediction)
        assert result.score == 1.0
        assert "perfecta" in result.feedback.lower()

    def test_empty_eval_fields_returns_zero(self):
        metric = create_rule_derived_metric_with_feedback([], is_true_fn=_is_true)
        ex = self._ex(ficha="f")
        assert metric(ex, dspy.Prediction()) == 0.0

    def test_invalid_default_mode_raises(self):
        with pytest.raises(ValueError):
            create_rule_derived_metric_with_feedback(
                ["a"], is_true_fn=_is_true, default_mode="bogus"
            )


class TestOtherFeedbackMetricsContract:
    """Contrato unitario para pipeline, sentiment y extraction con y sin pred_name."""

    def test_pipeline_metric_returns_float_or_prediction(self):
        metric = create_pipeline_metric_with_feedback(
            gate_field="triage_decision",
            gate_value="avanza",
            triage_fields=["triage_decision"],
            fastgate_fields=["riesgo"],
            default_mode="exact",
        )
        ex = dspy.Example(texto="x", triage_decision="avanza", riesgo="alto").with_inputs("texto")
        pred = dspy.Prediction(triage_decision="avanza", riesgo="bajo")

        plain = metric(ex, pred)
        assert type(plain) is float
        assert plain == pytest.approx(0.3)

        fb = metric(ex, pred, pred_name="triage")
        assert isinstance(fb, dspy.Prediction)
        assert hasattr(fb, "feedback")
        assert fb.score == pytest.approx(0.3)
        assert "Errores fast_gate:" in fb.feedback

    def test_sentiment_metric_returns_float_or_prediction(self):
        ex = dspy.Example(text="bad product", sentiment="negative").with_inputs("text")
        pred = dspy.Prediction(sentiment="positive")

        plain = sentiment_with_feedback_metric(ex, pred)
        assert type(plain) is float
        assert plain == 0.0

        fb = sentiment_with_feedback_metric(ex, pred, pred_name="self")
        assert isinstance(fb, dspy.Prediction)
        assert fb.score == 0.0
        assert "Expected 'negative' but got 'positive'" in fb.feedback

    def test_extraction_metric_returns_float_or_prediction_both_branches(self):
        ex = dspy.Example(
            text="order 42 for $10",
            extracted_info={"order_id": "42", "amount": "$10"},
        ).with_inputs("text")
        pred = dspy.Prediction(order_id="42", amount="$99")

        plain = extraction_with_feedback_metric(ex, pred)
        assert type(plain) is float
        assert plain == 0.5

        fb = extraction_with_feedback_metric(ex, pred, pred_name="self")
        assert isinstance(fb, dspy.Prediction)
        assert fb.score == 0.5
        assert "amount: expected '$10', got '$99'" in fb.feedback

        # Rama sin extracted_info (linea 518).
        ex_missing = dspy.Example(text="order 42").with_inputs("text")
        assert extraction_with_feedback_metric(ex_missing, pred) == 0.0
        fb_missing = extraction_with_feedback_metric(ex_missing, pred, pred_name="self")
        assert isinstance(fb_missing, dspy.Prediction)
        assert fb_missing.score == 0.0
        assert fb_missing.feedback == "No ground truth information available."

    def test_dspy_prediction_supports_gepa_and_evaluate_operations(self):
        p1 = dspy.Prediction(score=0.25, feedback="parcial")
        p2 = dspy.Prediction(score=0.75, feedback="casi")

        assert hasattr(p1, "feedback") and hasattr(p1, "score")
        assert p1["score"] == 0.25 and p1["feedback"] == "parcial"
        assert p1.get("score") == 0.25
        assert float(p1) == 0.25
        assert sum([p1, p2]) == pytest.approx(1.0)
        assert (p1 + 0.5) == pytest.approx(0.75)
        assert (p2 / 3) == pytest.approx(0.25)
        assert p1 < p2 and p1 <= 0.25 and p2 > 0.5 and p2 >= p1


# ==================== Integracion real con dspy.GEPA (D-024) ====================

TASK_MODEL = "openai/gpt-4o-mini"
REFLECTION_MODEL = "openai/gpt-4o"


def _lm(model: str, role: str):
    return LLMConfig(model=model, api_key="test-key", role=role, cache=False).get_dspy_lm()


def _dspy_fields(**fields: str) -> str:
    body = "".join(f"[[ ## {k} ## ]]\n{v}\n\n" for k, v in fields.items())
    return body + "[[ ## completed ## ]]"


class _WarningRecorder(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _run_gepa_and_capture(monkeypatch, *, student, dataset, metric, task_reply):
    """Ejecuta `dspy.GEPA.compile` real con LM simulado (`make_completion_response`) y
    devuelve `(prompts_de_reflexion, compiled_program)`."""
    monkeypatch.setattr("shared.llm.call.time.sleep", lambda _s: None)
    reflection_prompts: list[str] = []

    def fake_completion(request, num_retries, cache=None):
        if request["model"] == REFLECTION_MODEL:
            text = "\n".join(str(m.get("content", "")) for m in request["messages"])
            reflection_prompts.append(text)
            return make_completion_response("```\nImproved instruction.\n```", "stop")
        return make_completion_response(task_reply(request), "stop")

    patch_litellm_completion(monkeypatch, fake_completion)

    gepa_logger = logging.getLogger("dspy.teleprompt.gepa.gepa_utils")
    recorder = _WarningRecorder()
    gepa_logger.addHandler(recorder)
    try:
        optimizer = repo_dspy_gepa(
            _lm(REFLECTION_MODEL, "reflection"),
            metric=metric,
            max_metric_calls=8,
            reflection_minibatch_size=2,
            track_stats=True,
            warn_on_score_mismatch=True,
            seed=0,
        )
        with dspy.context(lm=_lm(TASK_MODEL, "task")):
            compiled = optimizer.compile(student, trainset=dataset, valset=dataset)
    finally:
        gepa_logger.removeHandler(recorder)

    assert reflection_prompts, "dspy.GEPA no invoco al reflection_lm"
    for prompt in reflection_prompts:
        assert "This trajectory got a score of {" not in prompt
        assert "This trajectory got a score of " not in prompt

    # Si `feedback_fn` devolviera un dict en `score` en vez de float, `gepa_utils`
    # detectaria `fb['score'] != module_score` y emitiria este WARNING.
    assert not any("different from the overall metric score" in m for m in recorder.messages), (
        recorder.messages
    )

    details = compiled.detailed_results
    assert details.val_aggregate_scores
    assert all(type(s) is float for s in details.val_aggregate_scores)
    subscores = [
        s for row in details.val_subscores for s in (row.values() if isinstance(row, dict) else row)
    ]
    assert subscores and all(type(s) is float for s in subscores)

    return reflection_prompts, details


class TestGepaReflectionReceivesFeedback:
    """Verifica con `dspy.GEPA` real que las cinco metricas entregan su feedback como
    texto propio al Profesor y que GEPA usa scores float."""

    def test_dynamic_metric_with_feedback_reaches_reflection(self, monkeypatch):
        sig_cfg = {
            "instruction": "Responde la pregunta.",
            "inputs": [{"name": "question", "desc": "pregunta"}],
            "outputs": [{"name": "answer", "desc": "respuesta"}],
        }
        student = DynamicModuleFactory.create_module(sig_cfg, predictor_type="predict")
        metric = create_dynamic_metric_with_feedback(["answer"], default_mode="exact")
        dataset = [
            dspy.Example(question=f"q{i}", answer="si").with_inputs("question") for i in range(2)
        ]

        prompts, details = _run_gepa_and_capture(
            monkeypatch,
            student=student,
            dataset=dataset,
            metric=metric,
            task_reply=lambda _req: _dspy_fields(answer="no"),
        )

        expected_fb = (
            "## Feedback\nScore 0.00 (0/1 campos perfectos). "
            "Errores por campo:\n  - answer [exact]:"
        )
        assert any(expected_fb in p for p in prompts), prompts
        assert details.val_aggregate_scores[0] == pytest.approx(0.0)

    def test_rule_derived_metric_with_feedback_reaches_reflection(self, monkeypatch):
        sig_cfg = {
            "instruction": "Responde las preguntas del Marco.",
            "inputs": [{"name": "ficha", "desc": "ficha"}],
            "outputs": [
                {"name": "p1"},
                {"name": "p2"},
                {"name": "p3"},
                {"name": "p4"},
                {"name": "p5"},
                {"name": "alto_impacto"},
                {"name": "clasificacion"},
            ],
        }
        student = DynamicModuleFactory.create_rule_derived_module(sig_cfg, predictor_type="predict")
        metric = create_rule_derived_metric_with_feedback(
            ["alto_impacto", "clasificacion"],
            is_true_fn=_is_true,
            field_configs={"alto_impacto": {"mode": "exact"}, "clasificacion": {"mode": "exact"}},
        )
        dataset = [
            dspy.Example(
                ficha=f"caso {i}",
                p1="si",
                p2="si",
                p3="No",
                p4="si",
                p5="si",
                alto_impacto="No",
                clasificacion="Rojo",
            ).with_inputs("ficha")
            for i in range(2)
        ]

        prompts, details = _run_gepa_and_capture(
            monkeypatch,
            student=student,
            dataset=dataset,
            metric=metric,
            task_reply=lambda _req: _dspy_fields(
                p1="si", p2="si", p3="No", p4="si", p5="si", alto_impacto="si"
            ),
        )

        assert any(
            "## Feedback\nScore 0.00 (0/2 campos perfectos)." in p
            and "El color 'clasificacion' es DERIVADO por regla" in p
            and "corregi estos juicios: alto_impacto." in p
            for p in prompts
        ), prompts
        assert details.val_aggregate_scores[0] == pytest.approx(0.0)

    def test_pipeline_metric_with_feedback_reaches_reflection(self, monkeypatch):
        stages = [
            {
                "name": "triage",
                "predictor_type": "predict",
                "signature": {
                    "instruction": "Decide si avanza.",
                    "inputs": [{"name": "texto"}],
                    "outputs": [{"name": "triage_decision"}],
                },
            },
            {
                "name": "fast_gate",
                "predictor_type": "predict",
                "signature": {
                    "instruction": "Clasifica el riesgo.",
                    "inputs": [{"name": "texto"}],
                    "outputs": [{"name": "riesgo"}],
                },
            },
        ]
        routing = {
            "gate_stage": "triage",
            "gate_field": "triage_decision",
            "gate_value": "avanza",
            "skip_outputs_when_gated": {"riesgo": "no_aplica"},
        }
        student = DynamicModuleFactory.create_pipeline_module(stages, routing)
        metric = create_pipeline_metric_with_feedback(
            gate_field="triage_decision",
            gate_value="avanza",
            triage_fields=["triage_decision"],
            fastgate_fields=["riesgo"],
            default_mode="exact",
        )
        dataset = [
            dspy.Example(texto=f"intent {i}", triage_decision="avanza", riesgo="alto").with_inputs(
                "texto"
            )
            for i in range(2)
        ]

        def reply(req):
            system = str(req["messages"][0]["content"])
            if "riesgo" in system:
                return _dspy_fields(riesgo="bajo")
            return _dspy_fields(triage_decision="avanza")

        prompts, details = _run_gepa_and_capture(
            monkeypatch,
            student=student,
            dataset=dataset,
            metric=metric,
            task_reply=reply,
        )

        assert any(
            "## Feedback\nScore total 0.30.\nTriage: 1/1 campos perfectos" in p
            and "Errores fast_gate:" in p
            for p in prompts
        ), prompts
        assert details.val_aggregate_scores[0] == pytest.approx(0.3)

    def test_sentiment_with_feedback_metric_reaches_reflection(self, monkeypatch):
        student = dspy.Predict(dspy.Signature("text -> sentiment", "Classify sentiment."))
        dataset = [
            dspy.Example(text=f"awful service {i}", sentiment="negative").with_inputs("text")
            for i in range(2)
        ]

        prompts, details = _run_gepa_and_capture(
            monkeypatch,
            student=student,
            dataset=dataset,
            metric=sentiment_with_feedback_metric,
            task_reply=lambda _req: _dspy_fields(sentiment="positive"),
        )

        assert any(
            "## Feedback\nIncorrect classification. Expected 'negative' but got 'positive'." in p
            for p in prompts
        ), prompts
        assert details.val_aggregate_scores[0] == pytest.approx(0.0)

    def test_extraction_with_feedback_metric_reaches_reflection(self, monkeypatch):
        student = dspy.Predict(dspy.Signature("text -> order_id, amount", "Extract order fields."))
        dataset = [
            dspy.Example(
                text=f"Order 42 for $10 ({i})",
                extracted_info={"order_id": "42", "amount": "$10"},
            ).with_inputs("text")
            for i in range(2)
        ]

        prompts, details = _run_gepa_and_capture(
            monkeypatch,
            student=student,
            dataset=dataset,
            metric=extraction_with_feedback_metric,
            task_reply=lambda _req: _dspy_fields(order_id="42", amount="$99"),
        )

        expected_fb = (
            "## Feedback\nExtracted 1/2 fields correctly. "
            "Errors: amount: expected '$10', got '$99'."
        )
        assert any(expected_fb in p for p in prompts), prompts
        assert details.val_aggregate_scores[0] == pytest.approx(0.5)

    def test_extraction_without_ground_truth_feedback_reaches_reflection(self, monkeypatch):
        student = dspy.Predict(dspy.Signature("text -> order_id, amount", "Extract order fields."))
        dataset = [dspy.Example(text=f"Order without gt {i}").with_inputs("text") for i in range(2)]

        prompts, details = _run_gepa_and_capture(
            monkeypatch,
            student=student,
            dataset=dataset,
            metric=extraction_with_feedback_metric,
            task_reply=lambda _req: _dspy_fields(order_id="42", amount="$99"),
        )

        assert any("## Feedback\nNo ground truth information available." in p for p in prompts), (
            prompts
        )
        assert details.val_aggregate_scores[0] == pytest.approx(0.0)
