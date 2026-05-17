"""
Unified run artifact persistence (initial/final prompt, config, results, latest symlink).

This helper consolidates what previously lived as ``save_run_details()`` in
``gepa_standalone/utils/results_logger.py`` and the inline equivalent in
``dspy_gepa_poc/reflexio_declarativa.py``. Both projects can use it via a
``BasePaths`` instance.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.paths import BasePaths

logger = logging.getLogger(__name__)


def _to_serializable(value: Any) -> Any:
    """Best-effort conversion of complex objects to JSON-serializable form."""
    if hasattr(value, "__dict__"):
        return value.__dict__
    return value


def save_run_artifacts(
    paths: BasePaths,
    case_name: str,
    run_id: str | None,
    initial_prompt: str,
    final_prompt: str,
    metadata: dict[str, Any],
    results: dict[str, Any],
    timestamp: datetime | None = None,
) -> Path:
    """
    Persist run artifacts (prompts, config, results) under ``paths.run_dir(...)``.

    Writes:
        - ``initial_prompt.txt``
        - ``final_prompt.txt``
        - ``config.json`` (the ``metadata`` dict)
        - ``results.json`` (the ``results`` dict, with best-effort serialization)

    If the ``paths`` instance exposes ``latest_run_symlink(case_name)`` (e.g.
    ``GEPAPaths``), a ``latest`` pointer is updated to the new run dir; on
    systems without symlink support a plain text file is written as fallback.

    Args:
        paths: Project paths (any ``BasePaths`` subclass).
        case_name: Logical case name.
        run_id: Optional unique run identifier; forwarded to ``paths.run_dir``.
        initial_prompt: Pre-optimization prompt.
        final_prompt: Optimized prompt.
        metadata: Run metadata dict (models, budget, ...).
        results: Run results dict (scores, detailed outputs, ...).
        timestamp: Optional timestamp (defaults to now).

    Returns:
        Path to the created run directory.
    """
    run_dir = paths.run_dir(case_name, run_id=run_id, timestamp=timestamp)

    (run_dir / "initial_prompt.txt").write_text(initial_prompt, encoding="utf-8")
    (run_dir / "final_prompt.txt").write_text(final_prompt, encoding="utf-8")

    (run_dir / "config.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    serializable_results = {k: _to_serializable(v) for k, v in results.items()}
    (run_dir / "results.json").write_text(
        json.dumps(serializable_results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    _update_latest_symlink(paths, case_name, run_dir)

    logger.info("Run artifacts written to %s", run_dir)
    return run_dir


def _update_latest_symlink(paths: BasePaths, case_name: str, run_dir: Path) -> None:
    """Update the ``latest`` pointer if the paths instance supports it."""
    latest_fn = getattr(paths, "latest_run_symlink", None)
    if latest_fn is None:
        return

    latest = latest_fn(case_name)
    if latest.exists() or latest.is_symlink():
        latest.unlink()

    try:
        latest.symlink_to(run_dir.name, target_is_directory=True)
    except OSError:
        # Systems without symlink support: write a plain pointer file.
        latest.write_text(str(run_dir), encoding="utf-8")
