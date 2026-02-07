"""
CSV structure validation utilities.

Provides common CSV validation functionality for dataset files.
"""

import csv
from pathlib import Path
from typing import Dict, List, Any, Optional, Set


class CSVValidator:
    """
    Validates CSV file structure for machine learning datasets.

    Checks for required columns, split column presence, and
    input/output column existence.
    """

    # Standard split column name
    SPLIT_COLUMN = "split"

    # Valid split values
    VALID_SPLITS = {"train", "val", "test"}

    @staticmethod
    def validate(
        csv_path: Path,
        required_columns: Optional[List[str]] = None,
        input_columns: Optional[List[str]] = None,
        output_columns: Optional[List[str]] = None,
        require_split: bool = True,
        encoding: str = "utf-8-sig",
    ) -> List[str]:
        """
        Validate CSV file structure.

        Args:
            csv_path: Path to the CSV file
            required_columns: List of columns that must exist
            input_columns: List of input columns to validate
            output_columns: List of output columns to validate
            require_split: If True, require a 'split' column
            encoding: File encoding (default: utf-8-sig to handle BOM)

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        if not csv_path.exists():
            errors.append(f"CSV file not found: {csv_path}")
            return errors

        try:
            headers = CSVValidator._read_headers(csv_path, encoding)

            if not headers:
                errors.append(f"CSV file is empty or has no headers: {csv_path.name}")
                return errors

            # Check split column
            if require_split:
                split_errors = CSVValidator._validate_split_column(headers, csv_path)
                errors.extend(split_errors)

            # Check required columns
            if required_columns:
                for col in required_columns:
                    if col not in headers:
                        errors.append(
                            f"Required column '{col}' not found in CSV\n"
                            f"  File: {csv_path.name}\n"
                            f"  Available: {', '.join(headers)}"
                        )

            # Check input columns
            if input_columns:
                for col in input_columns:
                    if col and col not in headers:
                        errors.append(
                            f"Input column '{col}' not found in CSV\n"
                            f"  File: {csv_path.name}\n"
                            f"  Available: {', '.join(headers)}"
                        )

            # Check output columns
            if output_columns:
                for col in output_columns:
                    if col and col not in headers:
                        errors.append(
                            f"Output column '{col}' not found in CSV\n"
                            f"  File: {csv_path.name}\n"
                            f"  Available: {', '.join(headers)}"
                        )

        except Exception as e:
            errors.append(f"Error reading CSV file '{csv_path.name}': {e}")

        return errors

    @staticmethod
    def _read_headers(csv_path: Path, encoding: str = "utf-8-sig") -> Optional[List[str]]:
        """
        Read CSV headers from file.

        Args:
            csv_path: Path to CSV file
            encoding: File encoding

        Returns:
            List of header names, or None if file is empty
        """
        with open(csv_path, "r", encoding=encoding) as f:
            reader = csv.DictReader(f)
            return reader.fieldnames

    @staticmethod
    def _validate_split_column(headers: List[str], csv_path: Path) -> List[str]:
        """
        Validate presence of split column.

        Args:
            headers: List of CSV headers
            csv_path: Path to CSV (for error messages)

        Returns:
            List of error messages
        """
        errors = []

        if CSVValidator.SPLIT_COLUMN not in headers:
            errors.append(
                f"CSV must have a '{CSVValidator.SPLIT_COLUMN}' column (values: train, val, test)\n"
                f"  File: {csv_path.name}\n"
                f"  Found columns: {', '.join(headers)}"
            )

        return errors

    @staticmethod
    def get_headers(csv_path: Path, encoding: str = "utf-8-sig") -> List[str]:
        """
        Get list of headers from CSV file.

        Args:
            csv_path: Path to CSV file
            encoding: File encoding

        Returns:
            List of header names

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is empty or has no headers
        """
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        headers = CSVValidator._read_headers(csv_path, encoding)

        if not headers:
            raise ValueError(f"CSV file is empty or has no headers: {csv_path}")

        return list(headers)

    @staticmethod
    def validate_from_config(
        csv_path: Path,
        config: Dict[str, Any],
        input_key: str = "input_column",
        output_key: str = "output_columns",
        data_section: str = "data",
    ) -> List[str]:
        """
        Validate CSV structure using configuration dictionary.

        Convenience method that extracts column names from config.

        Args:
            csv_path: Path to CSV file
            config: Configuration dictionary
            input_key: Key for input column in config (default: "input_column")
            output_key: Key for output columns in config (default: "output_columns")
            data_section: Section name containing data config (default: "data")

        Returns:
            List of error messages
        """
        data_config = config.get(data_section, {})

        # Extract input columns
        input_col = data_config.get(input_key)
        input_columns = [input_col] if input_col else None

        # Extract output columns (handle both list and single value)
        output_cols = data_config.get(output_key, [])
        if output_cols and not isinstance(output_cols, list):
            output_cols = [output_cols]
        output_columns = output_cols if output_cols else None

        return CSVValidator.validate(
            csv_path=csv_path,
            input_columns=input_columns,
            output_columns=output_columns,
        )
