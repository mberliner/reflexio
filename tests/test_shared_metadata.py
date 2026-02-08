"""
Unit tests for shared/logging/metadata.py.

Tests MetadataManager (3 levels), generate_seed, and collect_model_info.
"""

import json
from types import SimpleNamespace

import pytest

from shared.logging.metadata import _MAX_SEED, MetadataManager, collect_model_info, generate_seed


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


class TestCollectModelInfo:
    def test_returns_task_and_reflection(self):
        task = SimpleNamespace(model="azure/gpt-4o", temperature=0.0, max_tokens=1000)
        reflection = SimpleNamespace(model="azure/gpt-4o-mini", temperature=0.7, max_tokens=2000)

        info = collect_model_info(task, reflection)

        assert info["task"]["model"] == "azure/gpt-4o"
        assert info["task"]["temperature"] == 0.0
        assert info["reflection"]["model"] == "azure/gpt-4o-mini"
        assert info["reflection"]["max_tokens"] == 2000


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
