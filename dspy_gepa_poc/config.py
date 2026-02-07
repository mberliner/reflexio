"""
Configuration module for DSPy + GEPA POC.
"""

import os
import sys
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from .config_schema import ConfigValidator
from dotenv import load_dotenv

# Add project root to path for shared module access
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.llm import LLMConfig, LLMConnectionError

# Load environment variables from project .env
_PROJECT_DIR = Path(__file__).parent
_ENV_FILE = _PROJECT_DIR / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)


@dataclass
class GEPAConfig:
    """Configuration for GEPA optimizer."""

    # Budget configuration
    auto_budget: str = "medium"  # 'light', 'medium', or 'heavy'
    max_metric_calls: Optional[int] = None  # Manual override for budget

    # Reflection settings
    reflection_minibatch_size: int = 3
    skip_perfect_score: bool = True

    # Candidate selection strategy
    candidate_selection_strategy: str = "pareto"  # 'pareto' or 'current_best'

    # Merge configuration
    use_merge: bool = True
    max_merge_invocations: int = 5

    # Adapter-specific settings (Default values, can be overridden by YAML)
    max_text_length: int = 1000
    max_positive_examples: int = 2
    extractor_max_positive_examples: int = 0

    # Advanced features
    enable_tool_optimization: bool = False
    track_stats: bool = True
    track_best_outputs: bool = False


class AppConfig:
    """
    Main application configuration that can load from YAML.
    Mirroring the 'Universal Optimizer' approach from gepa_standalone.
    """

    # Centralized path configuration (relative to package directory)
    _PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATASETS_DIR = os.path.join(_PACKAGE_DIR, "datasets")
    RESULTS_DIR = os.path.join(_PACKAGE_DIR, "results", "runs")
    EXPERIMENTS_DIR = os.path.join(_PACKAGE_DIR, "results", "experiments")

    def __init__(self, yaml_path: Optional[str] = None):
        self.gepa = GEPAConfig()
        self.raw_config: Dict[str, Any] = {}

        if yaml_path:
            self.load_from_yaml(yaml_path)

    def load_from_yaml(self, path: str):
        """Load and validate configuration from a YAML file."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found: {path}")
            
        with open(path, 'r') as f:
            self.raw_config = yaml.safe_load(f)
            
        # Validate using our schema validator
        errors = ConfigValidator.validate(self.raw_config, self.DATASETS_DIR)
        if errors:
            error_msg = "\n".join(errors)
            raise ValueError(f"Configuration errors in {path}:\n{error_msg}")
            
        # Map YAML values to dataclasses
        if "optimization" in self.raw_config:
            opt = self.raw_config["optimization"]
            if "auto_budget" in opt: self.gepa.auto_budget = opt["auto_budget"]
            if "max_metric_calls" in opt: self.gepa.max_metric_calls = opt["max_metric_calls"]
            
        # Map Adapter settings from YAML
        if "adapter" in self.raw_config:
            adp = self.raw_config["adapter"]
            if "max_text_length" in adp: self.gepa.max_text_length = adp["max_text_length"]
            if "max_positive_examples" in adp: self.gepa.max_positive_examples = adp["max_positive_examples"]
            if "extractor_max_positive_examples" in adp: self.gepa.extractor_max_positive_examples = adp["extractor_max_positive_examples"]

        # Module and data settings are stored in raw_config for the optimizer/adapter to use
        print(f"Successfully loaded configuration from {path}")

    @property
    def dataset_path(self) -> str:
        """Get the absolute path to the dataset CSV."""
        if "data" not in self.raw_config:
            return ""
        return os.path.join(self.DATASETS_DIR, self.raw_config["data"]["csv_filename"])

