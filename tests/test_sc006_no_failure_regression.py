"""
SPEC-104 SC-006: sin fallas, scores y `run.json` de una corrida son iguales a los
de antes del cambio salvo los campos nuevos.

Corrida completa de cada orquestador (`tests/orchestrator_e2e.py`: YAML, CSV y
prompt reales, GEPA y DSPy reales, LLM simulado con respuestas reales de
LiteLLM). El oraculo es el comportamiento previo a SPEC-104 (commit 35c5b1c),
leido del codigo de ese commit y derivado a mano de las respuestas fijas:

- Scores: promedio simple de todos los casos de cada conjunto (sin fallas todo
  caso es evaluado), `effective_delta = optimizado - baseline`, rangos 0 con
  `eval_repeats = 1`; en `dspy_gepa_poc`, en la unidad de `Evaluate` (porcentaje).
- `run.json`: las claves de antes (`experiment_name`, `seed`, `models`,
  `created_at`, `usage`) con los mismos valores, mas las nuevas de FR-008
  (`status`, `abort`, `failures`, `metrics`).
- CSV maestro: mismo esquema de columnas (SPEC-100 FR-007) y mismos valores.
- Llamadas al LLM: sin fallas, exactamente 1 llamada HTTP por caso evaluado
  (sin reintentos, sin fallback de adapters, sin llamadas de atribucion al
  baseline). Unica diferencia esperada en el gasto: `gepa_standalone` ya no
  evalua test una segunda vez para el detalle (FR-014), asi que hace
  `len(test)` llamadas de tarea menos que antes; el resto del bloque `usage`
  sale de las mismas llamadas.
"""

import pytest

from tests.orchestrator_e2e import (
    DSPY_OPT,
    GEPA_OPT,
    REFLECTION_MODEL,
    TASK_MODEL,
    TOKENS_PER_CALL,
    dspy_answer,
    dspy_gold,
    dspy_question,
    run_dspy_gepa_poc,
    run_gepa_standalone,
)

# Claves de run.json antes de SPEC-104 (MetadataManager.create_run en 35c5b1c) y
# las que agrega FR-008.
PRE_SPEC104_RUN_KEYS = {"experiment_name", "seed", "models", "created_at", "usage"}
SPEC104_RUN_KEYS = {"status", "abort", "failures", "metrics"}

# Esquema del CSV maestro (SPEC-100 FR-007): no cambia con SPEC-104.
CSV_COLUMNS = [
    "Run ID",
    "Fecha",
    "Caso",
    "Modelo Tarea",
    "Modelo Profesor",
    "Baseline Score",
    "Optimizado Score",
    "Robustez Score",
    "Run Directory",
    "Reflexion Positiva",
    "Budget",
    "Tokens Task",
    "Tokens Reflection",
    "Costo Real USD",
    "Notas",
]

TRAIN, VAL, TEST = 4, 6, 4
BUDGET = 30

# Precios por millon de tokens de DEFAULT_PRICING (gpt-4.1-mini y gpt-4o).
TASK_PRICE = (0.15, 0.60)
REFLECTION_PRICE = (2.50, 10.00)


def _expected_cost(task_calls, reflection_calls):
    def cost(calls, price):
        return (calls * 10 * price[0] + calls * 5 * price[1]) / 1_000_000

    return cost(task_calls, TASK_PRICE) + cost(reflection_calls, REFLECTION_PRICE)


def _gepa_rule(model, system, user):
    """Baseline: siempre `greeting` (acierta los pares). Optimizado: siempre bien."""
    if model == REFLECTION_MODEL:
        return f"```\n{GEPA_OPT}\n```"
    i = int(user.strip()[1:])
    if GEPA_OPT in system:
        return "farewell" if i % 2 else "greeting"
    return "greeting"


def _dspy_rule(model, system, user):
    """Baseline: siempre `si` (acierta los pares). Optimizado: siempre bien."""
    if model == REFLECTION_MODEL:
        return f"```\n{DSPY_OPT}\n```"
    question = dspy_question(user)
    return dspy_answer(dspy_gold(question) if DSPY_OPT in system else "si")


def _assert_spec104_fields_without_failures(run_json, attempts_task):
    assert set(run_json) == PRE_SPEC104_RUN_KEYS | SPEC104_RUN_KEYS
    assert run_json["status"] == "completed"
    assert run_json["abort"] is None
    failures = run_json["failures"]
    assert failures["counts"] == {}
    assert failures["entrada_dato"] == []
    assert failures["aborted"] is False and failures["abort"] is None
    # Un intento de tarea por caso evaluado: el contador no suma llamadas extra.
    assert failures["attempts"]["task"] == attempts_task
    assert run_json["metrics"] == {
        "baseline": {"n_evaluados": VAL, "n_total": VAL},
        "optimized": {"n_evaluados": VAL, "n_total": VAL},
        "test": {"n_evaluados": TEST, "n_total": TEST},
    }


def _assert_pre_spec104_run_fields(run_json, case_name, task_calls, reflection_calls, max_tokens):
    assert run_json["experiment_name"] == case_name
    assert isinstance(run_json["seed"], int)
    models = run_json["models"]
    assert (models["task"]["model"], models["reflection"]["model"]) == (
        TASK_MODEL,
        REFLECTION_MODEL,
    )
    assert models["task"]["temperature"] == 0.0
    assert (models["task"]["max_tokens"], models["reflection"]["max_tokens"]) == max_tokens
    usage = run_json["usage"]
    assert usage["task"] == {
        "calls": task_calls,
        "prompt_tokens": 10 * task_calls,
        "completion_tokens": 5 * task_calls,
    }
    assert usage["reflection"] == {
        "calls": reflection_calls,
        "prompt_tokens": 10 * reflection_calls,
        "completion_tokens": 5 * reflection_calls,
    }
    assert usage["total_tokens"] == TOKENS_PER_CALL * (task_calls + reflection_calls)
    assert usage["cost_usd"] == pytest.approx(_expected_cost(task_calls, reflection_calls))


def _assert_csv_row(rows, *, case_title, scores, task_calls, reflection_calls, notes):
    assert len(rows) == 1
    row = rows[0]
    assert list(row) == CSV_COLUMNS
    assert (row["Caso"], row["Modelo Tarea"], row["Modelo Profesor"]) == (
        case_title,
        TASK_MODEL,
        REFLECTION_MODEL,
    )
    assert (row["Baseline Score"], row["Optimizado Score"], row["Robustez Score"]) == scores
    assert row["Budget"] == str(BUDGET)
    assert row["Tokens Task"] == str(TOKENS_PER_CALL * task_calls)
    assert row["Tokens Reflection"] == str(TOKENS_PER_CALL * reflection_calls)
    cost = _expected_cost(task_calls, reflection_calls)
    assert row["Costo Real USD"] == f"{cost:.6f}".replace(".", ",")
    assert row["Notas"] == notes


class TestGepaStandaloneWithoutFailures:
    @pytest.fixture
    def outcome(self, tmp_path, monkeypatch):
        out = run_gepa_standalone(
            tmp_path, monkeypatch, _gepa_rule, sizes=(TRAIN, VAL, TEST), max_metric_calls=BUDGET
        )
        assert out.error is None
        return out

    def test_scores_match_the_plain_mean_of_every_case(self, outcome):
        results = outcome.extra["results_json"]
        # Antes de SPEC-104: media de todos los casos del conjunto.
        assert results["baseline_score"] == pytest.approx(3 / 6)
        assert results["optimized_score"] == pytest.approx(1.0)
        assert results["test_score"] == pytest.approx(1.0)
        assert (results["baseline_range"], results["optimized_range"], results["test_range"]) == (
            0.0,
            0.0,
            0.0,
        )
        # Sin fallas el delta pareado es la diferencia de promedios de antes.
        assert results["effective_delta"] == pytest.approx(1.0 - 3 / 6)
        assert results["prompt_changed"] is True
        assert results["final_prompt"] == GEPA_OPT
        assert results["total_metric_calls"] == BUDGET
        # Campos nuevos de 4b, coherentes con los de antes.
        assert set(results) >= {"metrics", "paired_delta"}
        assert results["paired_delta"]["n_pareados"] == VAL

    def test_one_llm_call_per_evaluated_case(self, outcome):
        # Baseline en val + presupuesto de GEPA + optimizado en val + test una vez
        # (antes habia una segunda evaluacion de test, eliminada por FR-014).
        task_calls = VAL + BUDGET + VAL + TEST
        assert len(outcome.calls_to(TASK_MODEL)) == task_calls
        assert len(outcome.calls_to(REFLECTION_MODEL)) == 1

    def test_run_json_keeps_previous_fields_and_adds_the_new_ones(self, outcome):
        task_calls = VAL + BUDGET + VAL + TEST
        _assert_pre_spec104_run_fields(
            outcome.run_json, "saludos", task_calls, 1, max_tokens=(50, 2000)
        )
        _assert_spec104_fields_without_failures(outcome.run_json, attempts_task=task_calls)

    def test_csv_row_keeps_schema_and_values(self, outcome):
        _assert_csv_row(
            outcome.csv_rows,
            case_title="Saludos",
            scores=("0,5000", "1,0000", "1,0000"),
            task_calls=VAL + BUDGET + VAL + TEST,
            reflection_calls=1,
            notes="",
        )

    def test_no_warning_or_error_is_logged(self, outcome):
        assert [r.getMessage() for r in outcome.records] == []


class TestDspyGepaPocWithoutFailures:
    @pytest.fixture
    def outcome(self, tmp_path, monkeypatch):
        out = run_dspy_gepa_poc(
            tmp_path, monkeypatch, _dspy_rule, sizes=(TRAIN, VAL, TEST), max_metric_calls=BUDGET
        )
        assert out.error is None
        return out

    def test_scores_keep_the_evaluate_percentage_unit(self, outcome):
        orchestrator = outcome.orchestrator
        summaries = orchestrator.metric_summaries
        assert summaries["baseline"].score == pytest.approx(3 / 6)
        assert summaries["optimized"].score == pytest.approx(1.0)
        assert summaries["test"].score == pytest.approx(1.0)
        # Antes: `effective_delta = optimized_score - baseline_score` en porcentaje.
        assert orchestrator.effective_delta == pytest.approx(50.0)
        assert orchestrator.prompt_changed is True

    def test_one_llm_call_per_evaluated_case(self, outcome):
        # Sin fallas el fallback de ChatAdapter no actua y no hay llamadas al baseline
        # para atribuir: baseline en val + presupuesto de GEPA + optimizado en val + test.
        assert len(outcome.calls_to(TASK_MODEL)) == VAL + BUDGET + VAL + TEST
        assert len(outcome.calls_to(REFLECTION_MODEL)) == 1

    def test_run_json_keeps_previous_fields_and_adds_the_new_ones(self, outcome):
        task_calls = VAL + BUDGET + VAL + TEST
        _assert_pre_spec104_run_fields(
            outcome.run_json, "sino", task_calls, 1, max_tokens=(1000, 1000)
        )
        _assert_spec104_fields_without_failures(outcome.run_json, attempts_task=task_calls)

    def test_csv_row_keeps_schema_and_values(self, outcome):
        _assert_csv_row(
            outcome.csv_rows,
            case_title="Si o no",
            scores=("50,0000", "100,0000", "100,0000"),
            task_calls=VAL + BUDGET + VAL + TEST,
            reflection_calls=1,
            notes="Strategy: medium, Few-Shot: No, prompt_changed=yes, k=1",
        )

    def test_no_warning_or_error_is_logged(self, outcome):
        assert [r.getMessage() for r in outcome.records] == []
