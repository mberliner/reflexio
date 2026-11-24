"""
SPEC-104 FR-004 (3c): atribucion de fallas de la tarea contra el baseline.

Cubre el nucleo comun `shared/llm/attribution.py` (D5): `attribute_failure`,
`BaselineProbe` (cache por caso, una sola ejecucion con hilos, `infraestructura` no
cacheado), `is_evaluated` (tabla de tratamiento) y `failure_to_dict`. Las fallas se
producen con la llamada comun real sobre respuestas y payloads reales, no con dobles.
"""

import json
import logging
import threading

import pytest

from shared.llm import (
    BaselineOutcome,
    BaselineProbe,
    FailureClass,
    LLMCallFailure,
    LLMFailure,
    RunAborted,
    attribute_failure,
    checked_completion,
    failure_to_dict,
    get_failure_tracker,
    is_evaluated,
)
from tests.conftest import make_completion_response, project_warnings
from tests.litellm_failure_payloads import ALL_FAILURE_CASES
from tests.test_litellm_failure_mapping import intercept_httpx

KWARGS = {"model": "azure/gpt-4.1-mini", "api_key": "k", "api_base": "https://x.openai.azure.com/"}
MESSAGES = [{"role": "user", "content": "hola"}]


def _payload(case_id):
    return next(c for c in ALL_FAILURE_CASES if c.id == case_id)


def _task_failure(clase, finish_reason=None, case_id=None):
    return LLMFailure(
        clase=clase, rol="task", causa=finish_reason or "X", finish_reason=finish_reason
    )


def _real_call(payload_id):
    """Llamada comun real (un solo HTTP) contra el payload: lanza `LLMCallFailure`."""
    with intercept_httpx(_payload(payload_id)):
        return checked_completion(dict(KWARGS), MESSAGES, "task", infra_retries=0)


class TestAttributeFailure:
    @pytest.mark.parametrize("clase", [FailureClass.entrada, FailureClass.presupuesto])
    def test_baseline_ok_means_candidate(self, clase):
        out = attribute_failure(_task_failure(clase, "length"), BaselineOutcome(None, None, "stop"))
        assert out.atribucion == "candidato"
        assert out.clase == clase
        assert out.finish_reason == "length"
        assert out.baseline_finish_reason == "stop"

    @pytest.mark.parametrize("clase", [FailureClass.entrada, FailureClass.presupuesto])
    def test_baseline_same_class_means_external(self, clase):
        out = attribute_failure(
            _task_failure(clase, "length"), BaselineOutcome(clase, "length", "length")
        )
        assert out.atribucion == "externa"
        assert out.clase == clase
        assert out.baseline_finish_reason == "length"

    def test_baseline_other_class_replaces_the_failure(self):
        out = attribute_failure(
            _task_failure(FailureClass.presupuesto, "length"),
            BaselineOutcome(FailureClass.infraestructura, "APIConnectionError", None),
        )
        assert out.clase == FailureClass.infraestructura
        assert out.causa == "APIConnectionError"
        assert out.atribucion is None
        assert out.finish_reason == "length"

    def test_baseline_other_attributable_class_is_external(self):
        out = attribute_failure(
            _task_failure(FailureClass.presupuesto, "length"),
            BaselineOutcome(FailureClass.entrada, "ContentPolicyViolationError", None),
        )
        assert out.clase == FailureClass.entrada
        assert out.atribucion == "externa"

    @pytest.mark.parametrize(
        "clase", [FailureClass.filtro_salida, FailureClass.sin_texto, FailureClass.infraestructura]
    )
    def test_other_classes_are_not_attributed(self, clase):
        failure = _task_failure(clase)
        assert attribute_failure(failure, BaselineOutcome(None)) == failure

    @pytest.mark.parametrize("rol", ["judge", "reflection"])
    def test_other_roles_are_not_attributed(self, rol):
        failure = LLMFailure(FailureClass.entrada, rol, "X")
        assert attribute_failure(failure, BaselineOutcome(None)) == failure


class TestIsEvaluated:
    def test_no_failure_is_evaluated(self):
        assert is_evaluated(None) is True

    @pytest.mark.parametrize(
        ("clase", "atribucion", "expected"),
        [
            (FailureClass.entrada, "candidato", True),
            (FailureClass.entrada, "externa", False),
            (FailureClass.presupuesto, "candidato", True),
            (FailureClass.presupuesto, "externa", False),
            (FailureClass.formato, None, True),
            (FailureClass.filtro_salida, None, False),
            (FailureClass.sin_texto, None, False),
            (FailureClass.infraestructura, None, False),
        ],
    )
    def test_task_table(self, clase, atribucion, expected):
        failure = LLMFailure(clase, "task", "X", atribucion=atribucion)
        assert is_evaluated(failure) is expected

    @pytest.mark.parametrize("clase", [FailureClass.formato, FailureClass.entrada])
    def test_judge_failures_are_always_ne(self, clase):
        # `formato` del juez es NE (tabla: "NE, tras los reintentos de FR-009")
        assert is_evaluated(LLMFailure(clase, "judge", "X", atribucion="candidato")) is False


class TestFailureToDict:
    def test_is_json_serializable_with_all_fields(self):
        failure = LLMFailure(
            FailureClass.entrada,
            "task",
            "ContentPolicyViolationError",
            finish_reason=None,
            case_id="c1",
            atribucion="externa",
            baseline_finish_reason="stop",
        )
        data = failure_to_dict(failure)
        assert json.loads(json.dumps(data)) == data
        assert data["clase"] == "entrada"
        assert data["clave"] == "entrada_dato"
        assert data["case_id"] == "c1"
        assert data["baseline_finish_reason"] == "stop"


class TestBaselineProbe:
    def test_one_execution_per_case_and_cached(self):
        calls = []
        probe = BaselineProbe(lambda case: calls.append(case) or "ok")
        first = probe.outcome("c1", {"x": 1})
        second = probe.outcome("c1", {"x": 1})
        assert first == second == BaselineOutcome(None, None, None)
        assert calls == [{"x": 1}]
        probe.outcome("c2", {"x": 2})
        assert len(calls) == 2

    def test_real_input_filter_is_cached_and_shared_by_both_classes(self):
        """Un `entrada` real del baseline se cachea y sirve a `entrada` y `presupuesto`."""
        calls = []

        def call_baseline(case):
            calls.append(case)
            return _real_call("azure_400_content_filter_canonico")

        probe = BaselineProbe(call_baseline)
        a = probe.attribute(_task_failure(FailureClass.entrada), "c1", "caso", is_baseline=False)
        b = probe.attribute(
            _task_failure(FailureClass.presupuesto, "length"), "c1", "caso", is_baseline=False
        )
        assert len(calls) == 1
        assert a.atribucion == "externa"
        # El baseline fue rechazado (`entrada`), el candidato se corto (`presupuesto`): la
        # falla del caso pasa a ser la del baseline.
        assert b.clase == FailureClass.entrada
        assert b.atribucion == "externa"

    def test_infrastructure_outcome_is_not_cached(self):
        responses = iter(["falla", "ok"])
        calls = []

        def call_baseline(case):
            calls.append(case)
            if next(responses) == "falla":
                return _raise_infra()
            return "ok"

        probe = BaselineProbe(call_baseline)
        first = probe.outcome("c1", "caso")
        second = probe.outcome("c1", "caso")
        third = probe.outcome("c1", "caso")
        assert first.clase == FailureClass.infraestructura
        assert second == BaselineOutcome(None, None, None)
        assert third == second
        assert len(calls) == 2

    def test_run_aborted_propagates_and_is_not_cached(self):
        get_failure_tracker().abort(LLMFailure(FailureClass.configuracion, "task", "Auth"), "t")
        calls = []

        def call_baseline(case):
            calls.append(case)
            return checked_completion(dict(KWARGS), MESSAGES, "task", infra_retries=0)

        probe = BaselineProbe(call_baseline)
        with pytest.raises(RunAborted):
            probe.outcome("c1", "caso")
        assert calls == ["caso"]

    def test_programming_errors_propagate(self):
        def call_baseline(case):
            raise KeyError("bug")

        with pytest.raises(KeyError):
            BaselineProbe(call_baseline).outcome("c1", "caso")

    def test_is_baseline_is_external_without_calling(self):
        calls = []
        probe = BaselineProbe(lambda case: calls.append(case))
        out = probe.attribute(_task_failure(FailureClass.entrada), "c1", "caso", is_baseline=True)
        assert out.atribucion == "externa"
        assert out.case_id == "c1"
        assert calls == []

    def test_non_attributable_failures_do_not_call_the_baseline(self):
        calls = []
        probe = BaselineProbe(lambda case: calls.append(case))
        out = probe.attribute(
            _task_failure(FailureClass.filtro_salida), "c1", "caso", is_baseline=False
        )
        judge = probe.attribute(
            LLMFailure(FailureClass.entrada, "judge", "X"), "c1", "caso", is_baseline=False
        )
        assert out.atribucion is None and out.case_id == "c1"
        assert judge.atribucion is None
        assert calls == []

    def test_concurrent_threads_run_the_baseline_once_per_case(self):
        started = threading.Event()
        release = threading.Event()
        calls = []

        def call_baseline(case):
            calls.append(case)
            started.set()
            release.wait(timeout=5)
            return "ok"

        probe = BaselineProbe(call_baseline)
        results = []
        threads = [
            threading.Thread(target=lambda: results.append(probe.outcome("c1", "caso")))
            for _ in range(8)
        ]
        for t in threads:
            t.start()
        started.wait(timeout=5)
        release.set()
        for t in threads:
            t.join(timeout=5)
        assert len(calls) == 1
        assert len(results) == 8
        assert set(results) == {BaselineOutcome(None, None, None)}

    def test_attribution_call_is_not_counted_as_attempt_or_failure(self):
        """D4: el probe llama directo a la capa de llamada, que nunca cuenta."""

        def call_baseline(case):
            return _real_call("azure_400_content_filter_canonico")

        probe = BaselineProbe(call_baseline)
        probe.attribute(_task_failure(FailureClass.entrada), "c1", "caso", is_baseline=False)
        snapshot = get_failure_tracker().snapshot()
        assert snapshot["counts"] == {}
        assert snapshot["attempts"]["task"] == 0

    def test_real_ok_response_means_candidate_attribution(self, monkeypatch):
        monkeypatch.setattr(
            "litellm.completion", lambda *a, **k: make_completion_response("bien", "stop")
        )
        probe = BaselineProbe(
            lambda case: checked_completion(dict(KWARGS), MESSAGES, "task", infra_retries=0)
        )
        out = probe.attribute(
            _task_failure(FailureClass.presupuesto, "length"), "c1", "caso", is_baseline=False
        )
        assert out.atribucion == "candidato"
        assert is_evaluated(out) is True


def _raise_infra():
    """Falla `infraestructura` real: error de conexion del transporte HTTP."""
    case = next(c for c in ALL_FAILURE_CASES if c.case_type == "transport_error")
    with intercept_httpx(case):
        return checked_completion(dict(KWARGS), MESSAGES, "task", infra_retries=0)


def test_call_layer_failure_is_an_llm_call_failure():
    with pytest.raises(LLMCallFailure) as exc_info:
        _real_call("azure_400_content_filter_canonico")
    assert exc_info.value.failure.clase == FailureClass.entrada


def test_attribution_logs_both_finish_reasons_once(caplog):
    failure = LLMFailure(
        FailureClass.presupuesto,
        "task",
        "length",
        finish_reason="length",
        case_id="c1",
        atribucion="candidato",
        baseline_finish_reason="stop",
    )
    with caplog.at_level(logging.WARNING):
        get_failure_tracker().record(failure)
    records = project_warnings(caplog)
    assert len(records) == 1
    message = records[0].getMessage()
    assert "finish_reason=length" in message
    assert "baseline_finish_reason=stop" in message
    assert "clave=presupuesto_candidato" in message
