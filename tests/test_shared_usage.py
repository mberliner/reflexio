"""Tests for shared.llm.usage (real token usage tracking)."""

from types import SimpleNamespace

import pytest

from shared.llm.usage import (
    UsageTracker,
    extract_usage,
    get_tracker,
    record_dspy_history,
    record_usage,
)


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

    def test_reflection_and_judge_share_bucket(self, tracker):
        tracker.record("reflection", 200, 40)
        tracker.record("judge", 60, 10)
        snap = tracker.snapshot()
        assert snap["reflection"]["calls"] == 2
        assert snap["reflection"]["prompt_tokens"] == 260
        assert snap["reflection"]["completion_tokens"] == 50
        assert snap["task"]["calls"] == 0

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


class TestRecordDspyHistory:
    def test_sums_history_entries(self, tracker):
        history = [
            {"usage": {"prompt_tokens": 100, "completion_tokens": 20}},
            {"usage": {"prompt_tokens": 50, "completion_tokens": 10}},
        ]
        record_dspy_history("task", history)
        snap = tracker.snapshot()
        assert snap["task"]["calls"] == 2
        assert snap["task"]["prompt_tokens"] == 150
        assert snap["task"]["completion_tokens"] == 30

    def test_skips_entries_without_usage(self, tracker):
        history = [
            {"usage": {"prompt_tokens": 10, "completion_tokens": 5}},
            {"prompt": "no usage here"},
            {"usage": {"prompt_tokens": 0, "completion_tokens": 0}},
        ]
        record_dspy_history("reflection", history)
        snap = tracker.snapshot()
        assert snap["reflection"]["calls"] == 1
        assert snap["reflection"]["prompt_tokens"] == 10

    def test_none_history_is_noop(self, tracker):
        record_dspy_history("task", None)
        assert tracker.snapshot()["total_tokens"] == 0
