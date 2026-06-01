"""
Real token usage tracking for LLM calls.

Accumulates the actual token consumption reported by the provider
(litellm/DSPy ``response.usage``) instead of relying on fixed per-case
estimates. Tokens are split into two buckets:

- ``task``: calls made by the task/student model (candidate evaluation).
- ``reflection``: calls made by the reflection/teacher model AND by any
  LLM-as-judge, since both only run during optimization (never in
  production). See project decision: judge tokens count as reflection.

The tracker is a process-level singleton: LLM calls happen at several
points without a tracker being threaded through, so callers record into
the shared instance. Entry points are expected to ``reset()`` at the
start of a run and ``snapshot()`` at the end.
"""

import threading
from dataclasses import asdict, dataclass

_REFLECTION_ROLES = frozenset({"reflection", "judge"})


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

    Anything in _REFLECTION_ROLES (reflection, judge) lands in 'reflection';
    everything else (task, embedding probes, unknown) lands in 'task'.
    """
    return "reflection" if (role or "").lower() in _REFLECTION_ROLES else "task"


class UsageTracker:
    """Thread-safe accumulator of real token usage, split by role bucket."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets = {"task": UsageBucket(), "reflection": UsageBucket()}

    def reset(self) -> None:
        """Clear all accumulated usage (call at the start of a run)."""
        with self._lock:
            self._buckets = {"task": UsageBucket(), "reflection": UsageBucket()}

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
              "total_tokens": int,
            }
        """
        with self._lock:
            task = asdict(self._buckets["task"])
            reflection = asdict(self._buckets["reflection"])
        total = self._buckets["task"].total_tokens + self._buckets["reflection"].total_tokens
        return {"task": task, "reflection": reflection, "total_tokens": total}


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


def record_dspy_history(role: str, history) -> None:
    """Record usage from a ``dspy.LM.history`` list into the tracker.

    DSPy calls litellm internally (not via this module's wrappers), so its
    real token usage is only available after the run on each LM's ``history``.
    Each entry is a dict carrying a ``usage`` sub-dict; entries without usage
    are skipped so call counts stay accurate.
    """
    for entry in history or []:
        prompt_tokens, completion_tokens = extract_usage(entry)
        if prompt_tokens or completion_tokens:
            _tracker.record(role, prompt_tokens, completion_tokens)
