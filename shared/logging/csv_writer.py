"""
Base CSV logging functionality for experiment results.

Provides a base class and utilities for writing experiment results to CSV files
with European format (semicolon delimiter, comma decimal separator).
"""

import csv
import logging
import os
from pathlib import Path
from typing import Any

from .formatters import fmt_score, generate_run_id, get_timestamp

logger = logging.getLogger(__name__)


# European CSV configuration (semicolon delimiter, comma decimal)
EUROPEAN_CSV_CONFIG = {
    "delimiter": ";",
    "quotechar": '"',
    "quoting": csv.QUOTE_MINIMAL,
}


# Standard column mapping for experiment results
STANDARD_COLUMN_MAPPING = {
    "run_id": "Run ID",
    "date": "Fecha",
    "case_name": "Caso",
    "task_model": "Modelo Tarea",
    "reflection_model": "Modelo Profesor",
    "baseline_score": "Baseline Score",
    "optimized_score": "Optimizado Score",
    "test_score": "Robustez Score",
    "run_dir": "Run Directory",
    "positive_reflection": "Reflexion Positiva",
    "budget": "Budget",
    "notes": "Notas",
}


class BaseCSVLogger:
    """
    Base class for CSV-based experiment logging.

    Provides common functionality for initializing CSV files, formatting data,
    and appending results. Subclasses can customize column mappings and
    data processing.

    Attributes:
        csv_path: Path to the CSV file
        column_mapping: Dictionary mapping internal keys to display headers
        headers: List of column headers (derived from column_mapping)
    """

    def __init__(
        self,
        csv_path: Path,
        column_mapping: dict[str, str] | None = None,
        create_if_missing: bool = True,
    ):
        """
        Initialize the CSV logger.

        Args:
            csv_path: Path to the CSV file
            column_mapping: Dictionary mapping internal keys to display headers.
                           Defaults to STANDARD_COLUMN_MAPPING.
            create_if_missing: If True, create the CSV with headers if it doesn't exist.
        """
        self.csv_path = Path(csv_path)
        self.column_mapping = column_mapping or STANDARD_COLUMN_MAPPING.copy()
        self.headers = list(self.column_mapping.values())

        if create_if_missing:
            self._ensure_csv_exists()

    def _ensure_csv_exists(self) -> None:
        """Create the CSV file with headers if it doesn't exist."""
        # Ensure directory exists
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.csv_path.exists():
            self._write_headers()

    def _write_headers(self) -> None:
        """Write column headers to the CSV file."""
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, **EUROPEAN_CSV_CONFIG)
            writer.writerow(self.headers)

    def _prepare_row(self, data: dict[str, Any]) -> list[str]:
        """
        Prepare a row for CSV output from a data dictionary.

        Automatically formats score fields and handles missing values.

        Args:
            data: Dictionary with data keyed by internal column names

        Returns:
            List of string values in column order
        """
        row = []
        for key in self.column_mapping.keys():
            value = data.get(key, "N/A")

            # Auto-format score fields
            if "score" in key.lower() and value != "N/A":
                value = fmt_score(value)

            row.append(str(value) if value is not None else "N/A")

        return row

    def append_row(self, data: dict[str, Any]) -> None:
        """
        Append a single row to the CSV file.

        Args:
            data: Dictionary with data keyed by internal column names

        Raises:
            PermissionError: If file cannot be written due to permissions
            Exception: For other write errors
        """
        row = self._prepare_row(data)

        try:
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, **EUROPEAN_CSV_CONFIG)
                writer.writerow(row)
            logger.info(f"Row appended to: {self.csv_path}")
        except PermissionError:
            logger.error(f"Permission denied writing to CSV: {self.csv_path}")
            raise
        except Exception as e:
            logger.error(f"Error writing to CSV {self.csv_path}: {e}")
            raise

    def log_run(
        self,
        run_data: dict[str, Any],
        auto_generate_id: bool = True,
        auto_timestamp: bool = True,
    ) -> str:
        """
        Log an experiment run to the CSV.

        Convenience method that auto-generates run_id and timestamp if not provided.

        Args:
            run_data: Dictionary with run data
            auto_generate_id: If True and 'run_id' not in data, generate one
            auto_timestamp: If True and 'date' not in data, add current timestamp

        Returns:
            The run_id used (generated or provided)
        """
        data = run_data.copy()

        if auto_generate_id and "run_id" not in data:
            data["run_id"] = generate_run_id()

        if auto_timestamp and "date" not in data:
            data["date"] = get_timestamp()

        self.append_row(data)

        return data.get("run_id", "")


def make_path_relative(
    absolute_path: str,
    base_path: str,
    fallback: str | None = None,
) -> str:
    """
    Convert an absolute path to a relative path.

    Utility function for storing relative paths in CSV logs.

    Args:
        absolute_path: The absolute path to convert
        base_path: The base path to make it relative to
        fallback: Value to return if conversion fails. Defaults to original path.

    Returns:
        Relative path string, or fallback if conversion fails
    """
    if fallback is None:
        fallback = absolute_path

    try:
        if os.path.isabs(absolute_path):
            return os.path.relpath(absolute_path, base_path)
        return absolute_path
    except Exception:
        return fallback
