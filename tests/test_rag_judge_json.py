"""
SPEC-104 3d (FR-009): el juez de RAG pide su puntaje como JSON en el prompt, valida
el rango y reintenta ante un puntaje ilegible o fuera de rango antes de clasificarlo
como `formato` del juez (el caso queda NE, no score 0 del candidato).

Las respuestas salen de `make_completion_response` (`litellm.ModelResponse` real).
"""

import json

import pytest

from gepa_standalone.adapters.simple_rag_adapter import SimpleRAGAdapter
from shared.llm import LLMCallFailure, LLMConfig, get_failure_tracker
from tests.conftest import make_completion_response

CASE = {"case_id": "c0", "question": "q", "context": "ctx", "answer": "Paris"}


class JudgeScript:
    """`litellm.completion`: la tarea responde `Paris`; el juez sigue `judge_replies`."""

    def __init__(self, monkeypatch, judge_replies):
        self.judge_replies = list(judge_replies)
        self.judge_calls = []
        monkeypatch.setattr("litellm.completion", self)

    def __call__(self, *args, **kwargs):
        messages = kwargs["messages"]
        if "evaluador" not in messages[0]["content"]:
            return make_completion_response("Paris")
        self.judge_calls.append(messages)
        reply = self.judge_replies.pop(0) if len(self.judge_replies) > 1 else self.judge_replies[0]
        if isinstance(reply, tuple):
            return make_completion_response(reply[0], finish_reason=reply[1])
        return make_completion_response(reply)


def _judge_json(score, reason="razon"):
    return json.dumps({"puntaje": score, "razon": reason})


class TestJudgePromptAsksForJson:
    def test_prompt_requests_json_without_native_structured_outputs(self, mock_env, monkeypatch):
        script = JudgeScript(monkeypatch, [_judge_json(1.0)])
        captured = {}
        original = script.__call__

        def spy(*args, **kwargs):
            if "evaluador" in kwargs["messages"][0]["content"]:
                captured.update(kwargs)
            return original(*args, **kwargs)

        monkeypatch.setattr("litellm.completion", spy)

        SimpleRAGAdapter(LLMConfig.from_env("reflection"))._evaluate_with_judge("q", "gt", "gen")

        system = captured["messages"][0]["content"]
        assert "JSON" in system and "puntaje" in system
        assert "response_format" not in captured
        assert "PUNTAJE:" not in system


class TestJudgeScoreParsing:
    @pytest.mark.parametrize("score", [0, 0.0, 0.25, 0.5, 1, 1.0])
    def test_valid_score_in_range(self, mock_env, monkeypatch, score):
        JudgeScript(monkeypatch, [_judge_json(score, "buena")])

        value, reason = SimpleRAGAdapter(LLMConfig.from_env("reflection"))._evaluate_with_judge(
            "q", "gt", "gen"
        )

        assert value == float(score)
        assert reason == "buena"

    def test_json_inside_code_fence_is_accepted(self, mock_env, monkeypatch):
        JudgeScript(monkeypatch, ["```json\n" + _judge_json(0.75) + "\n```"])

        value, _ = SimpleRAGAdapter(LLMConfig.from_env("reflection"))._evaluate_with_judge(
            "q", "gt", "gen"
        )

        assert value == 0.75


class TestJudgeRetries:
    @pytest.mark.parametrize(
        "bad",
        [
            "texto sin json",
            "PUNTAJE: 1.0\nRAZON: formato viejo",
            '{"puntaje": ',
            '{"razon": "sin puntaje"}',
            '{"puntaje": "alto", "razon": "x"}',
            '{"puntaje": true, "razon": "x"}',
            '{"puntaje": null, "razon": "x"}',
            _judge_json(1.5),
            _judge_json(-0.1),
            '{"puntaje": NaN, "razon": "x"}',
            '{"puntaje": Infinity, "razon": "x"}',
        ],
    )
    def test_unreadable_or_out_of_range_then_valid_retries(self, mock_env, monkeypatch, bad):
        script = JudgeScript(monkeypatch, [bad, _judge_json(0.5)])

        value, _ = SimpleRAGAdapter(LLMConfig.from_env("reflection"))._evaluate_with_judge(
            "q", "gt", "gen"
        )

        assert value == 0.5
        assert len(script.judge_calls) == 2

    def test_default_is_two_retries_then_format_failure_of_the_judge(self, mock_env, monkeypatch):
        script = JudgeScript(monkeypatch, ["basura"])

        with pytest.raises(LLMCallFailure) as exc_info:
            SimpleRAGAdapter(LLMConfig.from_env("reflection"))._evaluate_with_judge(
                "q", "gt", "gen"
            )

        assert len(script.judge_calls) == 3
        failure = exc_info.value.failure
        assert failure.clase.value == "formato"
        assert failure.rol == "judge"

    def test_retries_are_configurable(self, mock_env, monkeypatch):
        script = JudgeScript(monkeypatch, ["basura"])

        with pytest.raises(LLMCallFailure):
            SimpleRAGAdapter(
                LLMConfig.from_env("reflection"), judge_retries=0
            )._evaluate_with_judge("q", "gt", "gen")

        assert len(script.judge_calls) == 1

    @pytest.mark.parametrize("bad", [-1, True, 1.5, "2"])
    def test_invalid_retries_value_is_rejected(self, mock_env, bad):
        with pytest.raises(ValueError, match="judge_retries"):
            SimpleRAGAdapter(LLMConfig.from_env("reflection"), judge_retries=bad)

    def test_layer_one_failure_is_not_retried_as_format(self, mock_env, monkeypatch):
        script = JudgeScript(monkeypatch, [(None, "length")])

        with pytest.raises(LLMCallFailure) as exc_info:
            SimpleRAGAdapter(LLMConfig.from_env("reflection"))._evaluate_with_judge(
                "q", "gt", "gen"
            )

        assert len(script.judge_calls) == 1
        assert exc_info.value.failure.clase.value == "presupuesto"
        assert exc_info.value.failure.rol == "judge"


class TestUnreadableJudgeLeavesCaseNE:
    def test_case_is_ne_format_of_judge_and_counted_once(self, mock_env, monkeypatch):
        """Agotados los reintentos: NE `formato` del juez; una sola falla contada."""
        script = JudgeScript(monkeypatch, ["basura"])
        adapter = SimpleRAGAdapter(LLMConfig.from_env("reflection"))

        result = adapter.evaluate([CASE], {"system_prompt": "p"})

        assert len(script.judge_calls) == 3
        output = result.outputs[0]
        assert output["evaluated"] is False
        assert output["failure"]["clase"] == "formato"
        assert output["failure"]["rol"] == "judge"
        assert result.scores == [0.0]
        snapshot = get_failure_tracker().snapshot()
        assert snapshot["counts"]["formato"]["judge"] == 1
        assert snapshot["attempts"]["judge"] == 1

    def test_ne_case_never_reaches_the_reflective_dataset(self, mock_env, monkeypatch):
        JudgeScript(monkeypatch, ["basura"])
        adapter = SimpleRAGAdapter(LLMConfig.from_env("reflection"))
        result = adapter.evaluate([CASE], {"system_prompt": "p"}, capture_traces=True)

        dataset = adapter.make_reflective_dataset({"system_prompt": "p"}, result, ["system_prompt"])

        assert dataset["system_prompt"] == []

    def test_recovered_judge_leaves_case_evaluated_without_failure(self, mock_env, monkeypatch):
        JudgeScript(monkeypatch, ["basura", _judge_json(0.75, "ok")])
        adapter = SimpleRAGAdapter(LLMConfig.from_env("reflection"))

        result = adapter.evaluate([CASE], {"system_prompt": "p"})

        assert result.outputs[0]["evaluated"] is True
        assert result.scores == [0.75]
        assert get_failure_tracker().snapshot()["counts"] == {}

    def test_judge_truncated_by_max_tokens_is_ne_presupuesto(self, mock_env, monkeypatch):
        JudgeScript(monkeypatch, [('{"puntaje": 0.5, "raz', "length")])
        adapter = SimpleRAGAdapter(LLMConfig.from_env("reflection"))

        result = adapter.evaluate([CASE], {"system_prompt": "p"})

        assert result.outputs[0]["evaluated"] is False
        assert result.outputs[0]["failure"]["clase"] == "presupuesto"
        assert result.outputs[0]["failure"]["rol"] == "judge"
