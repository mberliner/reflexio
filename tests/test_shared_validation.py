"""
Tests for shared/validation/ module.

Covers errors.py, csv_validator.py, and base_validator.py.
"""

import pytest

from shared.validation.base_validator import BaseConfigValidator
from shared.validation.csv_validator import CSVValidator
from shared.validation.errors import ValidationError, format_validation_errors

# ==================== ValidationError ====================


class TestValidationError:
    def test_errors_attribute_preserved(self):
        errors = ["error one", "error two"]
        exc = ValidationError(errors)
        assert exc.errors == errors

    def test_formatted_contains_numbered_errors(self):
        errors = ["missing field", "bad type"]
        exc = ValidationError(errors)
        assert "1. missing field" in exc.formatted
        assert "2. bad type" in exc.formatted

    def test_custom_message_in_str(self):
        exc = ValidationError(["err"], message="Custom failure")
        assert "Custom failure" in str(exc)


# ==================== format_validation_errors ====================


class TestFormatValidationErrors:
    def test_empty_list_returns_empty_string(self):
        assert format_validation_errors([]) == ""

    def test_single_error_format(self):
        result = format_validation_errors(["something broke"])
        assert "CONFIGURATION ERRORS DETECTED" in result
        assert "1. something broke" in result
        assert "=" * 70 in result

    def test_multiple_errors_numbered(self):
        result = format_validation_errors(["err A", "err B", "err C"])
        assert "1. err A" in result
        assert "2. err B" in result
        assert "3. err C" in result

    def test_custom_title(self):
        result = format_validation_errors(["x"], title="MY CUSTOM TITLE")
        assert "MY CUSTOM TITLE" in result
        assert "CONFIGURATION ERRORS DETECTED" not in result


# ==================== CSVValidator ====================


class TestCSVValidator:
    def test_read_headers_valid_csv(self, sample_csv):
        headers = CSVValidator._read_headers(sample_csv)
        assert headers == ["split", "text", "label"]

    def test_read_headers_empty_file(self, tmp_path):
        empty = tmp_path / "empty.csv"
        empty.write_text("")
        result = CSVValidator._read_headers(empty)
        assert result is None

    def test_get_headers_returns_list(self, sample_csv):
        headers = CSVValidator.get_headers(sample_csv)
        assert isinstance(headers, list)
        assert headers == ["split", "text", "label"]

    def test_get_headers_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            CSVValidator.get_headers(tmp_path / "nonexistent.csv")

    def test_get_headers_empty_file(self, tmp_path):
        empty = tmp_path / "empty.csv"
        empty.write_text("")
        with pytest.raises(ValueError):
            CSVValidator.get_headers(empty)

    def test_validate_no_errors(self, sample_csv):
        errors = CSVValidator.validate(sample_csv, require_split=True)
        assert errors == []

    def test_validate_file_not_found(self, tmp_path):
        errors = CSVValidator.validate(tmp_path / "missing.csv")
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_validate_empty_file(self, tmp_path):
        empty = tmp_path / "empty.csv"
        empty.write_text("")
        errors = CSVValidator.validate(empty)
        assert len(errors) == 1
        assert "empty or has no headers" in errors[0]

    def test_validate_missing_split_column(self, sample_csv_no_split):
        errors = CSVValidator.validate(sample_csv_no_split, require_split=True)
        assert len(errors) == 1
        assert "split" in errors[0]

    def test_validate_missing_required_column(self, sample_csv):
        errors = CSVValidator.validate(sample_csv, required_columns=["nonexistent"])
        assert len(errors) == 1
        assert "nonexistent" in errors[0]

    def test_validate_missing_input_column(self, sample_csv):
        errors = CSVValidator.validate(sample_csv, input_columns=["missing_input"])
        assert len(errors) == 1
        assert "missing_input" in errors[0]

    def test_validate_missing_output_column(self, sample_csv):
        errors = CSVValidator.validate(sample_csv, output_columns=["missing_output"])
        assert len(errors) == 1
        assert "missing_output" in errors[0]

    def test_validate_accumulates_multiple_errors(self, sample_csv_no_split):
        errors = CSVValidator.validate(
            sample_csv_no_split,
            require_split=True,
            required_columns=["nonexistent"],
            input_columns=["bad_input"],
        )
        assert len(errors) == 3

    def test_validate_from_config(self, sample_csv):
        config = {
            "data": {
                "input_column": "text",
                "output_columns": ["label"],
            }
        }
        errors = CSVValidator.validate_from_config(sample_csv, config)
        assert errors == []

    def test_validate_from_config_output_as_string(self, sample_csv):
        config = {
            "data": {
                "input_column": "text",
                "output_columns": "label",
            }
        }
        errors = CSVValidator.validate_from_config(sample_csv, config)
        assert errors == []


# ==================== BaseConfigValidator ====================


class TestBaseConfigValidator:
    def _minimal_config(self):
        return {
            "case": {"name": "test_case"},
            "data": {"csv_filename": "data.csv"},
            "optimization": {"max_metric_calls": 100},
        }

    def test_validate_minimal_valid(self):
        errors = BaseConfigValidator.validate(self._minimal_config())
        assert errors == []

    def test_validate_missing_section(self):
        config = {
            "data": {"csv_filename": "data.csv"},
            "optimization": {"max_metric_calls": 100},
        }
        errors = BaseConfigValidator.validate(config)
        assert any("Missing required section" in e for e in errors)
        assert any("case" in e for e in errors)

    def test_validate_missing_field(self):
        config = {
            "case": {},
            "data": {"csv_filename": "data.csv"},
            "optimization": {"max_metric_calls": 100},
        }
        errors = BaseConfigValidator.validate(config)
        assert any("Missing required field: 'case.name'" in e for e in errors)

    def test_validate_csv_exists(self, sample_csv):
        config = self._minimal_config()
        config["data"]["csv_filename"] = sample_csv.name
        errors = BaseConfigValidator.validate(config, datasets_dir=str(sample_csv.parent))
        assert errors == []

    def test_validate_csv_missing(self, tmp_path):
        config = self._minimal_config()
        config["data"]["csv_filename"] = "nonexistent.csv"
        errors = BaseConfigValidator.validate(config, datasets_dir=str(tmp_path))
        assert len(errors) == 1
        assert "nonexistent.csv" in errors[0]

    def test_validate_or_raise_passes(self):
        BaseConfigValidator.validate_or_raise(self._minimal_config())

    def test_validate_or_raise_raises(self):
        config = {"data": {"csv_filename": "x.csv"}}
        with pytest.raises(ValidationError):
            BaseConfigValidator.validate_or_raise(config)

    def test_type_schema_validation(self):
        """Subclass with TYPE_SCHEMAS validates type-specific fields."""

        class CustomValidator(BaseConfigValidator):
            REQUIRED_FIELDS = {"module": ["type"]}
            TYPE_SECTION = "module"
            TYPE_FIELD = "type"
            TYPE_SCHEMAS = {
                "alpha": {"required": ["param_a"]},
                "beta": {"required": ["param_b"]},
            }

        # Valid type with required field
        config = {"module": {"type": "alpha", "param_a": "value"}}
        assert CustomValidator.validate(config) == []

        # Valid type missing required field
        config_bad = {"module": {"type": "alpha"}}
        errors = CustomValidator.validate(config_bad)
        assert any("param_a" in e for e in errors)

        # Invalid type
        config_invalid = {"module": {"type": "gamma"}}
        errors = CustomValidator.validate(config_invalid)
        assert any("gamma" in e for e in errors)

    def test_get_valid_types_default(self):
        assert BaseConfigValidator.get_valid_types() == []

    def test_get_valid_types_subclass(self):

        class CustomValidator(BaseConfigValidator):
            TYPE_SCHEMAS = {"foo": {}, "bar": {}}

        assert sorted(CustomValidator.get_valid_types()) == ["bar", "foo"]
