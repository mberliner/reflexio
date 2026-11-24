"""
Offline wire-level regression tests for LiteLLM 1.108.5 error and response mapping.

Fija la evidencia de la verificacion del 2026-11-23 contra el stack pinned:
- litellm==1.108.5
- openai==3.57.0
- httpx==0.28.1
- dspy==3.2.1

Intercepta `httpx.Client.send` (sin red) para ejecutar la pila real completa
(`litellm.completion` -> `@client` -> `completion_with_retries` -> SDK de
`openai`/`AzureOpenAI` o `HTTPHandler` de Anthropic -> `exception_type` y
conversion de `ModelResponse`, mas `CheckedLM` de `shared/llm/dspy_lm.py`).

Verifica:
- Versiones fijadas del stack (si cambian, hay que re-verificar D-023 y SC-009).
- Mapeo de excepciones y preservacion de `exc.body` en filtros de entrada y
  ventana de contexto excedida para Azure, OpenAI y Anthropic (tablas 1 y 2).
- Normalizacion de respuestas HTTP 200: `finish_reason`, `content`, `refusal` y
  `provider_specific_fields` (tabla 3 + `model_context_window_exceeded`).
- Conteo exacto de llamadas HTTP bajo `default` (sin `num_retries`),
  `num_retries=0`, `num_retries=3` y `dspy.LM` por defecto (tabla 4), y el de
  `CheckedLM` tras SPEC-104 2a (1 llamada, o 1 + reintentos si es
  `infraestructura`).
- Que `CheckedLM._process_lm_response` recibe el objeto de respuesta completo
  con `finish_reason` y `message` intactos y rechaza las respuestas 200 con
  falla de capa 1 con su clase.

Referencias:
- `specs/SPEC-104-fallas-tecnicas-justas.md` ("Reglas de deteccion de la capa 1",
  FR-011, FR-015, SC-009 y "Limites conocidos")
- `historial/sdd.md` (D-023)
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any
from unittest import mock

import dspy
import httpx
import litellm
import pytest
import tenacity
from litellm.llms.azure.common_utils import BaseAzureLLM
from litellm.llms.openai.openai import OpenAIChatCompletion

from shared.llm.config import LLMConfig, is_empty_text
from shared.llm.dspy_lm import CheckedLM
from shared.llm.errors import EmptyResponseError
from shared.llm.failures import DEFAULT_INFRA_RETRIES, LLMCallFailure, root_exception
from tests.litellm_failure_payloads import (
    ALL_FAILURE_CASES,
    ALL_HTTP_200_CASES,
    CONTEXT_WINDOW_CASES,
    EXPECTED_VERSIONS,
    INPUT_FILTER_CASES,
    PROVIDER_KWARGS,
    RETRY_CASES,
    FailurePayloadCase,
)

_TRANSPORT_EXCEPTIONS: dict[str, type[httpx.TransportError]] = {
    "ReadTimeout": httpx.ReadTimeout,
    "ConnectTimeout": httpx.ConnectTimeout,
    "ConnectError": httpx.ConnectError,
    "RemoteProtocolError": httpx.RemoteProtocolError,
}

_TABLE_1_AND_2_ERRORS: tuple[FailurePayloadCase, ...] = tuple(
    c for c in (*INPUT_FILTER_CASES, *CONTEXT_WINDOW_CASES) if c.case_type == "http_error"
)


@pytest.fixture(autouse=True)
def _isolate_litellm_globals(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ensure LiteLLM globals and client caches never leak across tests."""
    monkeypatch.setattr(litellm, "drop_params", False)
    monkeypatch.setattr(litellm, "num_retries", None)
    monkeypatch.setattr(litellm, "suppress_debug_info", True)
    if hasattr(litellm, "in_memory_llm_clients_cache"):
        litellm.in_memory_llm_clients_cache.flush_cache()
    yield
    if hasattr(litellm, "in_memory_llm_clients_cache"):
        litellm.in_memory_llm_clients_cache.flush_cache()


def _clear_caches() -> None:
    litellm.num_retries = None
    if hasattr(litellm, "in_memory_llm_clients_cache"):
        litellm.in_memory_llm_clients_cache.flush_cache()


@contextmanager
def intercept_httpx(case: FailurePayloadCase) -> Iterator[list[dict[str, Any]]]:
    """Intercept `httpx.Client.send` and patch sleeps without touching the network."""
    calls: list[dict[str, Any]] = []

    def fake_send(self: httpx.Client, request: httpx.Request, *args: Any, **kwargs: Any):
        calls.append({"method": request.method, "url": str(request.url)})
        if case.case_type == "transport_error":
            assert case.transport_exc_type is not None
            exc_cls = _TRANSPORT_EXCEPTIONS[case.transport_exc_type]
            raise exc_cls(case.transport_exc_message or "", request=request)
        assert case.status_code is not None
        payload = case.body
        content = (
            json.dumps(payload).encode("utf-8")
            if isinstance(payload, (dict, list))
            else str(payload).encode("utf-8")
        )
        resp_headers = {"content-type": "application/json", **case.headers}
        return httpx.Response(
            status_code=case.status_code,
            headers=resp_headers,
            content=content,
            request=request,
        )

    _clear_caches()
    with (
        mock.patch.object(httpx.Client, "send", fake_send),
        mock.patch.object(BaseAzureLLM, "get_cached_openai_client", lambda *a, **kw: None),
        mock.patch.object(BaseAzureLLM, "set_cached_openai_client", lambda *a, **kw: None),
        mock.patch.object(
            OpenAIChatCompletion, "_get_cached_openai_client", lambda *a, **kw: None, create=True
        ),
        mock.patch.object(time, "sleep", lambda *a, **kw: None),
        mock.patch.object(tenacity.nap.time, "sleep", lambda *a, **kw: None),
    ):
        yield calls
    _clear_caches()


def _call_completion(
    case: FailurePayloadCase,
    *,
    drop_params: bool = True,
    extra_kwargs: dict[str, Any] | None = None,
) -> tuple[Any, Exception | None, int]:
    """Run `litellm.completion` under `intercept_httpx` and return `(resp, exc, calls)`."""
    litellm.drop_params = drop_params
    kwargs: dict[str, Any] = {
        **PROVIDER_KWARGS[case.provider],
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 50,
        **(extra_kwargs or {}),
    }
    with intercept_httpx(case) as calls:
        try:
            resp = litellm.completion(**kwargs)
            return resp, None, len(calls)
        except Exception as exc:
            return None, exc, len(calls)


def _assert_exception_contract(case: FailurePayloadCase, exc: Exception | None) -> None:
    assert exc is not None, f"{case.id}: expected {case.expected_exception}, got no exception"
    assert type(exc).__name__ == case.expected_exception
    if case.expected_status_code is not None:
        assert getattr(exc, "status_code", None) == case.expected_status_code

    body = getattr(exc, "body", None)
    if case.expected_body_preserved is True:
        assert isinstance(body, dict), f"{case.id}: expected dict exc.body, got {body!r}"
        assert body.get("code") == case.expected_body_code
        inner = body.get("innererror")
        inner_code = inner.get("code") if isinstance(inner, dict) else None
        assert inner_code == case.expected_body_innererror_code
    elif case.expected_body_preserved is False:
        assert not isinstance(body, dict), f"{case.id}: expected no dict exc.body, got {body!r}"

    if case.expected_exc_psf_innererror_code is not None:
        psf = getattr(exc, "provider_specific_fields", None)
        assert isinstance(psf, dict)
        inner = psf.get("innererror")
        assert isinstance(inner, dict)
        assert inner.get("code") == case.expected_exc_psf_innererror_code


def _case_by_id(case_id: str) -> FailurePayloadCase:
    for case in ALL_FAILURE_CASES:
        if case.id == case_id:
            return case
    raise KeyError(case_id)


# ==================== Versiones fijadas del stack ====================


class TestPinnedStackVersions:
    @pytest.mark.parametrize(("package", "expected"), sorted(EXPECTED_VERSIONS.items()))
    def test_installed_stack_versions_match_verified_baseline(
        self, package: str, expected: str
    ) -> None:
        actual = pkg_version(package)
        assert actual == expected, (
            f"{package} cambio de {expected} a {actual}: re-verificar D-023 "
            "(historial/sdd.md) y SC-009 de SPEC-104 (specs/SPEC-104-fallas-tecnicas-justas.md)."
        )

    def test_requirements_pins_expected_stack_versions(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        req_lines = [
            line.strip()
            for line in (repo_root / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        for package, expected in sorted(EXPECTED_VERSIONS.items()):
            pinned = f"{package}=={expected}"
            assert pinned in req_lines, (
                f"requirements.txt ya no fija {pinned}: re-verificar D-023 y SC-009 de SPEC-104."
            )

    def test_payload_registry_ids_are_unique(self) -> None:
        ids = [c.id for c in ALL_FAILURE_CASES]
        assert len(ids) == len(set(ids))


# ==================== (a) Mapeo de excepciones y exc.body (Tablas 1 y 2) ====================


class TestExceptionMappingAndBodyPreservation:
    @pytest.mark.parametrize("case", _TABLE_1_AND_2_ERRORS, ids=lambda c: c.id)
    def test_table_1_and_2_exception_and_body(self, case: FailurePayloadCase) -> None:
        _, exc, calls = _call_completion(case, extra_kwargs={"num_retries": 0})
        assert calls == 1
        _assert_exception_contract(case, exc)
        # Todas las subclases especializadas de 400 heredan de BadRequestError
        assert isinstance(exc, litellm.BadRequestError)

    @pytest.mark.parametrize(
        "case_id",
        [
            "azure_400_content_filter_innererror_otro_msg",
            "azure_400_content_filter_solo_code",
            "openai_400_content_policy_violation_canonico",
        ],
    )
    def test_input_filters_degraded_to_bad_request_keep_body_code(self, case_id: str) -> None:
        # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
        case = _case_by_id(case_id)
        _, exc, calls = _call_completion(case, extra_kwargs={"num_retries": 0})
        assert calls == 1
        assert type(exc) is litellm.BadRequestError
        assert not isinstance(exc, litellm.ContentPolicyViolationError)
        _assert_exception_contract(case, exc)

    @pytest.mark.parametrize(
        "case_id",
        [
            "azure_400_context_window_wording_nuevo",
            "azure_400_maximum_context_length_otro_prefijo",
            "openai_400_context_window_wording_nuevo",
        ],
    )
    def test_new_context_window_wording_degraded_to_bad_request_keeps_code(
        self, case_id: str
    ) -> None:
        # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
        case = _case_by_id(case_id)
        _, exc, calls = _call_completion(case, extra_kwargs={"num_retries": 0})
        assert calls == 1
        assert type(exc) is litellm.BadRequestError
        assert not isinstance(exc, litellm.ContextWindowExceededError)
        _assert_exception_contract(case, exc)

    def test_anthropic_400_usage_policy_other_wording_is_bad_request_without_body(self) -> None:
        # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
        case = _case_by_id("anthropic_400_usage_policy_otro_texto")
        _, exc, calls = _call_completion(case, extra_kwargs={"num_retries": 0})
        assert calls == 1
        assert type(exc) is litellm.BadRequestError
        assert getattr(exc, "body", None) is None

    def test_anthropic_413_request_too_large_maps_to_bad_request_with_marker_in_message(
        self,
    ) -> None:
        # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
        case = _case_by_id("anthropic_413_request_too_large")
        _, exc, calls = _call_completion(case, extra_kwargs={"num_retries": 0})
        assert calls == 1
        assert type(exc) is litellm.BadRequestError
        assert getattr(exc, "status_code", None) == 400
        assert getattr(exc, "body", None) is None
        assert "request_too_large" in str(exc)

    @pytest.mark.parametrize("case_id", ["azure_retry_403_perm", "openai_retry_403_perm"])
    def test_azure_and_openai_403_map_to_api_error_not_permission_denied(
        self, case_id: str
    ) -> None:
        # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
        case = _case_by_id(case_id)
        _, exc, calls = _call_completion(case, extra_kwargs={"num_retries": 0})
        assert calls == 1
        assert type(exc) is litellm.APIError
        assert not isinstance(exc, litellm.PermissionDeniedError)
        assert getattr(exc, "status_code", None) == 403

    def test_openai_422_with_drop_params_true_returns_none_after_two_calls(self) -> None:
        # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
        case = _case_by_id("openai_retry_422_unprocessable")
        resp, exc, calls = _call_completion(
            case,
            drop_params=True,
            extra_kwargs={"num_retries": 0, "drop_params": True},
        )
        assert exc is None
        assert resp is None
        assert calls == 2

    def test_openai_422_with_drop_params_false_raises_bad_request(self) -> None:
        case = _case_by_id("openai_retry_422_unprocessable")
        resp, exc, calls = _call_completion(
            case,
            drop_params=False,
            extra_kwargs={"num_retries": 0, "drop_params": False},
        )
        assert resp is None
        assert type(exc) is litellm.BadRequestError
        assert getattr(exc, "status_code", None) == 422
        assert calls == 1


# ==================== (b) Respuestas HTTP 200 normalizadas (Tabla 3) ====================


class TestHTTP200ResponseNormalization:
    @pytest.mark.parametrize("case", ALL_HTTP_200_CASES, ids=lambda c: c.id)
    def test_http_200_normalized_fields(self, case: FailurePayloadCase) -> None:
        resp, exc, calls = _call_completion(case, extra_kwargs={"num_retries": 0})
        assert exc is None
        assert calls == 1
        choice = resp.choices[0]
        message = choice.message

        assert choice.finish_reason == case.expected_finish_reason
        assert message.content == case.expected_content
        assert hasattr(message, "refusal") is case.expected_has_refusal_attr
        assert getattr(message, "refusal", None) == case.expected_refusal

        if case.expected_choice_psf is not None:
            assert getattr(choice, "provider_specific_fields", None) == case.expected_choice_psf

        if case.expected_message_psf_subset is not None:
            msg_psf = getattr(message, "provider_specific_fields", None)
            assert isinstance(msg_psf, dict)
            for key, value in case.expected_message_psf_subset.items():
                assert msg_psf.get(key) == value

    def test_anthropic_model_context_window_exceeded_normalized_to_stop_without_trace(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
        case = _case_by_id("anthropic_200_model_context_window_exceeded")
        with caplog.at_level(logging.WARNING, logger="LiteLLM"):
            resp, exc, calls = _call_completion(case, extra_kwargs={"num_retries": 0})
        assert exc is None
        assert calls == 1
        choice = resp.choices[0]
        assert choice.finish_reason == "stop"
        assert choice.message.content == "Hit ctx limit"
        assert "model_context_window_exceeded" not in str(
            getattr(choice.message, "provider_specific_fields", None)
        )
        assert "model_context_window_exceeded" not in str(getattr(resp, "_hidden_params", None))
        assert "Unmapped finish_reason 'model_context_window_exceeded'" in caplog.text


# ==================== (c) Conteo de llamadas HTTP por reintentos (Tabla 4) ====================


class TestRetryHTTPCounts:
    @pytest.mark.parametrize("case", RETRY_CASES, ids=lambda c: c.id)
    def test_retry_counts_default_without_num_retries(self, case: FailurePayloadCase) -> None:
        # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
        # Sin num_retries: Azure/OpenAI ya hacen 3 llamadas (1 + 2 del SDK) en
        # 408/409/429/5xx/red; Anthropic hace 1. OpenAI 422 + drop_params=True hace 2.
        assert case.expected_http_calls is not None
        _, _, calls = _call_completion(case, drop_params=True)
        assert calls == case.expected_http_calls["default"]

    @pytest.mark.parametrize("case", RETRY_CASES, ids=lambda c: c.id)
    def test_retry_counts_num_retries_0_and_mapped_exception(
        self, case: FailurePayloadCase
    ) -> None:
        assert case.expected_http_calls is not None
        resp, exc, calls = _call_completion(case, drop_params=True, extra_kwargs={"num_retries": 0})
        assert calls == case.expected_http_calls["num_retries_0"]
        if case.returns_none:
            # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
            assert exc is None
            assert resp is None
        else:
            _assert_exception_contract(case, exc)

    @pytest.mark.parametrize("case", RETRY_CASES, ids=lambda c: c.id)
    def test_retry_counts_num_retries_3(self, case: FailurePayloadCase) -> None:
        # Comportamiento actual de LiteLLM 1.108.5, no deseado: ver D-023
        # num_retries=3 reintenta 400/401/403/404 y filtros (4 llamadas), y se
        # apila sobre max_retries del SDK en Azure/OpenAI (7 llamadas en 429/5xx/red).
        assert case.expected_http_calls is not None
        _, _, calls = _call_completion(case, drop_params=True, extra_kwargs={"num_retries": 3})
        assert calls == case.expected_http_calls["num_retries_3"]

    @pytest.mark.parametrize("case", RETRY_CASES, ids=lambda c: c.id)
    def test_retry_counts_dspy_lm_default(self, case: FailurePayloadCase) -> None:
        # Comportamiento actual de dspy.LM (no de CheckedLM), no deseado: ver D-023
        # dspy.LM usa num_retries=3 por defecto (drop_params=False): repite 4 veces
        # un 401/400/422/filtro y 7 veces un 429/5xx/red en Azure/OpenAI.
        # CheckedLM lo reemplaza (SPEC-104 FR-011): ver test_retry_counts_checked_lm.
        assert case.expected_http_calls is not None
        lm = dspy.LM(**{**PROVIDER_KWARGS[case.provider], "cache": False})
        # dspy==3.2.1 (dspy/clients/lm.py:191-192) envuelve litellm.ContextWindowExceededError
        # en dspy.utils.exceptions.ContextWindowExceededError (original en __cause__).
        if case.expected_exception == "ContextWindowExceededError":
            with (
                intercept_httpx(case) as calls,
                pytest.raises(dspy.utils.exceptions.ContextWindowExceededError) as exc_info,
            ):
                lm("hello")
            assert isinstance(exc_info.value.__cause__, litellm.ContextWindowExceededError)
        else:
            with intercept_httpx(case) as calls, pytest.raises(litellm.openai.APIError):
                lm("hello")
        assert len(calls) == case.expected_http_calls["dspy_default"]

    @pytest.mark.parametrize("case", RETRY_CASES, ids=lambda c: c.id)
    def test_retry_counts_checked_lm(self, case: FailurePayloadCase) -> None:
        # SPEC-104 FR-011 / SC-009: CheckedLM con num_retries=0 y reintento propio
        # solo de infraestructura (default 3): 1 llamada, o 1 + 3 si es infraestructura.
        cfg = LLMConfig(**{**PROVIDER_KWARGS[case.provider], "role": "task", "cache": False})
        lm = cfg.get_dspy_lm()
        assert lm.num_retries == 0
        with intercept_httpx(case) as calls, pytest.raises(LLMCallFailure) as exc_info:
            lm("hello")
        exc = exc_info.value
        expected_calls = 1 + DEFAULT_INFRA_RETRIES if case.spec104_class == "infraestructura" else 1
        assert len(calls) == expected_calls
        assert exc.failure.clase.value == case.spec104_class
        assert exc.failure.rol == "task"
        # Corta el fallback ChatAdapter -> JSONAdapter (ver shared/llm/dspy_lm.py)
        assert isinstance(exc, dspy.utils.exceptions.ContextWindowExceededError)
        # El tipo original de LiteLLM queda en la cadena __cause__ (regla 3 de D1).
        # El 422 de OpenAI que con drop_params=True devuelve None, en CheckedLM
        # (drop_params=False) lanza BadRequestError (limite conocido de la spec).
        expected = "BadRequestError" if case.returns_none else case.expected_exception
        assert type(root_exception(exc)).__name__ == expected


# ================== (d) CheckedLM._process_lm_response (shared/llm/dspy_lm.py) ==================


class TestCheckedLMProcessResponse:
    @pytest.mark.parametrize("case", ALL_HTTP_200_CASES, ids=lambda c: c.id)
    def test_checked_lm_process_response_receives_intact_finish_reason_and_message(
        self, case: FailurePayloadCase, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = LLMConfig(**{**PROVIDER_KWARGS[case.provider], "role": "task", "cache": False})
        lm = cfg.get_dspy_lm()
        assert isinstance(lm, CheckedLM)

        captured_responses: list[Any] = []
        original_process = CheckedLM._process_lm_response

        def spy_process(
            self: CheckedLM, response: Any, prompt: Any, messages: Any, **kwargs: Any
        ) -> Any:
            captured_responses.append(response)
            return original_process(self, response, prompt, messages, **kwargs)

        monkeypatch.setattr(CheckedLM, "_process_lm_response", spy_process)

        with intercept_httpx(case) as calls:
            if case.spec104_class == "ok":
                outputs = lm("hello")
                assert outputs == [case.expected_content]
            else:
                # SPEC-104 (2a): la respuesta 200 con falla de capa 1 se rechaza con su clase;
                # sin texto sale como EmptyResponseError (D1), con texto como LLMCallFailure.
                with pytest.raises(LLMCallFailure) as exc_info:
                    lm("hello")
                failure = exc_info.value.failure
                assert failure.clase.value == case.spec104_class
                assert failure.rol == "task"
                assert failure.finish_reason == case.expected_finish_reason
                assert isinstance(exc_info.value, EmptyResponseError) is is_empty_text(
                    case.expected_content
                )
                if is_empty_text(case.expected_content):
                    assert exc_info.value.role == "task"
                    assert exc_info.value.finish_reason == case.expected_finish_reason

        assert len(calls) == 1
        assert len(captured_responses) == 1
        raw_resp = captured_responses[0]
        choice = raw_resp.choices[0]
        message = choice.message

        assert choice.finish_reason == case.expected_finish_reason
        assert message.content == case.expected_content
        assert hasattr(message, "refusal") is case.expected_has_refusal_attr
        assert getattr(message, "refusal", None) == case.expected_refusal
        # El historial de DSPy tambien conserva el objeto completo intacto
        assert len(lm.history) == 1
        assert lm.history[-1]["response"] is raw_resp
