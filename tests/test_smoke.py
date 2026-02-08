"""
Smoke tests: verify that core modules import without errors.

These tests catch broken imports, missing dependencies, and
circular import issues early.
"""


# ==================== shared/ imports ====================


class TestSharedImports:
    def test_shared_paths(self):
        from shared.paths import (  # noqa: F401  # noqa: F401
            BasePaths,
            DSPyPaths,
            GEPAPaths,
            get_dspy_paths,
            get_paths,
        )

    def test_shared_llm(self):
        from shared.llm import LLMConfig  # noqa: F401

    def test_shared_display(self):
        from shared.display import print_header, print_section  # noqa: F401

    def test_shared_logging(self):
        from shared.logging import STANDARD_COLUMN_MAPPING, BaseCSVLogger  # noqa: F401

    def test_shared_validation(self):
        from shared.validation import BaseConfigValidator, CSVValidator  # noqa: F401


# ==================== gepa_standalone/ imports ====================


class TestGEPAStandaloneImports:
    def test_config_schema(self):
        import gepa_standalone.config_schema  # noqa: F401

    def test_gepa_default_root(self):
        from shared.paths import GEPAPaths

        assert GEPAPaths._default_root().name == "gepa_standalone"


# ==================== dspy_gepa_poc/ imports ====================


class TestDSPyImports:
    def test_config(self):
        from dspy_gepa_poc.config import AppConfig  # noqa: F401

    def test_config_schema(self):
        from dspy_gepa_poc.config_schema import ConfigValidator  # noqa: F401

    def test_results_logger(self):
        from dspy_gepa_poc.results_logger import ResultsLogger  # noqa: F401

    def test_dspy_default_root(self):
        from shared.paths import DSPyPaths

        assert DSPyPaths._default_root().name == "dspy_gepa_poc"
