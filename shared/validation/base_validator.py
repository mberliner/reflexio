"""
Base configuration validator.

Provides common validation functionality that can be extended
by project-specific validators.
"""

from pathlib import Path
from typing import Any

from shared.llm.failures import FailureTracker

from .csv_validator import CSVValidator
from .errors import ValidationError, format_validation_errors

# Claves permitidas de la seccion opcional `failures` (SPEC-104 FR-006, D7).
FAILURES_KEYS = ("infra_retries", "judge_retries", "min_attempts", "thresholds")


class BaseConfigValidator:
    """
    Base class for YAML configuration validation.

    Provides common validation logic for required sections, fields,
    and CSV structure. Subclasses should define their own REQUIRED_FIELDS
    and type-specific schemas.

    Class Attributes:
        REQUIRED_FIELDS: Dict mapping section names to required field lists
        TYPE_SECTION: Section name containing type definition (e.g., "module", "adapter")
        TYPE_FIELD: Field name for type (default: "type")
        TYPE_SCHEMAS: Dict mapping type names to their required/optional fields
    """

    # Override in subclasses
    REQUIRED_FIELDS: dict[str, list[str]] = {
        "case": ["name"],
        "data": ["csv_filename"],
        "optimization": ["max_metric_calls"],
    }

    # Type validation config (override in subclasses)
    TYPE_SECTION: str = ""  # e.g., "module" or "adapter"
    TYPE_FIELD: str = "type"
    TYPE_SCHEMAS: dict[str, dict[str, list[str]]] = {}

    @classmethod
    def validate(
        cls,
        config: dict[str, Any],
        datasets_dir: str | None = None,
    ) -> list[str]:
        """
        Validate complete configuration dictionary.

        Args:
            config: Configuration dictionary loaded from YAML
            datasets_dir: Path to datasets directory for CSV validation

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # 1. Validate required sections and fields
        section_errors = cls._validate_required_sections(config)
        errors.extend(section_errors)

        # 2. Validate type-specific fields (if TYPE_SECTION is defined)
        if cls.TYPE_SECTION and cls.TYPE_SCHEMAS:
            type_errors = cls._validate_type_schema(config)
            errors.extend(type_errors)

        # 3. Validate optional `failures` section (SPEC-104)
        errors.extend(cls._validate_failures(config))

        # 4. Validate CSV file if datasets_dir provided
        if datasets_dir:
            csv_errors = cls._validate_csv_file(config, datasets_dir)
            errors.extend(csv_errors)

        return errors

    @classmethod
    def validate_or_raise(
        cls,
        config: dict[str, Any],
        datasets_dir: str | None = None,
    ) -> None:
        """
        Validate configuration and raise exception if invalid.

        Args:
            config: Configuration dictionary
            datasets_dir: Path to datasets directory

        Raises:
            ValidationError: If validation fails
        """
        errors = cls.validate(config, datasets_dir)
        if errors:
            raise ValidationError(errors)

    @classmethod
    def _validate_required_sections(cls, config: dict[str, Any]) -> list[str]:
        """
        Validate that required sections and fields exist.

        Args:
            config: Configuration dictionary

        Returns:
            List of error messages
        """
        errors = []

        for section, required_fields in cls.REQUIRED_FIELDS.items():
            if section not in config:
                errors.append(f"Missing required section: '{section}'")
                continue

            for field in required_fields:
                if field not in config[section]:
                    errors.append(f"Missing required field: '{section}.{field}'")

        return errors

    @classmethod
    def _validate_failures(cls, config: dict[str, Any]) -> list[str]:
        """
        Validate the optional `failures` section (SPEC-104 FR-006, D7).

        Shape: `{infra_retries: int, judge_retries: int, min_attempts: {role: int},
        thresholds: {key: {role: rate in [0, 1]}}}`. A missing section is valid
        (defaults apply). Values are checked with the same rules the failure
        counter enforces, so an invalid value fails here, before spending tokens.

        Args:
            config: Configuration dictionary

        Returns:
            List of error messages
        """
        section = config.get("failures")
        if section is None:
            return []
        if not isinstance(section, dict):
            return ["'failures' must be a mapping"]

        errors = [
            f"Unknown field: 'failures.{key}'. Valid: {', '.join(FAILURES_KEYS)}"
            for key in section
            if key not in FAILURES_KEYS
        ]

        judge_retries = section.get("judge_retries")
        if "judge_retries" in section and (
            isinstance(judge_retries, bool)
            or not isinstance(judge_retries, int)
            or judge_retries < 0
        ):
            errors.append(f"'failures.judge_retries' must be an integer >= 0: {judge_retries!r}")

        for key in ("min_attempts", "thresholds"):
            if key in section and not isinstance(section[key], dict):
                errors.append(f"'failures.{key}' must be a mapping")
        thresholds = section.get("thresholds")
        if isinstance(thresholds, dict):
            for key, by_role in thresholds.items():
                if not isinstance(by_role, dict):
                    errors.append(f"'failures.thresholds.{key}' must be a mapping of role to rate")
        if errors:
            return errors

        try:
            FailureTracker().configure(
                thresholds=section.get("thresholds"),
                min_attempts=section.get("min_attempts"),
                infra_retries=section.get("infra_retries"),
            )
        except ValueError as e:
            errors.append(f"Invalid 'failures' section: {e}")
        return errors

    @classmethod
    def _validate_type_schema(cls, config: dict[str, Any]) -> list[str]:
        """
        Validate type-specific schema requirements.

        Args:
            config: Configuration dictionary

        Returns:
            List of error messages
        """
        errors = []

        if cls.TYPE_SECTION not in config:
            return errors

        section_config = config[cls.TYPE_SECTION]
        if cls.TYPE_FIELD not in section_config:
            return errors

        type_name = section_config[cls.TYPE_FIELD]
        valid_types = list(cls.TYPE_SCHEMAS.keys())

        if type_name not in valid_types:
            errors.append(
                f"Invalid {cls.TYPE_SECTION} type: '{type_name}'. "
                f"Must be one of: {', '.join(valid_types)}"
            )
            return errors

        # Validate required fields for this type
        schema = cls.TYPE_SCHEMAS[type_name]
        for req_field in schema.get("required", []):
            if req_field not in section_config:
                errors.append(
                    f"{cls.TYPE_SECTION.capitalize()} '{type_name}' requires field: "
                    f"'{cls.TYPE_SECTION}.{req_field}'"
                )

        return errors

    @classmethod
    def _validate_csv_file(
        cls,
        config: dict[str, Any],
        datasets_dir: str,
    ) -> list[str]:
        """
        Validate CSV file existence and structure.

        Args:
            config: Configuration dictionary
            datasets_dir: Path to datasets directory

        Returns:
            List of error messages
        """
        errors = []

        data_config = config.get("data", {})
        csv_filename = data_config.get("csv_filename")

        if not csv_filename:
            return errors

        csv_path = Path(datasets_dir) / csv_filename

        if not csv_path.exists():
            errors.append(
                f"CSV file not found: {csv_filename}\n"
                f"  Expected at: {csv_path}\n"
                f"  Place your CSV in: {datasets_dir}"
            )
            return errors

        # Validate CSV structure
        csv_errors = CSVValidator.validate_from_config(csv_path, config)
        errors.extend(csv_errors)

        return errors

    @classmethod
    def get_valid_types(cls) -> list[str]:
        """
        Get list of valid type names.

        Returns:
            List of valid type strings
        """
        return list(cls.TYPE_SCHEMAS.keys())

    @staticmethod
    def display_errors(errors: list[str]) -> str:
        """
        Format errors for display.

        Args:
            errors: List of error messages

        Returns:
            Formatted error string
        """
        return format_validation_errors(errors)
