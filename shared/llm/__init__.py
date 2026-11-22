"""
Shared LLM configuration module.

Provides unified LLM configuration for both gepa_standalone and dspy_gepa_poc projects.
Uses LiteLLM as the underlying client.
"""

from .config import LLMConfig, response_text
from .errors import EmptyResponseError, LLMConfigError, LLMConnectionError
from .usage import UsageTracker, get_tracker, record_usage

__all__ = [
    "EmptyResponseError",
    "LLMConfig",
    "LLMConfigError",
    "LLMConnectionError",
    "UsageTracker",
    "get_tracker",
    "record_usage",
    "response_text",
]
