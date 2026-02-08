"""
Tests for shared/llm/ module.

Covers errors.py (LLMConnectionError) and config.py (LLMConfig).
"""

from unittest.mock import MagicMock

import pytest

from shared.llm.config import LLMConfig
from shared.llm.errors import LLMConnectionError

# ==================== LLMConnectionError ====================


class TestLLMConnectionError:
    def test_minimal_creation(self):
        err = LLMConnectionError(
            message="test error",
            provider="azure",
            model="azure/gpt-4",
        )
        assert err.message == "test error"
        assert err.provider == "azure"
        assert err.model == "azure/gpt-4"

    def test_full_creation(self):
        err = LLMConnectionError(
            message="full error",
            provider="openai",
            model="openai/gpt-4",
            endpoint="https://api.example.com",
            api_version="2024-01-01",
            original_error="Connection refused",
            extra_details={"status_code": 500},
            suggestions=["Check endpoint", "Retry later"],
        )
        assert err.endpoint == "https://api.example.com"
        assert err.api_version == "2024-01-01"
        assert err.original_error == "Connection refused"
        assert err.extra_details == {"status_code": 500}
        assert len(err.suggestions) == 2

    def test_format_error_contains_header(self):
        err = LLMConnectionError(message="x", provider="azure", model="m")
        formatted = err.format_error()
        assert "LLM CONNECTION ERROR" in formatted
        assert "=" * 60 in formatted
        assert "Provider: azure" in formatted
        assert "Model: m" in formatted

    def test_format_error_includes_endpoint_when_set(self):
        err = LLMConnectionError(
            message="x",
            provider="azure",
            model="m",
            endpoint="https://ep.com",
            api_version="v1",
        )
        formatted = err.format_error()
        assert "Endpoint: https://ep.com" in formatted
        assert "API Version: v1" in formatted

    def test_format_error_excludes_endpoint_when_none(self):
        err = LLMConnectionError(message="x", provider="p", model="m")
        formatted = err.format_error()
        assert "Endpoint:" not in formatted
        assert "API Version:" not in formatted

    def test_format_error_filters_none_extra_details(self):
        err = LLMConnectionError(
            message="x",
            provider="p",
            model="m",
            extra_details={"valid": "yes", "empty": "", "none_val": None},
        )
        formatted = err.format_error()
        assert "valid: yes" in formatted
        details_section = formatted.split("Details:")[1].split("=")[0]
        assert "empty" not in details_section
        assert "none_val" not in formatted

    def test_str_equals_format_error(self):
        err = LLMConnectionError(message="test", provider="p", model="m")
        assert str(err) == err.format_error()


# ==================== LLMConfig Basics ====================


class TestLLMConfigBasics:
    def test_defaults(self):
        config = LLMConfig(model="azure/gpt-4")
        assert config.api_version == "2024-02-15-preview"
        assert config.temperature == 0.7
        assert config.max_tokens == 1000
        assert config.cache is False

    def test_explicit_params(self):
        config = LLMConfig(
            model="openai/gpt-4",
            api_key="key123",
            api_base="https://api.openai.com",
            api_version="2024-01-01",
            temperature=0.0,
            max_tokens=500,
            cache=True,
        )
        assert config.model == "openai/gpt-4"
        assert config.api_key == "key123"
        assert config.temperature == 0.0
        assert config.cache is True


# ==================== LLMConfig.from_env ====================


class TestLLMConfigFromEnv:
    def test_reads_model_task(self, mock_env):
        config = LLMConfig.from_env("task")
        assert config.model == "azure/gpt-4.1-mini"
        assert config.api_key == "test-key-123"
        assert config.api_base == "https://test.openai.azure.com/"

    def test_reads_different_model(self, mock_env, monkeypatch):
        monkeypatch.setenv("LLM_MODEL_REFLECTION", "azure/gpt-4o")
        config = LLMConfig.from_env("reflection")
        assert config.model == "azure/gpt-4o"

    def test_overrides_priority(self, mock_env):
        config = LLMConfig.from_env("task", temperature=0.0, max_tokens=50)
        assert config.temperature == 0.0
        assert config.max_tokens == 50

    @pytest.mark.parametrize("env_val", ["true", "True", "TRUE"])
    def test_cache_parsing_true(self, mock_env, monkeypatch, env_val):
        monkeypatch.setenv("LLM_CACHE", env_val)
        config = LLMConfig.from_env("task")
        assert config.cache is True

    def test_cache_parsing_false(self, mock_env, monkeypatch):
        monkeypatch.setenv("LLM_CACHE", "false")
        config = LLMConfig.from_env("task")
        assert config.cache is False

    def test_defaults_without_env(self, clear_env):
        config = LLMConfig.from_env("task")
        assert config.model == "azure/gpt-4.1-mini"
        assert config.api_key is None


# ==================== LLMConfig.to_kwargs ====================


class TestLLMConfigToKwargs:
    def test_includes_required_fields(self):
        config = LLMConfig(
            model="azure/gpt-4",
            api_key="key",
            api_base="https://base.com",
            api_version="v1",
        )
        kwargs = config.to_kwargs()
        assert kwargs["model"] == "azure/gpt-4"
        assert kwargs["temperature"] == 0.7
        assert kwargs["max_tokens"] == 1000
        assert kwargs["api_key"] == "key"
        assert kwargs["api_base"] == "https://base.com"

    def test_excludes_cache_and_none_fields(self):
        config = LLMConfig(model="openai/gpt-4")
        kwargs = config.to_kwargs()
        assert "cache" not in kwargs
        assert "api_key" not in kwargs
        assert "api_base" not in kwargs


# ==================== LLMConfig.validate ====================


class TestLLMConfigValidate:
    def test_passes_with_complete_config(self):
        config = LLMConfig(
            model="azure/gpt-4",
            api_key="key",
            api_base="https://base.com",
        )
        config.validate()

    def test_fails_without_api_key(self):
        config = LLMConfig(model="azure/gpt-4")
        with pytest.raises(LLMConnectionError) as exc_info:
            config.validate()
        assert "LLM_API_KEY" in str(exc_info.value)

    def test_azure_fails_without_api_base(self):
        config = LLMConfig(model="azure/gpt-4", api_key="key")
        with pytest.raises(LLMConnectionError) as exc_info:
            config.validate()
        assert "LLM_API_BASE" in str(exc_info.value)

    def test_openai_passes_without_api_base(self):
        config = LLMConfig(model="openai/gpt-4", api_key="key")
        config.validate()


# ==================== LLMConfig.get_dspy_lm ====================


class TestLLMConfigGetDspyLM:
    def test_creates_dspy_lm(self, monkeypatch):
        import sys

        mock_lm_class = MagicMock()
        mock_dspy = MagicMock(LM=mock_lm_class)
        monkeypatch.setitem(sys.modules, "dspy", mock_dspy)

        config = LLMConfig(
            model="azure/gpt-4",
            api_key="key",
            api_base="https://base.com",
        )
        config.get_dspy_lm()

        mock_lm_class.assert_called_once()
        call_kwargs = mock_lm_class.call_args[1]
        assert call_kwargs["model"] == "azure/gpt-4"
        assert "cache" in call_kwargs

    def test_cache_passed_to_dspy(self, monkeypatch):
        import sys

        mock_lm_class = MagicMock()
        mock_dspy = MagicMock(LM=mock_lm_class)
        monkeypatch.setitem(sys.modules, "dspy", mock_dspy)

        config = LLMConfig(model="azure/gpt-4", cache=True)
        config.get_dspy_lm()

        call_kwargs = mock_lm_class.call_args[1]
        assert call_kwargs["cache"] is True


# ==================== LLMConfig.get_lm_function ====================


class TestLLMConfigGetLMFunction:
    def test_returns_callable(self, mock_litellm):
        config = LLMConfig(model="azure/gpt-4")
        fn = config.get_lm_function()
        assert callable(fn)

    def test_callable_invokes_litellm(self, mock_litellm):
        config = LLMConfig(model="azure/gpt-4")
        fn = config.get_lm_function()
        result = fn("Hello")

        assert result == "OK"
        mock_litellm.assert_called_once()
        call_kwargs = mock_litellm.call_args
        assert call_kwargs[1]["model"] == "azure/gpt-4"
        assert call_kwargs[1]["messages"] == [{"role": "user", "content": "Hello"}]


# ==================== LLMConfig.validate_connection ====================


class TestLLMConfigValidateConnection:
    def test_success(self, mock_litellm):
        config = LLMConfig(model="azure/gpt-4", api_key="key", api_base="https://base.com")
        assert config.validate_connection() is True

    def test_error_401(self, monkeypatch):
        exc = Exception("401 Unauthorized")
        monkeypatch.setattr("litellm.completion", MagicMock(side_effect=exc))

        config = LLMConfig(model="azure/gpt-4", api_key="bad", api_base="https://base.com")
        with pytest.raises(LLMConnectionError) as exc_info:
            config.validate_connection()
        assert "Authentication failed" in exc_info.value.message

    def test_error_404(self, monkeypatch):
        exc = Exception("404 not found")
        monkeypatch.setattr("litellm.completion", MagicMock(side_effect=exc))

        config = LLMConfig(model="azure/gpt-4", api_key="key", api_base="https://base.com")
        with pytest.raises(LLMConnectionError) as exc_info:
            config.validate_connection()
        assert "Model or deployment not found" in exc_info.value.message

    def test_error_429(self, monkeypatch):
        exc = Exception("429 rate limit exceeded")
        monkeypatch.setattr("litellm.completion", MagicMock(side_effect=exc))

        config = LLMConfig(model="azure/gpt-4", api_key="key", api_base="https://base.com")
        with pytest.raises(LLMConnectionError) as exc_info:
            config.validate_connection()
        assert "Rate limit exceeded" in exc_info.value.message

    def test_error_vnet(self, monkeypatch):
        exc = Exception("Virtual Network rules blocking request")
        monkeypatch.setattr("litellm.completion", MagicMock(side_effect=exc))

        config = LLMConfig(model="azure/gpt-4", api_key="key", api_base="https://base.com")
        with pytest.raises(LLMConnectionError) as exc_info:
            config.validate_connection()
        assert "VNet" in exc_info.value.message
        assert any("VPN" in s for s in exc_info.value.suggestions)

    def test_error_generic(self, monkeypatch):
        exc = Exception("Something totally unexpected")
        monkeypatch.setattr("litellm.completion", MagicMock(side_effect=exc))

        config = LLMConfig(model="azure/gpt-4", api_key="key", api_base="https://base.com")
        with pytest.raises(LLMConnectionError) as exc_info:
            config.validate_connection()
        assert "Connection failed" in exc_info.value.message

    def test_truncates_original_error(self, monkeypatch):
        long_msg = "x" * 1000
        exc = Exception(long_msg)
        monkeypatch.setattr("litellm.completion", MagicMock(side_effect=exc))

        config = LLMConfig(model="azure/gpt-4", api_key="key", api_base="https://base.com")
        with pytest.raises(LLMConnectionError) as exc_info:
            config.validate_connection()
        assert len(exc_info.value.original_error) == 500
