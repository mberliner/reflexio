"""
Centralized Path Management for DSPy + GEPA POC

Provides paths for the dspy_gepa_poc project, following the same
structure conventions as GEPAPaths but with DSPy-specific layout.
"""

from datetime import datetime
from pathlib import Path

from .base_paths import BasePaths


class DSPyPaths(BasePaths):
    """Manages all paths for dspy_gepa_poc project."""

    @staticmethod
    def _default_root() -> Path:
        return Path(__file__).parent.parent.parent.resolve() / "dspy_gepa_poc"

    # ==================== INPUT PATHS ====================

    @property
    def datasets(self) -> Path:
        """Directory for input CSV datasets."""
        path = self._root / "datasets"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def configs(self) -> Path:
        """Directory for YAML configuration files."""
        path = self._root / "configs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ==================== OUTPUT PATHS ====================

    def run_dir(self, case_name: str, timestamp: datetime | None = None) -> Path:
        """
        Generate directory path for a specific run.

        Args:
            case_name: Name of case (e.g., 'Sentiment Analysis (Hard)')
            timestamp: Optional timestamp (defaults to now)

        Returns:
            Path to run directory with format: runs/{safe_case}_{YYYYMMDD_HHMMSS}/
        """
        if timestamp is None:
            timestamp = datetime.now()

        safe_name = case_name.replace(" ", "_").replace("(", "").replace(")", "")
        ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
        dirname = f"{safe_name}_{ts_str}"

        path = self.runs / dirname
        path.mkdir(parents=True, exist_ok=True)
        return path


# ==================== GLOBAL INSTANCE ====================

_dspy_paths_instance: DSPyPaths | None = None


def get_dspy_paths(root_override: Path | None = None) -> DSPyPaths:
    """
    Get the global DSPyPaths instance.

    Args:
        root_override: Optional override for root directory (mainly for testing)

    Returns:
        Global DSPyPaths instance
    """
    global _dspy_paths_instance

    if _dspy_paths_instance is None or root_override is not None:
        _dspy_paths_instance = DSPyPaths(root_override=root_override)

    return _dspy_paths_instance
