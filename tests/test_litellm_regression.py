"""
Offline regression tests for LiteLLM request serialization (Anthropic and Azure OpenAI).

Verifies wire-level HTTP payloads and headers built by the pinned LiteLLM version
without making real network requests:
- Pinned LiteLLM version matches requirements.txt (SSOT).
- Anthropic Messages API headers (anthropic-version) and parameter pass-through
  (output_config.effort, reasoning_effort, thinking, api_version isolation).
- Anthropic support matrix (SPEC-103): models that preserve vs drop temperature.
- Azure OpenAI Chat Completions payloads (max_tokens vs max_completion_tokens,
  temperature, deployment routing, api-version) directly and through LLMConfig.
"""

from importlib.metadata import version as pkg_version
from pathlib import Path
from unittest import mock

import litellm
import pytest

from shared.llm.config import LLMConfig

EXPECTED_LITELLM_VERSION = "1.108.5"
EXPECTED_ANTHROPIC_VERSION_HEADER = "2023-06-01"

ANTHROPIC_TEMPERATURE_MATRIX: list[tuple[str, bool]] = [
    ("claude-haiku-4-5", True),
    ("claude-opus-4-5", True),
    ("claude-sonnet-4-6", True),
    ("claude-opus-4-6", True),
    ("claude-opus-4-7", False),
    ("claude-opus-4-8", False),
    ("claude-sonnet-5", False),
    ("claude-opus-5", False),
    ("claude-haiku-5-5", False),
    ("claude-sonnet-5-5", False),
    ("claude-opus-5-5", False),
    ("claude-fable-5", False),
    ("claude-fable-5-1", False),
    ("claude-fable-5-2", False),
]


@pytest.fixture(autouse=True)
def _reset_litellm_drop_params(monkeypatch):
    """Ensure global litellm.drop_params starts False and never leaks across tests."""
    monkeypatch.setattr(litellm, "drop_params", False)


# ==================== Version Pinning ====================


class TestLiteLLMPinnedVersion:
    def test_installed_version_matches_pinned_requirement(self):
        repo_root = Path(__file__).resolve().parents[1]
        req_lines = [
            line.strip()
            for line in (repo_root / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert f"litellm=={EXPECTED_LITELLM_VERSION}" in req_lines
        assert pkg_version("litellm") == EXPECTED_LITELLM_VERSION


# ==================== Anthropic Wire Contract (probe_litellm) ====================


class TestAnthropicWireContract:
    @pytest.mark.parametrize(
        "model",
        ["claude-haiku-4-5", "claude-sonnet-5-5", "claude-opus-5-5"],
    )
    def test_anthropic_version_header_and_azure_api_version_isolation(
        self, capture_anthropic_post, model
    ):
        response = litellm.completion(
            model=f"anthropic/{model}",
            messages=[{"role": "user", "content": "hi"}],
            api_key="x",
            max_tokens=100,
            drop_params=True,
            api_version="2024-02-15-preview",
        )

        assert response.choices[0].message.content == "ok"
        assert capture_anthropic_post["headers"].get("anthropic-version") == (
            EXPECTED_ANTHROPIC_VERSION_HEADER
        )
        assert "api_version" not in capture_anthropic_post["body"]

    @pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-opus-5-5"])
    def test_claude_5_5_drops_temperature_with_drop_params(self, capture_anthropic_post, model):
        litellm.completion(
            model=f"anthropic/{model}",
            messages=[{"role": "user", "content": "hi"}],
            api_key="x",
            max_tokens=100,
            temperature=0.1,
            drop_params=True,
            api_version="2024-02-15-preview",
        )

        body = capture_anthropic_post["body"]
        assert "temperature" not in body
        assert body["max_tokens"] == 100

    def test_haiku_4_5_sends_temperature(self, capture_anthropic_post):
        litellm.completion(
            model="anthropic/claude-haiku-4-5",
            messages=[{"role": "user", "content": "hi"}],
            api_key="x",
            max_tokens=100,
            temperature=0.1,
            drop_params=True,
            api_version="2024-02-15-preview",
        )

        body = capture_anthropic_post["body"]
        assert body["temperature"] == 0.1
        assert body["max_tokens"] == 100

    def test_output_config_effort_passed_intact_without_thinking(self, capture_anthropic_post):
        litellm.completion(
            model="anthropic/claude-sonnet-5-5",
            messages=[{"role": "user", "content": "hi"}],
            api_key="x",
            max_tokens=100,
            drop_params=True,
            output_config={"effort": "low"},
        )

        body = capture_anthropic_post["body"]
        assert body["output_config"] == {"effort": "low"}
        assert "thinking" not in body

    def test_reasoning_effort_translates_to_adaptive_thinking_and_output_config(
        self, capture_anthropic_post
    ):
        litellm.completion(
            model="anthropic/claude-sonnet-5-5",
            messages=[{"role": "user", "content": "hi"}],
            api_key="x",
            max_tokens=100,
            drop_params=True,
            reasoning_effort="low",
        )

        body = capture_anthropic_post["body"]
        assert body["output_config"] == {"effort": "low"}
        assert body["thinking"] == {"type": "adaptive", "display": "summarized"}
        assert "budget_tokens" not in body["thinking"]

    def test_thinking_between_tools_passed_intact(self, capture_anthropic_post):
        litellm.completion(
            model="anthropic/claude-sonnet-5-5",
            messages=[{"role": "user", "content": "hi"}],
            api_key="x",
            max_tokens=100,
            drop_params=True,
            thinking={"type": "between_tools"},
        )

        body = capture_anthropic_post["body"]
        assert body["thinking"] == {"type": "between_tools"}
        assert "output_config" not in body


# ==================== Anthropic Matrix (probe_matrix) ====================


class TestAnthropicMatrixTemperatureContract:
    @pytest.mark.parametrize(("model", "expects_temperature"), ANTHROPIC_TEMPERATURE_MATRIX)
    def test_matrix_temperature_with_drop_params_true(
        self, capture_anthropic_post, model, expects_temperature
    ):
        litellm.completion(
            model=f"anthropic/{model}",
            messages=[{"role": "user", "content": "hi"}],
            api_key="x",
            max_tokens=100,
            temperature=0.1,
            drop_params=True,
        )

        body = capture_anthropic_post["body"]
        assert body["model"] == model
        assert body["max_tokens"] == 100
        assert ("temperature" in body) is expects_temperature
        if expects_temperature:
            assert body["temperature"] == 0.1
        assert capture_anthropic_post["headers"].get("anthropic-version") == (
            EXPECTED_ANTHROPIC_VERSION_HEADER
        )

    @pytest.mark.parametrize(
        "model",
        [m for m, sends_temp in ANTHROPIC_TEMPERATURE_MATRIX if not sends_temp],
    )
    def test_matrix_non_temperature_models_reject_temperature_when_drop_params_false(
        self, capture_anthropic_post, model
    ):
        with pytest.raises(litellm.UnsupportedParamsError):
            litellm.completion(
                model=f"anthropic/{model}",
                messages=[{"role": "user", "content": "hi"}],
                api_key="x",
                max_tokens=100,
                temperature=0.1,
                drop_params=False,
            )


# ==================== Azure OpenAI Regression (probe_azure) ====================


class TestAzureOpenAIWireRegression:
    @pytest.mark.parametrize(
        ("model", "call_kwargs", "expected_fields", "absent_token_key"),
        [
            (
                "azure/gpt-4.1-mini",
                {"temperature": 0.1, "max_tokens": 100},
                {"model": "gpt-4.1-mini", "temperature": 0.1, "max_tokens": 100},
                "max_completion_tokens",
            ),
            (
                "azure/gpt-5.4-mini",
                {"temperature": 1.0, "max_tokens": 16000},
                {"model": "gpt-5.4-mini", "temperature": 1.0, "max_completion_tokens": 16000},
                "max_tokens",
            ),
            (
                "azure/gpt-4o",
                {"temperature": 0.7, "max_tokens": 2000},
                {"model": "gpt-4o", "temperature": 0.7, "max_tokens": 2000},
                "max_completion_tokens",
            ),
        ],
    )
    def test_azure_completion_wire_payload(
        self, capture_azure_post, model, call_kwargs, expected_fields, absent_token_key
    ):
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            api_key="x",
            api_base="https://x.openai.azure.com",
            api_version="2024-02-15-preview",
            drop_params=True,
            num_retries=0,
            **call_kwargs,
        )

        assert response.choices[0].message.content == "ok"
        assert capture_azure_post["path"] == "/chat/completions"
        assert capture_azure_post["query"].get("api-version") == "2024-02-15-preview"
        assert capture_azure_post["base_url"] == "https://x.openai.azure.com/openai/"

        body = capture_azure_post["body"]
        assert body["messages"] == [{"role": "user", "content": "hi"}]
        for key, value in expected_fields.items():
            assert body[key] == value
        assert absent_token_key not in body

    def test_azure_reasoning_model_through_llm_config(self, capture_azure_post):
        config = LLMConfig(
            model="azure/gpt-5.4-mini",
            api_key="x",
            api_base="https://x.openai.azure.com",
            api_version="2024-02-15-preview",
            temperature=0.1,
            max_tokens=400,
        )
        lm_fn = config.get_lm_function(role="task")
        with mock.patch("shared.llm.usage.record_usage"):
            result = lm_fn("hi")

        assert result == "ok"
        body = capture_azure_post["body"]
        assert body["model"] == "gpt-5.4-mini"
        assert body["temperature"] == 1.0
        assert body["max_completion_tokens"] == 16000
        assert "max_tokens" not in body
