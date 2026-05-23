"""
Config Schema Validator for DSPy + GEPA Integration.

Uses shared validation utilities for consistent validation across projects.
"""

from pathlib import Path
from typing import Any

from shared.validation import BaseConfigValidator, CSVValidator

# Documentation for optional optimization fields
OPTIONAL_OPTIMIZATION_FIELDS = {
    "predictor_type": "str - 'cot' o 'predict' (default: 'cot')",
    "use_few_shot": "bool - Habilitar few-shot learning",
    "few_shot_count": "int - Numero de ejemplos few-shot",
    "ignore_in_metric": "list - Campos a ignorar en evaluacion",
    "auto_budget": "str - 'light', 'medium', 'heavy'",
    "match_mode": "str - 'exact', 'normalized', 'fuzzy' (default: 'exact')",
    "fuzzy_threshold": "float - Umbral de similitud para modo fuzzy (0.0-1.0, default: 0.85)",
    "metric_feedback": "bool - Si True, la metrica emite diagnostico textual a GEPA",
    "field_configs": (
        "dict - Overrides por campo: {nombre: {mode: exact|normalized|fuzzy|set, "
        "fuzzy_threshold?: float, separators?: str}}. Implica metric_feedback=True."
    ),
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
        "data": ["csv_filename"],
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
        "pipeline": {
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
    def validate(cls, config: dict[str, Any], datasets_dir: str = None) -> list[str]:
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

        # Pipeline-specific validation
        module_type = config.get("module", {}).get("type")
        if module_type == "pipeline":
            errors.extend(cls._validate_pipeline(config))

        # Validate optimization requirements: max_metric_calls or auto_budget
        opt = config.get("optimization", {})
        if "max_metric_calls" not in opt and "auto_budget" not in opt:
            errors.append("Optimization requires 'max_metric_calls' or 'auto_budget'")

        # Validate data inputs: requiere 'input_column' (string) o 'input_columns' (lista)
        data = config.get("data", {})
        if "input_column" not in data and "input_columns" not in data:
            errors.append("data section requires 'input_column' (string) or 'input_columns' (list)")

        # Validate module-specific fields in data section
        if "module" in config and "type" in config["module"]:
            module_type = config["module"]["type"]
            if module_type in cls.TYPE_SCHEMAS:
                schema = cls.TYPE_SCHEMAS[module_type]
                for req_field in schema.get("required", []):
                    # Check both module and data sections
                    if req_field not in config.get("module", {}) and req_field not in config.get(
                        "data", {}
                    ):
                        errors.append(f"Module '{module_type}' requires field: '{req_field}'")

        return errors

    @classmethod
    def _validate_signature(cls, signature: dict[str, Any]) -> list[str]:
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
                    errors.append(f"Signature input #{idx + 1} missing 'name'")

        # Validate outputs structure
        if "outputs" in signature:
            for idx, out in enumerate(signature["outputs"]):
                if "name" not in out:
                    errors.append(f"Signature output #{idx + 1} missing 'name'")

        return errors

    @classmethod
    def _validate_pipeline(cls, config: dict[str, Any]) -> list[str]:
        """
        Validate pipeline module structure: stages + routing.

        Args:
            config: Full config dictionary.

        Returns:
            List of error messages.
        """
        errors: list[str] = []
        stages = config.get("stages")
        routing = config.get("routing")

        if not isinstance(stages, list) or len(stages) < 2:
            errors.append("Pipeline requires 'stages' as a list with at least 2 entries.")
            return errors

        stage_names: list[str] = []
        for idx, stage in enumerate(stages):
            if "name" not in stage:
                errors.append(f"Pipeline stage #{idx + 1} missing 'name'.")
                continue
            if stage["name"] in stage_names:
                errors.append(f"Pipeline stage name '{stage['name']}' duplicated.")
            stage_names.append(stage["name"])
            if "signature" not in stage:
                errors.append(f"Pipeline stage '{stage['name']}' missing 'signature' section.")
                continue
            errors.extend(cls._validate_signature(stage["signature"]))

        if not isinstance(routing, dict):
            errors.append("Pipeline requires 'routing' section (dict).")
            return errors

        for key in ("gate_stage", "gate_field", "gate_value"):
            if key not in routing:
                errors.append(f"Pipeline routing missing required key: '{key}'.")

        gate_stage = routing.get("gate_stage")
        if gate_stage and gate_stage not in stage_names:
            errors.append(f"routing.gate_stage='{gate_stage}' not in stages: {stage_names}.")

        gate_field = routing.get("gate_field")
        if gate_stage and gate_field:
            gate_stage_cfg = next((s for s in stages if s.get("name") == gate_stage), None)
            if gate_stage_cfg:
                gate_outputs = [
                    o.get("name") for o in gate_stage_cfg.get("signature", {}).get("outputs", [])
                ]
                if gate_field not in gate_outputs:
                    errors.append(
                        f"routing.gate_field='{gate_field}' not in outputs of "
                        f"gate_stage '{gate_stage}': {gate_outputs}."
                    )

        # skip_outputs_when_gated keys must exist in some post-gate stage output
        skip = routing.get("skip_outputs_when_gated", {})
        if skip:
            if gate_stage and gate_stage in stage_names:
                gate_idx = stage_names.index(gate_stage)
                post_outputs: list[str] = []
                for stage in stages[gate_idx + 1 :]:
                    post_outputs.extend(
                        o.get("name") for o in stage.get("signature", {}).get("outputs", [])
                    )
                for k in skip.keys():
                    if k not in post_outputs:
                        errors.append(
                            f"routing.skip_outputs_when_gated['{k}'] does not match any "
                            f"output of post-gate stages: {post_outputs}."
                        )

        return errors

    @classmethod
    def _validate_csv_file(cls, config: dict[str, Any], datasets_dir: str) -> list[str]:
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

        # Get input column(s): acepta 'input_column' (string, legacy) o
        # 'input_columns' (lista, multi-input).
        if "input_columns" in data_config:
            input_columns = data_config["input_columns"]
            if not isinstance(input_columns, list):
                input_columns = [input_columns]
        else:
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
            sig_outputs = [
                o.get("name")
                for o in config.get("signature", {}).get("outputs", [])
                if isinstance(o, dict)
            ]
            if sig_outputs:
                output_columns = sig_outputs

        # For pipeline modules, collect outputs from all stages
        if module_type == "pipeline":
            stage_outputs: list[str] = []
            for stage in config.get("stages", []):
                stage_outputs.extend(
                    o.get("name")
                    for o in stage.get("signature", {}).get("outputs", [])
                    if isinstance(o, dict)
                )
            # Auxiliares (con razonamiento_*) NO necesariamente estan en el CSV.
            # Filtramos los que se ignoran en la metrica para evitar falsos
            # negativos durante la validacion.
            ignore = config.get("optimization", {}).get("ignore_in_metric", []) or []
            stage_outputs = [o for o in stage_outputs if o not in ignore]
            if stage_outputs:
                output_columns = stage_outputs

        csv_errors = CSVValidator.validate(
            csv_path=csv_path,
            input_columns=input_columns,
            output_columns=output_columns,
        )
        errors.extend(csv_errors)

        return errors
