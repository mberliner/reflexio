"""
Base configuration validator.

Provides common validation functionality that can be extended
by project-specific validators.
"""

from pathlib import Path
from typing import Dict, List, Any, Optional

from .csv_validator import CSVValidator
from .errors import format_validation_errors, ValidationError


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
    REQUIRED_FIELDS: Dict[str, List[str]] = {
        "case": ["name"],
        "data": ["csv_filename"],
        "optimization": ["max_metric_calls"],
    }

    # Type validation config (override in subclasses)
    TYPE_SECTION: str = ""  # e.g., "module" or "adapter"
    TYPE_FIELD: str = "type"
    TYPE_SCHEMAS: Dict[str, Dict[str, List[str]]] = {}

    @classmethod
    def validate(
        cls,
        config: Dict[str, Any],
        datasets_dir: Optional[str] = None,
    ) -> List[str]:
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

        # 3. Validate CSV file if datasets_dir provided
        if datasets_dir:
            csv_errors = cls._validate_csv_file(config, datasets_dir)
            errors.extend(csv_errors)

        return errors

    @classmethod
    def validate_or_raise(
        cls,
        config: Dict[str, Any],
        datasets_dir: Optional[str] = None,
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
    def _validate_required_sections(cls, config: Dict[str, Any]) -> List[str]:
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
    def _validate_type_schema(cls, config: Dict[str, Any]) -> List[str]:
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
        config: Dict[str, Any],
        datasets_dir: str,
    ) -> List[str]:
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
    def get_valid_types(cls) -> List[str]:
        """
        Get list of valid type names.

        Returns:
            List of valid type strings
        """
        return list(cls.TYPE_SCHEMAS.keys())

    @staticmethod
    def display_errors(errors: List[str]) -> str:
        """
        Format errors for display.

        Args:
            errors: List of error messages

        Returns:
            Formatted error string
        """
        return format_validation_errors(errors)
