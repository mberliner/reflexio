"""
Schema YAML de dspy_gepa_poc (D-025): solo los tipos que el runtime ejecuta y sin
seccion `adapter` (propia de gepa_standalone, sin efecto en DSPy).
"""

from pathlib import Path

import pytest
import yaml

from dspy_gepa_poc.config_schema import ConfigValidator

ROOT = Path(__file__).resolve().parent.parent
DSPY_CONFIGS = sorted((ROOT / "dspy_gepa_poc" / "configs").glob("*.yaml"))
DSPY_DATASETS = ROOT / "dspy_gepa_poc" / "datasets"

SIGNATURE = {
    "instruction": "Clasificar el texto.",
    "inputs": [{"name": "text", "desc": "Texto."}],
    "outputs": [{"name": "label", "desc": "Etiqueta."}],
}


def _config(module_type: str = "dynamic", **extra) -> dict:
    cfg = {
        "case": {"name": "x", "title": "X"},
        "module": {"type": module_type},
        "signature": SIGNATURE,
        "data": {"csv_filename": "x.csv", "input_column": "text"},
        "optimization": {"max_metric_calls": 10},
    }
    cfg.update(extra)
    return cfg


@pytest.mark.parametrize("module_type", ["dynamic", "rule_derived", "rule_derived_alto"])
def test_supported_types_pass(module_type):
    assert ConfigValidator.validate(_config(module_type)) == []


@pytest.mark.parametrize("module_type", ["sentiment", "extractor", "qa"])
def test_legacy_types_are_rejected_at_validation(module_type):
    errors = ConfigValidator.validate(_config(module_type))
    assert any("Invalid module type" in e for e in errors), errors


def test_adapter_section_is_rejected():
    errors = ConfigValidator.validate(_config(adapter={"max_text_length": 1000}))
    assert any("Section 'adapter' is not supported" in e for e in errors), errors


@pytest.mark.parametrize("path", DSPY_CONFIGS, ids=lambda p: p.name)
def test_shipped_configs_validate(path):
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert ConfigValidator.validate(config, str(DSPY_DATASETS)) == []
