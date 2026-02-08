"""
Error formatting utilities for validation.

Provides consistent error formatting across all validation operations.
"""


class ValidationError(Exception):
    """
    Exception raised when configuration validation fails.

    Attributes:
        errors: List of validation error messages
        formatted: Pre-formatted error string for display
    """

    def __init__(self, errors: list[str], message: str = "Configuration validation failed"):
        self.errors = errors
        self.formatted = format_validation_errors(errors)
        super().__init__(f"{message}\n{self.formatted}")


def format_validation_errors(
    errors: list[str], title: str = "CONFIGURATION ERRORS DETECTED"
) -> str:
    """
    Format validation errors for display.

    Args:
        errors: List of error messages
        title: Header title for the error block

    Returns:
        Formatted error string with header, numbered errors, and footer.
        Returns empty string if no errors.

    Example:
        >>> errors = ["Missing field: 'name'", "Invalid type: 'foo'"]
        >>> print(format_validation_errors(errors))
        ======================================================================
        CONFIGURATION ERRORS DETECTED
        ======================================================================

        1. Missing field: 'name'

        2. Invalid type: 'foo'

        ======================================================================
        Please fix these errors and try again.
    """
    if not errors:
        return ""

    width = 70
    separator = "=" * width

    lines = [
        "",
        separator,
        title,
        separator,
        "",
    ]

    for i, error in enumerate(errors, 1):
        lines.append(f"{i}. {error}")
        lines.append("")

    lines.extend(
        [
            separator,
            "Please fix these errors and try again.",
            "",
        ]
    )

    return "\n".join(lines)
