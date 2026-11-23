"""
SPEC-103 FR-009 (2b) y SPEC-104 (2a): respuesta sin texto en los caminos LiteLLM.

Cubre el helper `response_text`, `call_llm`, `get_lm_function` (tarea y
reflexion), los adapters de gepa_standalone y el juez de RAG. Desde SPEC-104 2a
la respuesta sin texto sale de la llamada comun como `EmptyResponseError` con la
clase de capa 1 de su `finish_reason` normalizado por LiteLLM.
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
    get_failure_tracker,
    response_text,
)
from tests.conftest import make_completion_response

# (contenido, finish_reason normalizado, clase de capa 1 esperada)
EMPTY_CASES = [
    (None, "length", "presupuesto"),
    ("", "stop", "sin_texto"),
    ("   \n", "content_filter", "filtro_salida"),
]


def _response(content, finish_reason="stop"):
    return make_completion_response(content, finish_reason)


def _patch_completion(monkeypatch, content, finish_reason="stop"):
    monkeypatch.setattr("litellm.completion", lambda *a, **k: _response(content, finish_reason))


class TestResponseTextHelper:
    def test_returns_content_unchanged(self):
        assert response_text(_response(" hola "), "task") == " hola "

    @pytest.mark.parametrize(("content", "reason", "clase"), EMPTY_CASES)
    def test_empty_raises_with_cause(self, content, reason, clase, caplog):
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
    @pytest.mark.parametrize(("content", "reason", "clase"), EMPTY_CASES)
    def test_get_lm_function_raises(self, mock_env, monkeypatch, role, content, reason, clase):
        _patch_completion(monkeypatch, content, reason)
        func = LLMConfig.from_env("task").get_lm_function(role=role)
        with pytest.raises(EmptyResponseError) as exc_info:
            func("hola")
        assert exc_info.value.role == role
        assert exc_info.value.finish_reason == reason
        assert exc_info.value.failure.clase.value == clase

    @pytest.mark.parametrize(("content", "reason", "clase"), EMPTY_CASES)
    def test_call_llm_raises(self, mock_env, monkeypatch, content, reason, clase, caplog):
        _patch_completion(monkeypatch, content, reason)
        with caplog.at_level(logging.WARNING), pytest.raises(EmptyResponseError) as exc_info:
            call_llm("hola", model_name="task")
        assert exc_info.value.failure.clase.value == clase
        # SPEC-103 FR-009: la causa de la respuesta sin texto sigue registrada
        assert "rol=task" in caplog.text
        assert reason in caplog.text

    def test_call_llm_returns_text(self, mock_env, monkeypatch):
        _patch_completion(monkeypatch, "ok")
        assert call_llm("hola", model_name="task") == "ok"


class TestAdapters:
    @pytest.mark.parametrize(("content", "reason", "clase"), EMPTY_CASES)
    @pytest.mark.parametrize("traces", [False, True])
    def test_classifier_scores_zero_and_logs_cause(
        self, mock_env, monkeypatch, capsys, caplog, content, reason, clase, traces
    ):
        # Comportamiento vigente hasta 3c (SPEC-103 FR-009): score 0.0; 3c lo pasa a NE.
        calls = iter([_response(content, reason), _response("greeting")])
        monkeypatch.setattr("litellm.completion", lambda *a, **k: next(calls))
        adapter = SimpleClassifierAdapter(valid_classes=["greeting", "farewell"])
        batch = [{"text": "x", "label": "greeting"}, {"text": "hi", "label": "greeting"}]

        with caplog.at_level(logging.WARNING):
            result = adapter.evaluate(batch, {"system_prompt": "p"}, capture_traces=traces)

        assert result.scores == [0.0, 1.0]
        assert len(result.outputs) == len(result.scores) == len(batch)
        assert "rol=task" in capsys.readouterr().out + caplog.text
        assert reason in caplog.text
        if traces:
            assert len(result.trajectories) == len(batch)

    def test_classifier_unclassified_error_aborts_run(self, mock_env, monkeypatch):
        # SPEC-104 regla 3: una excepcion no clasificada es `configuracion` y fija el
        # aborto; la llamada siguiente no llega al LLM. Que el adapter descarte los
        # ejemplos (D-019) en vez de propagar `RunAborted` lo corrigen 3c y 4b.
        completion = MagicMock(side_effect=[RuntimeError("boom"), _response("greeting")])
        monkeypatch.setattr("litellm.completion", completion)
        adapter = SimpleClassifierAdapter(valid_classes=["greeting"])
        batch = [{"text": "x", "label": "greeting"}, {"text": "hi", "label": "greeting"}]

        with pytest.raises(RuntimeError, match="Todos los ejemplos fallaron"):
            adapter.evaluate(batch, {"system_prompt": "p"})

        assert completion.call_count == 1
        assert get_failure_tracker().aborted

    @pytest.mark.parametrize(("content", "reason", "clase"), EMPTY_CASES)
    @pytest.mark.parametrize("traces", [False, True])
    def test_sql_scores_zero_and_logs_cause(
        self, mock_env, monkeypatch, caplog, content, reason, clase, traces
    ):
        calls = iter([_response(content, reason), _response("SELECT 1")])
        monkeypatch.setattr("litellm.completion", lambda *a, **k: next(calls))
        adapter = SimpleSQLAdapter()
        ex = {"schema": "t(a)", "expected_sql": "SELECT 1"}
        batch = [{"question": "a", "extracted": ex}, {"question": "b", "extracted": ex}]

        with caplog.at_level(logging.WARNING):
            result = adapter.evaluate(batch, {"system_prompt": "p"}, capture_traces=traces)

        assert result.scores == [0.0, 1.0]
        assert len(result.outputs) == len(result.scores) == len(batch)
        assert reason in caplog.text
        if traces:
            assert len(result.trajectories) == len(batch)

    def test_sql_unclassified_error_aborts_run(self, mock_env, monkeypatch):
        # Igual que en el clasificador: `configuracion` aborta (3c y 4b ajustan el adapter).
        completion = MagicMock(side_effect=[RuntimeError("boom"), _response("SELECT 1")])
        monkeypatch.setattr("litellm.completion", completion)
        adapter = SimpleSQLAdapter()
        ex = {"schema": "t(a)", "expected_sql": "SELECT 1"}
        batch = [{"question": "a", "extracted": ex}, {"question": "b", "extracted": ex}]

        with pytest.raises(RuntimeError, match="Todos los ejemplos fallaron"):
            adapter.evaluate(batch, {"system_prompt": "p"})

        assert completion.call_count == 1
        assert get_failure_tracker().aborted

    def test_extractor_scores_zero(self, mock_env, monkeypatch):
        _patch_completion(monkeypatch, "", "stop")
        adapter = SimpleExtractorAdapter(required_fields=["name"])
        batch = [{"text": "x", "extracted": {"name": "Ana"}}]

        result = adapter.evaluate(batch, {"system_prompt": "p"})

        assert result.scores == [0.0]
        assert len(result.outputs) == 1

    @pytest.mark.parametrize(("content", "reason", "clase"), EMPTY_CASES)
    def test_rag_task_empty_scores_zero_not_content_filter(
        self, mock_env, monkeypatch, content, reason, clase
    ):
        _patch_completion(monkeypatch, content, reason)
        adapter = SimpleRAGAdapter()
        batch = [{"question": "q", "context": "c", "answer": "a"}]

        result = adapter.evaluate(batch, {"system_prompt": "p"})

        assert result.scores == [0.0]
        assert "Content filter" not in str(result.outputs)
        assert reason in str(result.outputs)

    def test_rag_judge_empty_names_judge(self, mock_env, monkeypatch, caplog):
        _patch_completion(monkeypatch, None, "length")
        adapter = SimpleRAGAdapter()
        with caplog.at_level(logging.WARNING):
            score, feedback = adapter._evaluate_with_judge("q", "gt", "gen")

        assert score == 0.0
        assert "Error del Juez" in feedback
        # Rol del contador (SPEC-104 D2): `judge`, no `juez`
        assert "rol=judge" in caplog.text
        assert "finish_reason=length" in caplog.text

    def test_rag_judge_config_error_propagates(self, mock_env, monkeypatch):
        adapter = SimpleRAGAdapter()

        def raise_config_error(*args, **kwargs):
            raise LLMConfigError("invalida", "anthropic/claude-opus-5-5", "LLM_EFFORT_TASK")

        monkeypatch.setattr(adapter, "_complete", raise_config_error)

        with pytest.raises(LLMConfigError):
            adapter._evaluate_with_judge("q", "gt", "gen")
