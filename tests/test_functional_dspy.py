"""
Functional tests for dspy_gepa_poc.

Exercises core components: module factory, metrics, data loading, and config,
without making real LLM calls.
"""

import csv

import dspy
import pytest
import yaml

from dspy_gepa_poc.data_loader import CSVDataLoader
from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory
from dspy_gepa_poc.metrics import create_dynamic_metric

# ==================== Fixtures ====================


@pytest.fixture
def dspy_root(tmp_path):
    """Create a mini dspy_gepa_poc directory structure with test data."""
    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir()

    csv_path = datasets_dir / "test_sentiment.csv"
    rows = [
        {"split": "train", "text": "I love this product!", "sentiment": "positive"},
        {"split": "train", "text": "Terrible experience.", "sentiment": "negative"},
        {"split": "val", "text": "Great service!", "sentiment": "positive"},
        {"split": "val", "text": "Not worth the price.", "sentiment": "negative"},
        {"split": "test", "text": "Amazing quality.", "sentiment": "positive"},
        {"split": "test", "text": "Very disappointing.", "sentiment": "negative"},
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "text", "sentiment"])
        writer.writeheader()
        writer.writerows(rows)

    return tmp_path


@pytest.fixture
def signature_config():
    """Valid DSPy signature configuration dict."""
    return {
        "instruction": "Classify the sentiment of the text as positive or negative.",
        "inputs": [{"name": "text", "desc": "The text to analyze."}],
        "outputs": [{"name": "sentiment", "desc": "The sentiment (positive or negative)."}],
    }


@pytest.fixture
def dspy_yaml_config(dspy_root):
    """Write a complete YAML config file and return its path."""
    config = {
        "case": {"name": "test_sentiment"},
        "module": {"type": "dynamic"},
        "signature": {
            "instruction": "Classify sentiment as positive or negative.",
            "inputs": [{"name": "text", "desc": "Input text."}],
            "outputs": [{"name": "sentiment", "desc": "Sentiment label."}],
        },
        "data": {
            "csv_filename": "test_sentiment.csv",
            "input_column": "text",
        },
        "optimization": {
            "max_metric_calls": 20,
            "auto_budget": "light",
        },
    }
    config_path = dspy_root / "test_config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f)
    return config_path


# ==================== Module Factory ====================


class TestDSPyModuleFactory:
    def test_create_signature(self, signature_config):
        sig = DynamicModuleFactory.create_signature(signature_config)

        assert issubclass(sig, dspy.Signature)
        # Verify fields exist
        field_names = list(sig.fields.keys())
        assert "text" in field_names
        assert "sentiment" in field_names

    def test_create_module_cot(self, signature_config):
        module = DynamicModuleFactory.create_module(signature_config, predictor_type="cot")

        assert isinstance(module, dspy.Module)
        assert hasattr(module, "predictor")
        assert isinstance(module.predictor, dspy.ChainOfThought)

    def test_create_module_predict(self, signature_config):
        module = DynamicModuleFactory.create_module(signature_config, predictor_type="predict")

        assert isinstance(module, dspy.Module)
        assert hasattr(module, "predictor")
        assert isinstance(module.predictor, dspy.Predict)


# ==================== Metrics ====================


class TestDSPyMetric:
    def test_exact_match_correct(self):
        metric = create_dynamic_metric(["sentiment"])

        example = dspy.Example(text="Great!", sentiment="positive").with_inputs("text")
        pred = dspy.Prediction(sentiment="positive")

        result = metric(example, pred)
        assert result is True

    def test_exact_match_wrong(self):
        metric = create_dynamic_metric(["sentiment"], normalize=True)

        example = dspy.Example(text="Great!", sentiment="positive").with_inputs("text")
        pred = dspy.Prediction(sentiment="negative")

        result = metric(example, pred)
        # With 1 field and 0 matches, normalized = 0/1 = 0.0
        assert result == 0.0

    def test_normalized_match(self):
        metric = create_dynamic_metric(["sentiment"], match_mode="normalized")

        example = dspy.Example(text="Great!", sentiment="positive").with_inputs("text")
        # Extra punctuation/spaces should be ignored in normalized mode
        pred = dspy.Prediction(sentiment="  positive!  ")

        result = metric(example, pred)
        assert result is True


# ==================== Data Loading ====================


class TestDSPyDataLoader:
    def test_csv_data_loader(self, dspy_root):
        loader = CSVDataLoader(datasets_dir=str(dspy_root / "datasets"))
        trainset, valset, testset = loader.load_dataset(
            filename="test_sentiment.csv",
            input_keys=["text"],
        )

        assert len(trainset) == 2
        assert len(valset) == 2
        assert len(testset) == 2

        # Verify dspy.Example structure
        example = trainset[0]
        assert isinstance(example, dspy.Example)
        assert hasattr(example, "text")
        assert hasattr(example, "sentiment")


# ==================== Config Loading ====================


class TestDSPyConfigLoading:
    def test_appconfig_loads_yaml(self, mock_env, dspy_yaml_config, dspy_root, monkeypatch):
        from dspy_gepa_poc.config import AppConfig

        # Override datasets dir to point to our temp path
        monkeypatch.setattr(AppConfig, "DATASETS_DIR", str(dspy_root / "datasets"))

        config = AppConfig(yaml_path=str(dspy_yaml_config))

        assert config.raw_config is not None
        assert config.raw_config["case"]["name"] == "test_sentiment"
        assert config.raw_config["module"]["type"] == "dynamic"
        assert "signature" in config.raw_config
        assert "data" in config.raw_config
