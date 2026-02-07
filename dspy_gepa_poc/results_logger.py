"""
Results logger for DSPy + GEPA experiments.

Uses shared logging utilities for consistent formatting across projects.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Add project root to path for shared module access
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.logging import (
    BaseCSVLogger,
    STANDARD_COLUMN_MAPPING,
    generate_run_id,
    get_timestamp,
    fmt_score,
    make_path_relative,
)

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility
COLUMN_MAPPING = STANDARD_COLUMN_MAPPING


class ResultsLogger(BaseCSVLogger):
    """
    Manages a centralized log of all DSPy + GEPA optimization experiments.

    Extends BaseCSVLogger with DSPy-specific path resolution.
    Uses European CSV format (semicolon delimiter, comma decimal).
    """

    # Default path (can be overridden via AppConfig.EXPERIMENTS_DIR)
    _DEFAULT_EXPERIMENTS_DIR = Path(__file__).parent / "results" / "experiments"

    def __init__(self, experiments_dir: str = None):
        """
        Initialize the logger.

        Args:
            experiments_dir: Path for experiment logs.
                             Defaults to AppConfig.EXPERIMENTS_DIR if available.
        """
        if experiments_dir:
            exp_dir = Path(experiments_dir)
        else:
            # Use centralized config if available, else fallback
            try:
                from .config import AppConfig
                exp_dir = Path(AppConfig.EXPERIMENTS_DIR)
            except ImportError:
                exp_dir = self._DEFAULT_EXPERIMENTS_DIR

        csv_path = exp_dir / "metricas_optimizacion.csv"
        super().__init__(csv_path=csv_path, column_mapping=STANDARD_COLUMN_MAPPING)

        # Store for path resolution
        self.experiments_dir = exp_dir

    def log_run(self, run_data: Dict[str, Any]) -> None:
        """
        Append a new run result to the master log.

        Handles DSPy-specific path resolution for run directories.

        Args:
            run_data: Dictionary containing run data with keys matching COLUMN_MAPPING
        """
        data = run_data.copy()

        # Auto-generate run_id and timestamp
        data["run_id"] = generate_run_id()
        data["date"] = get_timestamp()

        # Set budget from max_calls if not explicitly provided
        if "budget" not in data and "max_calls" in data:
            data["budget"] = data["max_calls"]

        # Notes is now free-form text (budget has its own column)
        if not data.get("notes"):
            data["notes"] = ""

        # Convert run_dir to relative path
        run_dir_raw = data.get("run_dir", "N/A")
        if run_dir_raw != "N/A" and not Path(run_dir_raw).exists():
            logger.warning("run_dir no existe: %s", run_dir_raw)
        try:
            from .config import AppConfig
            results_base = Path(AppConfig.RESULTS_DIR).parent
            data["run_dir"] = make_path_relative(run_dir_raw, str(results_base))
        except Exception:
            data["run_dir"] = run_dir_raw

        # Set default for positive_reflection
        if "positive_reflection" not in data:
            data["positive_reflection"] = "No"

        # Use parent's append_row (handles formatting automatically)
        self.append_row(data)
        logger.info(f"Run logged to master list: {self.csv_path}")
