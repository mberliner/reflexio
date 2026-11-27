"""
SPEC-106 subfase 2a: sonda de conexion por el punto de llamada comun (FR-005, D5).

- La sonda (`LLMConfig.validate_connection`) pasa por `shared/llm/call.py`
  (`probe_completion`), con `num_retries=0` y una sola llamada HTTP, sin
  reintento propio.
- La falla se clasifica con las reglas de SPEC-104 (capa 1, sin leer el texto):
  401 y 404 son `configuracion`; 429 y timeout son `infraestructura`, y su
  mensaje no habla de credencial invalida.
- `LLMConnectionError` nombra rol, proveedor, modelo y la variable concreta del
  rol (`LLM_API_KEY_REFLECTION` cuando la credencial salio de ella).
- La sonda no registra uso ni fija el aborto del contador (no hay corrida).
- Una respuesta sin texto cuenta como conexion valida con `[WARN]`.

Sin red: payloads de `tests/litellm_failure_payloads.py` inyectados en
`httpx.Client.send` (`intercept_httpx`) y respuestas con el helper de
`tests/conftest.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import litellm
import pytest

from shared.llm import LLMConfig, get_failure_tracker
from shared.llm.errors import LLMConnectionError
from shared.llm.failures import LLMCallFailure
from shared.llm.usage import get_tracker as get_usage_tracker
from tests.conftest import make_completion_response, patch_litellm_completion
from tests.litellm_failure_payloads import PROVIDER_KWARGS, RETRY_CASES, FailurePayloadCase
from tests.test_litellm_failure_mapping import intercept_httpx

_CASES = {c.id: c for c in RETRY_CASES}

# (caso, clase esperada): 401 y 404 son configuracion; 429 y timeout, infraestructura.
CONFIG_CASES = ("azure_retry_401_auth", "anthropic_retry_401_auth", "azure_retry_404_not_found")
INFRA_CASES = ("azure_retry_429_rate_limit", "anthropic_retry_read_timeout")


@pytest.fixture(autouse=True)
def _litellm_globals(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(litellm, "drop_params", False)
    monkeypatch.setattr(litellm, "num_retries", None)
    monkeypatch.setattr(litellm, "suppress_debug_info", True)
    yield


@pytest.fixture
def no_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "LLM_MODEL_TASK",
        "LLM_MODEL_REFLECTION",
        "LLM_API_KEY",
        "LLM_API_BASE",
        "LLM_API_VERSION",
        "LLM_API_KEY_TASK",
        "LLM_API_BASE_TASK",
        "LLM_API_VERSION_TASK",
        "LLM_API_KEY_REFLECTION",
        "LLM_API_BASE_REFLECTION",
        "LLM_API_VERSION_REFLECTION",
        "LLM_ENV_FILE",
    ):
        monkeypatch.delenv(var, raising=False)


def _config_for(case: FailurePayloadCase, role: str = "task") -> LLMConfig:
    return LLMConfig(**PROVIDER_KWARGS[case.provider], role=role)


def _probe(cfg: LLMConfig, case: FailurePayloadCase) -> tuple[LLMConnectionError, int]:
    with intercept_httpx(case) as calls, pytest.raises(LLMConnectionError) as exc_info:
        cfg.validate_connection()
    return exc_info.value, len(calls)


def _azure_task_anthropic_reflection(monkeypatch: pytest.MonkeyPatch) -> LLMConfig:
    """Escenario 1 de la spec: tarea Azure con globales, profesor Claude con su clave."""
    monkeypatch.setenv("LLM_MODEL_TASK", "azure/gpt-4.1-mini")
    monkeypatch.setenv("LLM_API_KEY", "azure-global-key")
    monkeypatch.setenv("LLM_API_BASE", "https://fake.openai.azure.com")
    monkeypatch.setenv("LLM_MODEL_REFLECTION", "anthropic/claude-sonnet-5-5")
    monkeypatch.setenv("LLM_API_KEY_REFLECTION", "anthropic-role-key")
    return LLMConfig.from_env("reflection", load_env=False)


# ==================== Clasificacion por capa 1 ====================


class TestProbeClassification:
    @pytest.mark.parametrize("case_id", CONFIG_CASES)
    def test_credential_or_model_invalid_is_configuracion(self, case_id: str) -> None:
        case = _CASES[case_id]
        err, calls = _probe(_config_for(case), case)

        assert err.failure_class == "configuracion"
        assert calls == 1
        assert err.role == "task"
        assert err.provider == case.provider
        assert err.model == case.model

    @pytest.mark.parametrize("case_id", INFRA_CASES)
    def test_rate_limit_or_timeout_is_infraestructura(self, case_id: str) -> None:
        case = _CASES[case_id]
        err, calls = _probe(_config_for(case), case)

        assert err.failure_class == "infraestructura"
        # Un intento: la sonda no reintenta (ni LiteLLM ni el reintento propio).
        assert calls == 1
        text = " ".join([err.message, *err.suggestions]).lower()
        assert "credential" not in text
        assert "credencial" not in text
        assert "api key" not in text

    def test_classification_does_not_depend_on_message_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Texto que la sonda vieja leia como "401": sin tipo de API es configuracion,
        # y un 429 real con texto de "Unauthorized" sigue siendo infraestructura.
        def fake(request, num_retries):
            raise litellm.RateLimitError(
                message="401 Unauthorized invalid api key",
                llm_provider="azure",
                model="gpt-4.1-mini",
            )

        patch_litellm_completion(monkeypatch, fake)
        cfg = LLMConfig(**PROVIDER_KWARGS["azure"], role="task")
        with pytest.raises(LLMConnectionError) as exc_info:
            cfg.validate_connection()

        assert exc_info.value.failure_class == "infraestructura"

    def test_none_response_is_configuracion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        patch_litellm_completion(monkeypatch, lambda request, num_retries: None)
        cfg = LLMConfig(**PROVIDER_KWARGS["openai"], role="reflection")

        with pytest.raises(LLMConnectionError) as exc_info:
            cfg.validate_connection()

        assert exc_info.value.failure_class == "configuracion"
        assert exc_info.value.role == "reflection"

    def test_probe_completion_raises_llm_call_failure(self) -> None:
        from shared.llm.call import probe_completion

        case = _CASES["azure_retry_401_auth"]
        kwargs = _config_for(case).to_kwargs()

        with intercept_httpx(case), pytest.raises(LLMCallFailure) as exc_info:
            probe_completion(kwargs, "reflection")

        assert exc_info.value.failure.clase.value == "configuracion"
        assert exc_info.value.failure.rol == "reflection"


# ==================== Rol, proveedor, modelo y variable ====================


class TestProbeErrorNamesRole:
    def test_role_variable_when_credential_came_from_it(
        self, no_llm_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _azure_task_anthropic_reflection(monkeypatch)
        err, calls = _probe(cfg, _CASES["anthropic_retry_401_auth"])

        assert calls == 1
        assert err.role == "reflection"
        assert err.provider == "anthropic"
        assert err.model == "anthropic/claude-sonnet-5-5"
        assert err.variable == "LLM_API_KEY_REFLECTION"
        assert err.failure_class == "configuracion"
        text = str(err)
        assert "Role: reflection" in text
        assert "LLM_API_KEY_REFLECTION" in text
        # Nunca el valor de la credencial (ni la global ni la del rol).
        assert "anthropic-role-key" not in text
        assert "azure-global-key" not in text

    def test_global_variable_when_role_inherits(
        self, no_llm_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL_TASK", "azure/gpt-4.1-mini")
        monkeypatch.setenv("LLM_MODEL_REFLECTION", "azure/gpt-4.1-mini")
        monkeypatch.setenv("LLM_API_KEY", "azure-global-key")
        monkeypatch.setenv("LLM_API_BASE", "https://fake.openai.azure.com")
        cfg = LLMConfig.from_env("reflection", load_env=False)

        err, _ = _probe(cfg, _CASES["azure_retry_401_auth"])

        assert err.role == "reflection"
        assert err.variable == "LLM_API_KEY"
        assert "azure-global-key" not in str(err)

    def test_suggestions_name_role_variables_not_generic(
        self, no_llm_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _azure_task_anthropic_reflection(monkeypatch)
        err, _ = _probe(cfg, _CASES["anthropic_retry_401_auth"])

        joined = " ".join(err.suggestions)
        assert "LLM_API_KEY_REFLECTION" in joined
        assert "LLM_MODEL_REFLECTION" in joined
        assert "LLM_MODEL_*" not in joined

    def test_diagnostic_details_preserved(self) -> None:
        case = _CASES["azure_retry_401_auth"]
        err, _ = _probe(_config_for(case), case)

        assert err.extra_details["status_code"] == 401
        assert err.extra_details["error_type"] == "AuthenticationError"
        assert err.original_error


# ==================== Una llamada, sin uso ni aborto ====================


class TestProbeSideEffects:
    def test_one_call_with_num_retries_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        requests: list[dict] = []

        def fake(request, num_retries):
            requests.append(request)
            return make_completion_response("OK")

        patch_litellm_completion(monkeypatch, fake)
        cfg = LLMConfig(**PROVIDER_KWARGS["azure"], role="task")

        assert cfg.validate_connection() is True
        assert len(requests) == 1
        assert requests[0]["num_retries"] == 0
        assert requests[0]["max_tokens"] == 5

    def test_success_does_not_record_usage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        get_usage_tracker().reset()
        before = get_usage_tracker().snapshot()
        patch_litellm_completion(
            monkeypatch, lambda request, num_retries: make_completion_response("OK")
        )

        assert LLMConfig(**PROVIDER_KWARGS["openai"], role="task").validate_connection() is True
        assert get_usage_tracker().snapshot() == before

    def test_configuracion_does_not_abort_run(self) -> None:
        case = _CASES["azure_retry_401_auth"]
        _probe(_config_for(case), case)

        tracker = get_failure_tracker()
        assert not tracker.aborted
        tracker.check_abort()  # no lanza RunAborted

    def test_infraestructura_is_not_retried(self) -> None:
        # El reintento propio de infraestructura de la corrida no aplica a la sonda.
        case = _CASES["azure_retry_429_rate_limit"]
        _, calls = _probe(_config_for(case), case)

        assert calls == 1
        assert not get_failure_tracker().aborted


# ==================== Respuesta sin texto ====================


class TestProbeEmptyResponse:
    @pytest.mark.parametrize("finish_reason", ["stop", "length", "content_filter"])
    def test_empty_text_is_valid_connection_with_warning(
        self,
        finish_reason: str,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        patch_litellm_completion(
            monkeypatch,
            lambda request, num_retries: make_completion_response(
                content="", finish_reason=finish_reason
            ),
        )
        cfg = LLMConfig(**PROVIDER_KWARGS["anthropic"], role="reflection")

        with caplog.at_level(logging.WARNING):
            assert cfg.validate_connection() is True

        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("[WARN]" in m and "reflection" in m for m in warnings), warnings
        assert not get_failure_tracker().aborted
