"""
Unit tests for shared/paths/ module.

Tests BasePaths (via concrete subclasses), GEPAPaths, and DSPyPaths.
"""

from datetime import datetime
from pathlib import Path

import pytest

from shared.paths import BasePaths, DSPyPaths, GEPAPaths, get_dspy_paths, get_paths
from shared.paths.gepa_paths import (
    create_run_dir,
    get_dataset_path,
    get_prompt_path,
    get_summary_csv_path,
)

# ==================== BasePaths (abstract) ====================


class TestBasePaths:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BasePaths()

    def test_concrete_subclass_requires_datasets(self):
        """A subclass missing 'datasets' should fail to instantiate."""

        class IncompletePaths(BasePaths):
            @staticmethod
            def _default_root():
                return Path("/tmp/test_incomplete")

        with pytest.raises(TypeError):
            IncompletePaths()


# ==================== GEPAPaths ====================


class TestGEPAPaths:
    @pytest.fixture
    def paths(self, tmp_path):
        return GEPAPaths(root_override=tmp_path)

    def test_root(self, paths, tmp_path):
        assert paths.root == tmp_path

    def test_results(self, paths, tmp_path):
        assert paths.results == tmp_path / "results"
        assert paths.results.exists()

    def test_runs(self, paths, tmp_path):
        assert paths.runs == tmp_path / "results" / "runs"
        assert paths.runs.exists()

    def test_experiments_log(self, paths, tmp_path):
        assert paths.experiments_log == tmp_path / "results" / "experiments"
        assert paths.experiments_log.exists()

    def test_summary_csv(self, paths, tmp_path):
        expected = tmp_path / "results" / "experiments" / "metricas_optimizacion.csv"
        assert paths.summary_csv == expected

    def test_datasets(self, paths, tmp_path):
        assert paths.datasets == tmp_path / "experiments" / "datasets"
        assert paths.datasets.exists()

    def test_dataset_returns_new_path_if_none_exist(self, paths, tmp_path):
        result = paths.dataset("test.csv")
        assert result == tmp_path / "experiments" / "datasets" / "test.csv"

    def test_dataset_prefers_new_location(self, paths, tmp_path):
        # Create file in new location
        new_file = tmp_path / "experiments" / "datasets" / "data.csv"
        new_file.parent.mkdir(parents=True, exist_ok=True)
        new_file.touch()

        assert paths.dataset("data.csv") == new_file

    def test_dataset_falls_back_to_legacy(self, paths, tmp_path):
        # Create file only in legacy location
        legacy_file = tmp_path / "data" / "csv" / "old.csv"
        legacy_file.parent.mkdir(parents=True, exist_ok=True)
        legacy_file.touch()

        with pytest.warns(DeprecationWarning, match="legacy location"):
            result = paths.dataset("old.csv")
        assert result == legacy_file

    def test_prompts(self, paths, tmp_path):
        assert paths.prompts == tmp_path / "experiments" / "prompts"
        assert paths.prompts.exists()

    def test_run_dir(self, paths, tmp_path):
        ts = datetime(2026, 1, 15, 10, 30, 0)
        result = paths.run_dir("email_urgency", "abc123", timestamp=ts)
        expected = tmp_path / "results" / "runs" / "email_urgency" / "2026-01-15_103000_abc123"
        assert result == expected
        assert result.exists()

    def test_latest_run_symlink(self, paths, tmp_path):
        result = paths.latest_run_symlink("email_urgency")
        assert result.name == "latest"

    def test_prompt_prefers_new_location(self, paths, tmp_path):
        new_file = tmp_path / "experiments" / "prompts" / "system.json"
        new_file.parent.mkdir(parents=True, exist_ok=True)
        new_file.touch()

        assert paths.prompt("system.json") == new_file

    def test_prompt_falls_back_to_legacy(self, paths, tmp_path):
        legacy_file = tmp_path / "prompts" / "old.json"
        legacy_file.parent.mkdir(parents=True, exist_ok=True)
        legacy_file.touch()

        with pytest.warns(DeprecationWarning, match="legacy location"):
            result = paths.prompt("old.json")
        assert result == legacy_file

    def test_prompt_returns_new_path_if_none_exist(self, paths, tmp_path):
        result = paths.prompt("missing.json")
        assert result == tmp_path / "experiments" / "prompts" / "missing.json"

    def test_run_dir_auto_timestamp(self, paths):
        result = paths.run_dir("test_case", "xyz789")
        assert result.exists()
        assert "xyz789" in result.name

    def test_archived(self, paths, tmp_path):
        assert paths.archived == tmp_path / "results" / "archived"
        assert paths.archived.exists()

    def test_demos(self, paths, tmp_path):
        assert paths.demos == tmp_path / "demos"

    def test_legacy_prompts(self, paths, tmp_path):
        assert paths.legacy_prompts == tmp_path / "prompts"

    def test_legacy_resultados(self, paths, tmp_path):
        assert paths.legacy_resultados == tmp_path / "resultados"

    def test_default_root_points_to_gepa_standalone(self):
        root = GEPAPaths._default_root()
        assert root.name == "gepa_standalone"

    def test_inherits_from_base(self):
        assert issubclass(GEPAPaths, BasePaths)


# ==================== DSPyPaths ====================


class TestDSPyPaths:
    @pytest.fixture
    def paths(self, tmp_path):
        return DSPyPaths(root_override=tmp_path)

    def test_root(self, paths, tmp_path):
        assert paths.root == tmp_path

    def test_results(self, paths, tmp_path):
        assert paths.results == tmp_path / "results"

    def test_runs(self, paths, tmp_path):
        assert paths.runs == tmp_path / "results" / "runs"

    def test_experiments_log(self, paths, tmp_path):
        assert paths.experiments_log == tmp_path / "results" / "experiments"

    def test_summary_csv(self, paths, tmp_path):
        expected = tmp_path / "results" / "experiments" / "metricas_optimizacion.csv"
        assert paths.summary_csv == expected

    def test_datasets(self, paths, tmp_path):
        assert paths.datasets == tmp_path / "datasets"
        assert paths.datasets.exists()

    def test_configs(self, paths, tmp_path):
        assert paths.configs == tmp_path / "configs"
        assert paths.configs.exists()

    def test_dataset(self, paths, tmp_path):
        result = paths.dataset("sentiment.csv")
        assert result == tmp_path / "datasets" / "sentiment.csv"

    def test_run_dir_sanitizes_name(self, paths, tmp_path):
        ts = datetime(2026, 2, 6, 12, 54, 33)
        result = paths.run_dir("Sentiment Analysis (Hard)", timestamp=ts)
        assert result.name == "Sentiment_Analysis_Hard_20260206_125433"
        assert result.exists()

    def test_run_dir_simple_name(self, paths, tmp_path):
        ts = datetime(2026, 3, 1, 8, 0, 0)
        result = paths.run_dir("email_urgency", timestamp=ts)
        assert result.name == "email_urgency_20260301_080000"

    def test_run_dir_auto_timestamp(self, paths):
        result = paths.run_dir("test_case")
        assert result.exists()
        assert "test_case_" in result.name

    def test_default_root_points_to_dspy_gepa_poc(self):
        root = DSPyPaths._default_root()
        assert root.name == "dspy_gepa_poc"

    def test_inherits_from_base(self):
        assert issubclass(DSPyPaths, BasePaths)


# ==================== Singletons ====================


class TestSingletons:
    def test_get_paths_returns_gepa(self):
        p = get_paths()
        assert isinstance(p, GEPAPaths)
        assert "gepa_standalone" in str(p.root)

    def test_get_dspy_paths_returns_dspy(self):
        p = get_dspy_paths()
        assert isinstance(p, DSPyPaths)
        assert "dspy_gepa_poc" in str(p.root)

    def test_get_paths_override(self, tmp_path):
        p = get_paths(root_override=tmp_path)
        assert p.root == tmp_path

    def test_get_dspy_paths_override(self, tmp_path):
        p = get_dspy_paths(root_override=tmp_path)
        assert p.root == tmp_path


# ==================== Convenience Functions ====================


class TestConvenienceFunctions:
    def test_get_dataset_path(self, tmp_path):
        get_paths(root_override=tmp_path)
        result = get_dataset_path("test.csv")
        assert result == tmp_path / "experiments" / "datasets" / "test.csv"

    def test_get_prompt_path(self, tmp_path):
        get_paths(root_override=tmp_path)
        result = get_prompt_path("system.json")
        assert result == tmp_path / "experiments" / "prompts" / "system.json"

    def test_get_summary_csv_path(self, tmp_path):
        get_paths(root_override=tmp_path)
        result = get_summary_csv_path()
        expected = tmp_path / "results" / "experiments" / "metricas_optimizacion.csv"
        assert result == expected

    def test_create_run_dir(self, tmp_path):
        get_paths(root_override=tmp_path)
        ts = datetime(2026, 6, 1, 12, 0, 0)
        result = create_run_dir("my_case", "run123", timestamp=ts)
        assert result.exists()
        assert "run123" in result.name


# ==================== Backward Compatibility ====================


class TestBackwardCompat:
    def test_appconfig_paths_match_dspy_paths(self):
        from dspy_gepa_poc.config import AppConfig

        dspy_p = get_dspy_paths()

        assert AppConfig.DATASETS_DIR == str(dspy_p.datasets)
        assert AppConfig.RESULTS_DIR == str(dspy_p.runs)
        assert AppConfig.EXPERIMENTS_DIR == str(dspy_p.experiments_log)
