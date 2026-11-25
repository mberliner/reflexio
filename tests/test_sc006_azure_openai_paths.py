"""
SPEC-103 SC-006 (subfase 1d): guardia de regresion silenciosa en `azure/` y `openai/`.

Completa `tests/test_anthropic_matrix.py::TestAzureOpenAIConfigRegression` (que fija
`to_kwargs()` y el cuerpo HTTP de `get_lm_function`) con los caminos que esa clase no
cubre: `call_llm` con overrides, `get_dspy_lm`, la sonda de `validate_connection`,
la no mutacion de `apply_constraints` y effort/thinking configurados en un modelo
no Anthropic. Sin red: los pedidos se interceptan con `capture_azure_post`.
"""

import logging

import litellm
import pytest

from shared.llm.config import LLMConfig

AZURE_BASE = "https://x.openai.azure.com"
AZURE_VERSION = "2024-02-15-preview"
NEW_KEYS = ("output_config", "thinking", "reasoning_effort")


@pytest.fixture(autouse=True)
def _no_usage_and_drop_params(monkeypatch):
    monkeypatch.setattr(litellm, "drop_params", False)
    monkeypatch.setattr("shared.llm.usage.record_usage", lambda *a, **kw: None)


@pytest.fixture
def azure_env(monkeypatch):
    """Entorno Azure minimo para from_env/call_llm, sin `.env` ni variables heredadas."""
    for var in (
        "LLM_CACHE",
        "LLM_TIMEOUT",
        "LLM_EFFORT_TASK",
        "LLM_THINKING_TASK",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("LLM_API_BASE", AZURE_BASE)
    monkeypatch.setenv("LLM_API_VERSION", AZURE_VERSION)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: False)

    def _set(model: str) -> None:
        monkeypatch.setenv("LLM_MODEL_TASK", model)

    return _set


def _azure(model: str, **kwargs) -> LLMConfig:
    params = {
        "model": model,
        "api_key": "x",
        "api_base": AZURE_BASE,
        "api_version": AZURE_VERSION,
    }
    params.update(kwargs)
    return LLMConfig(**params)


def _assert_no_new_keys(body: dict) -> None:
    for key in NEW_KEYS:
        assert key not in body


class TestCallLlmAzure:
    @pytest.mark.parametrize(
        ("model", "temperature", "max_tokens", "expected_temp", "token_key", "expected_tokens"),
        [
            ("azure/gpt-4.1-mini", 0.2, 50, 0.2, "max_tokens", 50),
            ("azure/gpt-5.4-mini", 0.2, 50, 1.0, "max_completion_tokens", 16000),
        ],
    )
    def test_overrides_then_constraints(
        self,
        azure_env,
        capture_azure_post,
        model,
        temperature,
        max_tokens,
        expected_temp,
        token_key,
        expected_tokens,
    ):
        from gepa_standalone.core.llm_factory import call_llm

        azure_env(model)
        assert call_llm("hi", temperature=temperature, max_tokens=max_tokens) == "ok"

        body = capture_azure_post["body"]
        assert body["model"] == model.split("/", 1)[1]
        assert body["temperature"] == expected_temp
        assert body[token_key] == expected_tokens
        _assert_no_new_keys(body)
        assert capture_azure_post["query"].get("api-version") == AZURE_VERSION


class TestDspyLmAzure:
    def test_dspy_lm_kwargs_unchanged(self):
        lm = _azure("azure/gpt-4.1-mini", temperature=0.3, max_tokens=300).get_dspy_lm()

        assert lm.model == "azure/gpt-4.1-mini"
        params = lm.engine.params
        assert params["temperature"] == 0.3
        assert params["max_tokens"] == 300
        assert params["api_base"] == AZURE_BASE
        assert params["api_version"] == AZURE_VERSION
        _assert_no_new_keys(params)

    def test_dspy_lm_wire_body_unchanged(self, capture_azure_post):
        lm = _azure("azure/gpt-4o", temperature=0.7, max_tokens=200).get_dspy_lm()

        lm("hi")

        body = capture_azure_post["body"]
        assert body["model"] == "gpt-4o"
        assert body["temperature"] == 0.7
        assert body["max_tokens"] == 200
        _assert_no_new_keys(body)


class TestValidateConnectionAzure:
    @pytest.mark.parametrize(
        ("model", "token_key", "expected_tokens", "expected_temp"),
        [
            ("azure/gpt-4.1-mini", "max_tokens", 5, 0.7),
            ("azure/gpt-5.4-mini", "max_completion_tokens", 16000, 1.0),
        ],
    )
    def test_probe_body(self, capture_azure_post, model, token_key, expected_tokens, expected_temp):
        assert _azure(model, temperature=0.7).validate_connection() is True

        body = capture_azure_post["body"]
        assert body[token_key] == expected_tokens
        assert body["temperature"] == expected_temp
        _assert_no_new_keys(body)


class TestNonAnthropicIgnoresNewParams:
    @pytest.mark.parametrize("model", ["azure/gpt-4.1-mini", "azure/gpt-5.4-mini", "openai/gpt-4o"])
    def test_valid_effort_and_thinking_are_not_sent(self, model, caplog):
        plain = _azure(model, temperature=0.1, max_tokens=400)
        configured = _azure(model, temperature=0.1, max_tokens=400, effort="high", thinking="off")

        with caplog.at_level(logging.WARNING):
            configured.validate()

        assert configured.to_kwargs() == plain.to_kwargs()
        assert caplog.text == ""

    def test_from_env_with_effort_set_keeps_azure_kwargs(self, azure_env, monkeypatch):
        azure_env("azure/gpt-4.1-mini")
        monkeypatch.setenv("LLM_EFFORT_TASK", "low")
        monkeypatch.setenv("LLM_THINKING_TASK", "off")

        kwargs = LLMConfig.from_env("task").to_kwargs()

        assert kwargs["model"] == "azure/gpt-4.1-mini"
        assert kwargs["api_base"] == AZURE_BASE
        assert kwargs["api_version"] == AZURE_VERSION
        _assert_no_new_keys(kwargs)

    def test_apply_constraints_does_not_mutate_input(self):
        config = _azure("azure/gpt-5.4-mini")
        original = {"model": config.model, "temperature": 0.2, "max_tokens": 50}
        snapshot = dict(original)

        result = config.apply_constraints(original)

        assert original == snapshot
        assert result is not original
        assert result["temperature"] == 1.0
        assert result["max_tokens"] == 16000

    def test_describe_keeps_temperature_line(self):
        text = _azure("azure/gpt-4.1-mini", temperature=0.1, max_tokens=400).describe()

        assert "temperature: 0.1" in text
        assert "not sent" not in text
