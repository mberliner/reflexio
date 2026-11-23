"""
Tests de SPEC-104 (1a, GREEN en 1c): clasificador de la capa 1 y `FailureTracker`.

Sin red: los payloads HTTP de `tests/litellm_failure_payloads.py` (102 casos) se
inyectan en el transporte HTTP (`httpx.Client.send`) y la excepcion o respuesta
real de LiteLLM se pasa al clasificador de `shared/llm/failures.py` (FR-001,
FR-015, SC-009).

Los nombres siguen las decisiones D1 y D2 del plan
(`docs/plans/PLAN_SPEC-104_fallas_tecnicas_justas.md`), confirmadas o
corregidas en la subfase 1b. Roles del contador: los del codigo (`task`,
`reflection`, `judge`), como en `shared/llm/usage.py`.

"""

from __future__ import annotations

import importlib
import json
import threading
from collections.abc import Iterator
from types import ModuleType
from typing import Any

import dspy
import litellm
import pytest

from shared.llm.config import LLMConfig
from tests.litellm_failure_payloads import (
    ALL_FAILURE_CASES,
    PROVIDER_KWARGS,
    FailurePayloadCase,
)
from tests.test_litellm_failure_mapping import _call_completion, intercept_httpx


def _failures() -> ModuleType:
    return importlib.import_module("shared.llm.failures")


@pytest.fixture(autouse=True)
def _isolate_litellm_globals(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(litellm, "drop_params", False)
    monkeypatch.setattr(litellm, "num_retries", None)
    monkeypatch.setattr(litellm, "suppress_debug_info", True)
    yield


@pytest.fixture
def tracker() -> Iterator[Any]:
    t = _failures().get_failure_tracker()
    t.reset()
    yield t
    t.reset()


def _classify_case(case: FailurePayloadCase) -> Any:
    """Corre el payload contra LiteLLM real (sin red) y clasifica el resultado."""
    f = _failures()
    resp, exc, _ = _call_completion(
        case, drop_params=True, extra_kwargs={"num_retries": 0, "drop_params": True}
    )
    if exc is not None:
        return f.classify_exception(exc)
    return f.classify_response(resp)


def _expected(case: FailurePayloadCase) -> Any:
    """Clase esperada o `None` si el payload es una respuesta sana."""
    return None if case.spec104_class == "ok" else _failures().FailureClass(case.spec104_class)


# ==================== Clasificador de capa 1 sobre los 102 payloads ====================


class TestClassifierOnPayloads:
    @pytest.mark.parametrize("case", ALL_FAILURE_CASES, ids=lambda c: c.id)
    def test_layer1_class_matches_expected(self, case: FailurePayloadCase) -> None:
        assert _classify_case(case) == _expected(case)

    def test_failure_class_values_match_spec(self) -> None:
        names = {c.value for c in _failures().FailureClass}
        assert names == {
            "configuracion",
            "entrada",
            "infraestructura",
            "filtro_salida",
            "presupuesto",
            "sin_texto",
            "formato",
        }


class TestClassifierEdgeCases:
    def test_none_response_is_configuracion(self) -> None:
        # Regla 3: `litellm.completion` que devuelve None (bug 422 + drop_params)
        f = _failures()
        assert f.classify_response(None) == f.FailureClass.configuracion

    def test_unclassified_exception_is_configuracion(self) -> None:
        f = _failures()
        assert f.classify_exception(RuntimeError("boom")) == f.FailureClass.configuracion

    @pytest.mark.parametrize("body", [None, "texto plano", ["lista"], 42])
    def test_non_dict_body_is_read_defensively(self, body: Any) -> None:
        f = _failures()
        exc = _bad_request_with_body(body)
        assert f.classify_exception(exc) == f.FailureClass.configuracion

    def test_bad_request_body_code_content_filter_is_entrada(self) -> None:
        f = _failures()
        exc = _bad_request_with_body({"code": "content_filter"})
        assert f.classify_exception(exc) == f.FailureClass.entrada

    def test_dspy_wrapped_context_window_is_entrada_via_cause(self) -> None:
        # dspy==3.2.1 envuelve litellm.ContextWindowExceededError y lo deja en __cause__
        f = _failures()
        case = next(
            c
            for c in ALL_FAILURE_CASES
            if c.expected_exception == "ContextWindowExceededError" and c.case_type == "http_error"
        )
        cfg = LLMConfig(**{**PROVIDER_KWARGS[case.provider], "role": "task", "cache": False})
        lm = cfg.get_dspy_lm()
        with (
            intercept_httpx(case),
            pytest.raises(dspy.utils.exceptions.ContextWindowExceededError) as exc_info,
        ):
            lm("hello")
        assert f.classify_exception(exc_info.value) == f.FailureClass.entrada

    def test_response_without_refusal_attribute_is_read_defensively(self) -> None:
        f = _failures()

        class _Msg:
            content = "texto"

        class _Choice:
            finish_reason = "stop"
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        assert f.classify_response(_Resp()) is None

    def test_refusal_wins_over_stop_without_text(self) -> None:
        f = _failures()

        class _Msg:
            content = None
            refusal = "no puedo ayudar"

        class _Choice:
            finish_reason = "stop"
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        assert f.classify_response(_Resp()) == f.FailureClass.filtro_salida


def _bad_request_with_body(body: Any) -> Exception:
    exc = litellm.BadRequestError(message="bad request", model="m", llm_provider="azure")
    exc.body = body
    return exc


# ==================== LLMFailure / LLMCallFailure ====================


class TestFailureTypes:
    def test_llm_failure_is_frozen(self) -> None:
        f = _failures()
        failure = f.LLMFailure(
            clase=f.FailureClass.sin_texto,
            rol="task",
            causa="EmptyContent",
            finish_reason="stop",
            case_id=None,
            atribucion=None,
        )
        with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError
            failure.rol = "judge"  # type: ignore[misc]

    def test_call_failure_carries_the_failure(self) -> None:
        f = _failures()
        failure = f.LLMFailure(
            clase=f.FailureClass.presupuesto,
            rol="judge",
            causa="length",
            finish_reason="length",
            case_id=None,
            atribucion=None,
        )
        err = f.LLMCallFailure(failure)
        assert isinstance(err, Exception)
        assert err.failure == failure


# ==================== FailureTracker ====================


def _failure(f: ModuleType, clase: str, rol: str = "task", **kw: Any) -> Any:
    return f.LLMFailure(
        clase=f.FailureClass(clase),
        rol=rol,
        causa=kw.pop("causa", "test"),
        finish_reason=kw.pop("finish_reason", None),
        case_id=kw.pop("case_id", None),
        atribucion=kw.pop("atribucion", None),
    )


def _attempts(tracker: Any, rol: str, n: int) -> None:
    for _ in range(n):
        tracker.record_attempt(rol)


class TestFailureTrackerCounts:
    def test_counts_by_class_and_role(self, tracker: Any) -> None:
        f = _failures()
        _attempts(tracker, "task", 100)
        _attempts(tracker, "judge", 100)
        for _ in range(3):
            tracker.record(_failure(f, "sin_texto", "task"))
        tracker.record(_failure(f, "sin_texto", "judge"))
        counts = tracker.snapshot()["counts"]
        assert counts["sin_texto"]["task"] == 3
        assert counts["sin_texto"]["judge"] == 1
        assert not tracker.aborted

    def test_entrada_dato_counts_unique_cases(self, tracker: Any) -> None:
        f = _failures()
        _attempts(tracker, "task", 100)
        for case_id in ("a", "a", "b", "a", "b"):
            tracker.record(_failure(f, "entrada", case_id=case_id, atribucion="externa"))
        snap = tracker.snapshot()
        assert sorted(snap["entrada_dato"]) == ["a", "b"]

    def test_snapshot_is_json_serializable(self, tracker: Any) -> None:
        f = _failures()
        tracker.record_attempt("task")
        tracker.record(_failure(f, "infraestructura"))
        json.dumps(tracker.snapshot())

    def test_reset_clears_counts_attempts_and_abort(self, tracker: Any) -> None:
        f = _failures()
        tracker.abort(_failure(f, "configuracion"), "401")
        tracker.record_attempt("task")
        tracker.reset()
        snap = tracker.snapshot()
        assert not tracker.aborted
        assert snap["counts"] == {} or all(
            v == 0 for by_role in snap["counts"].values() for v in by_role.values()
        )
        assert snap["entrada_dato"] == []

    def test_get_failure_tracker_is_singleton(self) -> None:
        f = _failures()
        assert f.get_failure_tracker() is f.get_failure_tracker()

    def test_concurrent_recording_is_exact(self, tracker: Any) -> None:
        f = _failures()
        n_threads, per_thread = 8, 100

        def worker() -> None:
            for _ in range(per_thread):
                tracker.record_attempt("task")
                # `formato` en tarea no tiene umbral: no aborta
                tracker.record(_failure(f, "formato"))

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert tracker.snapshot()["counts"]["formato"]["task"] == n_threads * per_thread
        assert not tracker.aborted


class TestFailureTrackerThresholds:
    def test_configuracion_aborts_on_first_occurrence(self, tracker: Any) -> None:
        f = _failures()
        tracker.abort(
            _failure(f, "configuracion", "reflection", causa="AuthenticationError"), "401"
        )
        assert tracker.aborted
        with pytest.raises(f.RunAborted) as exc_info:
            tracker.check_abort()
        msg = str(exc_info.value)
        assert "configuracion" in msg
        assert "reflection" in msg

    def test_check_abort_is_silent_when_not_aborted(self, tracker: Any) -> None:
        tracker.check_abort()

    def test_rate_above_default_threshold_aborts(self, tracker: Any) -> None:
        # infraestructura / task: umbral 0.10, minimo 20 intentos
        f = _failures()
        _attempts(tracker, "task", 20)
        for _ in range(2):  # 2/20 = 0.10, no supera
            tracker.record(_failure(f, "infraestructura"))
        assert not tracker.aborted
        tracker.record(_failure(f, "infraestructura"))  # 3/20 = 0.15
        assert tracker.aborted
        with pytest.raises(f.RunAborted) as exc_info:
            tracker.check_abort()
        assert "infraestructura" in str(exc_info.value)

    def test_below_min_attempts_does_not_abort(self, tracker: Any) -> None:
        f = _failures()
        _attempts(tracker, "task", 5)
        for _ in range(5):
            tracker.record(_failure(f, "presupuesto"))
        assert not tracker.aborted

    def test_presupuesto_default_threshold_is_stricter(self, tracker: Any) -> None:
        # presupuesto / task: umbral 0.05, minimo 20 intentos
        f = _failures()
        _attempts(tracker, "task", 20)
        tracker.record(_failure(f, "presupuesto"))  # 1/20 = 0.05, no supera
        assert not tracker.aborted
        tracker.record(_failure(f, "presupuesto"))  # 2/20 = 0.10
        assert tracker.aborted

    def test_reflection_sums_all_classes_against_half(self, tracker: Any) -> None:
        # reflexion: cualquier clase sumada, umbral 0.50, minimo 4 intentos
        f = _failures()
        _attempts(tracker, "reflection", 4)
        tracker.record(_failure(f, "formato", "reflection"))
        tracker.record(_failure(f, "sin_texto", "reflection"))  # 2/4 = 0.50, no supera
        assert not tracker.aborted
        tracker.record(_failure(f, "infraestructura", "reflection"))  # 3/4
        assert tracker.aborted

    def test_task_candidate_attributed_classes_have_no_threshold(self, tracker: Any) -> None:
        f = _failures()
        _attempts(tracker, "task", 100)
        for _ in range(100):
            tracker.record(_failure(f, "entrada", atribucion="candidato"))
            tracker.record(_failure(f, "presupuesto", atribucion="candidato"))
            tracker.record(_failure(f, "formato"))
        assert not tracker.aborted

    def test_entrada_dato_threshold_uses_unique_cases(self, tracker: Any) -> None:
        # 1b: tasa = casos unicos entrada_dato / casos unicos intentados en tarea
        # (no intentos). 5 candidatos sobre los mismos 20 casos: 100 intentos.
        f = _failures()
        for _ in range(5):
            for i in range(20):
                tracker.record_attempt("task", case_id=f"c{i}")
        for _ in range(10):  # el mismo caso repetido no sube la tasa
            tracker.record(_failure(f, "entrada", case_id="c0", atribucion="externa"))
        tracker.record(_failure(f, "entrada", case_id="c1", atribucion="externa"))
        assert not tracker.aborted  # 2/20 = 0.10, no supera
        tracker.record(_failure(f, "entrada", case_id="c2", atribucion="externa"))
        assert tracker.aborted  # 3/20 = 0.15 (sobre intentos seria 3/100)

    def test_entrada_dato_min_attempts_counts_unique_cases(self, tracker: Any) -> None:
        # Minimo de 20 sobre casos unicos: 100 intentos sobre 10 casos no alcanzan
        f = _failures()
        for _ in range(10):
            for i in range(10):
                tracker.record_attempt("task", case_id=f"c{i}")
        for i in range(5):
            tracker.record(_failure(f, "entrada", case_id=f"c{i}", atribucion="externa"))
        assert not tracker.aborted

    def test_count_keys_carry_task_attribution(self, tracker: Any) -> None:
        # Claves de conteo de la spec: entrada_candidato / entrada_dato y
        # presupuesto_candidato / presupuesto; entrada_dato cuenta casos unicos
        f = _failures()
        _attempts(tracker, "task", 100)
        tracker.record(_failure(f, "entrada", case_id="a", atribucion="candidato"))
        tracker.record(_failure(f, "entrada", case_id="b", atribucion="externa"))
        tracker.record(_failure(f, "entrada", case_id="b", atribucion="externa"))
        tracker.record(_failure(f, "presupuesto", case_id="c", atribucion="candidato"))
        tracker.record(_failure(f, "presupuesto", case_id="d", atribucion="externa"))
        tracker.record(_failure(f, "entrada", "judge", case_id="e"))
        counts = tracker.snapshot()["counts"]
        assert counts["entrada_candidato"]["task"] == 1
        assert counts["entrada_dato"]["task"] == 1
        assert counts["presupuesto_candidato"]["task"] == 1
        assert counts["presupuesto"]["task"] == 1
        assert counts["entrada"]["judge"] == 1

    def test_judge_entrada_threshold_is_010_with_min_20(self, tracker: Any) -> None:
        # Decidido tras 1b: `entrada` en juez con umbral 0.10 y minimo 20 intentos
        f = _failures()
        _attempts(tracker, "judge", 19)
        for _ in range(19):  # bajo el minimo: no aborta aunque la tasa sea 1.0
            tracker.record(_failure(f, "entrada", "judge"))
        assert not tracker.aborted
        tracker.reset()
        _attempts(tracker, "judge", 20)
        for _ in range(2):  # 2/20 = 0.10, no supera
            tracker.record(_failure(f, "entrada", "judge"))
        assert not tracker.aborted
        tracker.record(_failure(f, "entrada", "judge"))  # 3/20 = 0.15
        assert tracker.aborted
        with pytest.raises(f.RunAborted) as exc_info:
            tracker.check_abort()
        assert "entrada" in str(exc_info.value)
        assert "judge" in str(exc_info.value)

    def test_judge_formato_has_threshold(self, tracker: Any) -> None:
        f = _failures()
        _attempts(tracker, "judge", 20)
        for _ in range(3):
            tracker.record(_failure(f, "formato", "judge"))
        assert tracker.aborted

    def test_configure_overrides_thresholds_and_min_attempts(self, tracker: Any) -> None:
        f = _failures()
        # 1b: min_attempts por rol (la spec fija 20 en tarea/juez y 4 en reflexion)
        tracker.configure(thresholds={"infraestructura": {"task": 0.9}}, min_attempts={"task": 2})
        _attempts(tracker, "task", 10)
        for _ in range(5):
            tracker.record(_failure(f, "infraestructura"))
        assert not tracker.aborted
        for _ in range(5):
            tracker.record(_failure(f, "infraestructura"))  # 10/10 > 0.9
        assert tracker.aborted
