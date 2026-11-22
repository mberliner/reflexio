"""
SPEC-103 FR-009 (2b): respuesta sin texto en los caminos LiteLLM.

Cubre el helper `response_text`, `call_llm`, `get_lm_function` (tarea y
reflexion), los adapters de gepa_standalone y el juez de RAG.
"""

import logging
from unittest.mock import MagicMock

import pytest

from gepa_standalone.adapters.simple_classifier_adapter import SimpleClassifierAdapter
from gepa_standalone.adapters.simple_extractor_adapter import SimpleExtractorAdapter
from gepa_standalone.adapters.simple_rag_adapter import SimpleRAGAdapter
from gepa_standalone.adapters.simple_sql_adapter import SimpleSQLAdapter
from gepa_standalone.core.llm_factory import call_llm
from shared.llm import (
    EmptyResponseError,
    LLMConfig,
    LLMConfigError,
    LLMConnectionError,
    response_text,
)

EMPTY_CASES = [(None, "max_tokens"), ("", "refusal"), ("   \n", "max_tokens")]


def _response(content, finish_reason="stop"):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].finish_reason = finish_reason
    return response


def _patch_completion(monkeypatch, content, finish_reason="stop"):
    monkeypatch.setattr("litellm.completion", lambda *a, **k: _response(content, finish_reason))


class TestResponseTextHelper:
    def test_returns_content_unchanged(self):
        assert response_text(_response(" hola "), "task") == " hola "

    @pytest.mark.parametrize(("content", "reason"), EMPTY_CASES)
    def test_empty_raises_with_cause(self, content, reason, caplog):
        with caplog.at_level(logging.WARNING), pytest.raises(EmptyResponseError) as exc_info:
            response_text(_response(content, reason), "reflection")
        assert exc_info.value.role == "reflection"
        assert exc_info.value.finish_reason == reason
        assert reason in caplog.text
        assert "reflection" in caplog.text

    def test_not_a_connection_error(self):
        assert not issubclass(EmptyResponseError, LLMConnectionError)


class TestLmFunctions:
    @pytest.mark.parametrize("role", ["task", "reflection"])
    @pytest.mark.parametrize(("content", "reason"), EMPTY_CASES)
    def test_get_lm_function_raises(self, mock_env, monkeypatch, role, content, reason):
        _patch_completion(monkeypatch, content, reason)
        func = LLMConfig.from_env("task").get_lm_function(role=role)
        with pytest.raises(EmptyResponseError) as exc_info:
            func("hola")
        assert exc_info.value.role == role
        assert exc_info.value.finish_reason == reason

    @pytest.mark.parametrize(("content", "reason"), EMPTY_CASES)
    def test_call_llm_raises(self, mock_env, monkeypatch, content, reason):
        _patch_completion(monkeypatch, content, reason)
        with pytest.raises(EmptyResponseError):
            call_llm("hola", model_name="task")

    def test_call_llm_returns_text(self, mock_env, monkeypatch):
        _patch_completion(monkeypatch, "ok")
        assert call_llm("hola", model_name="task") == "ok"


class TestAdapters:
    @pytest.mark.parametrize(("content", "reason"), EMPTY_CASES)
    def test_classifier_does_not_abort_and_logs_cause(
        self, mock_env, monkeypatch, capsys, caplog, content, reason
    ):
        calls = iter([_response(content, reason), _response("greeting")])
        monkeypatch.setattr("litellm.completion", lambda *a, **k: next(calls))
        adapter = SimpleClassifierAdapter(valid_classes=["greeting", "farewell"])
        batch = [{"text": "x", "label": "greeting"}, {"text": "hi", "label": "greeting"}]

        with caplog.at_level(logging.WARNING):
            result = adapter.evaluate(batch, {"system_prompt": "p"})

        assert result.scores == [1.0]
        assert reason in capsys.readouterr().out + caplog.text

    def test_sql_does_not_abort(self, mock_env, monkeypatch):
        calls = iter([_response(None, "max_tokens"), _response("SELECT 1")])
        monkeypatch.setattr("litellm.completion", lambda *a, **k: next(calls))
        adapter = SimpleSQLAdapter()
        ex = {"schema": "t(a)", "expected_sql": "SELECT 1"}
        batch = [{"question": "a", "extracted": ex}, {"question": "b", "extracted": ex}]

        result = adapter.evaluate(batch, {"system_prompt": "p"})

        assert result.scores == [1.0]

    def test_extractor_scores_zero(self, mock_env, monkeypatch):
        _patch_completion(monkeypatch, "", "refusal")
        adapter = SimpleExtractorAdapter(required_fields=["name"])
        batch = [{"text": "x", "extracted": {"name": "Ana"}}]

        result = adapter.evaluate(batch, {"system_prompt": "p"})

        assert result.scores == [0.0]
        assert len(result.outputs) == 1

    @pytest.mark.parametrize(("content", "reason"), EMPTY_CASES)
    def test_rag_task_empty_scores_zero_not_content_filter(
        self, mock_env, monkeypatch, content, reason
    ):
        _patch_completion(monkeypatch, content, reason)
        adapter = SimpleRAGAdapter()
        batch = [{"question": "q", "context": "c", "answer": "a"}]

        result = adapter.evaluate(batch, {"system_prompt": "p"})

        assert result.scores == [0.0]
        assert "Content filter" not in str(result.outputs)
        assert reason in str(result.outputs)

    def test_rag_judge_empty_names_judge(self, mock_env, monkeypatch, caplog):
        _patch_completion(monkeypatch, None, "max_tokens")
        adapter = SimpleRAGAdapter()
        with caplog.at_level(logging.WARNING):
            score, feedback = adapter._evaluate_with_judge("q", "gt", "gen")

        assert score == 0.0
        assert "Error del Juez" in feedback
        assert "rol=juez" in caplog.text

    def test_rag_judge_config_error_propagates(self, mock_env, monkeypatch):
        adapter = SimpleRAGAdapter()

        def raise_config_error(*args, **kwargs):
            raise LLMConfigError("invalida", "anthropic/claude-opus-5-5", "LLM_EFFORT_TASK")

        monkeypatch.setattr(adapter, "_call_llm_with_retry", raise_config_error)

        with pytest.raises(LLMConfigError):
            adapter._evaluate_with_judge("q", "gt", "gen")
