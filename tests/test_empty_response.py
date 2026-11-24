"""
SPEC-103 FR-009 (2b) y SPEC-104 (2a, 3c): respuesta sin texto en los caminos LiteLLM.

Cubre `call_llm`, `get_lm_function` (tarea y
reflexion), los adapters de gepa_standalone y el juez de RAG. Desde SPEC-104 2a
la respuesta sin texto sale de la llamada comun como `EmptyResponseError` con la
clase de capa 1 de su `finish_reason` normalizado por LiteLLM; desde 3c cada
adapter la trata segun la tabla de la spec (score 0 del candidato o NE).
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
    LLMCallFailure,
    LLMConfig,
    LLMConfigError,
    LLMConnectionError,
    RunAborted,
    get_failure_tracker,
)
from tests.conftest import make_completion_response, project_warnings

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


class TestEmptyResponseError:
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
        with caplog.at_level(logging.DEBUG), pytest.raises(EmptyResponseError) as exc_info:
            call_llm("hola", model_name="task")
        assert exc_info.value.failure.clase.value == clase
        # SPEC-104 FR-007 / H-09: la capa de llamada deja un unico DEBUG por falla
        # (el de `raise_for_response`, sin duplicar) y ningun WARNING.
        debug_records = [
            r
            for r in caplog.records
            if r.levelno == logging.DEBUG and r.name.startswith("shared.llm")
        ]
        assert [r.getMessage() for r in debug_records] == [
            f"Falla de respuesta (rol=task, clase={clase}, finish_reason={reason})"
        ]
        assert not project_warnings(caplog)

    def test_call_llm_returns_text(self, mock_env, monkeypatch):
        _patch_completion(monkeypatch, "ok")
        assert call_llm("hola", model_name="task") == "ok"


# Tratamiento de la tarea segun la tabla de la spec: `filtro_salida` y `sin_texto` son NE;
# `presupuesto` se atribuye contra el baseline (que aca responde sano -> candidato, score 0).
TASK_TREATMENT = {
    "presupuesto": (True, "presupuesto_candidato"),
    "sin_texto": (False, "sin_texto"),
    "filtro_salida": (False, "filtro_salida"),
}


def _scripted(monkeypatch, fn):
    """`litellm.completion` con respuestas reales: `fn(system, user)` -> `ModelResponse`."""
    calls = []

    def completion(*args, **kwargs):
        messages = kwargs["messages"]
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user = messages[-1]["content"]
        calls.append((system, user))
        return fn(system, user)

    monkeypatch.setattr("litellm.completion", completion)
    return calls


class TestAdapters:
    @pytest.mark.parametrize(("content", "reason", "clase"), EMPTY_CASES)
    @pytest.mark.parametrize("traces", [False, True])
    @pytest.mark.parametrize("adapter_kind", ["classifier", "sql"])
    def test_task_failure_follows_treatment_table(
        self, mock_env, monkeypatch, caplog, content, reason, clase, traces, adapter_kind
    ):
        """FR-002 / FR-007: cada falla de la tarea es score 0 del candidato o NE segun la
        tabla, el lote conserva todos sus casos y se registra un WARNING por caso."""

        def respond(system, user):
            if system == "p" and "FALLA" in user:
                return _response(content, reason)
            return _response("greeting" if adapter_kind == "classifier" else "SELECT 1")

        _scripted(monkeypatch, respond)
        if adapter_kind == "classifier":
            adapter = SimpleClassifierAdapter(valid_classes=["greeting", "farewell"])
            batch = [
                {"case_id": "a", "text": "FALLA", "label": "greeting"},
                {"case_id": "b", "text": "hi", "label": "greeting"},
            ]
        else:
            adapter = SimpleSQLAdapter()
            ex = {"schema": "t(a)", "expected_sql": "SELECT 1"}
            batch = [
                {"case_id": "a", "question": "FALLA", "extracted": ex},
                {"case_id": "b", "question": "b", "extracted": ex},
            ]
        adapter.set_baseline("base")
        evaluated, key = TASK_TREATMENT[clase]

        with caplog.at_level(logging.WARNING):
            result = adapter.evaluate(batch, {"system_prompt": "p"}, capture_traces=traces)

        assert result.scores == [0.0, 1.0]
        assert len(result.outputs) == len(result.scores) == len(batch)
        assert result.outputs[0]["case_id"] == "a"
        assert result.outputs[0]["evaluated"] is evaluated
        assert result.outputs[0]["failure"]["clave"] == key
        assert result.outputs[1]["evaluated"] is True
        assert result.outputs[1]["failure"] is None
        if traces:
            assert len(result.trajectories) == len(batch)
            assert result.trajectories[0]["evaluated"] is evaluated
        snapshot = get_failure_tracker().snapshot()
        assert snapshot["counts"][key]["task"] == 1
        assert snapshot["attempts"]["task"] == 2
        warnings = project_warnings(caplog)
        assert len(warnings) == 1
        assert "rol=task" in warnings[0].getMessage()
        assert reason in warnings[0].getMessage()

    @pytest.mark.parametrize("adapter_kind", ["classifier", "sql"])
    def test_unclassified_error_aborts_run(self, mock_env, monkeypatch, adapter_kind):
        """Regla 3: excepcion no clasificada = `configuracion`; aborta (FR-006) y el adapter
        propaga `RunAborted` en vez de descartar ejemplos ni inventar un RuntimeError."""
        completion = MagicMock(side_effect=[RuntimeError("boom"), _response("greeting")])
        monkeypatch.setattr("litellm.completion", completion)
        if adapter_kind == "classifier":
            adapter = SimpleClassifierAdapter(valid_classes=["greeting"])
            batch = [
                {"case_id": "a", "text": "x", "label": "greeting"},
                {"case_id": "b", "text": "hi", "label": "greeting"},
            ]
        else:
            adapter = SimpleSQLAdapter()
            ex = {"schema": "t(a)", "expected_sql": "SELECT 1"}
            batch = [
                {"case_id": "a", "question": "a", "extracted": ex},
                {"case_id": "b", "question": "b", "extracted": ex},
            ]

        with pytest.raises(RunAborted):
            adapter.evaluate(batch, {"system_prompt": "p"})

        assert completion.call_count == 1
        assert get_failure_tracker().aborted

    @pytest.mark.parametrize(("content", "reason", "clase"), EMPTY_CASES)
    def test_extractor_task_failure_follows_treatment_table(
        self, mock_env, monkeypatch, content, reason, clase
    ):
        def respond(system, user):
            if system == "p":
                return _response(content, reason)
            return _response('{"name": "Ana"}')

        _scripted(monkeypatch, respond)
        adapter = SimpleExtractorAdapter(required_fields=["name"])
        adapter.set_baseline("base")
        batch = [{"case_id": "a", "text": "x", "extracted": {"name": "Ana"}}]
        evaluated, key = TASK_TREATMENT[clase]

        result = adapter.evaluate(batch, {"system_prompt": "p"})

        assert result.scores == [0.0]
        assert len(result.outputs) == 1
        assert result.outputs[0]["evaluated"] is evaluated
        assert result.outputs[0]["failure"]["clave"] == key

    @pytest.mark.parametrize(("content", "reason", "clase"), EMPTY_CASES)
    def test_rag_task_failure_follows_treatment_table(
        self, mock_env, monkeypatch, content, reason, clase
    ):
        def respond(system, user):
            if system == "p":
                return _response(content, reason)
            return _response("ok")

        _scripted(monkeypatch, respond)
        adapter = SimpleRAGAdapter()
        adapter.set_baseline("base")
        batch = [{"case_id": "a", "question": "q", "context": "c", "answer": "a"}]
        evaluated, key = TASK_TREATMENT[clase]

        result = adapter.evaluate(batch, {"system_prompt": "p"})

        assert result.scores == [0.0]
        assert "Content filter" not in str(result.outputs)
        assert result.outputs[0]["evaluated"] is evaluated
        assert result.outputs[0]["failure"]["clave"] == key
        assert result.outputs[0]["failure"]["finish_reason"] == reason
        # La tarea fallo: el juez no se intento (D4: un intento por caso y rol)
        assert get_failure_tracker().snapshot()["attempts"]["judge"] == 0

    def test_rag_judge_empty_is_ne_with_role_judge(self, mock_env, monkeypatch, caplog):
        """Falla de capa 1 del juez: el caso queda NE con rol `judge` (tabla de la spec)."""

        def respond(system, user):
            if "evaluador" in system:
                return _response(None, "length")
            return _response("Paris")

        _scripted(monkeypatch, respond)
        adapter = SimpleRAGAdapter()
        batch = [{"case_id": "a", "question": "q", "context": "c", "answer": "Paris"}]

        with caplog.at_level(logging.WARNING):
            result = adapter.evaluate(batch, {"system_prompt": "p"})

        assert result.scores == [0.0]
        assert result.outputs[0]["evaluated"] is False
        assert result.outputs[0]["failure"]["rol"] == "judge"
        snapshot = get_failure_tracker().snapshot()
        assert snapshot["counts"]["presupuesto"]["judge"] == 1
        assert snapshot["attempts"] == {"task": 1, "judge": 1, "reflection": 0}
        assert "rol=judge" in caplog.text
        assert "finish_reason=length" in caplog.text

    def test_rag_judge_failure_propagates_from_helper(self, mock_env, monkeypatch):
        _patch_completion(monkeypatch, None, "length")
        adapter = SimpleRAGAdapter()
        with pytest.raises(LLMCallFailure) as exc_info:
            adapter._evaluate_with_judge("q", "gt", "gen")
        assert exc_info.value.failure.rol == "judge"

    def test_rag_judge_config_error_propagates(self, mock_env, monkeypatch):
        adapter = SimpleRAGAdapter()

        def raise_config_error(*args, **kwargs):
            raise LLMConfigError("invalida", "anthropic/claude-opus-5-5", "LLM_EFFORT_TASK")

        monkeypatch.setattr(adapter, "_complete", raise_config_error)

        with pytest.raises(LLMConfigError):
            adapter._evaluate_with_judge("q", "gt", "gen")
