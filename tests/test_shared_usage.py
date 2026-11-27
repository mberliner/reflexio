"""Tests for shared.llm.usage (real token usage tracking)."""

from types import SimpleNamespace

import pytest

from shared.llm.call import checked_response
from shared.llm.usage import (
    UsageTracker,
    extract_usage,
    get_tracker,
    record_usage,
    reflection_tokens_for_csv,
)
from tests.conftest import make_completion_response, patch_litellm_completion


@pytest.fixture
def tracker():
    """Fresh tracker via the singleton, reset before and after each test."""
    t = get_tracker()
    t.reset()
    yield t
    t.reset()


def _response(prompt_tokens, completion_tokens):
    """Build a litellm-like response object with a usage attribute."""
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    )


class TestExtractUsage:
    def test_extracts_from_object(self):
        assert extract_usage(_response(100, 20)) == (100, 20)

    def test_extracts_from_dict(self):
        resp = {"usage": {"prompt_tokens": 50, "completion_tokens": 10}}
        assert extract_usage(resp) == (50, 10)

    def test_missing_usage_returns_zeros(self):
        assert extract_usage(SimpleNamespace()) == (0, 0)
        assert extract_usage({}) == (0, 0)

    def test_none_fields_treated_as_zero(self):
        assert extract_usage(_response(None, None)) == (0, 0)


class TestUsageTracker:
    def test_record_task_bucket(self, tracker):
        tracker.record("task", 100, 20)
        snap = tracker.snapshot()
        assert snap["task"] == {"calls": 1, "prompt_tokens": 100, "completion_tokens": 20}
        assert snap["reflection"]["calls"] == 0
        assert snap["total_tokens"] == 120

    def test_judge_has_its_own_bucket(self, tracker):
        """SPEC-106 FR-004: el juez no se pliega en `reflection`."""
        tracker.record("reflection", 200, 40)
        tracker.record("judge", 60, 10)
        snap = tracker.snapshot()
        assert snap["reflection"] == {"calls": 1, "prompt_tokens": 200, "completion_tokens": 40}
        assert snap["judge"] == {"calls": 1, "prompt_tokens": 60, "completion_tokens": 10}
        assert snap["task"]["calls"] == 0
        assert snap["total_tokens"] == 310

    def test_without_judge_bucket_is_zero(self, tracker):
        tracker.record("task", 10, 5)
        snap = tracker.snapshot()
        assert snap["judge"] == {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        assert snap["total_tokens"] == 15

    def test_reflection_tokens_for_csv_is_reflection_plus_judge(self, tracker):
        tracker.record("reflection", 200, 40)
        tracker.record("judge", 60, 10)
        tracker.record("task", 1000, 1000)
        assert reflection_tokens_for_csv(tracker.snapshot()) == 310

    def test_reflection_tokens_for_csv_tolerates_missing_judge(self):
        usage = {"reflection": {"prompt_tokens": 7, "completion_tokens": 3}}
        assert reflection_tokens_for_csv(usage) == 10
        assert reflection_tokens_for_csv({}) == 0

    def test_judge_call_through_call_point_lands_in_judge_bucket(self, tracker, monkeypatch):
        """Respuesta real de LiteLLM por el punto de llamada comun, rol `judge`."""
        patch_litellm_completion(
            monkeypatch,
            lambda request, num_retries: make_completion_response(
                "0.8", prompt_tokens=120, completion_tokens=8
            ),
        )
        checked_response({"model": "openai/gpt-4o"}, [{"role": "user", "content": "x"}], "judge")
        snap = tracker.snapshot()
        assert snap["judge"] == {"calls": 1, "prompt_tokens": 120, "completion_tokens": 8}
        assert snap["reflection"]["calls"] == 0

    def test_unknown_role_falls_back_to_task(self, tracker):
        tracker.record("embedding", 10, 0)
        assert tracker.snapshot()["task"]["calls"] == 1

    def test_accumulates_across_calls(self, tracker):
        tracker.record("task", 10, 5)
        tracker.record("task", 10, 5)
        snap = tracker.snapshot()
        assert snap["task"] == {"calls": 2, "prompt_tokens": 20, "completion_tokens": 10}
        assert snap["total_tokens"] == 30

    def test_reset_clears(self, tracker):
        tracker.record("task", 10, 5)
        tracker.reset()
        snap = tracker.snapshot()
        assert snap["task"]["calls"] == 0
        assert snap["total_tokens"] == 0

    def test_record_usage_helper(self, tracker):
        record_usage("task", _response(80, 12))
        snap = tracker.snapshot()
        assert snap["task"] == {"calls": 1, "prompt_tokens": 80, "completion_tokens": 12}

    def test_isolated_instance(self):
        t = UsageTracker()
        t.record("task", 1, 1)
        assert t.snapshot()["total_tokens"] == 2


class TestReasoningTokens:
    def test_reasoning_tokens_not_double_counted(self, tracker):
        """LiteLLM ya incluye los tokens de razonamiento en completion_tokens
        (Anthropic y OpenAI): el detalle no se suma de nuevo."""
        usage = SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=70,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=50),
        )
        resp = SimpleNamespace(usage=usage)
        assert extract_usage(resp) == (100, 70)
        record_usage("task", resp)
        assert tracker.snapshot()["task"]["completion_tokens"] == 70

    def test_reasoning_tokens_in_dict_usage(self):
        resp = {
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 40,
                "completion_tokens_details": {"reasoning_tokens": 30},
            }
        }
        assert extract_usage(resp) == (10, 40)
