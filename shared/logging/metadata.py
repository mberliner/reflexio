"""
Metadata management for experiment reproducibility.

Provides 3-level metadata tracking:
- Level 1 (Global): Framework versions (environment.json)
- Level 2 (Experiment): Dataset hash, run counter (experiment_name.meta.json)
- Level 3 (Run): Seed, models, overrides (run.json)
"""

import hashlib
import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_SEED = 2**31 - 1
RUN_STATUSES = ("completed", "aborted")


def metrics_coverage(summaries: dict[str, Any]) -> dict[str, dict[str, int]]:
    """`n_evaluados / n_total` per metric from MetricSummary-like objects (FR-008)."""
    return {
        name: {"n_evaluados": m.n_evaluados, "n_total": m.n_total} for name, m in summaries.items()
    }


def generate_seed() -> int:
    """Generate a random seed for reproducibility tracking."""
    return random.randint(0, _MAX_SEED)


def collect_model_info(
    task_config,
    reflection_config,
    judge_config=None,
    task_max_tokens: int | None = None,
    judge_max_tokens: int | None = None,
) -> dict[str, Any]:
    """
    Collect effective model parameters from LLMConfig instances (SPEC-103 FR-012).

    Each role stores `LLMConfig.effective_params()`: what is really sent (temperature
    omitted, effort, reasoning mode, final max_tokens), so a run.json is comparable
    across providers.

    Args:
        task_config: LLMConfig for the task model.
        reflection_config: LLMConfig for the reflection model.
        judge_config: LLMConfig of the judge (RAG adapter); omitted if None.
        task_max_tokens: max_tokens fixed per call by the adapter (None = config).
        judge_max_tokens: max_tokens fixed per call for the judge (None = config).

    Returns:
        Dictionary with "task", "reflection" and, if given, "judge" entries.
    """
    info = {
        "task": task_config.effective_params(task_max_tokens),
        "reflection": reflection_config.effective_params(),
    }
    if judge_config is not None:
        info["judge"] = judge_config.effective_params(judge_max_tokens)
    return info


def _hash_file(path: Path) -> str:
    """Compute SHA-256 hash of a file. Returns empty string if file not found."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        logger.warning("File not found for hashing: %s", path)
        return ""


def _collect_framework_versions() -> dict[str, str | None]:
    """Collect installed versions of key frameworks."""
    versions: dict[str, str | None] = {}
    for pkg in ("dspy", "litellm", "gepa"):
        try:
            from importlib.metadata import version

            versions[pkg] = version(pkg)
        except Exception:
            versions[pkg] = None
    return versions


class MetadataManager:
    """
    Manages reproducibility metadata at 3 levels.

    Args:
        results_dir: Base results directory for the project.
    """

    def __init__(self, results_dir: Path):
        self.results_dir = Path(results_dir)

    # ==================== Level 1: Environment ====================

    def ensure_environment(self) -> Path:
        """
        Create or update environment.json with framework versions.

        Only writes if the file is missing or versions changed. Idempotent.

        Returns:
            Path to environment.json.
        """
        meta_dir = self.results_dir / ".metadata"
        meta_dir.mkdir(parents=True, exist_ok=True)
        env_path = meta_dir / "environment.json"

        current_versions = _collect_framework_versions()

        if env_path.exists():
            existing = json.loads(env_path.read_text(encoding="utf-8"))
            if existing.get("frameworks") == current_versions:
                logger.debug("environment.json unchanged, skipping write")
                return env_path

        data = {
            "frameworks": current_versions,
            "updated_at": datetime.now().isoformat(),
        }
        env_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("environment.json written: %s", env_path)
        return env_path

    # ==================== Level 2: Experiment ====================

    def ensure_experiment(
        self,
        experiment_name: str,
        dataset_path: Path,
        base_config: dict[str, Any],
    ) -> Path:
        """
        Create or update experiment metadata.

        Increments total_runs. Detects dataset hash changes.

        Args:
            experiment_name: Name of the experiment (e.g. "email_urgency").
            dataset_path: Path to the dataset CSV file.
            base_config: Subset of config relevant for comparison.

        Returns:
            Path to the experiment meta file.
        """
        experiments_dir = self.results_dir / "experiments"
        experiments_dir.mkdir(parents=True, exist_ok=True)
        meta_path = experiments_dir / f"{experiment_name}.meta.json"

        current_hash = _hash_file(dataset_path)

        if meta_path.exists():
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
            existing["total_runs"] = existing.get("total_runs", 0) + 1
            existing["last_run_at"] = datetime.now().isoformat()

            prev_hash = existing.get("dataset_hash", "")
            if prev_hash and prev_hash != current_hash:
                existing["dataset_hash_changed"] = True
                existing["previous_dataset_hash"] = prev_hash
                logger.warning(
                    "Dataset hash changed for experiment '%s': %s -> %s",
                    experiment_name,
                    prev_hash[:12],
                    current_hash[:12],
                )
            existing["dataset_hash"] = current_hash
            data = existing
        else:
            data = {
                "experiment_name": experiment_name,
                "dataset_hash": current_hash,
                "dataset_path": str(dataset_path),
                "base_config": base_config,
                "total_runs": 1,
                "created_at": datetime.now().isoformat(),
                "last_run_at": datetime.now().isoformat(),
            }

        meta_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Experiment metadata written: %s", meta_path)
        return meta_path

    # ==================== Level 3: Run ====================

    def create_run(
        self,
        run_dir: Path,
        experiment_name: str,
        seed: int,
        models: dict[str, Any],
        usage: dict[str, Any] | None = None,
        status: str = "completed",
        failures: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        paired_delta: dict[str, Any] | None = None,
    ) -> Path:
        """
        Write run-level metadata (run.json) to the run directory.

        Args:
            run_dir: Directory for this specific run.
            experiment_name: Name of the parent experiment.
            seed: Random seed used for this run.
            models: Model info from collect_model_info().
            usage: Optional real token-usage block (task/reflection buckets,
                total_tokens and cost_usd) from shared.llm.usage. Omitted from
                run.json when None.
            status: "completed" or "aborted" (SPEC-104 FR-008).
            failures: FailureTracker.snapshot(): counts per (class, role), attempts,
                `entrada_dato` cases and abort detail. When given, run.json gains
                `failures` and `abort` (class, role, count, cause; None if completed).
            metrics: `n_evaluados / n_total` per metric, e.g.
                {"baseline": {"n_evaluados": 9, "n_total": 10}}. Omitted when None.
            paired_delta: PairedDelta.to_dict() over val cases evaluated with both
                prompts (FR-003 / FR-008). Omitted when None (e.g. aborted runs).

        Returns:
            Path to run.json.

        Raises:
            ValueError: If status is not "completed" or "aborted".
        """
        if status not in RUN_STATUSES:
            raise ValueError(f"status debe ser uno de {RUN_STATUSES}: {status!r}")
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        run_path = run_dir / "run.json"

        data = {
            "experiment_name": experiment_name,
            "seed": seed,
            "models": models,
            "status": status,
            "created_at": datetime.now().isoformat(),
        }
        if failures is not None:
            abort = failures.get("abort")
            data["abort"] = (
                {k: abort[k] for k in ("clase", "rol", "conteo", "causa")} if abort else None
            )
            data["failures"] = failures
        if metrics is not None:
            data["metrics"] = metrics
        if paired_delta is not None:
            data["paired_delta"] = paired_delta
        if usage is not None:
            data["usage"] = usage

        run_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Run metadata written: %s", run_path)
        return run_path
