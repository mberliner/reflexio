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
    "judge_model": "Modelo Juez",
    "baseline_score": "Baseline Score",
    "optimized_score": "Optimizado Score",
    "test_score": "Robustez Score",
    "run_dir": "Run Directory",
    "positive_reflection": "Reflexion Positiva",
    "budget": "Budget",
    "tokens_task": "Tokens Task",
    "tokens_reflection": "Tokens Reflection",
    "cost_real_usd": "Costo Real USD",
    "lib_versions": "Versiones Librerias",
    "notes": "Notas",
}

# The judge exists only in RAG: empty (not "N/A") elsewhere (SPEC-106 FR-006).
_EMPTY_WHEN_MISSING = frozenset({"judge_model"})


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
        self._display_to_key = {display: key for key, display in self.column_mapping.items()}
        # Internal keys to write, in order. For a fresh file this is the full
        # mapping; for an existing file it is aligned to that file's header
        # (see _sync_active_keys_to_file) so appends never misalign columns.
        self._active_keys: list[str | None] = list(self.column_mapping.keys())

        if create_if_missing:
            self._ensure_csv_exists()

    def _ensure_csv_exists(self) -> None:
        """Create the CSV with headers if missing, else align to its header."""
        # Ensure directory exists
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.csv_path.exists():
            self._write_headers()
        else:
            self._sync_active_keys_to_file()

    def _sync_active_keys_to_file(self) -> None:
        """Align the write order to the existing file's header.

        Guarantees appended rows match the columns already on disk: columns the
        mapping has and the file lacks are added to the file (never dropped
        silently, SPEC-106 FR-006), and any column the file has that the
        mapping no longer knows keeps an empty slot to preserve alignment. An
        existing-but-empty file is (re)initialized with the current full header.
        """
        try:
            with open(self.csv_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f, **EUROPEAN_CSV_CONFIG)
                existing = next(reader, None)
        except OSError:
            return

        if not existing:
            self._write_headers()
            return

        if existing == self.headers:
            return

        missing = [h for h in self.headers if h not in existing]
        if missing:
            existing = self._add_missing_columns(existing, missing)

        self._active_keys = [self._display_to_key.get(h) for h in existing]
        logger.info(
            "CSV header differs from current mapping; appending aligned to existing %d columns: %s",
            len(existing),
            self.csv_path,
        )

    def _add_missing_columns(self, existing: list[str], missing: list[str]) -> list[str]:
        """Rewrite the file adding the mapping columns it lacks (SPEC-106 FR-006, D10).

        Existing columns keep their order and values, including those the mapping
        does not know; each missing column goes right after the nearest preceding
        mapping column present in the file, and is empty in existing rows. The
        rewrite is atomic (temporary file and replace). A new column is never
        dropped silently: a WARN asks to run ``migrate_metrics_csv`` to backfill
        ``Modelo Juez`` in earlier RAG rows.
        """
        with open(self.csv_path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f, **EUROPEAN_CSV_CONFIG))

        new_header = list(existing)
        for header in self.headers:
            if header not in missing:
                continue
            pos = 0
            for earlier in reversed(self.headers[: self.headers.index(header)]):
                if earlier in new_header:
                    pos = new_header.index(earlier) + 1
                    break
            new_header.insert(pos, header)

        index_of = {h: i for i, h in enumerate(existing)}
        out_rows = [new_header]
        for raw in rows[1:]:
            out_rows.append(
                [
                    raw[index_of[h]] if h in index_of and index_of[h] < len(raw) else ""
                    for h in new_header
                ]
            )

        tmp_path = self.csv_path.with_name(self.csv_path.name + ".tmp")
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f, **EUROPEAN_CSV_CONFIG).writerows(out_rows)
        os.replace(tmp_path, self.csv_path)

        logger.warning(
            "[WARN] CSV %s lacked columns %s; added them (empty in earlier rows). "
            "Run `python -m shared.utils.migrate_metrics_csv` to fill 'Modelo Juez' "
            "in earlier RAG rows.",
            self.csv_path,
            missing,
        )
        return new_header

    def _write_headers(self) -> None:
        """Write column headers to the CSV file."""
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, **EUROPEAN_CSV_CONFIG)
            writer.writerow(self.headers)

    def _prepare_row(self, data: dict[str, Any]) -> list[str]:
        """
        Prepare a row for CSV output from a data dictionary.

        Automatically formats score fields and handles missing values.
        Iterates ``_active_keys`` so the row aligns with the file's header.

        Args:
            data: Dictionary with data keyed by internal column names

        Returns:
            List of string values in column order
        """
        row = []
        for key in self._active_keys:
            # Unknown legacy column: keep an empty slot to preserve alignment.
            if key is None:
                row.append("")
                continue

            # Keys that stay empty (not "N/A") when the case does not use them.
            empty = "" if key in _EMPTY_WHEN_MISSING else "N/A"
            value = data.get(key, empty)

            # Auto-format score fields
            if "score" in key.lower() and value != "N/A":
                value = fmt_score(value)

            row.append(str(value) if value is not None else empty)

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
