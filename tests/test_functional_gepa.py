"""
Functional tests for gepa_standalone.

Exercises the real flow: config -> validate -> load data -> adapter -> evaluate,
with mocked LLM calls to avoid real API requests.
"""

import csv
import json
from unittest.mock import MagicMock

import pytest

from gepa_standalone.config_schema import ConfigValidator
from gepa_standalone.data.data_loader import load_gepa_data
from shared.paths import get_paths

# ==================== Fixtures ====================


@pytest.fixture
def gepa_root(tmp_path):
    """Create a mini gepa_standalone directory structure with test data."""
    # CSV dataset
    datasets_dir = tmp_path / "experiments" / "datasets"
    datasets_dir.mkdir(parents=True)
    csv_path = datasets_dir / "test_classify.csv"

    rows = [
        {"split": "train", "text": "Hello, how are you?", "label": "greeting"},
        {"split": "train", "text": "Good morning!", "label": "greeting"},
        {"split": "val", "text": "See you later", "label": "farewell"},
        {"split": "val", "text": "Hi there!", "label": "greeting"},
        {"split": "test", "text": "Goodbye friend", "label": "farewell"},
        {"split": "test", "text": "Hey!", "label": "greeting"},
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "text", "label"])
        writer.writeheader()
        writer.writerows(rows)

    # Prompt JSON
    prompts_dir = tmp_path / "experiments" / "prompts"
    prompts_dir.mkdir(parents=True)
    prompt_path = prompts_dir / "test_prompt.json"
    prompt_path.write_text(
        json.dumps({"system_prompt": "Classify as greeting or farewell"}),
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture
def gepa_paths(gepa_root):
    """Override get_paths() to use the temporary directory, then restore."""
    import shared.paths.gepa_paths as gp_module

    original = gp_module._paths_instance
    paths = get_paths(root_override=gepa_root)
    yield paths
    gp_module._paths_instance = original


@pytest.fixture
def gepa_config():
    """Valid GEPA config dictionary (classifier type)."""
    return {
        "case": {
            "name": "test_classify",
            "title": "Test Classification",
        },
        "adapter": {
            "type": "classifier",
            "valid_classes": ["greeting", "farewell"],
        },
        "data": {
            "csv_filename": "test_classify.csv",
            "input_column": "text",
            "output_columns": ["label"],
        },
        "prompt": {
            "filename": "test_prompt.json",
        },
        "optimization": {
            "max_metric_calls": 20,
            "skip_perfect_score": True,
            "display_progress_bar": False,
        },
    }


# ==================== Config Validation ====================


class TestGEPAConfigValidation:
    def test_valid_config_passes(self, gepa_paths, gepa_config):
        errors = ConfigValidator.validate(gepa_config)
        assert errors == []

    def test_invalid_config_detected(self, gepa_paths):
        invalid_config = {
            "case": {"name": "broken"},
            "adapter": {"type": "classifier"},  # missing valid_classes
            "data": {"csv_filename": "test_classify.csv"},
            "optimization": {"max_metric_calls": 20},
        }
        errors = ConfigValidator.validate(invalid_config)
        assert len(errors) > 0
        assert any("valid_classes" in e for e in errors)


# ==================== Data Loading ====================


class TestGEPADataLoading:
    def test_load_gepa_data_splits(self, gepa_paths):
        train, val, test = load_gepa_data(
            csv_filename="test_classify.csv",
            input_column="text",
            output_columns=["label"],
        )
        assert len(train) == 2
        assert len(val) == 2
        assert len(test) == 2

    def test_load_gepa_data_content(self, gepa_paths):
        train, _val, _test = load_gepa_data(
            csv_filename="test_classify.csv",
            input_column="text",
            output_columns=["label"],
        )
        example = train[0]
        assert "text" in example
        assert "label" in example
        assert example["label"] in ("greeting", "farewell")


# ==================== Adapter Evaluation ====================


class TestGEPAAdapterEvaluation:
    def test_classifier_adapter_creation(self, mock_env):
        from gepa_standalone.adapters.simple_classifier_adapter import SimpleClassifierAdapter

        adapter = SimpleClassifierAdapter(
            valid_classes=["greeting", "farewell"],
            temperature=0.0,
        )
        assert adapter.valid_classes == ["greeting", "farewell"]
        assert adapter.model is not None

    def test_classifier_evaluate_all_correct(self, mock_env, monkeypatch):
        from gepa_standalone.adapters.simple_classifier_adapter import SimpleClassifierAdapter

        # Mock litellm to always return "greeting"
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "greeting"
        monkeypatch.setattr("litellm.completion", MagicMock(return_value=mock_response))

        adapter = SimpleClassifierAdapter(
            valid_classes=["greeting", "farewell"],
            temperature=0.0,
        )

        batch = [
            {"text": "Hello!", "label": "greeting"},
            {"text": "Hi there!", "label": "greeting"},
        ]
        candidate = {"system_prompt": "Classify as greeting or farewell"}

        result = adapter.evaluate(batch, candidate)

        assert len(result.scores) == 2
        assert all(s == 1.0 for s in result.scores)

    def test_classifier_evaluate_mixed(self, mock_env, monkeypatch):
        from gepa_standalone.adapters.simple_classifier_adapter import SimpleClassifierAdapter

        # Mock litellm to return different values per call
        responses = ["greeting", "greeting"]  # second is wrong for "farewell"
        call_count = {"n": 0}

        def mock_completion(**kwargs):
            resp = MagicMock()
            resp.choices = [MagicMock()]
            resp.choices[0].message.content = responses[call_count["n"]]
            call_count["n"] += 1
            return resp

        monkeypatch.setattr("litellm.completion", mock_completion)

        adapter = SimpleClassifierAdapter(
            valid_classes=["greeting", "farewell"],
            temperature=0.0,
        )

        batch = [
            {"text": "Hello!", "label": "greeting"},
            {"text": "Goodbye!", "label": "farewell"},
        ]
        candidate = {"system_prompt": "Classify as greeting or farewell"}

        result = adapter.evaluate(batch, candidate)

        assert len(result.scores) == 2
        assert result.scores[0] == 1.0  # correct
        assert result.scores[1] == 0.0  # wrong


# ==================== End-to-End ====================


class TestGEPAEndToEnd:
    def test_config_to_evaluation_pipeline(self, gepa_paths, gepa_config, mock_env, monkeypatch):
        """Full pipeline: config -> validate -> load data -> adapter -> evaluate."""
        from gepa_standalone.adapters.simple_classifier_adapter import SimpleClassifierAdapter

        # Mock litellm
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "greeting"
        monkeypatch.setattr("litellm.completion", MagicMock(return_value=mock_response))

        # 1. Validate config
        errors = ConfigValidator.validate(gepa_config)
        assert errors == [], f"Validation errors: {errors}"

        # 2. Load data
        train, val, test = load_gepa_data(
            csv_filename=gepa_config["data"]["csv_filename"],
            input_column=gepa_config["data"]["input_column"],
            output_columns=gepa_config["data"]["output_columns"],
        )
        assert len(train) > 0
        assert len(val) > 0

        # 3. Create adapter
        adapter = SimpleClassifierAdapter(
            valid_classes=gepa_config["adapter"]["valid_classes"],
            temperature=0.0,
        )

        # 4. Load prompt
        prompt_path = gepa_paths.prompt(gepa_config["prompt"]["filename"])
        with open(prompt_path, encoding="utf-8") as f:
            prompt = json.load(f)

        # 5. Evaluate
        result = adapter.evaluate(val, prompt)

        assert result is not None
        assert len(result.scores) == len(val)
        assert len(result.outputs) == len(val)
        assert all(isinstance(s, float) for s in result.scores)
