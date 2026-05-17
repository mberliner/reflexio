"""
GEPA standalone results logger.

Thin wrappers over shared.logging utilities:
- ``GEPAResultsLogger`` is an ``ExperimentLogger`` pre-bound to ``GEPAPaths``.
- ``save_run_details`` is a backwards-compatible alias for
  ``shared.logging.save_run_artifacts`` that fills in ``GEPAPaths``.
- ``log_experiment_result`` mirrors the legacy positional API.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from shared.logging import ExperimentLogger, save_run_artifacts
from shared.paths import get_gepa_paths


def save_run_details(
    case_name: str,
    run_id: str,
    initial_prompt: str,
    final_prompt: str,
    metadata: dict[str, Any],
    results: dict[str, Any],
    timestamp: datetime | None = None,
) -> Path:
    """Persist run artifacts using ``GEPAPaths``.

    Backwards-compatible wrapper around ``shared.logging.save_run_artifacts``.
    """
    return save_run_artifacts(
        paths=get_gepa_paths(),
        case_name=case_name,
        run_id=run_id,
        initial_prompt=initial_prompt,
        final_prompt=final_prompt,
        metadata=metadata,
        results=results,
        timestamp=timestamp,
    )


class GEPAResultsLogger(ExperimentLogger):
    """ExperimentLogger pre-bound to ``GEPAPaths``."""

    def __init__(self) -> None:
        super().__init__(paths=get_gepa_paths(), positive_reflection_default="No")

    def log_experiment(
        self,
        case_title: str,
        task_model: str,
        reflection_model: str,
        baseline_score: float,
        optimized_score: float,
        robustness_score: float,
        run_directory: str,
        has_positive_reflection: bool = False,
        budget: int | None = None,
        notes: str = "",
    ) -> str:
        """Log an experiment row, returning the generated run_id."""
        return self.log_run(
            {
                "case_name": case_title,
                "task_model": task_model,
                "reflection_model": reflection_model,
                "baseline_score": baseline_score,
                "optimized_score": optimized_score,
                "test_score": robustness_score,
                "run_dir": run_directory,
                "positive_reflection": "Si" if has_positive_reflection else "No",
                "budget": budget if budget is not None else "N/A",
                "notes": notes,
            }
        )


def log_experiment_result(
    case_title: str,
    task_model: str,
    reflection_model: str,
    baseline_score: float,
    optimized_score: float,
    robustness_score: float,
    run_directory: str,
    has_positive_reflection: bool = False,
    budget: int | None = None,
    notes: str = "",
) -> str:
    """Legacy positional wrapper around ``GEPAResultsLogger.log_experiment``."""
    return GEPAResultsLogger().log_experiment(
        case_title=case_title,
        task_model=task_model,
        reflection_model=reflection_model,
        baseline_score=baseline_score,
        optimized_score=optimized_score,
        robustness_score=robustness_score,
        run_directory=run_directory,
        has_positive_reflection=has_positive_reflection,
        budget=budget,
        notes=notes,
    )
