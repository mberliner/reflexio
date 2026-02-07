"""
Config Schema Validator for DSPy + GEPA Integration.

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


# Documentation for optional optimization fields
OPTIONAL_OPTIMIZATION_FIELDS = {
    "predictor_type": "str - 'cot' o 'predict' (default: 'cot')",
    "use_few_shot": "bool - Habilitar few-shot learning",
    "few_shot_count": "int - Numero de ejemplos few-shot",
    "ignore_in_metric": "list - Campos a ignorar en evaluacion",
    "auto_budget": "str - 'light', 'medium', 'heavy'",
    "match_mode": "str - 'exact', 'normalized', 'fuzzy' (default: 'exact')",
    "fuzzy_threshold": "float - Umbral de similitud para modo fuzzy (0.0-1.0, default: 0.85)",
}


class ConfigValidator(BaseConfigValidator):
    """
    Validates DSPy+GEPA config YAML structure and parameters.

    Extends BaseConfigValidator with DSPy-specific validation for
    modules and dynamic signatures.
    """

    REQUIRED_FIELDS = {
        "case": ["name"],
        "module": ["type"],
        "data": ["csv_filename", "input_column"],
        "optimization": [],
    }

    # Type validation for modules
    TYPE_SECTION = "module"
    TYPE_FIELD = "type"

    TYPE_SCHEMAS = {
        "dynamic": {
            "required": [],
            "optional": [],
        },
        "sentiment": {
            "required": [],
            "optional": [],
        },
        "extractor": {
            "required": ["output_columns"],
            "optional": [],
        },
        "qa": {
            "required": ["input_column_context", "input_column_question"],
            "optional": ["use_cot"],
        },
    }

    # Dynamic signature fields
    DYNAMIC_SIGNATURE_FIELDS = ["instruction", "inputs", "outputs"]

    @classmethod
    def validate(cls, config: Dict[str, Any], datasets_dir: str = None) -> List[str]:
        """
        Validate complete config dictionary.

        Extends base validation with DSPy-specific signature validation.

        Args:
            config: Configuration dictionary loaded from YAML
            datasets_dir: Path to datasets directory for CSV validation

        Returns:
            List of error messages (empty if valid)
        """
        # Run base validation
        errors = super().validate(config, datasets_dir)

        # Additional DSPy-specific validation: dynamic signature
        if "signature" in config:
            signature_errors = cls._validate_signature(config["signature"])
            errors.extend(signature_errors)

        # Validate optimization requirements: max_metric_calls or auto_budget
        opt = config.get("optimization", {})
        if "max_metric_calls" not in opt and "auto_budget" not in opt:
            errors.append("Optimization requires 'max_metric_calls' or 'auto_budget'")

        # Validate module-specific fields in data section
        if "module" in config and "type" in config["module"]:
            module_type = config["module"]["type"]
            if module_type in cls.TYPE_SCHEMAS:
                schema = cls.TYPE_SCHEMAS[module_type]
                for req_field in schema.get("required", []):
                    # Check both module and data sections
                    if req_field not in config.get("module", {}) and req_field not in config.get("data", {}):
                        errors.append(f"Module '{module_type}' requires field: '{req_field}'")

        return errors

    @classmethod
    def _validate_signature(cls, signature: Dict[str, Any]) -> List[str]:
        """
        Validate dynamic signature structure.

        Args:
            signature: Signature configuration dictionary

        Returns:
            List of error messages
        """
        errors = []

        # Check required signature fields
        for field in cls.DYNAMIC_SIGNATURE_FIELDS:
            if field not in signature:
                errors.append(f"Dynamic signature requires field: 'signature.{field}'")

        # Validate inputs structure
        if "inputs" in signature:
            for idx, inp in enumerate(signature["inputs"]):
                if "name" not in inp:
                    errors.append(f"Signature input #{idx+1} missing 'name'")

        # Validate outputs structure
        if "outputs" in signature:
            for idx, out in enumerate(signature["outputs"]):
                if "name" not in out:
                    errors.append(f"Signature output #{idx+1} missing 'name'")

        return errors

    @classmethod
    def _validate_csv_file(cls, config: Dict[str, Any], datasets_dir: str) -> List[str]:
        """
        Validate CSV file with DSPy-specific column handling.

        Overrides base method to handle output_columns from module section.
        """
        errors = []

        data_config = config.get("data", {})
        csv_filename = data_config.get("csv_filename")

        if not csv_filename:
            return errors

        csv_path = Path(datasets_dir) / csv_filename

        if not csv_path.exists():
            errors.append(f"CSV file not found at: {csv_path}")
            return errors

        # Get input column
        input_col = data_config.get("input_column")
        input_columns = [input_col] if input_col else None

        # Get output columns (can be in module section for DSPy)
        output_cols = config.get("module", {}).get("output_columns", [])
        if not isinstance(output_cols, list):
            output_cols = [output_cols]
        output_columns = output_cols if output_cols else None

        # For dynamic modules, use signature.outputs when available
        module_type = config.get("module", {}).get("type")
        if module_type == "dynamic":
            sig_outputs = [o.get("name") for o in config.get("signature", {}).get("outputs", []) if isinstance(o, dict)]
            if sig_outputs:
                output_columns = sig_outputs

        csv_errors = CSVValidator.validate(
            csv_path=csv_path,
            input_columns=input_columns,
            output_columns=output_columns,
        )
        errors.extend(csv_errors)

        return errors
