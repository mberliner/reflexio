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


def test_project_matches_prefix_disambiguates():
    """'gepa' must match only gepa_standalone, not dspy_gepa_poc (substring trap)."""
    assert base.project_matches("gepa_standalone", "gepa")
    assert not base.project_matches("dspy_gepa_poc", "gepa")
    assert base.project_matches("dspy_gepa_poc", "dspy")
    assert not base.project_matches("gepa_standalone", "dspy")


def test_load_metrics_project_filter_gepa_excludes_dspy(tmp_path, monkeypatch):
    """--project gepa must load only gepa_standalone even though 'gepa' is a
    substring of dspy_gepa_poc (regression for prefix-match fix)."""
    dspy = tmp_path / "dspy_gepa_poc" / "results" / "experiments"
    gepa = tmp_path / "gepa_standalone" / "results" / "experiments"
    dspy.mkdir(parents=True)
    gepa.mkdir(parents=True)

    content_template = (
        "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;"
        "Baseline Score;Optimizado Score;Robustez Score;Budget;Notas\n"
        "{run_id};2026-02-01 10:00:00;Test;gpt-4o-mini;gpt-4o;0,50;0,60;0,55;20;Test\n"
    )
    (dspy / "metricas_optimizacion.csv").write_text(
        content_template.format(run_id="dspy_run"), encoding="utf-8"
    )
    (gepa / "metricas_optimizacion.csv").write_text(
        content_template.format(run_id="gepa_run"), encoding="utf-8"
    )

    monkeypatch.setattr(base, "get_shared_root", lambda: tmp_path)

    data = base.load_metrics(csv_path=None, project="gepa", merge=True)

    run_ids = {d["Run ID"] for d in data}
    assert run_ids == {"gepa_run"}


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


def test_get_model_pricing_unknown_warns(caplog):
    """Unknown model logs a warning (silent cheapest-fallback would hide cost)."""
    import logging

    with caplog.at_level(logging.WARNING):
        roi_calculator.get_model_pricing("totally-unknown-model")
    assert any("sin precio configurado" in r.message for r in caplog.records)


def test_lookup_by_case_matches_real_names():
    """Real case names (with suffixes) match the right family by substring."""
    # CV Triage must win over the generic 'Triage' (longest key first).
    assert (
        roi_calculator.lookup_by_case(
            "CV Triage v3 (Backend Senior Python LATAM, CVs extensos)",
            roi_calculator.DEFAULT_TOKEN_ESTIMATES,
            roi_calculator.DEFAULT_TOKEN_ESTIMATES["default"],
        )
        == roi_calculator.DEFAULT_TOKEN_ESTIMATES["CV Triage"]
    )
    # Suffixed extraction case maps to CV Extraction, not default.
    assert (
        roi_calculator.lookup_by_case(
            "CV Extraction v3 (DSPy, condiciones iguales a GEPA)",
            roi_calculator.DEFAULT_TOKEN_ESTIMATES,
            roi_calculator.DEFAULT_TOKEN_ESTIMATES["default"],
        )
        == roi_calculator.DEFAULT_TOKEN_ESTIMATES["CV Extraction"]
    )


def test_lookup_by_case_falls_back_to_default():
    """An unrecognized case name returns the table default."""
    default = roi_calculator.DEFAULT_TOKEN_ESTIMATES["default"]
    assert (
        roi_calculator.lookup_by_case(
            "Algo Totalmente Nuevo", roi_calculator.DEFAULT_TOKEN_ESTIMATES, default
        )
        == default
    )
    # Tables without a 'default' key return the provided fallback.
    assert roi_calculator.lookup_by_case("Nada", roi_calculator.DEFAULT_VAL_SIZES, 5) == 5


def test_model_pricing_cost_per_call():
    """Calculate cost per call correctly."""
    pricing = roi_calculator.ModelPricing("Test", 2.0, 10.0)
    cost = pricing.cost_per_call(input_tokens=1000, output_tokens=500)
    expected = (1000 * 2.0 / 1_000_000) + (500 * 10.0 / 1_000_000)
    assert cost == pytest.approx(expected, rel=1e-6)


def test_parse_real_cost_variants():
    """parse_real_cost: valid European decimal, else None for empty/N/A/zero/missing."""
    assert base.parse_real_cost({"Costo Real USD": "0,012345"}) == pytest.approx(0.012345)
    assert base.parse_real_cost({"Costo Real USD": ""}) is None
    assert base.parse_real_cost({"Costo Real USD": "N/A"}) is None
    assert base.parse_real_cost({"Costo Real USD": "0,000000"}) is None
    assert base.parse_real_cost({}) is None


def test_budget_breakdown_uses_real_cost(tmp_path, capsys):
    """When 'Costo Real USD' is present, it is used verbatim (not the estimate)."""
    csv_path = tmp_path / "metrics.csv"
    csv_path.write_text(
        "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;Baseline Score;"
        "Optimizado Score;Robustez Score;Budget;Tokens Task;Tokens Reflection;"
        "Costo Real USD;Notas\n"
        "r1;2026-02-01 10:00:00;Real Case;gpt-4o-mini;gpt-4o;0,5;0,8;0,75;30;"
        "1000;500;1,234567;n\n",
        encoding="utf-8",
    )
    budget_breakdown.run(csv_path=csv_path)
    output = capsys.readouterr().out
    assert "$1.23" in output  # real cost, formatted as currency
    assert "1 real (medido)" in output


def test_roi_uses_real_cost(tmp_path, capsys):
    """ROI labels the optimization cost as real and averages cost_real_usd."""
    csv_path = tmp_path / "metrics.csv"
    csv_path.write_text(
        "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;Baseline Score;"
        "Optimizado Score;Robustez Score;Budget;Tokens Task;Tokens Reflection;"
        "Costo Real USD;Notas\n"
        "r1;2026-02-01 10:00:00;Real Case;gpt-4o-mini;gpt-4o;0,5;0,9;0,85;30;"
        "1000;500;2,000000;n\n",
        encoding="utf-8",
    )
    roi_calculator.run(csv_path=csv_path)
    output = capsys.readouterr().out
    assert "real, medido" in output


def test_roi_skips_same_model_groups(tmp_path, capsys):
    """Grupos con Modelo Tarea == Profesor se omiten (sin sustitucion de modelo)."""
    csv_path = tmp_path / "metrics.csv"
    csv_path.write_text(
        "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;Baseline Score;"
        "Optimizado Score;Robustez Score;Budget;Tokens Task;Tokens Reflection;"
        "Costo Real USD;Notas\n"
        # Mismo modelo (azure/ en uno solo): debe omitirse pese al prefijo.
        "r1;2026-02-01 10:00:00;Same Model;azure/gpt-4o;gpt-4o;0,5;0,9;0,85;30;;;;n\n"
        # Sustitucion real (barato vs caro): debe reportarse.
        "r2;2026-02-01 11:00:00;Subst Case;gpt-4o-mini;gpt-4o;0,5;0,9;0,85;30;;;;n\n",
        encoding="utf-8",
    )
    roi_calculator.run(csv_path=csv_path)
    output = capsys.readouterr().out
    assert "Omitidos 1 grupo" in output
    assert "Same Model" not in output
    assert "Subst Case" in output


def test_roi_all_same_model_reports_none(tmp_path, capsys):
    """Si todos los grupos son mismo-modelo, no hay ROI que calcular."""
    csv_path = tmp_path / "metrics.csv"
    csv_path.write_text(
        "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;Baseline Score;"
        "Optimizado Score;Robustez Score;Budget;Tokens Task;Tokens Reflection;"
        "Costo Real USD;Notas\n"
        "r1;2026-02-01 10:00:00;Only Same;gpt-4o;gpt-4o;0,5;0,9;0,85;30;;;;n\n",
        encoding="utf-8",
    )
    roi_calculator.run(csv_path=csv_path)
    output = capsys.readouterr().out
    assert "No hay grupos con sustitucion de modelo" in output


def test_cost_from_usage_matches_pricing():
    """Real-usage cost = task pricing on task bucket + reflection pricing on reflection bucket."""
    usage = {
        "task": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
        "reflection": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
    }
    cost = roi_calculator.cost_from_usage(
        usage, task_model="gpt-4o-mini", reflection_model="gpt-4o"
    )
    # gpt-4o-mini: 0.15 in + 0.60 out = 0.75 ; gpt-4o: 2.50 in + 10.00 out = 12.50
    assert cost == pytest.approx(0.75 + 12.50)


def test_cost_from_usage_prices_judge_with_its_own_model():
    """SPEC-106 FR-004 / H1: cada bucket se tarifa con el modelo de su rol."""
    usage = {
        "task": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
        "reflection": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
        "judge": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
    }
    cost = roi_calculator.cost_from_usage(
        usage, task_model="gpt-4o-mini", reflection_model="gpt-4o", judge_model="gpt-4o-mini"
    )
    # task 0.75 + reflection 12.50 + judge (gpt-4o-mini) 0.75
    assert cost == pytest.approx(0.75 + 12.50 + 0.75)


def test_cost_from_usage_judge_defaults_to_reflection_model():
    usage = {"judge": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}}
    cost = roi_calculator.cost_from_usage(usage, "gpt-4o-mini", "gpt-4o")
    assert cost == pytest.approx(12.50)


def test_cost_from_usage_without_judge_equals_previous_total():
    usage = {
        "task": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
        "reflection": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
        "judge": {"prompt_tokens": 0, "completion_tokens": 0},
    }
    assert roi_calculator.cost_from_usage(
        usage, "gpt-4o-mini", "gpt-4o", judge_model="gpt-4o-mini"
    ) == pytest.approx(0.75 + 12.50)


def test_cost_from_usage_handles_missing_buckets():
    """Empty/partial usage must not raise and yields zero cost."""
    assert roi_calculator.cost_from_usage({}, "gpt-4o-mini", "gpt-4o") == 0.0


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


def test_calculate_production_roi_same_model_returns_none():
    """Sin sustitucion de modelo (Tarea == Profesor) la funcion devuelve None."""
    roi = roi_calculator.calculate_production_roi(
        case_name="CV Extraction",
        optimization_cost=0.5,
        expensive_model="azure/gpt-4o",
        cheap_model="gpt-4o",  # mismo modelo, distinto prefijo
        production_calls=10000,
    )
    assert roi is None


def test_calculate_production_roi_uses_family_overhead():
    """El overhead del prompt optimizado es por familia (CV ~1120), no +500 fijo."""
    tokens = roi_calculator.DEFAULT_TOKEN_ESTIMATES["CV Extraction"]
    overhead = roi_calculator.DEFAULT_PROMPT_OVERHEAD["CV Extraction"]
    cheap = roi_calculator.get_model_pricing("gpt-4o-mini")
    roi = roi_calculator.calculate_production_roi(
        case_name="CV Extraction",
        optimization_cost=0.5,
        expensive_model="gpt-4o",
        cheap_model="gpt-4o-mini",
        production_calls=1000,
    )
    expected_prod = 1000 * cheap.cost_per_call(tokens["input"] + overhead, tokens["output"])
    assert roi["cost_with_gepa_production"] == pytest.approx(expected_prod)
    assert overhead != 500  # ya no es la constante antigua


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


def test_run_grouping_by_models(metrics_csv_sample, tmp_path, capsys):
    """Groups runs by (case, task_model, reflection_model)."""
    leaderboard.run(csv_path=metrics_csv_sample, graphs=False, output_dir=tmp_path)

    captured = capsys.readouterr()
    output = captured.out

    assert "Email Urgency" in output
    assert "CV Extraction" in output
    assert "gpt-4o-mini" in output
    assert "gpt-4o" in output


def test_run_same_model_shows_na(tmp_path, capsys):
    """Leaderboard: grupo mismo-modelo con delta positivo muestra N/A, no negativo."""
    csv_path = tmp_path / "metrics.csv"
    csv_path.write_text(
        "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;Baseline Score;"
        "Optimizado Score;Robustez Score;Budget;Tokens Task;Tokens Reflection;"
        "Costo Real USD;Notas\n"
        # Mismo modelo, delta positivo: el ROI no aplica -> N/A en Ahorro/Break-even.
        "r1;2026-02-01 10:00:00;Same Case;azure/gpt-4o;gpt-4o;0,5;0,9;0,9;30;;;;n\n",
        encoding="utf-8",
    )
    leaderboard.run(csv_path=csv_path, graphs=False, output_dir=tmp_path)
    output = capsys.readouterr().out

    assert "Same Case" in output
    assert "N/A" in output
    # No debe aparecer un ahorro negativo (el artefacto que se eliminó).
    assert "$-" not in output


def test_run_statistics_calculation(metrics_csv_sample, tmp_path, capsys):
    """Calculates avg and std correctly."""
    leaderboard.run(csv_path=metrics_csv_sample, graphs=False, output_dir=tmp_path)

    captured = capsys.readouterr()
    output = captured.out

    assert "LEADERBOARD" in output
    assert "Base%" in output
    assert "Opt%" in output
    assert "Rob%" in output


def test_run_output_dir_isolates_generated_files(metrics_csv_sample, tmp_path, monkeypatch):
    """Passing output_dir writes CSV and Markdown there without touching default output."""

    def _forbid_default(*args, **kwargs):
        raise AssertionError("get_output_dir must not be called when output_dir is given")

    monkeypatch.setattr(leaderboard, "get_output_dir", _forbid_default)
    out_dir = tmp_path / "isolated_lb"

    leaderboard.run(csv_path=metrics_csv_sample, graphs=False, output_dir=out_dir)

    assert (out_dir / "leaderboard.csv").exists()
    assert (out_dir / "leaderboard.md").exists()


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


def test_normalize_model_strips_provider_prefixes():
    for prefix in ("azure/", "openai/", "anthropic/"):
        assert roi_calculator.normalize_model(prefix + "Gpt-4o") == "gpt-4o"


def test_normalize_model_resolves_snapshot_to_alias():
    norm = roi_calculator.normalize_model
    assert norm("anthropic/claude-opus-5-5-20260514") == "claude-opus-5-5"
    assert norm("claude-haiku-5-5-20260101") == "claude-haiku-5-5"
    # fuera de la matriz no se toca el sufijo
    assert norm("claude-opus-5-5-preview") == "claude-opus-5-5-preview"
    assert norm("gpt-4o-20250101") == "gpt-4o-20250101"


@pytest.mark.parametrize(
    "alias", sorted(k for k in roi_calculator.DEFAULT_PRICING if k.startswith("claude-"))
)
def test_get_model_pricing_anthropic_alias_and_snapshot(alias, caplog):
    import logging

    expected = roi_calculator.DEFAULT_PRICING[alias]
    with caplog.at_level(logging.WARNING):
        for name in (alias, "anthropic/" + alias, "anthropic/" + alias + "-20260514"):
            assert roi_calculator.get_model_pricing(name) is expected
    assert not any("sin precio configurado" in r.message for r in caplog.records)


# =============================================================================
# SPEC-110: Filtros combinables por caso, estudiante y profesor + --no-merge
# =============================================================================

_SPEC110_CSV_HEADER = (
    "Run ID;Fecha;Caso;Modelo Tarea;Modelo Profesor;"
    "Baseline Score;Optimizado Score;Robustez Score;Budget;Tokens Task;"
    "Tokens Reflection;Costo Real USD;Notas\n"
)


def _write_spec110_csv(csv_path, rows: list[str]) -> None:
    csv_path.write_text(_SPEC110_CSV_HEADER + "".join(rows), encoding="utf-8")


def _csv_row(
    run_id: str,
    fecha: str,
    caso: str,
    student: str,
    teacher: str,
    base_s: str = "0,60",
    opt_s: str = "0,85",
    rob_s: str = "0,82",
    cost: str = "0,50",
) -> str:
    return f"{run_id};{fecha};{caso};{student};{teacher};{base_s};{opt_s};{rob_s};30;;;{cost};\n"


@pytest.fixture
def spec110_rows():
    """Filas cubriendo las 8 combinaciones de (case='CV', student='4.1-mini', teacher='claude')."""
    return [
        {
            "Run ID": "em_4o_ok",
            "Fecha": "2026-02-01 10:00:00",
            "Caso": "Email Urgency",
            "Modelo Tarea": "azure/gpt-4o-mini",
            "Modelo Profesor": "azure/gpt-4o",
            "Baseline Score": "0,70",
            "Optimizado Score": "0,85",
            "Robustez Score": "0,82",
            "Budget": "30",
            "Costo Real USD": "0,50",
            "Notas": "",
            "source": "proj_a",
        },
        {
            "Run ID": "em_4o_anom",
            "Fecha": "2026-02-02 10:00:00",
            "Caso": "Email Urgency",
            "Modelo Tarea": "azure/gpt-4o-mini",
            "Modelo Profesor": "azure/gpt-4o",
            "Baseline Score": "0,80",
            "Optimizado Score": "0,70",
            "Robustez Score": "0,75",
            "Budget": "30",
            "Costo Real USD": "0,50",
            "Notas": "",
            "source": "proj_a",
        },
        {
            "Run ID": "em_41_claude_ok",
            "Fecha": "2026-02-03 10:00:00",
            "Caso": "Email Urgency",
            "Modelo Tarea": "azure/gpt-4.1-mini",
            "Modelo Profesor": "anthropic/claude-sonnet-5-5",
            "Baseline Score": "0,65",
            "Optimizado Score": "0,88",
            "Robustez Score": "0,84",
            "Budget": "30",
            "Costo Real USD": "0,80",
            "Notas": "",
            "source": "proj_a",
        },
        {
            "Run ID": "em_41_claude_anom",
            "Fecha": "2026-02-04 10:00:00",
            "Caso": "Email Urgency",
            "Modelo Tarea": "azure/gpt-4.1-mini",
            "Modelo Profesor": "anthropic/claude-sonnet-5-5",
            "Baseline Score": "0,80",
            "Optimizado Score": "0,72",
            "Robustez Score": "0,75",
            "Budget": "30",
            "Costo Real USD": "0,80",
            "Notas": "",
            "source": "proj_a",
        },
        {
            "Run ID": "cv_41_claude_ok",
            "Fecha": "2026-02-05 10:00:00",
            "Caso": "CV Extraction",
            "Modelo Tarea": "azure/gpt-4.1-mini",
            "Modelo Profesor": "anthropic/claude-sonnet-5-5",
            "Baseline Score": "0,60",
            "Optimizado Score": "0,90",
            "Robustez Score": "0,88",
            "Budget": "30",
            "Costo Real USD": "1,20",
            "Notas": "",
            "source": "proj_a",
        },
        {
            "Run ID": "cv_41_claude_anom",
            "Fecha": "2026-02-06 10:00:00",
            "Caso": "CV Extraction",
            "Modelo Tarea": "azure/gpt-4.1-mini",
            "Modelo Profesor": "anthropic/claude-sonnet-5-5",
            "Baseline Score": "0,85",
            "Optimizado Score": "0,75",
            "Robustez Score": "0,80",
            "Budget": "30",
            "Costo Real USD": "1,20",
            "Notas": "",
            "source": "proj_a",
        },
        {
            "Run ID": "cv_41_gpt4o_ok",
            "Fecha": "2026-02-07 10:00:00",
            "Caso": "CV Extraction",
            "Modelo Tarea": "azure/gpt-4.1-mini",
            "Modelo Profesor": "azure/gpt-4o",
            "Baseline Score": "0,60",
            "Optimizado Score": "0,86",
            "Robustez Score": "0,82",
            "Budget": "30",
            "Costo Real USD": "0,90",
            "Notas": "",
            "source": "proj_a",
        },
        {
            "Run ID": "cv_41_gpt4o_anom",
            "Fecha": "2026-02-08 10:00:00",
            "Caso": "CV Extraction",
            "Modelo Tarea": "azure/gpt-4.1-mini",
            "Modelo Profesor": "azure/gpt-4o",
            "Baseline Score": "0,82",
            "Optimizado Score": "0,74",
            "Robustez Score": "0,78",
            "Budget": "30",
            "Costo Real USD": "0,90",
            "Notas": "",
            "source": "proj_a",
        },
        {
            "Run ID": "cv_4o_claude_ok",
            "Fecha": "2026-02-09 10:00:00",
            "Caso": "CV Extraction",
            "Modelo Tarea": "azure/gpt-4o-mini",
            "Modelo Profesor": "anthropic/claude-sonnet-5-5",
            "Baseline Score": "0,58",
            "Optimizado Score": "0,84",
            "Robustez Score": "0,80",
            "Budget": "30",
            "Costo Real USD": "1,00",
            "Notas": "",
            "source": "proj_a",
        },
        {
            "Run ID": "cv_4o_claude_anom",
            "Fecha": "2026-02-10 10:00:00",
            "Caso": "CV Extraction",
            "Modelo Tarea": "azure/gpt-4o-mini",
            "Modelo Profesor": "anthropic/claude-sonnet-5-5",
            "Baseline Score": "0,84",
            "Optimizado Score": "0,71",
            "Robustez Score": "0,76",
            "Budget": "30",
            "Costo Real USD": "1,00",
            "Notas": "",
            "source": "proj_a",
        },
    ]


@pytest.fixture
def spec110_csv(tmp_path, spec110_rows):
    """CSV escrito desde spec110_rows para pruebas de integracion de modulos."""
    csv_path = tmp_path / "spec110_metrics.csv"
    lines = [
        (
            f"{r['Run ID']};{r['Fecha']};{r['Caso']};{r['Modelo Tarea']};"
            f"{r['Modelo Profesor']};{r['Baseline Score']};{r['Optimizado Score']};"
            f"{r['Robustez Score']};{r['Budget']};;;{r['Costo Real USD']};{r['Notas']}\n"
        )
        for r in spec110_rows
    ]
    _write_spec110_csv(csv_path, lines)
    return csv_path


def test_filter_metrics_exported_in_shared_analysis():
    """FR-004: filter_metrics se exporta en shared.analysis."""
    import shared.analysis as analysis_pkg

    assert hasattr(analysis_pkg, "filter_metrics")
    assert "filter_metrics" in analysis_pkg.__all__
    assert analysis_pkg.filter_metrics is base.filter_metrics


_EIGHT_COMBINATIONS = [
    (
        None,
        None,
        None,
        {
            "em_4o_ok",
            "em_4o_anom",
            "em_41_claude_ok",
            "em_41_claude_anom",
            "cv_41_claude_ok",
            "cv_41_claude_anom",
            "cv_41_gpt4o_ok",
            "cv_41_gpt4o_anom",
            "cv_4o_claude_ok",
            "cv_4o_claude_anom",
        },
        None,
    ),
    (
        "CV",
        None,
        None,
        {
            "cv_41_claude_ok",
            "cv_41_claude_anom",
            "cv_41_gpt4o_ok",
            "cv_41_gpt4o_anom",
            "cv_4o_claude_ok",
            "cv_4o_claude_anom",
        },
        "Filtros: caso=CV",
    ),
    (
        None,
        "4.1-mini",
        None,
        {
            "em_41_claude_ok",
            "em_41_claude_anom",
            "cv_41_claude_ok",
            "cv_41_claude_anom",
            "cv_41_gpt4o_ok",
            "cv_41_gpt4o_anom",
        },
        "Filtros: estudiante=4.1-mini",
    ),
    (
        None,
        None,
        "claude",
        {
            "em_41_claude_ok",
            "em_41_claude_anom",
            "cv_41_claude_ok",
            "cv_41_claude_anom",
            "cv_4o_claude_ok",
            "cv_4o_claude_anom",
        },
        "Filtros: profesor=claude",
    ),
    (
        "CV",
        "4.1-mini",
        None,
        {
            "cv_41_claude_ok",
            "cv_41_claude_anom",
            "cv_41_gpt4o_ok",
            "cv_41_gpt4o_anom",
        },
        "Filtros: caso=CV, estudiante=4.1-mini",
    ),
    (
        "CV",
        None,
        "claude",
        {
            "cv_41_claude_ok",
            "cv_41_claude_anom",
            "cv_4o_claude_ok",
            "cv_4o_claude_anom",
        },
        "Filtros: caso=CV, profesor=claude",
    ),
    (
        None,
        "4.1-mini",
        "claude",
        {
            "em_41_claude_ok",
            "em_41_claude_anom",
            "cv_41_claude_ok",
            "cv_41_claude_anom",
        },
        "Filtros: estudiante=4.1-mini, profesor=claude",
    ),
    (
        "CV",
        "4.1-mini",
        "claude",
        {
            "cv_41_claude_ok",
            "cv_41_claude_anom",
        },
        "Filtros: caso=CV, estudiante=4.1-mini, profesor=claude",
    ),
]


@pytest.mark.parametrize(
    ("case_f", "student_f", "teacher_f", "expected_ids", "_expected_md_line"),
    _EIGHT_COMBINATIONS,
)
def test_filter_metrics_all_eight_combinations(
    spec110_rows, case_f, student_f, teacher_f, expected_ids, _expected_md_line
):
    """FR-002 / SC-002: las 8 combinaciones de presencia/ausencia aplican AND logico."""
    result = base.filter_metrics(
        spec110_rows,
        case_filter=case_f,
        student_filter=student_f,
        teacher_filter=teacher_f,
    )
    assert {r["Run ID"] for r in result} == expected_ids
    # Preserva orden original
    expected_order = [r["Run ID"] for r in spec110_rows if r["Run ID"] in expected_ids]
    assert [r["Run ID"] for r in result] == expected_order


def test_filter_metrics_returns_new_list_and_does_not_mutate(spec110_rows):
    """FR-004: devuelve lista nueva tambien sin filtros activos y no muta data ni sus filas."""
    import copy

    snapshot = copy.deepcopy(spec110_rows)

    result_none = base.filter_metrics(spec110_rows)
    assert result_none is not spec110_rows
    assert result_none == spec110_rows

    result_blank = base.filter_metrics(
        spec110_rows, case_filter="   ", student_filter="", teacher_filter="\t\n"
    )
    assert result_blank is not spec110_rows
    assert result_blank == spec110_rows

    result_none.pop()
    assert spec110_rows == snapshot


def test_filter_metrics_progressive_case_insensitive_strip_and_limits():
    """FR-003: busqueda progresiva case-insensitive, strip, subcadenas y limite gpt-5/gpt-5.4."""
    rows = [
        {
            "Run ID": "r1",
            "Caso": "Triage",
            "Modelo Tarea": "azure/gpt-4o",
            "Modelo Profesor": "azure/gpt-5",
        },
        {
            "Run ID": "r2",
            "Caso": "Email Urgency",
            "Modelo Tarea": "azure/gpt-4o-mini",
            "Modelo Profesor": "azure/gpt-5.4",
        },
        {
            "Run ID": "r3",
            "Caso": "CV Extraction",
            "Modelo Tarea": "azure/gpt-4.1-mini",
            "Modelo Profesor": "anthropic/claude-sonnet-5-5",
        },
        {
            "Run ID": "r4",
            "Caso": "CV Profile",
            "Modelo Tarea": "azure/gpt-4.1",
            "Modelo Profesor": "anthropic/claude-opus-5-5",
        },
    ]

    # Busqueda progresiva sobre estudiante: gpt -> gpt-4 -> gpt-4.1 -> gpt-4.1-mini
    assert {r["Run ID"] for r in base.filter_metrics(rows, student_filter="gpt")} == {
        "r1",
        "r2",
        "r3",
        "r4",
    }
    assert {r["Run ID"] for r in base.filter_metrics(rows, student_filter="GPT-4.1")} == {
        "r3",
        "r4",
    }
    assert {r["Run ID"] for r in base.filter_metrics(rows, student_filter="  gpt-4.1-mini  ")} == {
        "r3"
    }

    # Nota de subcadena: gpt-4o coincide con gpt-4o y gpt-4o-mini; claude con toda la familia
    assert {r["Run ID"] for r in base.filter_metrics(rows, student_filter="gpt-4o")} == {
        "r1",
        "r2",
    }
    assert {r["Run ID"] for r in base.filter_metrics(rows, teacher_filter="CLAUDE")} == {
        "r3",
        "r4",
    }

    # Limite conocido: gpt-5 coincide con gpt-5 y gpt-5.4; gpt-5.4 aisla solo gpt-5.4
    assert {r["Run ID"] for r in base.filter_metrics(rows, teacher_filter="gpt-5")} == {
        "r1",
        "r2",
    }
    assert {r["Run ID"] for r in base.filter_metrics(rows, teacher_filter="gpt-5.4")} == {"r2"}

    # Cambio aceptado sobre --case: espacios en blanco equivale a sin filtro (incluye 'Triage')
    assert {r["Run ID"] for r in base.filter_metrics(rows, case_filter=" ")} == {
        "r1",
        "r2",
        "r3",
        "r4",
    }


def test_filter_metrics_missing_empty_and_none_columns():
    """FR-003: columnas ausentes, None o vacias no fallan y se excluyen si el filtro esta activo."""
    rows = [
        {"Run ID": "ok", "Caso": "CV", "Modelo Tarea": "gpt-4.1-mini", "Modelo Profesor": "gpt-4o"},
        {"Run ID": "no_teacher_key", "Caso": "CV", "Modelo Tarea": "gpt-4.1-mini"},
        {
            "Run ID": "none_teacher",
            "Caso": "CV",
            "Modelo Tarea": "gpt-4.1-mini",
            "Modelo Profesor": None,
        },
        {
            "Run ID": "empty_teacher",
            "Caso": "CV",
            "Modelo Tarea": "gpt-4.1-mini",
            "Modelo Profesor": "",
        },
        {"Run ID": "none_case", "Caso": None, "Modelo Tarea": None, "Modelo Profesor": "gpt-4o"},
    ]

    # Sin filtro de profesor se conservan las filas sin Modelo Profesor
    assert {r["Run ID"] for r in base.filter_metrics(rows)} == {
        "ok",
        "no_teacher_key",
        "none_teacher",
        "empty_teacher",
        "none_case",
    }
    # Con filtro de profesor quedan excluidas sin error
    assert {r["Run ID"] for r in base.filter_metrics(rows, teacher_filter="gpt-4o")} == {
        "ok",
        "none_case",
    }
    # Con filtro de caso y estudiante tolera None/ausente sin error
    assert {
        r["Run ID"] for r in base.filter_metrics(rows, case_filter="cv", student_filter="4.1-mini")
    } == {"ok", "no_teacher_key", "none_teacher", "empty_teacher"}


@pytest.mark.parametrize(
    ("case_f", "student_f", "teacher_f", "expected_ids", "expected_md_line"),
    _EIGHT_COMBINATIONS,
)
def test_leaderboard_all_eight_filter_combinations(
    spec110_csv,
    spec110_rows,
    tmp_path,
    case_f,
    student_f,
    teacher_f,
    expected_ids,
    expected_md_line,
):
    """FR-007 / SC-002 / SC-003: leaderboard coherente en CSV, MD, stats, anomalias y Filtros."""
    import csv as csv_mod

    out_dir = tmp_path / "lb_out"
    leaderboard.run(
        csv_path=spec110_csv,
        case_filter=case_f,
        student_filter=student_f,
        teacher_filter=teacher_f,
        graphs=False,
        output_dir=out_dir,
    )

    csv_file = out_dir / "leaderboard.csv"
    md_file = out_dir / "leaderboard.md"
    assert csv_file.exists()
    assert md_file.exists()

    # Grupos esperados segun expected_ids
    expected_rows = [r for r in spec110_rows if r["Run ID"] in expected_ids]
    expected_groups = {(r["Caso"], r["Modelo Tarea"], r["Modelo Profesor"]) for r in expected_rows}
    expected_cases = {r["Caso"] for r in expected_rows}
    expected_anoms = {r["Run ID"] for r in expected_rows if r["Run ID"].endswith("_anom")}
    excluded_anoms = {
        r["Run ID"]
        for r in spec110_rows
        if r["Run ID"].endswith("_anom") and r["Run ID"] not in expected_ids
    }

    # Verificar leaderboard.csv (mismo formato, solo grupos esperados)
    with open(csv_file, encoding="utf-8") as f:
        parsed_csv = list(csv_mod.DictReader(f, delimiter=";"))
    actual_groups = {(r["Caso"], r["Tarea"], r["Profesor"]) for r in parsed_csv}
    assert actual_groups == expected_groups

    # Verificar leaderboard.md: linea Filtros, secciones y anomalias por Run ID
    md_text = md_file.read_text(encoding="utf-8")
    md_lines = md_text.splitlines()
    gen_idx = next(i for i, line in enumerate(md_lines) if line.startswith("Generado:"))

    if expected_md_line is None:
        assert "Filtros:" not in md_text
    else:
        assert md_lines[gen_idx + 1] == expected_md_line

    # Estadisticas por caso solo contiene casos esperados
    stats_section = md_text.split("## Estadisticas por Caso")[1].split("## Anomalias")[0]
    for c in expected_cases:
        assert c in stats_section
    for c in {"Email Urgency", "CV Extraction"} - expected_cases:
        assert c not in stats_section

    # Anomalias solo contiene Run IDs anomalos del subconjunto filtrado
    anom_section = md_text.split("## Anomalias")[1]
    for run_id in expected_anoms:
        assert run_id in anom_section
    for run_id in excluded_anoms:
        assert run_id not in anom_section


def test_leaderboard_no_matches_does_not_create_or_overwrite_files(spec110_csv, tmp_path, capsys):
    """FR-006 / SC-003: sin coincidencias imprime mensaje y no crea ni sobrescribe archivos."""
    # Caso 1: directorio vacio -> no crea CSV, MD, -o ni PNGs
    empty_dir = tmp_path / "empty_out"
    custom_md = tmp_path / "custom_report.md"
    leaderboard.run(
        csv_path=spec110_csv,
        case_filter="Email",
        teacher_filter="inexistente",
        output=custom_md,
        graphs=True,
        output_dir=empty_dir,
    )
    assert "No hay datos para analizar." in capsys.readouterr().out
    assert not empty_dir.exists()
    assert not custom_md.exists()

    # Caso 2: archivos preexistentes -> no los sobrescribe
    existing_dir = tmp_path / "existing_out"
    existing_dir.mkdir()
    existing_csv = existing_dir / "leaderboard.csv"
    existing_md = existing_dir / "leaderboard.md"
    existing_csv.write_text("KEEP_CSV", encoding="utf-8")
    existing_md.write_text("KEEP_MD", encoding="utf-8")

    leaderboard.run(
        csv_path=spec110_csv,
        case_filter="Email",
        student_filter="gpt-4o-mini",
        teacher_filter="claude",
        graphs=True,
        output_dir=existing_dir,
    )
    assert "No hay datos para analizar." in capsys.readouterr().out
    assert existing_csv.read_text(encoding="utf-8") == "KEEP_CSV"
    assert existing_md.read_text(encoding="utf-8") == "KEEP_MD"
    assert not (existing_dir / "performance_improvement.png").exists()


def test_leaderboard_whitespace_filters_omits_filtros_line(spec110_csv, tmp_path):
    """FR-002 / FR-007: filtros vacios o solo espacios no generan linea Filtros:."""
    out_dir = tmp_path / "ws_out"
    leaderboard.run(
        csv_path=spec110_csv,
        case_filter="   ",
        student_filter="",
        teacher_filter="\t",
        output_dir=out_dir,
    )
    md_text = (out_dir / "leaderboard.md").read_text(encoding="utf-8")
    assert "Filtros:" not in md_text


def test_leaderboard_gpt5_vs_gpt54_scenario(tmp_path):
    """FR-003 / Escenario: gpt-5 devuelve ambos profesores; gpt-5.4 aisla azure/gpt-5.4."""
    csv_path = tmp_path / "gpt5.csv"
    _write_spec110_csv(
        csv_path,
        [
            _csv_row(
                "r1", "2026-02-01 10:00:00", "CV Extraction", "azure/gpt-4.1-mini", "azure/gpt-5"
            ),
            _csv_row(
                "r2",
                "2026-02-02 10:00:00",
                "CV Extraction",
                "azure/gpt-4.1-mini",
                "azure/gpt-5.4",
                opt_s="0,90",
                rob_s="0,88",
                cost="0,60",
            ),
        ],
    )

    out_both = tmp_path / "out_both"
    leaderboard.run(csv_path=csv_path, teacher_filter="gpt-5", output_dir=out_both)
    csv_both = (out_both / "leaderboard.csv").read_text(encoding="utf-8")
    assert "azure/gpt-5;" in csv_both
    assert "azure/gpt-5.4;" in csv_both

    out_54 = tmp_path / "out_54"
    leaderboard.run(csv_path=csv_path, teacher_filter="gpt-5.4", output_dir=out_54)
    csv_54 = (out_54 / "leaderboard.csv").read_text(encoding="utf-8")
    assert "azure/gpt-5;" not in csv_54
    assert "azure/gpt-5.4;" in csv_54


def test_roi_filters_by_student_and_teacher(spec110_csv, capsys):
    """FR-005 / SC-006: roi filtra por estudiante y profesor con AND y muestra solo ese grupo."""
    roi_calculator.run(
        csv_path=spec110_csv,
        student_filter="4.1-mini",
        teacher_filter="gpt-4o",
    )
    out = capsys.readouterr().out
    assert "CASO: CV Extraction" in out
    assert "Modelo Tarea: azure/gpt-4.1-mini" in out
    assert "Modelo Profesor: azure/gpt-4o" in out
    assert "Email Urgency" not in out
    assert "claude-sonnet-5-5" not in out


def test_roi_raw_column_excludes_missing_teacher_default(tmp_path, capsys):
    """FR-003: roi evalua filtro sobre columna cruda, no sobre el default 'gpt-4o' de agrupacion."""
    csv_path = tmp_path / "no_teacher.csv"
    csv_path.write_text(
        "Run ID;Fecha;Caso;Modelo Tarea;Baseline Score;Optimizado Score;Robustez Score;Budget\n"
        "r1;2026-02-01 10:00:00;Email Urgency;azure/gpt-4o-mini;0,60;0,85;0,80;30\n",
        encoding="utf-8",
    )
    roi_calculator.run(csv_path=csv_path, teacher_filter="gpt-4o")
    assert "No hay datos para analizar." in capsys.readouterr().out

    # Sin filtro de profesor, la fila se conserva
    roi_calculator.run(csv_path=csv_path)
    assert "CASO: Email Urgency" in capsys.readouterr().out


def test_roi_empty_after_filter_prints_no_data(spec110_csv, capsys):
    """FR-006: roi sin coincidencias imprime mensaje y retorna sin excepcion."""
    roi_calculator.run(csv_path=spec110_csv, case_filter="Email", teacher_filter="inexistente")
    assert "No hay datos para analizar." in capsys.readouterr().out


def test_roi_filtered_same_model_preserves_omitted_message(tmp_path, capsys):
    """FR-006 / Escenario: filtro que deja solo Tarea == Profesor conserva [NOTA] vigente."""
    csv_path = tmp_path / "same_model.csv"
    _write_spec110_csv(
        csv_path,
        [
            _csv_row("r1", "2026-02-01 10:00:00", "CV Extraction", "azure/gpt-4o", "azure/gpt-4o"),
            _csv_row(
                "r2",
                "2026-02-02 10:00:00",
                "Email Urgency",
                "azure/gpt-4.1-mini",
                "azure/gpt-4o",
                cost="0,20",
            ),
        ],
    )
    roi_calculator.run(
        csv_path=csv_path,
        student_filter="gpt-4o",
        teacher_filter="gpt-4o",
    )
    out = capsys.readouterr().out
    assert "[NOTA] Omitidos 1 grupo(s)" in out
    assert "No hay grupos con sustitucion de modelo (Tarea distinto de Profesor)" in out
    assert "Email Urgency" not in out


def test_stats_filters_by_model_and_recalculates_batch_boundaries(tmp_path, capsys):
    """FR-002 / FR-005 / SC-006: stats filtra por modelo y calcula limites sobre lo filtrado."""
    csv_path = tmp_path / "stats_filter.csv"
    _write_spec110_csv(
        csv_path,
        [
            # Grupo excluido en enero que desplazaria los limites si no se filtrara antes
            _csv_row(
                "r0",
                "2026-01-01 00:00:00",
                "Email Urgency",
                "azure/gpt-4o-mini",
                "azure/gpt-4o",
                base_s="0,50",
                opt_s="0,60",
                rob_s="0,55",
                cost="0,10",
            ),
            # Grupo incluido en marzo (2026-03-01..03 -> corte medio en 2026-03-02)
            _csv_row(
                "r1",
                "2026-03-01 00:00:00",
                "CV Extraction",
                "azure/gpt-4.1-mini",
                "anthropic/claude-sonnet-5-5",
                opt_s="0,80",
                rob_s="0,78",
            ),
            _csv_row(
                "r2",
                "2026-03-03 00:00:00",
                "CV Extraction",
                "azure/gpt-4.1-mini",
                "anthropic/claude-sonnet-5-5",
                opt_s="0,90",
                rob_s="0,88",
            ),
        ],
    )
    stats_evolution.run(
        csv_path=csv_path,
        student_filter="4.1-mini",
        teacher_filter="claude",
        num_batches=2,
    )
    out = capsys.readouterr().out
    assert "CV Extraction" in out
    assert "azure/gpt-4.1-mini/anthropic/claude-sonnet-5-5" in out
    assert "Email Urgency" not in out
    assert "gpt-4o-mini" not in out
    # Limite automatico calculado solo sobre las filas filtradas (2026-03-01..03 -> 2026-03-02)
    assert "2026-03-02 00:00" in out


def test_stats_empty_after_filter_prints_no_data(spec110_csv, capsys):
    """FR-006: stats sin coincidencias imprime mensaje y retorna sin excepcion."""
    stats_evolution.run(csv_path=spec110_csv, student_filter="modelo-inexistente")
    assert "No hay datos para analizar." in capsys.readouterr().out


def test_budget_filters_by_model(spec110_csv, capsys):
    """FR-005 / SC-006: budget filtra por modelo y muestra solo combinaciones coincidentes."""
    budget_breakdown.run(
        csv_path=spec110_csv,
        case_filter="CV",
        student_filter="4.1-mini",
        teacher_filter="claude",
    )
    out = capsys.readouterr().out
    assert "CASO: CV Extraction" in out
    assert "azure/gpt-4.1-mini + anthropic/claude-sonnet-5-5" in out
    assert "Total Experimentos: 2" in out
    assert "$2.40" in out
    assert "Email Urgency" not in out
    assert "azure/gpt-4o" not in out


def test_budget_raw_column_excludes_missing_teacher_default(tmp_path, capsys):
    """FR-003: budget evalua filtro sobre columna cruda, no sobre default 'gpt-4o'."""
    csv_path = tmp_path / "no_teacher_budget.csv"
    csv_path.write_text(
        "Run ID;Fecha;Caso;Modelo Tarea;Baseline Score;Optimizado Score;Robustez Score;Budget\n"
        "r1;2026-02-01 10:00:00;Email Urgency;azure/gpt-4o-mini;0,60;0,85;0,80;30\n",
        encoding="utf-8",
    )
    budget_breakdown.run(csv_path=csv_path, teacher_filter="gpt-4o")
    assert "No hay datos para analizar." in capsys.readouterr().out

    budget_breakdown.run(csv_path=csv_path)
    assert "CASO: Email Urgency" in capsys.readouterr().out


def test_budget_empty_after_filter_prints_no_data(spec110_csv, capsys):
    """FR-006: budget sin coincidencias imprime mensaje y retorna sin excepcion."""
    budget_breakdown.run(csv_path=spec110_csv, teacher_filter="modelo-inexistente")
    assert "No hay datos para analizar." in capsys.readouterr().out


@pytest.mark.parametrize("subcmd", ["leaderboard", "lb", "roi", "stats", "budget"])
def test_cli_model_flags_and_aliases(subcmd):
    """FR-001 / SC-001 / SC-004: subcomandos aceptan --student/--task y --teacher/--reflection."""
    from shared.analysis import cli

    parser = cli.build_parser()

    args_default = parser.parse_args([subcmd])
    assert args_default.student is None
    assert args_default.teacher is None
    assert args_default.case is None
    assert args_default.no_merge is False

    args_primary = parser.parse_args(
        [subcmd, "--case", "CV", "--student", "4.1-mini", "--teacher", "claude", "--no-merge"]
    )
    assert args_primary.case == "CV"
    assert args_primary.student == "4.1-mini"
    assert args_primary.teacher == "claude"
    assert args_primary.no_merge is True

    args_alias = parser.parse_args(
        [subcmd, "--case", "CV", "--task", "4.1-mini", "--reflection", "claude"]
    )
    assert args_alias.student == args_primary.student
    assert args_alias.teacher == args_primary.teacher

    # Si se pasan flag y alias en la misma invocacion, prevalece el ultimo (estandar argparse)
    args_override = parser.parse_args(
        [subcmd, "--student", "first", "--task", "second", "--reflection", "r1", "--teacher", "r2"]
    )
    assert args_override.student == "second"
    assert args_override.teacher == "r2"


@pytest.mark.parametrize(
    ("subcmd", "ambiguous_flag"),
    [
        ("leaderboard", "--t"),
        ("roi", "--t"),
        ("stats", "--t"),
        ("budget", "--t"),
        ("budget", "--s"),
        ("leaderboard", "--c"),
        ("roi", "--c"),
        ("stats", "--c"),
        ("budget", "--c"),
    ],
)
def test_cli_ambiguous_abbreviations_rejected(subcmd, ambiguous_flag, capsys):
    """FR-001: allow_abbrev por defecto rechaza abreviaturas ambiguas (--t, --s en budget, --c)."""
    from shared.analysis import cli

    parser = cli.build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args([subcmd, ambiguous_flag, "valor"])
    assert exc_info.value.code == 2
    assert "ambiguous" in capsys.readouterr().err.lower()


@pytest.mark.parametrize(
    ("subcmd", "module_obj"),
    [
        ("leaderboard", leaderboard),
        ("roi", roi_calculator),
        ("stats", stats_evolution),
        ("budget", budget_breakdown),
    ],
)
def test_cli_cmd_propagates_filters_and_merge(subcmd, module_obj, monkeypatch):
    """FR-001 / FR-009 / SC-006: cada cmd_* propaga student_filter, teacher_filter y merge."""
    from shared.analysis import cli

    captured: list[dict] = []

    def fake_run(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(module_obj, "run", fake_run)

    cli.main([subcmd, "--case", "CV", "--student", "4.1-mini", "--teacher", "claude"])
    cli.main([subcmd, "--task", "gpt-4o", "--reflection", "gpt-5", "--no-merge"])

    assert len(captured) == 2
    assert captured[0]["case_filter"] == "CV"
    assert captured[0]["student_filter"] == "4.1-mini"
    assert captured[0]["teacher_filter"] == "claude"
    assert captured[0]["merge"] is True

    assert captured[1]["student_filter"] == "gpt-4o"
    assert captured[1]["teacher_filter"] == "gpt-5"
    assert captured[1]["merge"] is False


@pytest.mark.parametrize("subcmd", ["leaderboard", "roi", "stats", "budget"])
def test_cli_no_merge_with_multiple_csvs(subcmd, tmp_path, monkeypatch, capsys):
    """FR-009 / SC-007: --no-merge con 2 CSVs sale con Error y codigo 1; sin el los combina."""
    from shared.analysis import cli

    p1 = tmp_path / "proj_one" / "results" / "experiments"
    p2 = tmp_path / "proj_two" / "results" / "experiments"
    lb_out = tmp_path / "lb_isolated"
    p1.mkdir(parents=True)
    p2.mkdir(parents=True)
    lb_out.mkdir(parents=True)

    _write_spec110_csv(
        p1 / "metricas_optimizacion.csv",
        [
            _csv_row(
                "r1",
                "2026-02-01 10:00:00",
                "Email Urgency",
                "azure/gpt-4o-mini",
                "azure/gpt-4o",
                opt_s="0,80",
                rob_s="0,78",
                cost="0,30",
            )
        ],
    )
    _write_spec110_csv(
        p2 / "metricas_optimizacion.csv",
        [
            _csv_row(
                "r2",
                "2026-02-05 10:00:00",
                "CV Extraction",
                "azure/gpt-4.1-mini",
                "anthropic/claude-sonnet-5-5",
                cost="0,70",
            )
        ],
    )

    monkeypatch.setattr(base, "get_shared_root", lambda: tmp_path)
    monkeypatch.setattr(leaderboard, "get_output_dir", lambda *a, **k: lb_out)

    # Con --no-merge -> Error y codigo de salida 1
    with pytest.raises(SystemExit) as exc_info:
        cli.main([subcmd, "--no-merge"])
    assert exc_info.value.code == 1
    assert "Error: Multiples CSVs encontrados" in capsys.readouterr().out

    # Sin --no-merge -> combina ambos CSVs y muestra los dos casos
    cli.main([subcmd])
    merged_out = capsys.readouterr().out
    assert "Email Urgency" in merged_out
    assert "CV Extraction" in merged_out


def test_cli_help_documents_model_filters_and_progressive_search():
    """FR-008: la ayuda del CLI documenta flags, alias, AND, busqueda progresiva y limites."""
    from shared.analysis import cli

    parser = cli.build_parser()
    main_help = parser.format_help()
    for expected in ("--student", "--task", "--teacher", "--reflection", "AND", "gpt-4o", "gpt-5"):
        assert expected in main_help
    assert "progresiva" in main_help.lower()


def test_project_filter_combines_with_row_filters_and(tmp_path, monkeypatch, capsys):
    """FR-002: los filtros de fila se combinan en AND con --project."""
    dspy_dir = tmp_path / "dspy_gepa_poc" / "results" / "experiments"
    gepa_dir = tmp_path / "gepa_standalone" / "results" / "experiments"
    dspy_dir.mkdir(parents=True)
    gepa_dir.mkdir(parents=True)

    _write_spec110_csv(
        dspy_dir / "metricas_optimizacion.csv",
        [
            _csv_row(
                "d1",
                "2026-02-01 10:00:00",
                "CV Extraction",
                "azure/gpt-4.1-mini",
                "anthropic/claude-sonnet-5-5",
                cost="1,10",
            ),
            _csv_row(
                "d2",
                "2026-02-02 10:00:00",
                "CV Extraction",
                "azure/gpt-4o-mini",
                "azure/gpt-4o",
                cost="0,40",
            ),
        ],
    )
    _write_spec110_csv(
        gepa_dir / "metricas_optimizacion.csv",
        [
            _csv_row(
                "g1",
                "2026-02-03 10:00:00",
                "CV Extraction",
                "azure/gpt-4.1-mini",
                "anthropic/claude-sonnet-5-5",
                opt_s="0,88",
                rob_s="0,85",
                cost="2,20",
            ),
        ],
    )
    monkeypatch.setattr(base, "get_shared_root", lambda: tmp_path)

    budget_breakdown.run(project="dspy", student_filter="4.1-mini", teacher_filter="claude")
    out = capsys.readouterr().out
    assert "dspy_gepa_poc" in out
    assert "gepa_standalone" not in out
    assert "Total Experimentos: 1" in out
    assert "$1.10" in out


def test_stats_filters_with_fixed_cuts(tmp_path, capsys):
    """FR-002: con --cuts los limites son fijos aun con filtros activos."""
    csv_path = tmp_path / "stats_cuts.csv"
    _write_spec110_csv(
        csv_path,
        [
            _csv_row(
                "r1",
                "2026-03-01 10:00:00",
                "CV Extraction",
                "azure/gpt-4.1-mini",
                "anthropic/claude-sonnet-5-5",
                opt_s="0,80",
                rob_s="0,78",
            ),
            _csv_row(
                "r2",
                "2026-03-10 10:00:00",
                "CV Extraction",
                "azure/gpt-4.1-mini",
                "anthropic/claude-sonnet-5-5",
                opt_s="0,90",
                rob_s="0,88",
            ),
            _csv_row(
                "r3",
                "2026-01-05 10:00:00",
                "Email Urgency",
                "azure/gpt-4o-mini",
                "azure/gpt-4o",
                base_s="0,50",
                opt_s="0,60",
                rob_s="0,55",
                cost="0,10",
            ),
        ],
    )
    stats_evolution.run(
        csv_path=csv_path,
        student_filter="4.1-mini",
        teacher_filter="claude",
        cuts="2026-03-05",
    )
    out = capsys.readouterr().out
    assert "2026-03-05 00:00" in out
    assert "CV Extraction" in out
    assert "Email Urgency" not in out


def test_leaderboard_custom_output_redirects_md_with_filters(spec110_csv, tmp_path):
    """FR-007: -o/--output redirige el Markdown con linea Filtros:, CSV va en output_dir."""
    out_dir = tmp_path / "out_dir"
    custom_md = tmp_path / "custom.md"
    leaderboard.run(
        csv_path=spec110_csv,
        case_filter="CV",
        student_filter="4.1-mini",
        teacher_filter="claude",
        output=custom_md,
        output_dir=out_dir,
    )
    assert (out_dir / "leaderboard.csv").exists()
    assert not (out_dir / "leaderboard.md").exists()
    assert custom_md.exists()
    assert "Filtros: caso=CV, estudiante=4.1-mini, profesor=claude" in custom_md.read_text(
        encoding="utf-8"
    )
