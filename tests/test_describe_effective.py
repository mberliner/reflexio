"""SPEC-103 FR-010: describe() muestra los parametros efectivos enviados."""

from unittest.mock import patch

import pytest

from gepa_standalone.adapters.simple_classifier_adapter import SimpleClassifierAdapter
from gepa_standalone.adapters.simple_extractor_adapter import SimpleExtractorAdapter
from gepa_standalone.adapters.simple_rag_adapter import SimpleRAGAdapter
from gepa_standalone.adapters.simple_sql_adapter import SimpleSQLAdapter
from shared.llm import LLMConfig


def _cfg(alias: str, **kwargs) -> LLMConfig:
    params = {
        "model": f"anthropic/{alias}",
        "api_key": "x",
        "temperature": 0.3,
        "max_tokens": 2000,
        "role": "task",
        "effort": None,
        "thinking": "default",
    }
    params.update(kwargs)
    return LLMConfig(**params)


class TestDescribeAnthropic:
    def test_temperature_not_sent_notes_ignored_value(self):
        text = _cfg("claude-opus-4-7").describe()

        assert "temperature: not sent (0.3 in config is ignored)" in text

    def test_temperature_sent_for_family_that_accepts_it(self):
        text = _cfg("claude-haiku-4-5").describe()

        assert "temperature: 0.3" in text
        assert "not sent" not in text

    def test_default_effort_and_reasoning_mode(self):
        text = _cfg("claude-opus-5-5").describe()

        assert "effort:      medium (default)" in text
        assert "thinking:    adaptive" in text

    def test_configured_effort_is_marked_as_config(self):
        text = _cfg("claude-opus-5-5", effort="high").describe()

        assert "effort:      high (config)" in text

    def test_thinking_off_is_reported(self):
        text = _cfg("claude-haiku-5-5", thinking="off").describe()

        assert "thinking:    off" in text

    def test_family_without_effort_has_no_effort_line(self):
        text = _cfg("claude-haiku-4-5").describe()

        assert "effort:" not in text

    def test_max_tokens_raised_when_reasoning_active(self):
        text = _cfg("claude-opus-5-5").describe()

        assert "max_tokens:  2000 (requested) -> 16000 (reasoning override)" in text

    def test_per_call_max_tokens_is_reported_instead_of_config(self):
        text = _cfg("claude-opus-5-5").describe(max_tokens=50)

        assert "50 (requested) -> 16000" in text
        assert "2000" not in text

    def test_per_call_max_tokens_without_reasoning_is_not_flagged(self):
        text = _cfg("claude-haiku-4-5").describe(max_tokens=50)

        assert "max_tokens:  50" in text
        assert "override" not in text


class TestDescribeOtherProviders:
    def test_azure_per_call_max_tokens(self):
        config = LLMConfig(model="azure/gpt-4.1-mini", api_key="x", max_tokens=2000)

        text = config.describe(max_tokens=200)

        assert "max_tokens:  200" in text
        assert "effort:" not in text
        assert "thinking:" not in text


@pytest.fixture
def _patched_configs():
    cfg = LLMConfig(model="azure/gpt-4.1-mini", api_key="x")
    with (
        patch("gepa_standalone.adapters.base_adapter.get_task_config", return_value=cfg),
    ):
        yield


@pytest.mark.usefixtures("_patched_configs")
class TestAdapterMaxTokens:
    def test_classifier(self):
        assert SimpleClassifierAdapter(valid_classes=["a"]).task_max_tokens == 50

    def test_sql(self):
        assert SimpleSQLAdapter().task_max_tokens == 200

    def test_extractor_default_and_explicit(self):
        assert SimpleExtractorAdapter(required_fields=["a"]).task_max_tokens == 4000
        explicit = SimpleExtractorAdapter(required_fields=["a"], max_response_tokens=123)
        assert explicit.task_max_tokens == 123

    def test_rag_task_and_judge(self):
        adapter = SimpleRAGAdapter(LLMConfig(model="azure/gpt-4.1-mini", api_key="x"))

        assert adapter.task_max_tokens == 400
        assert adapter.judge_max_tokens == 200
