"""
Shared LLM configuration module.

Provides unified LLM configuration for both gepa_standalone and dspy_gepa_poc projects.
Uses LiteLLM as the underlying client.
"""

from .call import call_with_infra_retry, checked_completion, raise_for_response
from .config import LLMConfig, response_text
from .errors import EmptyResponseError, LLMConfigError, LLMConnectionError
from .failures import (
    FailureClass,
    FailureTracker,
    LLMCallFailure,
    LLMFailure,
    RunAborted,
    classify_exception,
    classify_response,
    get_failure_tracker,
)
from .usage import UsageTracker, get_tracker, record_usage

__all__ = [
    "EmptyResponseError",
    "FailureClass",
    "FailureTracker",
    "LLMCallFailure",
    "LLMFailure",
    "RunAborted",
    "call_with_infra_retry",
    "checked_completion",
    "classify_exception",
    "classify_response",
    "get_failure_tracker",
    "raise_for_response",
    "LLMConfig",
    "LLMConfigError",
    "LLMConnectionError",
    "UsageTracker",
    "get_tracker",
    "record_usage",
    "response_text",
]
