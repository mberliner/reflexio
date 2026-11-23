"""
Tests RED de SPEC-104 subfase 1a: llamada comun con reintento propio (FR-011).

Sin red: se intercepta `httpx.Client.send` con los payloads de
`tests/litellm_failure_payloads.py`. Verifica el conteo de llamadas HTTP (1 si
la clase no es `infraestructura`, 1 + reintentos si lo es), que la capa de
llamada no cuenta fallas (D4) y que un estado de aborto impide llamar al LLM.

Nombres segun D3 del plan, confirmados en 1b
(`shared.llm.call.checked_completion(kwargs, messages, role, infra_retries=...)`).
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from types import ModuleType
from typing import Any

import litellm
import pytest

from shared.llm.usage import get_tracker as get_usage_tracker
from tests.litellm_failure_payloads import (
    ALL_FAILURE_CASES,
    PROVIDER_KWARGS,
    RETRY_CASES,
    FailurePayloadCase,
)
from tests.test_litellm_failure_mapping import intercept_httpx

INFRA_RETRIES = 3
_HTTP_200_OK = tuple(
    c for c in ALL_FAILURE_CASES if c.case_type == "http_200" and c.spec104_class == "ok"
)
_HTTP_200_FAIL = tuple(
    c for c in ALL_FAILURE_CASES if c.case_type == "http_200" and c.spec104_class != "ok"
)


def _failures() -> ModuleType:
    return importlib.import_module("shared.llm.failures")


def _call_mod() -> ModuleType:
    return importlib.import_module("shared.llm.call")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr("shared.llm.call.time.sleep", lambda _s: None)
    monkeypatch.setattr(litellm, "drop_params", True)
    monkeypatch.setattr(litellm, "num_retries", None)
    monkeypatch.setattr(litellm, "suppress_debug_info", True)
    yield


@pytest.fixture
def tracker() -> Iterator[Any]:
    t = _failures().get_failure_tracker()
    t.reset()
    yield t
    t.reset()


def _run(case: FailurePayloadCase, role: str = "task") -> tuple[Any, Exception | None, int]:
    kwargs = {**PROVIDER_KWARGS[case.provider], "max_tokens": 50, "drop_params": True}
    messages = [{"role": "user", "content": "hello"}]
    with intercept_httpx(case) as calls:
        try:
            out = _call_mod().checked_completion(
                kwargs, messages, role, infra_retries=INFRA_RETRIES
            )
            return out, None, len(calls)
        except Exception as exc:
            return None, exc, len(calls)


class TestHttpCallCounts:
    @pytest.mark.parametrize("case", RETRY_CASES, ids=lambda c: c.id)
    def test_persistent_error_call_count_and_class(
        self, case: FailurePayloadCase, tracker: Any
    ) -> None:
        f = _failures()
        assert case.expected_http_calls is not None
        # num_retries=0 fija el piso por proveedor (1 llamada; 2 en el bug 422 + drop_params)
        base = case.expected_http_calls["num_retries_0"]
        expected_calls = (
            base * (1 + INFRA_RETRIES) if case.spec104_class == "infraestructura" else base
        )

        _, exc, calls = _run(case)

        assert isinstance(exc, f.LLMCallFailure)
        assert exc.failure.clase == f.FailureClass(case.spec104_class)
        assert exc.failure.case_id is None
        assert calls == expected_calls

    def test_call_layer_never_records_failures(self, tracker: Any) -> None:
        # D4: la capa de llamada solo lanza; cuenta quien conoce el caso
        case = next(c for c in RETRY_CASES if c.spec104_class == "infraestructura")
        _run(case)
        counts = tracker.snapshot()["counts"]
        assert all(v == 0 for by_role in counts.values() for v in by_role.values())


class TestResponseClassification:
    @pytest.mark.parametrize("case", _HTTP_200_OK, ids=lambda c: c.id)
    def test_healthy_response_returns_text_with_one_call(
        self, case: FailurePayloadCase, tracker: Any
    ) -> None:
        out, exc, calls = _run(case)
        assert exc is None
        assert out == case.expected_content
        assert calls == 1

    @pytest.mark.parametrize("case", _HTTP_200_FAIL, ids=lambda c: c.id)
    def test_failed_200_raises_without_retrying(
        self, case: FailurePayloadCase, tracker: Any
    ) -> None:
        f = _failures()
        _, exc, calls = _run(case)
        assert isinstance(exc, f.LLMCallFailure)
        assert exc.failure.clase == f.FailureClass(case.spec104_class)
        assert calls == 1

    def test_success_records_token_usage(self, tracker: Any) -> None:
        usage = get_usage_tracker()
        usage.reset()
        _run(_HTTP_200_OK[0], role="judge")
        assert usage.snapshot()["reflection"]["calls"] == 1


class TestAbortState:
    def test_configuracion_sets_abort_state_before_raising(self, tracker: Any) -> None:
        f = _failures()
        case = next(c for c in RETRY_CASES if c.id.endswith("401_auth"))
        _, exc, calls = _run(case, role="reflection")
        assert isinstance(exc, f.LLMCallFailure)
        assert exc.failure.clase == f.FailureClass.configuracion
        assert calls == 1
        assert tracker.aborted

    def test_aborted_state_blocks_the_llm_call(self, tracker: Any) -> None:
        f = _failures()
        tracker.abort(
            f.LLMFailure(
                clase=f.FailureClass.configuracion,
                rol="task",
                causa="AuthenticationError",
                finish_reason=None,
                case_id=None,
                atribucion=None,
            ),
            "401",
        )
        case = _HTTP_200_OK[0]
        _, exc, calls = _run(case)
        assert isinstance(exc, f.RunAborted)
        assert calls == 0
