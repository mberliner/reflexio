"""
SPEC-104 subfase 4b: orquestador de `gepa_standalone` (`UniversalOptimizer`).

Verifica el comportamiento que pide la spec, con el pipeline real del orquestador y
respuestas reales de LiteLLM (`make_completion_response` de `tests/conftest.py`;
las fallas son las excepciones reales de LiteLLM):

- FR-003 / SC-002 / SC-007: baseline y optimizado se reportan cada uno sobre sus
  propios casos evaluados, con `n_evaluados/n_total`, junto al delta pareado; con
  `n_evaluados == 0` el reporte dice "sin casos evaluados" y no 0.0.
- FR-006 / SC-004: el corte es por estado, consultado tras cada paso y antes de
  `save_results()`; el error nombra la clase, el rol y el conteo.
- FR-014: el detalle de test reutiliza la evaluacion ya calculada.
- FR-005 / FR-013: el cableado del callback de GEPA da a la reflexion el numero de
  iteracion como `case_id`.
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import litellm
import pytest

from gepa_standalone.adapters.simple_classifier_adapter import SimpleClassifierAdapter
from gepa_standalone.core.llm_factory import ReflectionLM
from gepa_standalone.universal_optimizer import UniversalOptimizer
from shared.llm import FailureClass, LLMFailure, RunAborted, get_failure_tracker
from tests.conftest import make_completion_response

BASE = "BASE"
OPT = "OPT"
TASK_MODEL = "azure/gpt-4.1-mini"
REFLECTION_MODEL = "azure/gpt-4.1"
CLASSES = ["greeting", "farewell"]


@pytest.fixture(autouse=True)
def _env(mock_env, monkeypatch):
    monkeypatch.setenv("LLM_MODEL_REFLECTION", REFLECTION_MODEL)
    monkeypatch.setattr("shared.llm.call.time.sleep", lambda s: None)
    monkeypatch.setattr("gepa_standalone.data.data_loader.print_dataset_info", lambda *_: None)


def _rate_limit():
    return litellm.RateLimitError(message="slow down", llm_provider="azure", model=TASK_MODEL)


def _auth_error():
    return litellm.AuthenticationError(message="bad key", llm_provider="azure", model=TASK_MODEL)


class Completion:
    """`litellm.completion` por (modelo, system, user): respuesta real o excepcion."""

    def __init__(self, monkeypatch, rule):
        self.rule = rule
        self.calls: list[tuple[str, str, str]] = []
        monkeypatch.setattr("litellm.completion", self)

    def __call__(self, *args, **kwargs):
        messages = kwargs["messages"]
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        call = (kwargs["model"], system, messages[-1]["content"])
        self.calls.append(call)
        out = self.rule(*call)
        if isinstance(out, Exception):
            raise out
        return make_completion_response(out)

    def task_calls(self, system=None):
        return [c for c in self.calls if c[0] == TASK_MODEL and system in (None, c[1])]


def _split(prefix, n):
    return [
        {"case_id": f"{prefix}{i}", "text": f"{prefix}{i}", "label": "greeting"} for i in range(n)
    ]


def _optimizer(monkeypatch, *, eval_repeats=1, skip_perfect_score=True, max_metric_calls=40):
    opt = UniversalOptimizer()
    opt.config = {
        "case": {"name": "caso", "title": "Caso"},
        "data": {"csv_filename": "x.csv"},
        "adapter": {"type": "classifier", "valid_classes": CLASSES},
        "optimization": {
            "max_metric_calls": max_metric_calls,
            "eval_repeats": eval_repeats,
            "skip_perfect_score": skip_perfect_score,
            "display_progress_bar": False,
        },
    }
    opt.build_llm_configs()
    opt.adapter = SimpleClassifierAdapter(valid_classes=CLASSES)
    opt.adapter.set_baseline(BASE)
    opt.train_data, opt.val_data, opt.test_data = _split("t", 4), _split("v", 10), _split("x", 5)
    return opt


def _fake_optimize(monkeypatch, *, before_return=None):
    seen = {}

    def fake(**kwargs):
        seen.update(kwargs)
        if before_return is not None:
            before_return()
        return SimpleNamespace(
            best_candidate={"system_prompt": OPT},
            candidates=[{"system_prompt": BASE}, {"system_prompt": OPT}],
            val_aggregate_scores=[0.5, 0.9],
            best_idx=1,
            total_metric_calls=7,
        )

    monkeypatch.setattr("gepa_standalone.universal_optimizer.optimize", fake)
    return seen


def _pipeline(opt):
    opt.execute_gepa_pipeline({"system_prompt": BASE})


# ==================== FR-003: metricas sobre casos evaluados y delta pareado ====================


class TestReportedMetrics:
    @staticmethod
    def _asymmetric_rule(model, system, user):
        # Baseline: v0 y v1 mal (score 0), v2 NE. Optimizado: todo bien salvo v3 NE.
        if system == BASE:
            if user == "v2":
                return _rate_limit()
            return "farewell" if user in ("v0", "v1") else "greeting"
        if user == "v3":
            return _rate_limit()
        return "greeting"

    def test_each_metric_uses_own_evaluated_cases_and_delta_is_paired(self, monkeypatch, capsys):
        Completion(monkeypatch, self._asymmetric_rule)
        _fake_optimize(monkeypatch)
        opt = _optimizer(monkeypatch)

        _pipeline(opt)

        baseline, optimized = opt.metric_summaries["baseline"], opt.metric_summaries["optimized"]
        assert (baseline.n_evaluados, baseline.n_total) == (9, 10)
        assert (optimized.n_evaluados, optimized.n_total) == (9, 10)
        # 7 aciertos de 9 evaluados (un NE no suma ni resta; no es 7/10).
        assert baseline.score == pytest.approx(7 / 9)
        assert optimized.score == pytest.approx(1.0)
        # Pareado sobre los 8 casos evaluados con ambos prompts (todos menos v2 y v3):
        # baseline 6/8, optimizado 8/8. La diferencia de promedios daria 2/9.
        delta = opt.paired_delta
        assert delta.n_pareados == 8
        assert delta.baseline_score == pytest.approx(0.75)
        assert delta.optimized_score == pytest.approx(1.0)
        assert delta.delta == pytest.approx(0.25)
        assert delta.delta != pytest.approx(optimized.score - baseline.score)
        assert opt.results["effective_delta"] == pytest.approx(0.25)
        assert opt.results["baseline_score"] == pytest.approx(7 / 9)

        assert "9/10" in capsys.readouterr().out

    def test_sc002_ten_percent_infra_matches_the_healthy_run_on_evaluated_cases(
        self, monkeypatch, capsys
    ):
        def healthy(model, system, user):
            return "farewell" if user in ("v0", "v1") else "greeting"

        def with_infra(model, system, user):
            return _rate_limit() if user == "v7" else healthy(model, system, user)

        Completion(monkeypatch, healthy)
        _fake_optimize(monkeypatch)
        reference = _optimizer(monkeypatch)
        _pipeline(reference)
        capsys.readouterr()
        get_failure_tracker().reset()

        Completion(monkeypatch, with_infra)
        degraded = _optimizer(monkeypatch)
        _pipeline(degraded)

        ref, got = reference.metric_summaries["baseline"], degraded.metric_summaries["baseline"]
        assert (got.n_evaluados, got.n_total) == (9, 10)
        same_cases = {cid: score for cid, score in ref.per_case.items() if cid != "v7"}
        assert got.per_case == same_cases
        assert got.score == pytest.approx(sum(same_cases.values()) / 9)
        assert "9/10" in capsys.readouterr().out

    def test_summary_block_shows_both_scores_and_paired_delta(self, monkeypatch, capsys):
        Completion(monkeypatch, self._asymmetric_rule)
        _fake_optimize(monkeypatch)
        opt = _optimizer(monkeypatch)
        _pipeline(opt)
        capsys.readouterr()

        from shared.display import print_summary

        print_summary(
            metrics=opt._summary_metrics, config=opt._summary_config, delta=opt._summary_delta
        )
        out = capsys.readouterr().out
        assert "Baseline" in out and "9/10 casos evaluados" in out
        assert "Improvement (pareado)" in out
        assert "+25.00% sobre 8 casos pareados" in out

    def test_eval_repeats_counts_case_evaluated_if_any_repeat_was(self, monkeypatch):
        seen_v2 = []

        def rule(model, system, user):
            if system == BASE and user == "v2":
                seen_v2.append(user)
                # 1 intento + 3 reintentos de infraestructura: la primera repeticion queda NE.
                if len(seen_v2) <= 4:
                    return _rate_limit()
            return "greeting"

        Completion(monkeypatch, rule)
        _fake_optimize(monkeypatch)
        opt = _optimizer(monkeypatch, eval_repeats=2)

        _pipeline(opt)

        baseline = opt.metric_summaries["baseline"]
        # v2 fue NE en la primera repeticion y evaluado en la segunda: cuenta evaluado.
        assert (baseline.n_evaluados, baseline.n_total) == (10, 10)
        assert baseline.ne_repeats == 1
        assert baseline.repeats == 2

    def test_no_evaluated_cases_is_reported_as_such_not_as_zero(self, monkeypatch, capsys):
        def rule(model, system, user):
            return _rate_limit() if user.startswith("v") else "greeting"

        Completion(monkeypatch, rule)
        _fake_optimize(monkeypatch)
        # Pocos casos: bajo el minimo de intentos del contador no hay aborto por umbral.
        opt = _optimizer(monkeypatch)
        opt.val_data = _split("v", 5)

        _pipeline(opt)  # sin ZeroDivisionError

        for name in ("baseline", "optimized"):
            summary = opt.metric_summaries[name]
            assert (summary.n_evaluados, summary.n_total) == (0, 5)
            assert summary.score is None
        assert opt.paired_delta.n_pareados == 0
        assert opt.paired_delta.delta is None
        assert opt.results["baseline_score"] is None
        assert opt.results["optimized_score"] is None
        assert opt.results["effective_delta"] is None
        out = capsys.readouterr().out
        assert "sin casos evaluados" in out
        assert "0/5" in out

    def test_csv_row_gets_na_for_a_metric_without_evaluated_cases(self, monkeypatch):
        def rule(model, system, user):
            return _rate_limit() if user.startswith("v") else "greeting"

        Completion(monkeypatch, rule)
        _fake_optimize(monkeypatch)
        opt = _optimizer(monkeypatch)
        opt.val_data = _split("v", 5)
        _pipeline(opt)
        opt.metadata_mgr = MagicMock()
        opt.seed = 0
        logged = {}
        monkeypatch.setattr(
            "gepa_standalone.universal_optimizer.save_run_details", lambda **kw: "run_dir"
        )
        monkeypatch.setattr(
            "gepa_standalone.universal_optimizer.log_experiment_result",
            lambda **kw: logged.update(kw),
        )
        monkeypatch.setattr(
            "gepa_standalone.universal_optimizer.collect_model_info", lambda *a, **k: {}
        )
        monkeypatch.setattr("gepa_standalone.universal_optimizer.get_paths", MagicMock())

        opt.save_results()

        assert logged["baseline_score"] == "N/A"
        assert logged["optimized_score"] == "N/A"
        assert logged["robustness_score"] == pytest.approx(1.0)


# ==================== FR-014: sin segunda evaluacion de test ====================


class TestNoSecondTestEvaluation:
    def test_test_set_is_evaluated_once_and_detail_reuses_it(self, monkeypatch, capsys):
        completion = Completion(monkeypatch, lambda model, system, user: "greeting")
        _fake_optimize(monkeypatch)
        opt = _optimizer(monkeypatch)
        evaluated_batches = []
        original = opt.adapter.evaluate

        def spy(batch, candidate, capture_traces=False):
            evaluated_batches.append(batch)
            return original(batch, candidate, capture_traces)

        monkeypatch.setattr(opt.adapter, "evaluate", spy)

        _pipeline(opt)

        test_evals = [b for b in evaluated_batches if b is opt.test_data]
        assert len(test_evals) == 1
        # Una llamada por caso de test (k=1), no dos.
        assert sorted(u for _, _, u in completion.task_calls(OPT) if u.startswith("x")) == [
            f"x{i}" for i in range(5)
        ]
        assert "DETALLE DE RESULTADOS" in capsys.readouterr().out

    def test_with_repeats_test_set_is_evaluated_exactly_k_times(self, monkeypatch):
        completion = Completion(monkeypatch, lambda model, system, user: "greeting")
        _fake_optimize(monkeypatch)
        opt = _optimizer(monkeypatch, eval_repeats=3)

        _pipeline(opt)

        per_case = [u for _, _, u in completion.task_calls(OPT) if u == "x0"]
        assert len(per_case) == 3


# ==================== FR-006 / SC-004: aborto por estado ====================


class TestAbortByState:
    def test_configuracion_stops_the_run_naming_class_and_role(self, monkeypatch):
        completion = Completion(monkeypatch, lambda model, system, user: _auth_error())
        seen = _fake_optimize(monkeypatch)
        opt = _optimizer(monkeypatch)

        with pytest.raises(RunAborted) as exc_info:
            _pipeline(opt)

        message = str(exc_info.value)
        assert "configuracion" in message and "rol=task" in message and "conteo=" in message
        # Una sola llamada HTTP: el estado abortado corta las siguientes.
        assert len(completion.calls) == 1
        assert seen == {}  # GEPA nunca arranco

    def test_state_is_checked_after_optimization_before_evaluating_again(self, monkeypatch):
        completion = Completion(monkeypatch, lambda model, system, user: "greeting")

        def abort_silently():
            # GEPA atrapa las excepciones de la reflexion: el estado queda abortado.
            get_failure_tracker().abort(
                LLMFailure(FailureClass.formato, "reflection", "sin_bloque_instruccion"),
                "umbral superado",
            )

        _fake_optimize(monkeypatch, before_return=abort_silently)
        opt = _optimizer(monkeypatch)

        with pytest.raises(RunAborted, match="rol=reflection"):
            _pipeline(opt)

        # Solo el baseline sobre val (10 casos); ni val optimizado ni test.
        assert len(completion.task_calls()) == 10
        assert not hasattr(opt, "metric_summaries")

    def test_eval_repeated_stops_between_repeats_on_threshold_abort(self, monkeypatch):
        """H-01: si la 1a repeticion deja el contador abortado, no se ejecuta la 2da."""
        get_failure_tracker().configure(min_attempts={"task": 4})
        completion = Completion(
            monkeypatch,
            lambda model, system, user: _rate_limit() if user == "v3" else "greeting",
        )
        opt = _optimizer(monkeypatch, eval_repeats=2)
        opt.val_data = _split("v", 4)

        with pytest.raises(RunAborted, match="infraestructura"):
            opt._eval_repeated(opt.val_data, {"system_prompt": BASE})

        # v0..v2 sanos (3) + v3 con 1+3 reintentos (4) = 7; 0 de la 2da repeticion.
        assert len(completion.calls) == 7
        assert get_failure_tracker().snapshot()["attempts"]["task"] == 4

    def test_run_does_not_reach_save_results_when_aborted(self, monkeypatch):
        opt = _optimizer(monkeypatch)
        for name in ("validate_config", "build_llm_configs", "validate_llm_connections"):
            monkeypatch.setattr(opt, name, lambda: None)
        monkeypatch.setattr(opt, "load_config", lambda: opt.config)
        monkeypatch.setattr(opt, "load_data", lambda: None)
        monkeypatch.setattr(opt, "initialize_adapter", lambda: None)
        monkeypatch.setattr(opt, "load_prompt", lambda: {"system_prompt": BASE})
        monkeypatch.setattr(opt, "save_results", MagicMock())
        monkeypatch.setattr("gepa_standalone.universal_optimizer.Config", MagicMock())
        monkeypatch.setattr("gepa_standalone.universal_optimizer.MetadataManager", MagicMock())
        monkeypatch.setattr("gepa_standalone.universal_optimizer.get_paths", MagicMock())

        def pipeline_that_swallows_the_abort(initial_prompt, verbose=False):
            get_failure_tracker().abort(
                LLMFailure(FailureClass.configuracion, "task", "AuthenticationError"), "test"
            )

        monkeypatch.setattr(opt, "execute_gepa_pipeline", pipeline_that_swallows_the_abort)
        opt.config_path = None
        monkeypatch.setattr(opt, "run_wizard", lambda: opt.config)

        with pytest.raises(RunAborted, match="configuracion"):
            opt.run()

        opt.save_results.assert_not_called()

    def test_run_resets_the_failure_counter(self, monkeypatch):
        get_failure_tracker().abort(
            LLMFailure(FailureClass.configuracion, "task", "AuthenticationError"), "de otra corrida"
        )
        opt = _optimizer(monkeypatch)
        for name in ("validate_config", "build_llm_configs", "validate_llm_connections"):
            monkeypatch.setattr(opt, name, lambda: None)
        monkeypatch.setattr(opt, "load_data", lambda: None)
        monkeypatch.setattr(opt, "initialize_adapter", lambda: None)
        monkeypatch.setattr(opt, "load_prompt", lambda: {"system_prompt": BASE})
        monkeypatch.setattr(opt, "execute_gepa_pipeline", lambda *a, **k: None)
        monkeypatch.setattr(opt, "save_results", MagicMock(side_effect=StopIteration))
        monkeypatch.setattr("gepa_standalone.universal_optimizer.Config", MagicMock())
        monkeypatch.setattr("gepa_standalone.universal_optimizer.MetadataManager", MagicMock())
        monkeypatch.setattr("gepa_standalone.universal_optimizer.get_paths", MagicMock())
        opt.config_path = None
        monkeypatch.setattr(opt, "run_wizard", lambda: opt.config)

        with pytest.raises(StopIteration):  # llego a save_results: el aborto previo se limpio
            opt.run()


class TestAbortMessage:
    @staticmethod
    def _aborted(clase, rol="task"):
        return RunAborted(
            LLMFailure(clase, rol, "length"), "umbral superado", conteo=3, intentos=20
        )

    def test_presupuesto_suggests_effort_only_when_the_role_model_accepts_it(self, monkeypatch):
        opt = _optimizer(monkeypatch)
        opt.task_config.model = "anthropic/claude-sonnet-5-5"
        with_effort = opt.abort_message(self._aborted(FailureClass.presupuesto))
        assert "baseline tambien se corta" in with_effort and "max_tokens" in with_effort
        assert "effort" in with_effort

        opt.task_config.model = "azure/gpt-4.1-mini"
        without_effort = opt.abort_message(self._aborted(FailureClass.presupuesto))
        assert "max_tokens" in without_effort and "effort" not in without_effort

    def test_other_classes_do_not_suggest_effort(self, monkeypatch):
        opt = _optimizer(monkeypatch)
        opt.task_config.model = "anthropic/claude-sonnet-5-5"
        message = opt.abort_message(self._aborted(FailureClass.infraestructura))
        assert "infraestructura" in message and "effort" not in message

    def test_main_exits_with_the_abort_message(self, monkeypatch, capsys):
        from gepa_standalone import universal_optimizer as module

        def run(self, verbose=False):
            raise RunAborted(
                LLMFailure(FailureClass.infraestructura, "task", "RateLimitError"),
                "umbral superado",
                conteo=4,
                intentos=20,
            )

        monkeypatch.setattr(module.UniversalOptimizer, "run", run)
        monkeypatch.setattr("sys.argv", ["universal_optimizer"])
        with pytest.raises(SystemExit) as exc_info:
            module.main()
        assert exc_info.value.code == 1
        out = capsys.readouterr()
        assert "infraestructura" in out.out + out.err and "conteo=4/20" in out.out + out.err


# ==================== FR-005 / FR-013: callback de reflexion ====================


class TestReflectionCallbackWiring:
    def test_reflection_lm_is_passed_to_gepa_as_callback(self, monkeypatch):
        Completion(monkeypatch, lambda model, system, user: "greeting")
        seen = _fake_optimize(monkeypatch)
        opt = _optimizer(monkeypatch)

        _pipeline(opt)

        assert len(seen["callbacks"]) == 1
        assert seen["callbacks"][0] is seen["reflection_lm"]
        assert isinstance(seen["reflection_lm"], ReflectionLM)

    def test_failed_proposals_use_the_gepa_iteration_as_case_id(self, monkeypatch, caplog):
        def rule(model, system, user):
            if model == REFLECTION_MODEL:
                return "propuesta sin bloque de instruccion"
            # El baseline falla en train: sin ejemplos negativos GEPA no llega a reflexionar.
            return "farewell" if user.startswith("t") else "greeting"

        Completion(monkeypatch, rule)
        # GEPA real: sin `skip_perfect_score` cada iteracion llega a proponer.
        opt = _optimizer(monkeypatch, skip_perfect_score=False, max_metric_calls=80)

        with caplog.at_level(logging.WARNING), pytest.raises(RunAborted) as exc_info:
            _pipeline(opt)

        assert "rol=reflection" in str(exc_info.value)
        counts = get_failure_tracker().snapshot()["counts"]
        assert counts["formato"]["reflection"] >= 1
        warned = [r.getMessage() for r in caplog.records if "formato" in r.getMessage()]
        assert warned
        assert all("case_id=iteracion:" in message for message in warned)
