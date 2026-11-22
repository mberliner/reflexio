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

    title = "LLM CONNECTION ERROR"

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
            self.title,
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


class LLMConfigError(LLMConnectionError):
    """
    Combinacion invalida de parametros de configuracion del LLM (SPEC-103, FR-005/FR-008).

    Hereda de LLMConnectionError para que los entry points que ya la atrapan sigan
    funcionando. El mensaje nombra modelo, rol, parametro y valores aceptados.
    """

    title = "LLM CONFIGURATION ERROR"

    def __init__(
        self,
        message: str,
        model: str,
        parameter: str,
        accepted: list[str] | tuple[str, ...] | None = None,
    ):
        self.parameter = parameter
        self.accepted = list(accepted) if accepted else []
        provider = model.split("/")[0] if "/" in model else "unknown"
        suggestions = [f"Set {parameter} to one of: {', '.join(self.accepted)}"] if accepted else []
        super().__init__(
            message=message,
            provider=provider,
            model=model,
            suggestions=suggestions,
        )


class EmptyResponseError(Exception):
    """
    Respuesta del LLM sin texto (SPEC-103, FR-009).

    Se lanza cuando el contenido es None o vacio (p. ej. `finish_reason`
    `max_tokens` o `refusal`). No hereda de LLMConnectionError: los adapters
    la tratan como fallo del ejemplo, no como corte de la corrida.
    """

    def __init__(self, role: str, finish_reason: str | None = None):
        self.role = role
        self.finish_reason = finish_reason
        super().__init__(f"Respuesta sin texto del LLM (rol={role}, finish_reason={finish_reason})")
