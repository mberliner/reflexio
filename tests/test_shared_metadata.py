"""
Unit tests for shared/logging/metadata.py.

Tests MetadataManager (3 levels), generate_seed, and collect_model_info.
"""

import json

import pytest

from shared.llm import LLMConfig
from shared.logging.metadata import (
    _MAX_SEED,
    MetadataManager,
    collect_model_info,
    generate_seed,
    metrics_coverage,
)


@pytest.fixture
def results_dir(tmp_path):
    """Provide a temporary results directory."""
    return tmp_path / "results"


@pytest.fixture
def manager(results_dir):
    return MetadataManager(results_dir)


@pytest.fixture
def sample_dataset(tmp_path):
    """Create a sample CSV file for hashing."""
    csv = tmp_path / "data.csv"
    csv.write_text("split,text,label\ntrain,hello,1\ndev,world,0\n", encoding="utf-8")
    return csv


# ==================== generate_seed ====================


class TestGenerateSeed:
    def test_returns_int(self):
        seed = generate_seed()
        assert isinstance(seed, int)

    def test_in_range(self):
        seed = generate_seed()
        assert 0 <= seed <= _MAX_SEED


# ==================== collect_model_info ====================


def _cfg(model, role="task", **kwargs):
    params = {
        "model": model,
        "api_key": "x",
        "temperature": 0.0,
        "max_tokens": 1000,
        "role": role,
    }
    params.update(kwargs)
    return LLMConfig(**params)


class TestCollectModelInfo:
    def test_returns_task_and_reflection_effective_params(self):
        task = _cfg("azure/gpt-4o")
        reflection = _cfg("azure/gpt-4o-mini", "reflection", temperature=0.7, max_tokens=2000)

        info = collect_model_info(task, reflection)

        assert info["task"] == task.effective_params()
        assert info["reflection"] == reflection.effective_params()
        assert info["task"]["model"] == "azure/gpt-4o"
        assert info["reflection"]["temperature"] == 0.7
        assert info["reflection"]["max_tokens"] == 2000
        assert "judge" not in info

    def test_anthropic_reports_what_is_sent(self):
        task = _cfg("anthropic/claude-opus-4-7", temperature=0.3, max_tokens=500)
        reflection = _cfg("anthropic/claude-opus-5-5", "reflection", effort="high")

        info = collect_model_info(task, reflection)

        assert info["task"]["temperature"] is None
        assert info["task"]["temperature_omitted"] is True
        assert info["task"]["temperature_requested"] == 0.3
        assert info["reflection"]["effort"] == "high"
        assert info["reflection"]["thinking"] == "adaptive"
        assert info["reflection"]["max_tokens"] >= 16000
        assert info["reflection"]["max_tokens_requested"] == 1000

    def test_per_call_max_tokens_and_judge(self):
        task = _cfg("anthropic/claude-haiku-4-5", max_tokens=2000)
        reflection = _cfg("anthropic/claude-haiku-4-5", "reflection")
        judge = _cfg("anthropic/claude-haiku-4-5", "reflection", max_tokens=2000)

        info = collect_model_info(
            task, reflection, judge_config=judge, task_max_tokens=400, judge_max_tokens=200
        )

        assert info["task"]["max_tokens"] == 400
        assert info["judge"]["max_tokens"] == 200
        assert info["reflection"]["max_tokens"] == 1000

    def test_is_json_serializable_and_has_no_secrets(self):
        task = _cfg("anthropic/claude-opus-5-5", api_key="sk-secret")

        info = collect_model_info(task, _cfg("azure/gpt-4o"))

        assert "sk-secret" not in json.dumps(info)


# ==================== Level 1: Environment ====================


class TestEnsureEnvironment:
    def test_creates_environment_json(self, manager, results_dir):
        path = manager.ensure_environment()

        assert path.exists()
        assert path == results_dir / ".metadata" / "environment.json"

        data = json.loads(path.read_text(encoding="utf-8"))
        assert "frameworks" in data
        assert "updated_at" in data

    def test_idempotent_no_rewrite(self, manager):
        path = manager.ensure_environment()
        mtime1 = path.stat().st_mtime_ns

        # Second call should not rewrite (same versions)
        path2 = manager.ensure_environment()
        mtime2 = path2.stat().st_mtime_ns

        assert mtime1 == mtime2

    def test_updates_on_version_change(self, manager, results_dir):
        path = manager.ensure_environment()

        # Tamper with versions to simulate a change
        data = json.loads(path.read_text(encoding="utf-8"))
        data["frameworks"]["dspy"] = "0.0.0-fake"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tampered = path.read_text(encoding="utf-8")

        # Should detect mismatch and rewrite with real versions
        manager.ensure_environment()
        updated = path.read_text(encoding="utf-8")

        assert updated != tampered
        reloaded = json.loads(updated)
        assert reloaded["frameworks"]["dspy"] != "0.0.0-fake"


# ==================== Level 2: Experiment ====================


class TestEnsureExperiment:
    def test_creates_experiment_meta(self, manager, results_dir, sample_dataset):
        path = manager.ensure_experiment(
            experiment_name="email_urgency",
            dataset_path=sample_dataset,
            base_config={"case": "email_urgency"},
        )

        assert path.exists()
        assert path == results_dir / "experiments" / "email_urgency.meta.json"

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["total_runs"] == 1
        assert data["dataset_hash"] != ""
        assert data["experiment_name"] == "email_urgency"

    def test_increments_total_runs(self, manager, sample_dataset):
        cfg = {"case": "test"}
        manager.ensure_experiment("test_exp", sample_dataset, cfg)
        path = manager.ensure_experiment("test_exp", sample_dataset, cfg)

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["total_runs"] == 2

    def test_detects_dataset_hash_change(self, manager, sample_dataset):
        cfg = {"case": "test"}
        manager.ensure_experiment("hash_exp", sample_dataset, cfg)

        # Modify dataset content
        sample_dataset.write_text("split,text,label\ntrain,changed,9\n", encoding="utf-8")
        path = manager.ensure_experiment("hash_exp", sample_dataset, cfg)

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("dataset_hash_changed") is True
        assert "previous_dataset_hash" in data


# ==================== Level 3: Run ====================


class TestCreateRun:
    def test_creates_run_json(self, manager, tmp_path):
        run_dir = tmp_path / "runs" / "email_urgency" / "run_001"
        models = {
            "task": {"model": "azure/gpt-4o", "temperature": 0.0, "max_tokens": 1000},
            "reflection": {"model": "azure/gpt-4o-mini", "temperature": 0.7, "max_tokens": 2000},
        }

        path = manager.create_run(
            run_dir=run_dir,
            experiment_name="email_urgency",
            seed=42,
            models=models,
        )

        assert path.exists()
        assert path == run_dir / "run.json"

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["seed"] == 42
        assert data["experiment_name"] == "email_urgency"
        assert data["models"]["task"]["model"] == "azure/gpt-4o"
        assert "created_at" in data
        # usage omitted when not provided
        assert "usage" not in data

    def test_creates_run_json_with_usage(self, manager, tmp_path):
        run_dir = tmp_path / "runs" / "demo" / "run_001"
        usage = {
            "task": {"calls": 10, "prompt_tokens": 1000, "completion_tokens": 200},
            "reflection": {"calls": 3, "prompt_tokens": 900, "completion_tokens": 150},
            "total_tokens": 2250,
            "cost_usd": 0.01234,
        }
        path = manager.create_run(
            run_dir=run_dir,
            experiment_name="demo",
            seed=1,
            models={"task": {}, "reflection": {}},
            usage=usage,
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["usage"]["total_tokens"] == 2250
        assert data["usage"]["cost_usd"] == 0.01234
        assert data["usage"]["task"]["prompt_tokens"] == 1000


class TestCreateRunFailures:
    """SPEC-104 FR-008 / D8: estado, conteos, casos entrada_dato y n_evaluados / n_total."""

    SNAPSHOT_ABORTED = {
        "counts": {"presupuesto": {"task": 3}},
        "attempts": {"task": 20},
        "unique_cases": {"task": 20},
        "entrada_dato": ["val:4", "val:7"],
        "aborted": True,
        "abort": {
            "clase": "presupuesto",
            "rol": "task",
            "conteo": 3,
            "intentos": 20,
            "causa": "length",
            "motivo": "Tasa 3/20 supera el umbral 0.05",
        },
    }

    def _create(self, manager, tmp_path, **kwargs):
        path = manager.create_run(
            run_dir=tmp_path / "run",
            experiment_name="demo",
            seed=1,
            models={"task": {}, "reflection": {}},
            **kwargs,
        )
        return json.loads(path.read_text(encoding="utf-8"))

    def test_status_defaults_to_completed(self, manager, tmp_path):
        data = self._create(manager, tmp_path)
        assert data["status"] == "completed"
        assert "abort" not in data and "failures" not in data

    def test_aborted_run_records_class_role_count_and_cause(self, manager, tmp_path):
        data = self._create(manager, tmp_path, status="aborted", failures=self.SNAPSHOT_ABORTED)
        assert data["status"] == "aborted"
        assert data["abort"] == {
            "clase": "presupuesto",
            "rol": "task",
            "conteo": 3,
            "causa": "length",
        }
        assert data["failures"]["counts"] == {"presupuesto": {"task": 3}}
        assert data["failures"]["entrada_dato"] == ["val:4", "val:7"]

    def test_completed_run_has_null_abort_and_the_counts(self, manager, tmp_path):
        snapshot = {**self.SNAPSHOT_ABORTED, "aborted": False, "abort": None}
        data = self._create(manager, tmp_path, status="completed", failures=snapshot)
        assert data["status"] == "completed"
        assert data["abort"] is None
        assert data["failures"]["attempts"] == {"task": 20}

    def test_metrics_coverage_is_n_evaluados_over_n_total(self, manager, tmp_path):
        from shared.scoring import summarize

        summaries = {
            "baseline": summarize([[("a", 1.0, True), ("b", 0.0, False), ("c", 0.0, True)]]),
            "test": summarize([]),
        }
        data = self._create(manager, tmp_path, metrics=metrics_coverage(summaries))
        assert data["metrics"]["baseline"] == {"n_evaluados": 2, "n_total": 3}
        assert data["metrics"]["test"] == {"n_evaluados": 0, "n_total": 0}

    def test_invalid_status_is_rejected(self, manager, tmp_path):
        with pytest.raises(ValueError, match="status"):
            self._create(manager, tmp_path, status="done")
