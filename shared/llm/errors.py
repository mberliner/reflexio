"""
LLM Error classes.

Provides structured error handling for LLM connection issues.
"""

from typing import Any


class LLMConnectionError(Exception):
    """
    Error de conexion con el LLM.

    Provides structured error information with actionable suggestions.
    """

    def __init__(
        self,
        message: str,
        provider: str,
        model: str,
        endpoint: str | None = None,
        api_version: str | None = None,
        original_error: str | None = None,
        extra_details: dict[str, Any] | None = None,
        suggestions: list[str] | None = None,
    ):
        """
        Initialize LLMConnectionError.

        Args:
            message: Human-readable error message.
            provider: LLM provider (e.g., "azure", "openai").
            model: Model identifier.
            endpoint: API endpoint URL.
            original_error: Original exception message.
            suggestions: List of actionable suggestions to fix the error.
        """
        self.message = message
        self.provider = provider
        self.model = model
        self.endpoint = endpoint
        self.api_version = api_version
        self.original_error = original_error
        self.extra_details = extra_details or {}
        self.suggestions = suggestions or []
        super().__init__(self.format_error())

    def format_error(self) -> str:
        """Format the error as a readable string."""
        lines = [
            "",
            "=" * 60,
            "LLM CONNECTION ERROR",
            "=" * 60,
            "",
            f"Message: {self.message}",
            "",
            "Configuration:",
            f"  - Provider: {self.provider}",
            f"  - Model: {self.model}",
        ]

        if self.endpoint:
            lines.append(f"  - Endpoint: {self.endpoint}")

        if self.api_version:
            lines.append(f"  - API Version: {self.api_version}")

        if self.original_error:
            lines.extend(
                [
                    "",
                    "Original error:",
                    f"  {self.original_error}",
                ]
            )

        if self.extra_details:
            lines.extend(
                [
                    "",
                    "Details:",
                ]
            )
            for key, value in self.extra_details.items():
                if value is None or value == "":
                    continue
                lines.append(f"  - {key}: {value}")

        if self.suggestions:
            lines.extend(
                [
                    "",
                    "Suggested actions:",
                ]
            )
            for i, suggestion in enumerate(self.suggestions, 1):
                lines.append(f"  {i}. {suggestion}")

        lines.extend(["", "=" * 60, ""])
        return "\n".join(lines)
