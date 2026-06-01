"""
Tests for the consolidated shared.logging helpers:
- ExperimentLogger (replaces ResultsLogger/GEPAResultsLogger duplication)
- save_run_artifacts (replaces save_run_details)
"""

import csv
from datetime import datetime
from pathlib import Path

import pytest

from shared.logging import ExperimentLogger, save_run_artifacts
from shared.paths import DSPyPaths, GEPAPaths


@pytest.fixture
def gepa_paths(tmp_path: Path) -> GEPAPaths:
    return GEPAPaths(root_override=tmp_path)


@pytest.fixture
def dspy_paths(tmp_path: Path) -> DSPyPaths:
    return DSPyPaths(root_override=tmp_path)


# ==================== ExperimentLogger ====================


class TestExperimentLogger:
    def test_auto_run_id_and_timestamp(self, gepa_paths: GEPAPaths) -> None:
        logger = ExperimentLogger(paths=gepa_paths)
        run_id = logger.log_run(
            {
                "case_name": "demo",
                "task_model": "gpt-4o-mini",
                "reflection_model": "gpt-4o",
                "baseline_score": 0.5,
                "optimized_score": 0.8,
                "test_score": 0.75,
                "run_dir": "N/A",
            }
        )
        assert run_id  # generated
        assert gepa_paths.summary_csv.exists()

    def test_max_calls_maps_to_budget(self, gepa_paths: GEPAPaths) -> None:
        logger = ExperimentLogger(paths=gepa_paths)
        logger.log_run({"case_name": "demo", "max_calls": 42, "run_dir": "N/A"})

        rows = list(csv.reader(gepa_paths.summary_csv.open(encoding="utf-8"), delimiter=";"))
        # Header + 1 row
        assert len(rows) == 2
        # Find the budget column by header name
        budget_idx = rows[0].index("Budget")
        assert rows[1][budget_idx] == "42"

    def test_default_positive_reflection(self, gepa_paths: GEPAPaths) -> None:
        logger = ExperimentLogger(paths=gepa_paths, positive_reflection_default="Si")
        logger.log_run({"case_name": "demo", "run_dir": "N/A"})

        rows = list(csv.reader(gepa_paths.summary_csv.open(encoding="utf-8"), delimiter=";"))
        col_idx = rows[0].index("Reflexion Positiva")
        assert rows[1][col_idx] == "Si"

    def test_new_token_columns_written(self, gepa_paths: GEPAPaths) -> None:
        logger = ExperimentLogger(paths=gepa_paths)
        logger.log_run(
            {
                "case_name": "demo",
                "run_dir": "N/A",
                "tokens_task": 1234,
                "tokens_reflection": 567,
                "cost_real_usd": "0,012345",
            }
        )
        rows = list(csv.reader(gepa_paths.summary_csv.open(encoding="utf-8"), delimiter=";"))
        header = rows[0]
        assert "Tokens Task" in header
        assert "Tokens Reflection" in header
        assert "Costo Real USD" in header
        assert rows[1][header.index("Tokens Task")] == "1234"
        assert rows[1][header.index("Costo Real USD")] == "0,012345"

    def test_append_aligns_to_legacy_header(self, gepa_paths: GEPAPaths) -> None:
        # Simulate a pre-existing CSV without the new token columns.
        legacy_header = (
            "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;Baseline Score;"
            "Optimizado Score;Robustez Score;Run Directory;Reflexion Positiva;Budget;Notas"
        )
        gepa_paths.summary_csv.parent.mkdir(parents=True, exist_ok=True)
        gepa_paths.summary_csv.write_text(legacy_header + "\n", encoding="utf-8")

        logger = ExperimentLogger(paths=gepa_paths)
        logger.log_run(
            {
                "case_name": "demo",
                "run_dir": "N/A",
                "budget": 30,
                "tokens_task": 999,  # new column absent in legacy file -> dropped
            }
        )
        rows = list(csv.reader(gepa_paths.summary_csv.open(encoding="utf-8"), delimiter=";"))
        # Header unchanged (still 12 cols); appended row has matching width.
        assert len(rows[0]) == 12
        assert len(rows[1]) == 12
        assert rows[1][rows[0].index("Budget")] == "30"
        assert "Tokens Task" not in rows[0]

    def test_run_dir_made_relative(self, gepa_paths: GEPAPaths) -> None:
        run_dir = gepa_paths.run_dir("demo", run_id="abc123")
        logger = ExperimentLogger(paths=gepa_paths)
        logger.log_run({"case_name": "demo", "run_dir": str(run_dir)})

        rows = list(csv.reader(gepa_paths.summary_csv.open(encoding="utf-8"), delimiter=";"))
        col_idx = rows[0].index("Run Directory")
        # Should be relative to paths.results
        assert not Path(rows[1][col_idx]).is_absolute()
        assert "abc123" in rows[1][col_idx]


# ==================== save_run_artifacts ====================


class TestSaveRunArtifacts:
    def test_writes_all_files_gepa(self, gepa_paths: GEPAPaths) -> None:
        ts = datetime(2026, 5, 17, 13, 0, 0)
        run_dir = save_run_artifacts(
            paths=gepa_paths,
            case_name="email_urgency",
            run_id="r123",
            initial_prompt="initial",
            final_prompt="final",
            metadata={"task_model": "gpt-4o-mini"},
            results={"baseline_score": 0.7, "optimized_score": 0.9},
            timestamp=ts,
        )
        assert (run_dir / "initial_prompt.txt").read_text(encoding="utf-8") == "initial"
        assert (run_dir / "final_prompt.txt").read_text(encoding="utf-8") == "final"
        assert (run_dir / "config.json").exists()
        assert (run_dir / "results.json").exists()
        # Latest pointer should exist (symlink or text file).
        latest = gepa_paths.latest_run_symlink("email_urgency")
        assert latest.exists() or latest.is_symlink()

    def test_works_without_latest_symlink(self, dspy_paths: DSPyPaths) -> None:
        # DSPyPaths does NOT define latest_run_symlink — must still succeed.
        run_dir = save_run_artifacts(
            paths=dspy_paths,
            case_name="sentiment",
            run_id=None,
            initial_prompt="a",
            final_prompt="b",
            metadata={},
            results={},
        )
        assert (run_dir / "initial_prompt.txt").exists()

    def test_serializes_dict_with_object(self, gepa_paths: GEPAPaths) -> None:
        class Holder:
            def __init__(self) -> None:
                self.score = 0.42

        run_dir = save_run_artifacts(
            paths=gepa_paths,
            case_name="demo",
            run_id="x",
            initial_prompt="i",
            final_prompt="f",
            metadata={},
            results={"obj": Holder()},
        )
        # results.json should contain the object's __dict__ rather than crashing.
        import json

        data = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
        assert data["obj"] == {"score": 0.42}
