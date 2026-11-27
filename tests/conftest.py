"""
Shared fixtures for all tests.
"""

import csv
import json
import logging
import os
from unittest.mock import MagicMock

import litellm
import openai._base_client as openai_base_client
import pytest
from litellm.llms.azure.common_utils import BaseAzureLLM
from litellm.llms.custom_httpx.http_handler import HTTPHandler
from openai.types.chat import ChatCompletion

import dspy_gepa_poc.config  # noqa: F401  (carga su .env al importarse)
import gepa_standalone.config  # noqa: F401  (carga su .env al importarse)
from shared.llm.failures import get_failure_tracker
from shared.llm.usage import get_tracker as get_usage_tracker


def _strip_llm_env() -> None:
    """Quita del proceso toda variable `LLM_*` (globales, por rol y `LLM_ENV_FILE`)."""
    for name in [n for n in os.environ if n.startswith("LLM_")]:
        del os.environ[name]


# Tests hermeticos frente al `.env` real del desarrollador: cada subproyecto carga
# el suyo al importar su `config.py` (`load_dotenv`, una sola vez por proceso). Se
# fuerza esa carga aca y despues se quita todo `LLM_*`, para que ningun test vea
# credenciales ni roles (p. ej. `LLM_MODEL_JUDGE`, SPEC-106) que en CI no existen.
_strip_llm_env()


def make_completion_response(
    content: str | None = "OK",
    finish_reason: str = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
    model: str = "test-model",
) -> litellm.ModelResponse:
    """
    Respuesta real de `litellm.completion` (SPEC-104, 2a): `litellm.ModelResponse`
    con un choice, `finish_reason` y `usage`, sin `refusal`.

    Los mocks de `litellm.completion` MUST usar este helper y no `MagicMock`: la
    clasificacion de la capa 1 (`classify_response`) lee `finish_reason` y
    `message.refusal`, y un `MagicMock` tiene ambos atributos truthy, lo que no
    refleja ninguna respuesta real.
    """
    return litellm.ModelResponse(
        model=model,
        choices=[
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        usage={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    )


def patch_litellm_completion(monkeypatch: pytest.MonkeyPatch, fake) -> None:
    """
    Simula `litellm.completion`, la unica llamada al proveedor del punto de llamada
    (`shared.llm.call.checked_response`, SPEC-105 FR-001), tambien desde DSPy.

    `fake(request, num_retries)` recibe en `request` los kwargs de la llamada
    (`model`, `messages`, ...) y devuelve la respuesta o lanza la excepcion.
    """

    def completion(**kwargs):
        return fake(request=kwargs, num_retries=kwargs.get("num_retries"))

    monkeypatch.setattr("litellm.completion", completion)


def repo_dspy_gepa(reflection_lm, probe=None, **params):
    """
    `dspy.GEPA` cableado como `GEPAOptimizer` (SPEC-105 FR-010): la reflexion la
    hace el `ReflectionProposer` del repo (`instruction_proposer`), que es tambien
    el callback `on_proposal_start`. `probe` es un callback extra opcional.
    """
    import dspy

    from shared.llm.dspy_lm import dspy_reflection_proposer

    proposer = dspy_reflection_proposer(reflection_lm)
    callbacks = [c for c in (probe, proposer) if c is not None]
    return dspy.GEPA(
        reflection_lm=reflection_lm,
        instruction_proposer=proposer,
        gepa_kwargs={"callbacks": callbacks},
        **params,
    )


PROJECT_LOGGER_ROOTS: frozenset[str] = frozenset({"shared", "dspy_gepa_poc", "gepa_standalone"})


def project_warnings(
    caplog: pytest.LogCaptureFixture,
    *,
    include_errors: bool = True,
) -> list[logging.LogRecord]:
    """
    Registros WARNING (o >= WARNING si `include_errors=True`) emitidos por loggers
    del proyecto (`shared`, `dspy_gepa_poc`, `gepa_standalone`).

    Excluye loggers de terceros (p. ej. `dspy`, `LiteLLM`) que pytest 9.1+ captura
    en `caplog` aunque tengan `propagate=False`, sin relajar FR-007 (un unico
    WARNING propio por falla, el de `FailureTracker.record`).
    """
    return [
        r
        for r in caplog.records
        if r.name.split(".", 1)[0] in PROJECT_LOGGER_ROOTS
        and (r.levelno >= logging.WARNING if include_errors else r.levelno == logging.WARNING)
    ]


@pytest.fixture(autouse=True)
def reset_failure_tracker():
    """
    Contador de fallas limpio en cada test (SPEC-104): es un singleton de modulo y
    una falla `configuracion` de un test fija el aborto para los siguientes. Igual
    el de uso de tokens, que el punto de llamada registra en cada llamada (SPEC-105).
    """
    get_failure_tracker().reset()
    get_usage_tracker().reset()
    yield
    get_failure_tracker().reset()
    get_usage_tracker().reset()


@pytest.fixture(autouse=True, scope="session")
def repo_dspy_adapter():
    """
    Adapter del repo en todos los tests (SPEC-105 FR-012), como `configure_dspy`
    en los entry points: dspy 3.5 usa `XMLAdapter` por defecto y los tests que
    arman el LM con `dspy.context(lm=...)` no lo fijan. Que los entry points usen
    `configure_dspy` lo verifica `tests/test_lib_contracts.py`.
    """
    import dspy

    dspy.configure(adapter=dspy.ChatAdapter())
    yield


@pytest.fixture
def mock_env(monkeypatch):
    """Set standard LLM environment variables."""
    monkeypatch.setenv("LLM_MODEL_TASK", "azure/gpt-4.1-mini")
    monkeypatch.setenv("LLM_MODEL_REFLECTION", "azure/gpt-4.1-mini")
    monkeypatch.setenv("LLM_API_KEY", "test-key-123")
    monkeypatch.setenv("LLM_API_BASE", "https://test.openai.azure.com/")
    monkeypatch.setenv("LLM_API_VERSION", "2024-02-15-preview")
    monkeypatch.setenv("LLM_CACHE", "false")


@pytest.fixture
def clear_env(monkeypatch):
    """Remove all LLM environment variables (globales y por rol, SPEC-106 FR-001)."""
    for var in [n for n in os.environ if n.startswith("LLM_")]:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def sample_csv(tmp_path):
    """CSV with split, text, and label columns (3 rows: train/val/test)."""
    csv_path = tmp_path / "data.csv"
    rows = [
        {"split": "train", "text": "hello world", "label": "greeting"},
        {"split": "val", "text": "goodbye", "label": "farewell"},
        {"split": "test", "text": "hi there", "label": "greeting"},
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "text", "label"])
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


@pytest.fixture
def sample_csv_no_split(tmp_path):
    """CSV without split column."""
    csv_path = tmp_path / "no_split.csv"
    rows = [
        {"text": "hello", "label": "greeting"},
        {"text": "bye", "label": "farewell"},
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["text", "label"])
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


@pytest.fixture
def mock_litellm(monkeypatch):
    """Mock litellm.completion returning a real response with content='OK'."""
    mock_completion = MagicMock(return_value=make_completion_response("OK"))
    monkeypatch.setattr("litellm.completion", mock_completion)
    return mock_completion


@pytest.fixture
def metrics_csv_sample(tmp_path):
    """CSV de metricas con formato europeo."""
    csv_path = tmp_path / "metricas_optimizacion.csv"
    content = (
        "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;"
        "Baseline Score;Optimizado Score;Robustez Score;Budget;Notas\n"
        "abc123;2026-02-01 10:00:00;Email Urgency;gpt-4o-mini;gpt-4o;"
        "0,75;0,85;0,80;30;Strategy: adaptive\n"
        "def456;2026-02-02 11:00:00;CV Extraction;gpt-4.1-mini;gpt-4o;"
        "0,60;0,75;0,72;25;Strategy: greedy\n"
        "ghi789;2026-02-03 12:00:00;Email Urgency;gpt-4o-mini;gpt-4o;"
        "0,70;0,82;0,78;30;Strategy: adaptive\n"
    )
    csv_path.write_text(content, encoding="utf-8")
    return csv_path


@pytest.fixture
def metrics_rows():
    """Lista de dicts simulando datos cargados."""
    return [
        {
            "Run ID": "abc123",
            "Fecha": "2026-02-01 10:00:00",
            "Caso": "Email Urgency",
            "Modelo Tarea": "gpt-4o-mini",
            "Modelo Profesor": "gpt-4o",
            "Baseline Score": "0,75",
            "Optimizado Score": "0,85",
            "Robustez Score": "0,80",
            "Budget": "30",
            "Notas": "Strategy: adaptive",
            "source": "test_project",
        },
        {
            "Run ID": "def456",
            "Fecha": "2026-02-02 11:00:00",
            "Caso": "CV Extraction",
            "Modelo Tarea": "gpt-4.1-mini",
            "Modelo Profesor": "gpt-4o",
            "Baseline Score": "0,60",
            "Optimizado Score": "0,75",
            "Robustez Score": "0,72",
            "Budget": "25",
            "Notas": "Strategy: greedy",
            "source": "test_project",
        },
    ]


@pytest.fixture
def mock_matplotlib(monkeypatch):
    """Mock matplotlib para evitar crear archivos PNG reales."""
    mock_plt = MagicMock()
    monkeypatch.setattr("matplotlib.pyplot", mock_plt)
    return mock_plt


# ==================== Intercepcion HTTP sin red (LiteLLM) ====================


class _FakeAnthropicHTTPResponse:
    status_code = 200
    headers: dict[str, str] = {}
    text = "{}"

    def json(self) -> dict:
        return {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "m",
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }


class _FakeAzureRawResponse:
    headers: dict[str, str] = {}

    def parse(self) -> ChatCompletion:
        return ChatCompletion.model_validate(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "m",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
        )


@pytest.fixture
def capture_anthropic_post(monkeypatch):
    """Intercept HTTPHandler.post for Anthropic calls without touching the network."""
    captured: dict = {}

    def fake_post(self, url, *args, **kwargs):
        raw_data = kwargs.get("data")
        body = json.loads(raw_data) if raw_data is not None else dict(kwargs.get("json") or {})
        headers = {k.lower(): v for k, v in (kwargs.get("headers") or {}).items()}
        captured["url"] = url
        captured["body"] = body
        captured["headers"] = headers
        return _FakeAnthropicHTTPResponse()

    monkeypatch.setattr(HTTPHandler, "post", fake_post)
    return captured


@pytest.fixture
def capture_azure_post(monkeypatch):
    """Intercept SyncAPIClient.post for Azure OpenAI calls without touching the network."""
    captured: dict = {}

    def fake_post(self, path, *, cast_to=None, body=None, **kwargs):
        captured["path"] = path
        captured["body"] = dict(body or {})
        captured["base_url"] = str(self.base_url)
        captured["query"] = dict(self._custom_query)
        return _FakeAzureRawResponse()

    # SyncAPIResource binds client.post at AzureOpenAI.__init__ time, so bypass
    # LiteLLM's in-memory client cache to ensure each test binds its own fake_post.
    monkeypatch.setattr(BaseAzureLLM, "get_cached_openai_client", lambda *a, **kw: None)
    monkeypatch.setattr(BaseAzureLLM, "set_cached_openai_client", lambda *a, **kw: None)
    monkeypatch.setattr(openai_base_client.SyncAPIClient, "post", fake_post)
    return captured
