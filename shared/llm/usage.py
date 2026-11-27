"""
Real token usage tracking for LLM calls.

Accumulates the actual token consumption reported by the provider
(litellm/DSPy ``response.usage``) instead of relying on fixed per-case
estimates. Tokens are split into three buckets (SPEC-106 FR-004):

- ``task``: calls made by the task/student model (candidate evaluation).
- ``reflection``: calls made by the reflection/teacher model.
- ``judge``: calls made by the LLM-as-judge (RAG adapter). It has its own
  bucket so it can be priced with its own model; the CSV column
  ``Tokens Reflection`` sums reflection + judge (``reflection_tokens_for_csv``).

The tracker is a process-level singleton: LLM calls happen at several
points without a tracker being threaded through, so callers record into
the shared instance. Entry points are expected to ``reset()`` at the
start of a run and ``snapshot()`` at the end.
"""

import threading
from dataclasses import asdict, dataclass

_BUCKETS = ("task", "reflection", "judge")


@dataclass
class UsageBucket:
    """Accumulated usage for a single role."""

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def _normalize_role(role: str) -> str:
    """Map a raw role/model_name to its usage bucket.

    'reflection' and 'judge' keep their own bucket; everything else (task,
    embedding probes, unknown) lands in 'task'.
    """
    name = (role or "").lower()
    return name if name in ("reflection", "judge") else "task"


def _new_buckets() -> dict:
    return {name: UsageBucket() for name in _BUCKETS}


class UsageTracker:
    """Thread-safe accumulator of real token usage, split by role bucket."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets = _new_buckets()

    def reset(self) -> None:
        """Clear all accumulated usage (call at the start of a run)."""
        with self._lock:
            self._buckets = _new_buckets()

    def record(self, role: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Add a single call's token counts to the appropriate bucket."""
        bucket_name = _normalize_role(role)
        with self._lock:
            bucket = self._buckets[bucket_name]
            bucket.calls += 1
            bucket.prompt_tokens += int(prompt_tokens or 0)
            bucket.completion_tokens += int(completion_tokens or 0)

    def snapshot(self) -> dict:
        """Return a serializable snapshot of accumulated usage.

        Shape::

            {
              "task":       {"calls", "prompt_tokens", "completion_tokens"},
              "reflection": {"calls", "prompt_tokens", "completion_tokens"},
              "judge":      {"calls", "prompt_tokens", "completion_tokens"},
              "total_tokens": int,
            }
        """
        with self._lock:
            snap = {name: asdict(self._buckets[name]) for name in _BUCKETS}
            total = sum(self._buckets[name].total_tokens for name in _BUCKETS)
        snap["total_tokens"] = total
        return snap


def reflection_tokens_for_csv(usage: dict) -> int:
    """Tokens of the ``Tokens Reflection`` CSV column: reflection + judge."""
    return sum(
        (usage.get(name) or {}).get("prompt_tokens", 0)
        + (usage.get(name) or {}).get("completion_tokens", 0)
        for name in ("reflection", "judge")
    )


# Process-level singleton.
_tracker = UsageTracker()


def get_tracker() -> UsageTracker:
    """Return the shared process-level UsageTracker."""
    return _tracker


def extract_usage(response) -> tuple[int, int]:
    """Extract (prompt_tokens, completion_tokens) from a litellm/DSPy response.

    Defensive: returns (0, 0) when usage is missing or malformed, so a
    provider that omits usage never breaks the call path.
    """
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return 0, 0

    def _get(obj, key):
        if isinstance(obj, dict):
            return obj.get(key, 0)
        return getattr(obj, key, 0)

    return int(_get(usage, "prompt_tokens") or 0), int(_get(usage, "completion_tokens") or 0)


def record_usage(role: str, response) -> None:
    """Extract usage from a response and record it under the given role."""
    prompt_tokens, completion_tokens = extract_usage(response)
    _tracker.record(role, prompt_tokens, completion_tokens)
