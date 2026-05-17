"""
DSPy + GEPA results logger.

Thin wrapper around shared.logging.ExperimentLogger that wires in DSPy paths.
The class is kept for callers that import ``ResultsLogger`` by name.
"""

import sys
from pathlib import Path

# Add project root to path for shared module access
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.logging import STANDARD_COLUMN_MAPPING, ExperimentLogger  # noqa: E402
from shared.paths import get_dspy_paths  # noqa: E402

# Re-export for backwards compatibility
COLUMN_MAPPING = STANDARD_COLUMN_MAPPING


class ResultsLogger(ExperimentLogger):
    """ExperimentLogger pre-bound to ``DSPyPaths``."""

    def __init__(self, experiments_dir: str | None = None):
        paths = get_dspy_paths()
        if experiments_dir:
            # Caller overrode the experiments directory: keep the CSV there but
            # otherwise behave like the standard DSPy logger.
            from shared.logging import BaseCSVLogger  # noqa: PLC0415

            BaseCSVLogger.__init__(
                self,
                csv_path=Path(experiments_dir) / "metricas_optimizacion.csv",
                column_mapping=STANDARD_COLUMN_MAPPING,
            )
            self._paths = paths
            self._positive_reflection_default = "No"
            self.experiments_dir = Path(experiments_dir)
            return

        super().__init__(paths=paths, positive_reflection_default="No")
        self.experiments_dir = paths.experiments_log
