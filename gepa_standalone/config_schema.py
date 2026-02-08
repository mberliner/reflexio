"""
Config Schema Validator for Universal GEPA Optimizer.

Uses shared validation utilities for consistent validation across projects.
"""

import sys
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path for shared module access
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.validation import BaseConfigValidator, CSVValidator, format_validation_errors
from shared.paths import get_paths


class ConfigValidator(BaseConfigValidator):
    """
    Validates GEPA config YAML structure and parameters.

    Extends BaseConfigValidator with GEPA-specific validation for
    adapters and optimization parameters.
    """

    REQUIRED_FIELDS = {
        "case": ["name"],
        "adapter": ["type"],
        "data": ["csv_filename"],
        "optimization": ["max_metric_calls"],
    }

    # Type validation for adapters
    TYPE_SECTION = "adapter"
    TYPE_FIELD = "type"

    TYPE_SCHEMAS = {
        "classifier": {
            "required": ["valid_classes"],
            "optional": [],
        },
        "extractor": {
            "required": ["required_fields"],
            "optional": ["max_positive_examples"],
        },
        "sql": {
            "required": [],
            "optional": [],
        },
        "rag": {
            "required": [],
            "optional": ["max_positive_examples"],
        },
    }

    # Optimization parameter limits
    MAX_METRIC_CALLS_MIN = 10
    MAX_METRIC_CALLS_MAX = 500

    @classmethod
    def validate(cls, config: Dict[str, Any]) -> List[str]:
        """
        Validate complete config dictionary.

        Uses paths from get_paths() for file validation.

        Args:
            config: Configuration dictionary loaded from YAML

        Returns:
            List of error messages (empty if valid)
        """
        paths = get_paths()

        # Run base validation (uses datasets dir from paths)
        errors = super().validate(config, str(paths.datasets))

        # Additional GEPA-specific validation
        adapter_errors = cls._validate_adapter_specific(config)
        errors.extend(adapter_errors)

        # Validate optimization parameters
        opt_errors = cls._validate_optimization_params(config)
        errors.extend(opt_errors)

        # Validate prompt file if specified
        prompt_errors = cls._validate_prompt_file(config)
        errors.extend(prompt_errors)

        return errors

    @classmethod
    def _validate_adapter_specific(cls, config: Dict[str, Any]) -> List[str]:
        """
        Validate adapter-specific field values.

        Args:
            config: Configuration dictionary

        Returns:
            List of error messages
        """
        errors = []

        if "adapter" not in config or "type" not in config["adapter"]:
            return errors

        adapter_config = config["adapter"]
        adapter_type = adapter_config["type"]

        # Validate classifier specific
        if adapter_type == "classifier" and "valid_classes" in adapter_config:
            valid_classes = adapter_config["valid_classes"]
            if not isinstance(valid_classes, list):
                errors.append("'adapter.valid_classes' must be a list")
            elif len(valid_classes) == 0:
                errors.append("'adapter.valid_classes' cannot be empty")

        # Validate extractor specific
        if adapter_type == "extractor" and "required_fields" in adapter_config:
            required_fields = adapter_config["required_fields"]
            if not isinstance(required_fields, list):
                errors.append("'adapter.required_fields' must be a list")
            elif len(required_fields) == 0:
                errors.append("'adapter.required_fields' cannot be empty")

        return errors

    @classmethod
    def _validate_optimization_params(cls, config: Dict[str, Any]) -> List[str]:
        """
        Validate optimization parameter values.

        Args:
            config: Configuration dictionary

        Returns:
            List of error messages
        """
        errors = []

        opt_config = config.get("optimization", {})
        max_calls = opt_config.get("max_metric_calls")

        if max_calls is not None:
            if not isinstance(max_calls, int):
                errors.append(
                    f"'optimization.max_metric_calls' must be an integer, "
                    f"got: {type(max_calls).__name__}"
                )
            elif max_calls < cls.MAX_METRIC_CALLS_MIN or max_calls > cls.MAX_METRIC_CALLS_MAX:
                errors.append(
                    f"'optimization.max_metric_calls' must be between "
                    f"{cls.MAX_METRIC_CALLS_MIN} and {cls.MAX_METRIC_CALLS_MAX}, got: {max_calls}"
                )

        return errors

    @classmethod
    def _validate_prompt_file(cls, config: Dict[str, Any]) -> List[str]:
        """
        Validate prompt file existence if specified.

        Args:
            config: Configuration dictionary

        Returns:
            List of error messages
        """
        errors = []

        prompt_config = config.get("prompt", {})
        prompt_filename = prompt_config.get("filename")

        if prompt_filename:
            paths = get_paths()
            prompt_path = paths.prompt(prompt_filename)

            if not prompt_path.exists():
                errors.append(
                    f"Prompt file not found: {prompt_filename}\n"
                    f"  Expected at: {prompt_path}\n"
                    f"  Place your JSON in: experiments/prompts/"
                )

        return errors

    @classmethod
    def _validate_csv_file(cls, config: Dict[str, Any], datasets_dir: str) -> List[str]:
        """
        Validate CSV file with GEPA-specific column handling.

        Overrides base method to use GEPA's column configuration.
        """
        errors = []

        data_config = config.get("data", {})
        csv_filename = data_config.get("csv_filename")

        if not csv_filename:
            return errors

        paths = get_paths()
        csv_path = paths.dataset(csv_filename)

        if not csv_path.exists():
            errors.append(
                f"CSV file not found: {csv_filename}\n"
                f"  Expected at: {csv_path}\n"
                f"  Place your CSV in: experiments/datasets/"
            )
            return errors

        # Get input column (default: "text")
        input_col = data_config.get("input_column", "text")
        input_columns = [input_col] if input_col else None

        # Get output columns
        output_cols = data_config.get("output_columns", [])
        output_columns = output_cols if output_cols else None

        csv_errors = CSVValidator.validate(
            csv_path=csv_path,
            input_columns=input_columns,
            output_columns=output_columns,
        )
        errors.extend(csv_errors)

        return errors

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
