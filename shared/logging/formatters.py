"""
Common formatting utilities for experiment logging.

These functions provide consistent formatting across all logging operations
in both dspy_gepa_poc and gepa_standalone projects.
"""

import uuid
from datetime import datetime


def generate_run_id() -> str:
    """
    Generate a unique run identifier.

    Returns:
        8-character UUID string (e.g., "a3f9b2c1")
    """
    return str(uuid.uuid4())[:8]


def get_timestamp(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Get current timestamp as formatted string.

    Args:
        fmt: strftime format string. Default: "%Y-%m-%d %H:%M:%S"

    Returns:
        Formatted timestamp string (e.g., "2026-02-02 14:30:45")
    """
    return datetime.now().strftime(fmt)


def fmt_score(val: float | int | str, decimal_separator: str = ",") -> str:
    """
    Format a score value with specified decimal separator.

    Uses European format by default (comma as decimal separator).

    Args:
        val: Score value to format (float, int, or string)
        decimal_separator: Character to use as decimal separator. Default: ","

    Returns:
        Formatted score string with 4 decimal places (e.g., "0,8523")

    Examples:
        >>> fmt_score(0.8523)
        '0,8523'
        >>> fmt_score(0.8523, decimal_separator=".")
        '0.8523'
        >>> fmt_score("invalid")
        'invalid'
    """
    try:
        formatted = f"{float(val):.4f}"
        if decimal_separator != ".":
            formatted = formatted.replace(".", decimal_separator)
        return formatted
    except (ValueError, TypeError):
        return str(val)
