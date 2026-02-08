"""
Abstract base class for path management across projects.

Provides common output path structure (results, runs, experiments_log, summary_csv)
while allowing each project to define its own root and input paths.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class BasePaths(ABC):
    """Base class with shared path logic for all projects."""

    def __init__(self, root_override: Path | None = None):
        if root_override:
            self._root = Path(root_override).resolve()
        else:
            self._root = self._default_root()

    @staticmethod
    @abstractmethod
    def _default_root() -> Path:
        """Return the default root directory for this project."""

    @property
    def root(self) -> Path:
        return self._root

    # ==================== OUTPUT PATHS (common) ====================

    @property
    def results(self) -> Path:
        """Base results directory (all outputs)."""
        path = self._root / "results"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def runs(self) -> Path:
        """Base directory for individual experiment runs."""
        path = self.results / "runs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def experiments_log(self) -> Path:
        """Directory for experiment tracking logs."""
        path = self.results / "experiments"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def summary_csv(self) -> Path:
        """Path to main experiments tracking CSV."""
        return self.experiments_log / "metricas_optimizacion.csv"

    # ==================== INPUT PATHS (project-specific) ====================

    @property
    @abstractmethod
    def datasets(self) -> Path:
        """Directory for input datasets. Location varies by project."""

    def dataset(self, filename: str) -> Path:
        """Get path to a specific dataset file."""
        return self.datasets / filename
