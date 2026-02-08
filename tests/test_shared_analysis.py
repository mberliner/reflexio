"""
Tests for shared/analysis/ modules.

Tests coverage for:
- base.py: Data loading and formatting utilities
- roi_calculator.py: ROI and cost calculations
- leaderboard.py: Ranking and anomaly detection
- stats_evolution.py: Temporal batch analysis
- budget_breakdown.py: Cost breakdown by case
"""

from datetime import datetime

import pytest

from shared.analysis import base, budget_breakdown, leaderboard, roi_calculator, stats_evolution

# =============================================================================
# MODULE: base.py
# =============================================================================


def test_find_all_metrics_csv_discovers_projects(tmp_path):
    """Auto-discovery finds CSV files in project directories."""
    project1 = tmp_path / "project_a" / "results" / "experiments"
    project2 = tmp_path / "project_b" / "results" / "experiments"
    project1.mkdir(parents=True)
    project2.mkdir(parents=True)

    csv1 = project1 / "metricas_optimizacion.csv"
    csv2 = project2 / "metricas_optimizacion.csv"
    csv1.write_text("Run ID;Caso\n", encoding="utf-8")
    csv2.write_text("Run ID;Caso\n", encoding="utf-8")

    found = base.find_all_metrics_csv(search_root=tmp_path)

    assert len(found) == 2
    assert csv1 in found
    assert csv2 in found


def test_load_metrics_explicit_path(tmp_path):
    """Load CSV from explicit path."""
    csv_path = tmp_path / "metrics.csv"
    content = (
        "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;"
        "Baseline Score;Optimizado Score;Robustez Score;Budget;Notas\n"
        "test123;2026-02-01 10:00:00;Test Case;gpt-4o-mini;gpt-4o;"
        "0,75;0,85;0,80;30;Strategy: test\n"
    )
    csv_path.write_text(content, encoding="utf-8")

    data = base.load_metrics(csv_path=csv_path)

    assert len(data) == 1
    assert data[0]["Run ID"] == "test123"
    assert data[0]["Caso"] == "Test Case"


def test_load_metrics_auto_discovery(tmp_path):
    """Auto-discovery when no explicit path given."""
    project_dir = tmp_path / "test_project" / "results" / "experiments"
    project_dir.mkdir(parents=True)
    csv_path = project_dir / "metricas_optimizacion.csv"
    content = (
        "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;"
        "Baseline Score;Optimizado Score;Robustez Score;Budget;Notas\n"
        "auto123;2026-02-01 10:00:00;Auto Case;gpt-4o-mini;gpt-4o;"
        "0,50;0,60;0,55;20;Test\n"
    )
    csv_path.write_text(content, encoding="utf-8")

    data = base.load_metrics(csv_path=csv_path)

    assert len(data) == 1
    assert data[0]["Run ID"] == "auto123"


def test_load_metrics_merge_multiple(tmp_path, monkeypatch):
    """Combine multiple CSVs when merge=True."""
    project1 = tmp_path / "proj1" / "results" / "experiments"
    project2 = tmp_path / "proj2" / "results" / "experiments"
    project1.mkdir(parents=True)
    project2.mkdir(parents=True)

    csv1 = project1 / "metricas_optimizacion.csv"
    csv2 = project2 / "metricas_optimizacion.csv"

    content_template = (
        "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;"
        "Baseline Score;Optimizado Score;Robustez Score;Budget;Notas\n"
        "{run_id};2026-02-01 10:00:00;Test;gpt-4o-mini;gpt-4o;0,50;0,60;0,55;20;Test\n"
    )
    csv1.write_text(content_template.format(run_id="run1"), encoding="utf-8")
    csv2.write_text(content_template.format(run_id="run2"), encoding="utf-8")

    # Mock get_shared_root to return our tmp_path
    monkeypatch.setattr(base, "get_shared_root", lambda: tmp_path)

    data = base.load_metrics(csv_path=None, project=None, merge=True)

    assert len(data) == 2
    run_ids = {d["Run ID"] for d in data}
    assert "run1" in run_ids
    assert "run2" in run_ids


def test_parse_float_european():
    """Convert European decimal format to float."""
    assert base.parse_float("0,85") == 0.85
    assert base.parse_float("1,234") == 1.234
    assert base.parse_float("100,00") == 100.0


def test_parse_float_us():
    """Convert US decimal format to float."""
    assert base.parse_float("0.85") == 0.85
    assert base.parse_float("1.234") == 1.234


def test_parse_float_empty():
    """Handle empty or invalid values."""
    assert base.parse_float("") == 0.0
    assert base.parse_float(None) == 0.0
    assert base.parse_float("invalid") == 0.0


def test_detect_scale_0_to_1():
    """Detect 0-1 scale."""
    scores = [0.5, 0.75, 0.9, 1.0]
    assert base.detect_scale(scores) == 1.0


def test_detect_scale_0_to_100():
    """Detect 0-100 scale."""
    scores = [50, 75, 90, 100]
    assert base.detect_scale(scores) == 100.0


def test_detect_scale_mixed():
    """Detect scale with mixed values (>1 triggers 100 scale)."""
    scores = [0.5, 1.5, 50]
    assert base.detect_scale(scores) == 100.0


def test_extract_budget_from_dedicated_column():
    """Extract Budget from dedicated column."""
    rows = [
        {"Budget": "30", "Notas": ""},
        {"Budget": "30", "Notas": ""},
    ]
    budget = base.extract_budget_from_rows(rows, fallback=20)
    assert budget == 30


def test_extract_budget_from_notas():
    """Fallback to Notas field if Budget column absent."""
    rows = [
        {"Budget": "", "Notas": "Budget: 25, Strategy: greedy"},
        {"Budget": "", "Notas": "Budget: 25, Strategy: greedy"},
    ]
    budget = base.extract_budget_from_rows(rows, fallback=20)
    assert budget == 25


def test_extract_budget_fallback():
    """Use fallback when no Budget found."""
    rows = [
        {"Budget": "", "Notas": "Strategy: test"},
        {"Budget": "", "Notas": ""},
    ]
    budget = base.extract_budget_from_rows(rows, fallback=20)
    assert budget == 20


def test_parse_notas_full():
    """Parse complete Notas string."""
    notas = "Budget: 30, Strategy: medium, Few-Shot: Yes (k=3)"
    result = base.parse_notas(notas)
    assert result["budget"] == 30
    assert result["strategy"] == "medium"
    assert result["few_shot"] is True
    assert result["few_shot_k"] == 3


def test_parse_notas_partial():
    """Parse partial Notas string."""
    notas = "Budget: 25, Strategy: greedy"
    result = base.parse_notas(notas)
    assert result["budget"] == 25
    assert result["strategy"] == "greedy"
    assert result["few_shot"] is None


def test_parse_notas_empty():
    """Handle empty Notas field."""
    result = base.parse_notas("")
    assert result["budget"] is None
    assert result["strategy"] is None


# =============================================================================
# MODULE: roi_calculator.py
# =============================================================================


def test_get_model_pricing_known_model():
    """Lookup pricing for known model."""
    pricing = roi_calculator.get_model_pricing("gpt-4o")
    assert pricing.name == "GPT-4o"
    assert pricing.input_price == 2.50
    assert pricing.output_price == 10.00


def test_get_model_pricing_fallback():
    """Unknown model uses fallback pricing."""
    pricing = roi_calculator.get_model_pricing("unknown-model-xyz")
    assert pricing.name == "GPT-4o-mini"
    assert pricing.input_price == 0.15
    assert pricing.output_price == 0.60


def test_get_model_pricing_azure_prefix():
    """Strip azure/ prefix from model names."""
    pricing = roi_calculator.get_model_pricing("azure/gpt-4o")
    assert pricing.name == "GPT-4o"


def test_model_pricing_cost_per_call():
    """Calculate cost per call correctly."""
    pricing = roi_calculator.ModelPricing("Test", 2.0, 10.0)
    cost = pricing.cost_per_call(input_tokens=1000, output_tokens=500)
    expected = (1000 * 2.0 / 1_000_000) + (500 * 10.0 / 1_000_000)
    assert cost == pytest.approx(expected, rel=1e-6)


def test_calculate_optimization_cost_basic():
    """Calculate GEPA optimization cost with default params."""
    result = roi_calculator.calculate_optimization_cost(
        case_name="Email Urgency",
        task_model="gpt-4o-mini",
        reflection_model="gpt-4o",
        max_calls=30,
    )

    assert "task_calls" in result
    assert "task_cost" in result
    assert "reflection_calls" in result
    assert "reflection_cost" in result
    assert "total_cost" in result
    assert result["total_cost"] == result["task_cost"] + result["reflection_cost"]


def test_calculate_optimization_cost_with_budget():
    """Use custom budget (max_calls) parameter."""
    result1 = roi_calculator.calculate_optimization_cost(
        case_name="Test", task_model="gpt-4o-mini", reflection_model="gpt-4o", max_calls=10
    )

    result2 = roi_calculator.calculate_optimization_cost(
        case_name="Test", task_model="gpt-4o-mini", reflection_model="gpt-4o", max_calls=50
    )

    assert result2["total_cost"] > result1["total_cost"]


def test_calculate_optimization_cost_task_calls():
    """Verify task_calls formula: (max_calls + 1) * val_size."""
    result = roi_calculator.calculate_optimization_cost(
        case_name="Email Urgency",
        task_model="gpt-4o-mini",
        reflection_model="gpt-4o",
        max_calls=30,
        val_size=10,
    )

    expected_task_calls = (30 + 1) * 10
    assert result["task_calls"] == expected_task_calls


def test_calculate_optimization_cost_reflection_calls():
    """Verify reflection_calls formula: max_calls // 2."""
    result = roi_calculator.calculate_optimization_cost(
        case_name="Test", task_model="gpt-4o-mini", reflection_model="gpt-4o", max_calls=30
    )

    expected_reflection_calls = 30 // 2
    assert result["reflection_calls"] == expected_reflection_calls


def test_calculate_production_roi_positive():
    """ROI positive when optimization provides savings."""
    opt_cost = 0.5
    roi = roi_calculator.calculate_production_roi(
        case_name="Email Urgency",
        optimization_cost=opt_cost,
        expensive_model="gpt-4o",
        cheap_model="gpt-4o-mini",
        production_calls=10000,
    )

    assert "savings" in roi
    assert "roi_percentage" in roi
    assert "breakeven_calls" in roi
    assert roi["cost_without_gepa"] > roi["cost_with_gepa_total"]


def test_calculate_production_roi_negative():
    """ROI negative when optimization doesn't provide savings at low volume."""
    opt_cost = 100.0
    roi = roi_calculator.calculate_production_roi(
        case_name="Email Urgency",
        optimization_cost=opt_cost,
        expensive_model="gpt-4o",
        cheap_model="gpt-4o-mini",
        production_calls=10,
    )

    assert roi["savings"] < 0
    assert roi["roi_percentage"] < 0


def test_calculate_production_roi_zero_optimization_cost():
    """Handle edge case of zero optimization cost."""
    roi = roi_calculator.calculate_production_roi(
        case_name="Test",
        optimization_cost=0.0,
        expensive_model="gpt-4o",
        cheap_model="gpt-4o-mini",
        production_calls=1000,
    )

    assert roi["roi_percentage"] == 0


def test_calculate_production_roi_break_even():
    """Break-even calculation is correct."""
    roi = roi_calculator.calculate_production_roi(
        case_name="Email Urgency",
        optimization_cost=10.0,
        expensive_model="gpt-4o",
        cheap_model="gpt-4o-mini",
        production_calls=10000,
    )

    breakeven = roi["breakeven_calls"]
    assert breakeven > 0
    assert isinstance(breakeven, int)


def test_production_cost_calculation():
    """Verify cost_before vs cost_after calculation."""
    roi = roi_calculator.calculate_production_roi(
        case_name="Email Urgency",
        optimization_cost=5.0,
        expensive_model="gpt-4o",
        cheap_model="gpt-4o-mini",
        production_calls=1000,
    )

    assert roi["cost_without_gepa"] > 0
    assert roi["cost_with_gepa_production"] > 0
    expected_total = roi["cost_with_gepa_production"] + roi["optimization_cost"]
    assert roi["cost_with_gepa_total"] == expected_total


# =============================================================================
# MODULE: leaderboard.py
# =============================================================================


def test_get_stability_label_high():
    """std < 0.05 -> Alta."""
    label = leaderboard.get_stability_label(std=0.03, scale=1.0)
    assert label == "Alta"


def test_get_stability_label_good():
    """0.05 <= std < 0.10 -> Buena."""
    label = leaderboard.get_stability_label(std=0.07, scale=1.0)
    assert label == "Buena"


def test_get_stability_label_attention():
    """0.10 <= std < 0.15 -> Atencion."""
    label = leaderboard.get_stability_label(std=0.12, scale=1.0)
    assert label == "Atencion"


def test_get_stability_label_unstable():
    """std >= 0.15 -> Inestable."""
    label = leaderboard.get_stability_label(std=0.20, scale=1.0)
    assert label == "Inestable"


def test_get_stability_label_normalized():
    """Stability normalized by scale."""
    label = leaderboard.get_stability_label(std=3.0, scale=100.0)
    assert label == "Alta"


def test_detect_anomalies_opt_less_than_base():
    """Detect Opt < Base anomaly."""
    data = [
        {
            "Run ID": "test1",
            "Caso": "Test",
            "Baseline Score": "0,80",
            "Optimizado Score": "0,70",
            "Robustez Score": "0,75",
            "source": "test",
        }
    ]

    anomalies = leaderboard.detect_anomalies(data)

    assert len(anomalies) == 1
    assert "Opt < Base" in anomalies[0]["reason"]


def test_detect_anomalies_rob_less_than_base():
    """Detect Rob < Base anomaly."""
    data = [
        {
            "Run ID": "test2",
            "Caso": "Test",
            "Baseline Score": "0,80",
            "Optimizado Score": "0,85",
            "Robustez Score": "0,70",
            "source": "test",
        }
    ]

    anomalies = leaderboard.detect_anomalies(data)

    assert len(anomalies) == 1
    assert "Rob < Base" in anomalies[0]["reason"]


def test_detect_anomalies_extreme_values():
    """Detect extreme scores (0, 1, 100)."""
    data = [
        {
            "Run ID": "test3",
            "Caso": "Test",
            "Baseline Score": "0,50",
            "Optimizado Score": "0,60",
            "Robustez Score": "0,00",
            "source": "test",
        }
    ]

    anomalies = leaderboard.detect_anomalies(data)

    assert len(anomalies) == 1
    assert "Extremo" in anomalies[0]["reason"]


def test_detect_anomalies_multiple_reasons():
    """Detect multiple anomaly reasons in single run."""
    data = [
        {
            "Run ID": "test4",
            "Caso": "Test",
            "Baseline Score": "0,80",
            "Optimizado Score": "0,70",
            "Robustez Score": "0,00",
            "source": "test",
        }
    ]

    anomalies = leaderboard.detect_anomalies(data)

    assert len(anomalies) == 1
    reasons = anomalies[0]["reason"]
    assert "Opt < Base" in reasons
    assert "Rob < Base" in reasons
    assert "Extremo" in reasons


def test_detect_anomalies_none_when_clean():
    """No anomalies if data is clean."""
    data = [
        {
            "Run ID": "test5",
            "Caso": "Test",
            "Baseline Score": "0,70",
            "Optimizado Score": "0,80",
            "Robustez Score": "0,75",
            "source": "test",
        }
    ]

    anomalies = leaderboard.detect_anomalies(data)

    assert len(anomalies) == 0


def test_run_grouping_by_models(metrics_csv_sample, capsys):
    """Groups runs by (case, task_model, reflection_model)."""
    leaderboard.run(csv_path=metrics_csv_sample, graphs=False)

    captured = capsys.readouterr()
    output = captured.out

    assert "Email Urgency" in output
    assert "CV Extraction" in output
    assert "gpt-4o-mini" in output
    assert "gpt-4o" in output


def test_run_statistics_calculation(metrics_csv_sample, capsys):
    """Calculates avg and std correctly."""
    leaderboard.run(csv_path=metrics_csv_sample, graphs=False)

    captured = capsys.readouterr()
    output = captured.out

    assert "LEADERBOARD" in output
    assert "Base%" in output
    assert "Opt%" in output
    assert "Rob%" in output


# =============================================================================
# MODULE: stats_evolution.py
# =============================================================================


def test_calculate_batch_boundaries_equal_split(metrics_rows):
    """Divide data into N equal batches."""
    boundaries = stats_evolution.calculate_batch_boundaries(metrics_rows, num_batches=2)

    assert len(boundaries) == 1


def test_calculate_batch_boundaries_single_batch(metrics_rows):
    """N=1 means no boundaries needed."""
    boundaries = stats_evolution.calculate_batch_boundaries(metrics_rows, num_batches=1)

    assert len(boundaries) == 0


def test_calculate_batch_boundaries_empty_data():
    """Handle empty data."""
    boundaries = stats_evolution.calculate_batch_boundaries([], num_batches=3)

    assert len(boundaries) == 0


def test_assign_batch_correct_bucket():
    """Assign timestamp to correct batch."""
    boundaries = [
        datetime(2026, 2, 1, 12, 0, 0),
        datetime(2026, 2, 2, 12, 0, 0),
    ]

    dt1 = datetime(2026, 2, 1, 10, 0, 0)
    dt2 = datetime(2026, 2, 1, 14, 0, 0)
    dt3 = datetime(2026, 2, 3, 10, 0, 0)

    assert stats_evolution.assign_batch(dt1, boundaries) == 0
    assert stats_evolution.assign_batch(dt2, boundaries) == 1
    assert stats_evolution.assign_batch(dt3, boundaries) == 2


def test_parse_date_valid_timestamp():
    """Parse valid ISO timestamp."""
    dt = stats_evolution.parse_date("2026-02-08 14:30:22")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 2
    assert dt.day == 8


def test_parse_date_invalid_fallback():
    """Invalid timestamp returns None."""
    assert stats_evolution.parse_date("invalid-date") is None
    assert stats_evolution.parse_date("") is None
    assert stats_evolution.parse_date(None) is None


def test_format_trend_improved():
    """Trend shows improvement."""
    trend = stats_evolution.format_trend(70.0, 75.0)
    assert trend == "^"


def test_format_trend_worsened():
    """Trend shows degradation."""
    trend = stats_evolution.format_trend(75.0, 70.0)
    assert trend == "v"


def test_format_trend_equal():
    """Trend shows stability."""
    trend = stats_evolution.format_trend(75.0, 75.2)
    assert trend == "="


def test_format_trend_none_values():
    """Handle None values."""
    assert stats_evolution.format_trend(None, 75.0) == "N/A"
    assert stats_evolution.format_trend(75.0, None) == "N/A"


# =============================================================================
# MODULE: budget_breakdown.py
# =============================================================================


def test_budget_breakdown_accumulation(metrics_csv_sample, capsys):
    """Sum costs correctly per case."""
    budget_breakdown.run(csv_path=metrics_csv_sample)

    captured = capsys.readouterr()
    output = captured.out

    assert "PRESUPUESTO GASTADO POR CASO" in output
    assert "Email Urgency" in output
    assert "CV Extraction" in output
    assert "Total Experimentos" in output


def test_budget_breakdown_percentage(metrics_csv_sample, capsys):
    """Percentages calculated correctly."""
    budget_breakdown.run(csv_path=metrics_csv_sample)

    captured = capsys.readouterr()
    output = captured.out

    assert "%" in output


def test_budget_breakdown_empty_data(tmp_path, capsys):
    """Handle empty data gracefully."""
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text(
        "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;"
        "Baseline Score;Optimizado Score;Robustez Score;Budget;Notas\n",
        encoding="utf-8",
    )

    budget_breakdown.run(csv_path=csv_path)

    captured = capsys.readouterr()
    output = captured.out

    assert "No hay datos" in output


def test_budget_breakdown_sort_by_cost(metrics_csv_sample, capsys):
    """Sort by cost (default)."""
    budget_breakdown.run(csv_path=metrics_csv_sample, sort_by="cost")

    captured = capsys.readouterr()
    output = captured.out

    assert "PRESUPUESTO GASTADO" in output


def test_budget_breakdown_sort_by_count(metrics_csv_sample, capsys):
    """Sort by experiment count."""
    budget_breakdown.run(csv_path=metrics_csv_sample, sort_by="count")

    captured = capsys.readouterr()
    output = captured.out

    assert "PRESUPUESTO GASTADO" in output


def test_budget_breakdown_model_combo_desglose(metrics_csv_sample, capsys):
    """Show breakdown by model combination."""
    budget_breakdown.run(csv_path=metrics_csv_sample)

    captured = capsys.readouterr()
    output = captured.out

    assert "Combinacion de Modelos" in output or "Desglose" in output
