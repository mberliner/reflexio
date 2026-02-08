"""
Shared fixtures for all tests.
"""

import csv
from unittest.mock import MagicMock

import pytest

LLM_ENV_VARS = [
    "LLM_MODEL_TASK",
    "LLM_MODEL_REFLECTION",
    "LLM_API_KEY",
    "LLM_API_BASE",
    "LLM_API_VERSION",
    "LLM_CACHE",
]


@pytest.fixture
def mock_env(monkeypatch):
    """Set standard LLM environment variables."""
    monkeypatch.setenv("LLM_MODEL_TASK", "azure/gpt-4.1-mini")
    monkeypatch.setenv("LLM_API_KEY", "test-key-123")
    monkeypatch.setenv("LLM_API_BASE", "https://test.openai.azure.com/")
    monkeypatch.setenv("LLM_API_VERSION", "2024-02-15-preview")
    monkeypatch.setenv("LLM_CACHE", "false")


@pytest.fixture
def clear_env(monkeypatch):
    """Remove all LLM environment variables."""
    for var in LLM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def sample_csv(tmp_path):
    """CSV with split, text, and label columns (3 rows: train/val/test)."""
    csv_path = tmp_path / "data.csv"
    rows = [
        {"split": "train", "text": "hello world", "label": "greeting"},
        {"split": "val", "text": "goodbye", "label": "farewell"},
        {"split": "test", "text": "hi there", "label": "greeting"},
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "text", "label"])
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


@pytest.fixture
def sample_csv_no_split(tmp_path):
    """CSV without split column."""
    csv_path = tmp_path / "no_split.csv"
    rows = [
        {"text": "hello", "label": "greeting"},
        {"text": "bye", "label": "farewell"},
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["text", "label"])
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


@pytest.fixture
def mock_litellm(monkeypatch):
    """Mock litellm.completion returning a response with content='OK'."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "OK"

    mock_completion = MagicMock(return_value=mock_response)
    monkeypatch.setattr("litellm.completion", mock_completion)
    return mock_completion
