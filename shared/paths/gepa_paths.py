"""
Centralized Path Management for GEPA Standalone

This module provides a single source of truth for all file paths
used throughout the gepa_standalone system.

Benefits:
- Works from any working directory
- Consistent path resolution
- Easy to test and mock
- Clear contract for file locations
- Backward compatibility with legacy paths
"""

import os
import warnings
from pathlib import Path
from datetime import datetime
from typing import Optional


class GEPAPaths:
    """Manages all paths for GEPA standalone system."""

    def __init__(self, root_override: Optional[Path] = None):
        """
        Initialize paths manager.

        Args:
            root_override: Optional override for root directory (useful for testing)
        """
        if root_override:
            self._root = Path(root_override).resolve()
        else:
            # Root is the gepa_standalone directory (sibling of shared/)
            self._root = Path(__file__).parent.parent.parent.resolve() / "gepa_standalone"

    @property
    def root(self) -> Path:
        """Root directory of gepa_standalone package."""
        return self._root

    # ==================== INPUT PATHS ====================

    @property
    def experiments(self) -> Path:
        """Base experiments directory (user input workspace)."""
        return self._root / "experiments"

    @property
    def datasets(self) -> Path:
        """Directory for input CSV datasets."""
        path = self.experiments / "datasets"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def dataset(self, filename: str) -> Path:
        """
        Get path to specific dataset CSV.

        Falls back to legacy location (data/csv/) if not found in new location.

        Args:
            filename: Name of the CSV file

        Returns:
            Path to the dataset file
        """
        new_path = self.datasets / filename

        # Try new location first
        if new_path.exists():
            return new_path

        # Fallback to legacy location
        legacy_path = self.legacy_data_csv / filename
        if legacy_path.exists():
            warnings.warn(
                f"Dataset '{filename}' found in legacy location (data/csv/). "
                f"Consider moving to experiments/datasets/ for better organization.",
                DeprecationWarning,
                stacklevel=2
            )
            return legacy_path

        # If neither exists, return new path (will be created or raise error downstream)
        return new_path

    @property
    def prompts(self) -> Path:
        """Directory for initial prompt configurations."""
        path = self.experiments / "prompts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def prompt(self, filename: str) -> Path:
        """
        Get path to specific prompt JSON.

        Falls back to legacy location (prompts/) if not found in new location.

        Args:
            filename: Name of the prompt JSON file

        Returns:
            Path to the prompt file
        """
        new_path = self.prompts / filename

        # Try new location first
        if new_path.exists():
            return new_path

        # Fallback to legacy location
        legacy_path = self.legacy_prompts / filename
        if legacy_path.exists():
            warnings.warn(
                f"Prompt '{filename}' found in legacy location (prompts/). "
                f"Consider moving to experiments/prompts/ for better organization.",
                DeprecationWarning,
                stacklevel=2
            )
            return legacy_path

        # If neither exists, return new path
        return new_path

    # ==================== OUTPUT PATHS ====================

    @property
    def results(self) -> Path:
        """Base results directory (all outputs)."""
        path = self._root / "results"
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
        """Path to main experiments tracking CSV (metricas_optimizacion without prompts)."""
        return self.experiments_log / "metricas_optimizacion.csv"

    @property
    def runs(self) -> Path:
        """Base directory for individual experiment runs."""
        path = self.results / "runs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def case_runs_dir(self, case_name: str) -> Path:
        """
        Get directory for specific case's runs.

        Args:
            case_name: Name of case (e.g., 'email_urgency', 'cv_extraction')

        Returns:
            Path to case's runs directory
        """
        path = self.runs / case_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def run_dir(
        self,
        case_name: str,
        run_id: str,
        timestamp: Optional[datetime] = None
    ) -> Path:
        """
        Generate directory path for a specific run.

        Args:
            case_name: Name of case
            run_id: Unique run identifier (typically 8-char UUID)
            timestamp: Optional timestamp (defaults to now)

        Returns:
            Path to run directory with format: runs/{case}/{YYYY-MM-DD_HHMMSS}_{runid}/
        """
        if timestamp is None:
            timestamp = datetime.now()

        ts_str = timestamp.strftime("%Y-%m-%d_%H%M%S")
        dirname = f"{ts_str}_{run_id}"

        path = self.case_runs_dir(case_name) / dirname
        path.mkdir(parents=True, exist_ok=True)
        return path

    def latest_run_symlink(self, case_name: str) -> Path:
        """
        Path to 'latest' symlink for a case.

        Args:
            case_name: Name of case

        Returns:
            Path to latest symlink
        """
        return self.case_runs_dir(case_name) / "latest"

    @property
    def archived(self) -> Path:
        """Directory for archived/legacy result files."""
        path = self.results / "archived"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ==================== DEMOS PATH ====================

    @property
    def demos(self) -> Path:
        """Directory containing demo scripts."""
        return self._root / "demos"

    # ==================== LEGACY SUPPORT ====================

    @property
    def legacy_data_csv(self) -> Path:
        """Legacy data/csv directory path (for backward compatibility)."""
        return self._root / "data" / "csv"

    @property
    def legacy_prompts(self) -> Path:
        """Legacy prompts directory path (for backward compatibility)."""
        return self._root / "prompts"

    @property
    def legacy_resultados(self) -> Path:
        """Legacy resultados directory path (for backward compatibility)."""
        return self._root / "resultados"


# ==================== GLOBAL INSTANCE ====================

_paths_instance: Optional[GEPAPaths] = None


def get_paths(root_override: Optional[Path] = None) -> GEPAPaths:
    """
    Get the global GEPAPaths instance.

    Args:
        root_override: Optional override for root directory (mainly for testing)

    Returns:
        Global GEPAPaths instance
    """
    global _paths_instance

    # Create instance if it doesn't exist or if override is provided
    if _paths_instance is None or root_override is not None:
        _paths_instance = GEPAPaths(root_override=root_override)

    return _paths_instance


# ==================== CONVENIENCE FUNCTIONS ====================

def get_dataset_path(filename: str) -> Path:
    """Convenience function to get dataset path."""
    return get_paths().dataset(filename)


def get_prompt_path(filename: str) -> Path:
    """Convenience function to get prompt path."""
    return get_paths().prompt(filename)


def get_summary_csv_path() -> Path:
    """Convenience function to get summary CSV path."""
    return get_paths().summary_csv


def create_run_dir(case_name: str, run_id: str, timestamp: Optional[datetime] = None) -> Path:
    """
    Convenience function to create a run directory.

    Args:
        case_name: Name of case
        run_id: Unique run identifier
        timestamp: Optional timestamp

    Returns:
        Path to created run directory
    """
    return get_paths().run_dir(case_name, run_id, timestamp)
