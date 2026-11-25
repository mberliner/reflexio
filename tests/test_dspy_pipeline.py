"""
Modo `pipeline` de dspy_gepa_poc (D-011): composicion de etapas con gate,
metrica condicional jerarquica y validacion del YAML.

Los predictores se reemplazan por dobles que registran las llamadas: se verifica
el routing sin LLM.
"""

import copy
from types import SimpleNamespace

import dspy
import pytest

from dspy_gepa_poc.config_schema import ConfigValidator
from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory
from dspy_gepa_poc.metrics import create_pipeline_metric_with_feedback

STAGES = [
    {
        "name": "triage",
        "predictor_type": "predict",
        "signature": {
            "instruction": "Decide si avanza.",
            "inputs": [{"name": "texto", "desc": "Intent."}],
            "outputs": [{"name": "triage_decision", "desc": "avanza o rechaza."}],
        },
    },
    {
        "name": "fast_gate",
        "signature": {
            "instruction": "Clasifica el riesgo.",
            "inputs": [
                {"name": "texto", "desc": "Intent."},
                {"name": "contexto", "desc": "Contexto."},
            ],
            "outputs": [
                {"name": "riesgo", "desc": "Nivel."},
                {"name": "motivo", "desc": "Motivo."},
            ],
        },
    },
]
ROUTING = {
    "gate_stage": "triage",
    "gate_field": "triage_decision",
    "gate_value": "avanza",
    "skip_outputs_when_gated": {"riesgo": "no_aplica"},
}


class _FakePredictor:
    def __init__(self, **outputs):
        self.outputs = outputs
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(**self.outputs)


def _module_with_fakes(gate_output: str):
    module = DynamicModuleFactory.create_pipeline_module(STAGES, ROUTING)
    triage = _FakePredictor(triage_decision=gate_output)
    fast_gate = _FakePredictor(riesgo="alto", motivo="datos sensibles")
    module.triage = triage
    module.fast_gate = fast_gate
    return module, triage, fast_gate


class TestCreatePipelineModule:
    def test_requires_two_stages(self):
        with pytest.raises(ValueError, match="at least 2 stages"):
            DynamicModuleFactory.create_pipeline_module(STAGES[:1], ROUTING)

    def test_unknown_gate_stage_raises(self):
        with pytest.raises(ValueError, match="gate_stage='nope'"):
            DynamicModuleFactory.create_pipeline_module(STAGES, {**ROUTING, "gate_stage": "nope"})

    def test_one_named_predictor_per_stage_with_its_type(self):
        module = DynamicModuleFactory.create_pipeline_module(STAGES, ROUTING)
        assert isinstance(module.triage, dspy.Predict)
        # predictor_type omitido -> cot
        assert isinstance(module.fast_gate, dspy.ChainOfThought)
        names = {name.split(".")[0] for name, _ in module.named_predictors()}
        assert names == {"triage", "fast_gate"}

    def test_gate_open_runs_post_stages_with_their_inputs(self):
        module, triage, fast_gate = _module_with_fakes(" avanza ")
        pred = module(texto="t", contexto="c", extra="ignorado")

        assert triage.calls == [{"texto": "t"}]
        assert fast_gate.calls == [{"texto": "t", "contexto": "c"}]
        assert pred.triage_decision == " avanza "
        assert pred.riesgo == "alto"
        assert pred.motivo == "datos sensibles"

    def test_gate_closed_skips_post_stages_and_injects_fixed_values(self):
        module, _triage, fast_gate = _module_with_fakes("rechaza")
        pred = module(texto="t", contexto="c")

        assert fast_gate.calls == []
        assert pred.triage_decision == "rechaza"
        assert pred.riesgo == "no_aplica"
        # output sin valor fijo configurado -> cadena vacia
        assert pred.motivo == ""


class TestPipelineMetric:
    def _metric(self, **kwargs):
        params = {
            "gate_field": "triage_decision",
            "gate_value": "avanza",
            "triage_fields": ["triage_decision"],
            "fastgate_fields": ["riesgo"],
            "default_mode": "exact",
        }
        params.update(kwargs)
        return create_pipeline_metric_with_feedback(**params)

    def test_case_that_advances_combines_both_stages_with_weight(self):
        metric = self._metric(triage_weight=0.5)
        ex = dspy.Example(triage_decision="avanza", riesgo="alto")
        assert metric(ex, dspy.Prediction(triage_decision="avanza", riesgo="alto")) == 1.0
        assert metric(ex, dspy.Prediction(triage_decision="rechaza", riesgo="alto")) == 0.5
        assert metric(ex, dspy.Prediction(triage_decision="avanza", riesgo="bajo")) == 0.5

    def test_case_that_does_not_advance_only_scores_triage(self):
        metric = self._metric()
        ex = dspy.Example(triage_decision="rechaza", riesgo="no_aplica")
        pred = dspy.Prediction(triage_decision="rechaza", riesgo="cualquier cosa")
        assert metric(ex, pred) == 1.0

        fb = metric(ex, pred, pred_name="triage")
        assert fb.score == 1.0
        assert "Fast Gate: omitido" in fb.feedback

    def test_invalid_modes_are_rejected(self):
        with pytest.raises(ValueError, match="default_mode invalido"):
            self._metric(default_mode="nope")
        with pytest.raises(ValueError, match="Modo invalido para campo 'riesgo'"):
            self._metric(field_configs={"riesgo": {"mode": "nope"}})


class TestValidatePipeline:
    BASE = {
        "case": {"name": "p", "title": "P"},
        "module": {"type": "pipeline"},
        "stages": STAGES,
        "routing": ROUTING,
        "data": {"csv_filename": "x.csv", "input_column": "texto"},
        "optimization": {"max_metric_calls": 10},
    }

    def _errors(self, mutate=None):
        cfg = copy.deepcopy(self.BASE)
        if mutate:
            mutate(cfg)
        return ConfigValidator.validate(cfg)

    def test_valid_pipeline_passes(self):
        assert self._errors() == []

    @pytest.mark.parametrize(
        ("mutate", "expected"),
        [
            (lambda c: c.update(stages=c["stages"][:1]), "at least 2 entries"),
            (lambda c: c["stages"][1].pop("name"), "missing 'name'"),
            (lambda c: c["stages"][1].update(name="triage"), "duplicated"),
            (lambda c: c["stages"][1].pop("signature"), "missing 'signature'"),
            (lambda c: c.pop("routing"), "requires 'routing'"),
            (lambda c: c["routing"].pop("gate_value"), "missing required key: 'gate_value'"),
            (lambda c: c["routing"].update(gate_stage="nope"), "gate_stage='nope' not in stages"),
            (
                lambda c: c["routing"].update(gate_field="riesgo"),
                "gate_field='riesgo' not in outputs",
            ),
            (
                lambda c: c["routing"].update(skip_outputs_when_gated={"triage_decision": "x"}),
                "does not match any output of post-gate stages",
            ),
        ],
    )
    def test_structural_errors_are_reported(self, mutate, expected):
        errors = self._errors(mutate)
        assert any(expected in e for e in errors), errors
