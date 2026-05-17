"""
Unified experiment logger backed by ``BasePaths``.

Replaces the previously duplicated ``ResultsLogger`` (DSPy) and
``GEPAResultsLogger`` (GEPA standalone) by extracting their common shape:

- Auto-generate ``run_id`` + ``date`` when not provided.
- Convert ``run_dir`` to a path relative to ``paths.results``.
- Map ``max_calls`` -> ``budget`` when only the former is present.
- Apply project-style default for ``positive_reflection``.

Project-specific defaults are passed via constructor (no subclassing required).
"""

import logging
from pathlib import Path
from typing import Any

from shared.paths import BasePaths

from .csv_writer import STANDARD_COLUMN_MAPPING, BaseCSVLogger, make_path_relative
from .formatters import generate_run_id, get_timestamp

logger = logging.getLogger(__name__)


class ExperimentLogger(BaseCSVLogger):
    """
    Append experiment runs to ``paths.summary_csv`` with shared conventions.

    Args:
        paths: A ``BasePaths`` subclass providing ``summary_csv`` and ``results``.
        positive_reflection_default: Value to fill the ``positive_reflection``
            column when the caller does not supply one. ``"No"`` for DSPy
            historically, GEPA passes its own ``"Si"``/``"No"`` per call.
        column_mapping: Override of the standard column mapping.
    """

    def __init__(
        self,
        paths: BasePaths,
        positive_reflection_default: str = "No",
        column_mapping: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            csv_path=paths.summary_csv,
            column_mapping=column_mapping or STANDARD_COLUMN_MAPPING,
        )
        self._paths = paths
        self._positive_reflection_default = positive_reflection_default

    def log_run(self, run_data: dict[str, Any]) -> str:
        """
        Append a normalized run row to the CSV.

        Returns the ``run_id`` used (generated when not provided).
        """
        data = dict(run_data)

        data.setdefault("run_id", generate_run_id())
        data.setdefault("date", get_timestamp())

        if "budget" not in data and "max_calls" in data:
            data["budget"] = data["max_calls"]

        if not data.get("notes"):
            data["notes"] = ""

        data["run_dir"] = self._resolve_run_dir(data.get("run_dir", "N/A"))

        if "positive_reflection" not in data:
            data["positive_reflection"] = self._positive_reflection_default

        self.append_row(data)
        logger.info("Run logged to %s", self.csv_path)
        return str(data["run_id"])

    def _resolve_run_dir(self, run_dir_raw: str) -> str:
        if run_dir_raw == "N/A":
            return run_dir_raw
        if not Path(run_dir_raw).exists():
            logger.warning("run_dir no existe: %s", run_dir_raw)
        try:
            return make_path_relative(run_dir_raw, str(self._paths.results))
        except Exception:
            return run_dir_raw
