"""
Smoke tests: verify that core modules import without errors.

These tests catch broken imports, missing dependencies, and
circular import issues early.
"""

import sys
from pathlib import Path

# Ensure project root is in path
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.paths import GEPAPaths, DSPyPaths


# ==================== shared/ imports ====================

class TestSharedImports:

    def test_shared_paths(self):
        from shared.paths import BasePaths, GEPAPaths, DSPyPaths
        from shared.paths import get_paths, get_dspy_paths

    def test_shared_llm(self):
        from shared.llm import LLMConfig

    def test_shared_display(self):
        from shared.display import print_header, print_section

    def test_shared_logging(self):
        from shared.logging import BaseCSVLogger, STANDARD_COLUMN_MAPPING

    def test_shared_validation(self):
        from shared.validation import BaseConfigValidator, CSVValidator


# ==================== gepa_standalone/ imports ====================

class TestGEPAStandaloneImports:

    def test_config_schema(self):
        import gepa_standalone.config_schema

    def test_gepa_default_root(self):
        assert GEPAPaths._default_root().name == "gepa_standalone"


# ==================== dspy_gepa_poc/ imports ====================

class TestDSPyImports:

    def test_config(self):
        from dspy_gepa_poc.config import AppConfig

    def test_config_schema(self):
        from dspy_gepa_poc.config_schema import ConfigValidator

    def test_results_logger(self):
        from dspy_gepa_poc.results_logger import ResultsLogger

    def test_dspy_default_root(self):
        assert DSPyPaths._default_root().name == "dspy_gepa_poc"
