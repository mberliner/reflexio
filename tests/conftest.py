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


@pytest.fixture
def metrics_csv_sample(tmp_path):
    """CSV de metricas con formato europeo."""
    csv_path = tmp_path / "metricas_optimizacion.csv"
    content = (
        "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;"
        "Baseline Score;Optimizado Score;Robustez Score;Budget;Notas\n"
        "abc123;2026-02-01 10:00:00;Email Urgency;gpt-4o-mini;gpt-4o;"
        "0,75;0,85;0,80;30;Strategy: adaptive\n"
        "def456;2026-02-02 11:00:00;CV Extraction;gpt-4.1-mini;gpt-4o;"
        "0,60;0,75;0,72;25;Strategy: greedy\n"
        "ghi789;2026-02-03 12:00:00;Email Urgency;gpt-4o-mini;gpt-4o;"
        "0,70;0,82;0,78;30;Strategy: adaptive\n"
    )
    csv_path.write_text(content, encoding="utf-8")
    return csv_path


@pytest.fixture
def metrics_rows():
    """Lista de dicts simulando datos cargados."""
    return [
        {
            "Run ID": "abc123",
            "Fecha": "2026-02-01 10:00:00",
            "Caso": "Email Urgency",
            "Modelo Tarea": "gpt-4o-mini",
            "Modelo Profesor": "gpt-4o",
            "Baseline Score": "0,75",
            "Optimizado Score": "0,85",
            "Robustez Score": "0,80",
            "Budget": "30",
            "Notas": "Strategy: adaptive",
            "source": "test_project",
        },
        {
            "Run ID": "def456",
            "Fecha": "2026-02-02 11:00:00",
            "Caso": "CV Extraction",
            "Modelo Tarea": "gpt-4.1-mini",
            "Modelo Profesor": "gpt-4o",
            "Baseline Score": "0,60",
            "Optimizado Score": "0,75",
            "Robustez Score": "0,72",
            "Budget": "25",
            "Notas": "Strategy: greedy",
            "source": "test_project",
        },
    ]


@pytest.fixture
def mock_matplotlib(monkeypatch):
    """Mock matplotlib para evitar crear archivos PNG reales."""
    mock_plt = MagicMock()
    monkeypatch.setattr("matplotlib.pyplot", mock_plt)
    return mock_plt
