"""
SPEC-104 subfase 4b: orquestador de `dspy_gepa_poc` (`ReflexioDeclarativa`,
`GEPAOptimizer` y `scripts/baseline_only.py`).

Verifica el comportamiento que pide la spec, sin red, con dspy real (`Evaluate`,
`dspy.GEPA`) y respuestas reales de LiteLLM (`make_completion_response` de
`tests/conftest.py`; las fallas son las excepciones reales de LiteLLM):

- FR-003 / SC-002 / SC-007: baseline y optimizado se reportan cada uno sobre sus
  propios casos evaluados (`n_evaluados/n_total`) junto al delta pareado; con
  `n_evaluados == 0` el reporte dice "sin casos evaluados" y no 0.0.
- FR-006 / SC-004: el corte es por estado, tras cada paso y antes de `save_results()`.
- FR-005 / FR-013: el cableado del callback de GEPA da a la reflexion el numero de
  iteracion como `case_id`.
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from dspy.evaluate import Evaluate

from dspy_gepa_poc.call_failures import guard_program_and_metric
from dspy_gepa_poc.config import GEPAConfig
from dspy_gepa_poc.optimizer import GEPAOptimizer
from dspy_gepa_poc.reflexio_declarativa import ReflexioDeclarativa
from dspy_gepa_poc.scripts import baseline_only
from shared.display import print_summary
from shared.llm import FailureClass, LLMFailure, RunAborted, get_failure_tracker
from shared.llm.reflection import ReflectionProposer
from shared.scoring import paired_delta
from tests.test_dspy_call_failures import (
    CANDIDATE,
    REFLECTION_MODEL,
    SEED,
    FakeLLM,
    _adapter,
    _answer_yes,
    _dataset,
    _lm,
    _metric,
    _ok,
    _seed_student,
    _server_error,
    task_lm,  # noqa: F401 - fixture reutilizada
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("shared.llm.call.time.sleep", lambda s: None)


def _orchestrator(eval_repeats=1):
    orchestrator = ReflexioDeclarativa.__new__(ReflexioDeclarativa)
    orchestrator.eval_repeats = eval_repeats
    return orchestrator


def _evaluator(devset, metric):
    return Evaluate(devset=devset, metric=metric, num_threads=1)


def _on(*questions, answer=None):
    """Regla: `_server_error` en las preguntas dadas (NE por infraestructura)."""

    def rule(user_text):
        if any(q in user_text for q in questions):
            return _server_error(user_text)
        return answer(user_text) if answer else _ok(answer="yes")

    return rule


def _right_except_q0_q1(user_text):
    return _ok(answer="no" if ("q0" in user_text or "q1" in user_text) else "yes")


# ==================== FR-003: metricas sobre casos evaluados y delta pareado ====================


class TestReportedMetrics:
    def _evaluate_both(self, monkeypatch, repeats=1):
        # Baseline: q0 y q1 mal, q2 NE. Optimizado: todo bien salvo q3 NE (infra).
        fake = FakeLLM(
            {
                SEED: _on("q2", answer=_right_except_q0_q1),
                CANDIDATE: _on("q3"),
            }
        ).install(monkeypatch)
        student, metric = guard_program_and_metric(_seed_student(), _metric)
        devset = _dataset(10)
        orchestrator = _orchestrator(repeats)
        evaluator = _evaluator(devset, metric)
        baseline, _ = orchestrator._eval_repeated(evaluator, student)
        candidate = _adapter(student, metric).build_program({"self": CANDIDATE})
        optimized, _ = orchestrator._eval_repeated(evaluator, candidate)
        return baseline, optimized, fake

    def test_each_metric_uses_own_evaluated_cases(self, monkeypatch, task_lm):  # noqa: F811
        baseline, optimized, _ = self._evaluate_both(monkeypatch)

        assert (baseline.n_evaluados, baseline.n_total) == (9, 10)
        assert (optimized.n_evaluados, optimized.n_total) == (9, 10)
        # 7 aciertos de 9 evaluados: un NE no suma ni resta (no es 7/10).
        assert baseline.score == pytest.approx(7 / 9)
        assert optimized.score == pytest.approx(1.0)

    def test_delta_is_paired_over_cases_evaluated_with_both_prompts(
        self,
        monkeypatch,
        task_lm,  # noqa: F811
    ):
        baseline, optimized, _ = self._evaluate_both(monkeypatch)

        delta = paired_delta(baseline, optimized)
        # 8 casos evaluados con ambos (todos menos q2 y q3): baseline 6/8, optimizado 8/8.
        assert delta.n_pareados == 8
        assert delta.baseline_score == pytest.approx(0.75)
        assert delta.optimized_score == pytest.approx(1.0)
        assert delta.delta == pytest.approx(0.25)
        assert delta.delta != pytest.approx(optimized.score - baseline.score)

    def test_case_without_evaluated_repeat_is_ne_with_repeats(self, monkeypatch, task_lm):  # noqa: F811
        seen = []

        def flaky_q2(user_text):
            if "q2" in user_text:
                seen.append(1)
                # 1 intento + 3 reintentos de infraestructura: la 1a repeticion queda NE.
                if len(seen) <= 4:
                    return _server_error(user_text)
            return _ok(answer="yes")

        FakeLLM({SEED: flaky_q2}).install(monkeypatch)
        student, metric = guard_program_and_metric(_seed_student(), _metric)

        summary, _ = _orchestrator(2)._eval_repeated(_evaluator(_dataset(4), metric), student)

        assert (summary.n_evaluados, summary.n_total) == (4, 4)
        assert (summary.repeats, summary.ne_repeats) == (2, 1)

    def test_summary_block_shows_both_scores_and_paired_delta(
        self,
        monkeypatch,
        task_lm,  # noqa: F811
        capsys,
    ):
        baseline, optimized, _ = self._evaluate_both(monkeypatch)
        test = baseline

        print_summary(
            metrics={"Baseline": baseline, "Optimized": optimized, "Test": test},
            delta=paired_delta(baseline, optimized),
        )

        out = capsys.readouterr().out
        assert "9/10 casos evaluados" in out
        assert "Improvement (pareado)" in out
        assert "+25.00% sobre 8 casos pareados" in out

    def test_no_evaluated_cases_is_reported_as_such_not_as_zero(
        self,
        monkeypatch,
        task_lm,  # noqa: F811
        capsys,
    ):
        FakeLLM({SEED: _on("q")}).install(monkeypatch)
        student, metric = guard_program_and_metric(_seed_student(), _metric)

        # Pocos casos: bajo el minimo de intentos del contador no hay aborto por umbral.
        summary, _ = _orchestrator()._eval_repeated(_evaluator(_dataset(5), metric), student)

        assert (summary.n_evaluados, summary.n_total) == (0, 5)
        assert summary.score is None
        assert paired_delta(summary, summary).delta is None
        print_summary(metrics={"Baseline": summary}, delta=paired_delta(summary, summary))
        out = capsys.readouterr().out
        assert out.count("sin casos evaluados") == 2
        assert "0/5" in out

    def test_scores_keep_the_evaluate_percentage_unit(self, monkeypatch, task_lm):  # noqa: F811
        # SC-006: el CSV y run.json de DSPy guardan el score en la unidad de Evaluate.
        FakeLLM({SEED: _right_except_q0_q1}).install(monkeypatch)
        student, metric = guard_program_and_metric(_seed_student(), _metric)
        evaluator = _evaluator(_dataset(4), metric)

        summary, _ = _orchestrator()._eval_repeated(evaluator, student)

        from dspy_gepa_poc.reflexio_declarativa import _percent

        assert _percent(summary.score) == ReflexioDeclarativa._to_float_score(evaluator(student))
        assert _percent(None) is None

    def test_csv_row_gets_na_for_a_metric_without_evaluated_cases(self, tmp_path):
        orchestrator = _orchestrator()
        orchestrator.results_dir = tmp_path
        orchestrator.optimized_student = MagicMock()
        orchestrator.metadata_mgr = MagicMock()
        orchestrator.seed = 0
        orchestrator.run_id = "r"
        orchestrator.task_config = SimpleNamespace(model="openai/gpt-4o-mini")
        orchestrator.reflection_config = SimpleNamespace(model="openai/gpt-4o")
        orchestrator.task_lm = orchestrator.reflection_lm = None
        orchestrator.logger = MagicMock()
        orchestrator.config = SimpleNamespace(
            raw_config={
                "case": {"name": "caso"},
                "module": {"type": "dynamic"},
                "optimization": {},
            },
            dataset_path=str(tmp_path / "d.csv"),
            gepa=SimpleNamespace(auto_budget="light", max_metric_calls=4),
        )
        import dspy_gepa_poc.reflexio_declarativa as module

        original = (module.cost_from_usage, module.collect_model_info)
        module.cost_from_usage = lambda *a, **k: 0.0
        module.collect_model_info = lambda *a, **k: {}
        try:
            orchestrator.save_results(None, 42.5, None)
        finally:
            module.cost_from_usage, module.collect_model_info = original

        row = orchestrator.logger.log_run.call_args.args[0]
        assert (row["baseline_score"], row["optimized_score"], row["test_score"]) == (
            "N/A",
            42.5,
            "N/A",
        )


# ==================== FR-006 / SC-004: aborto por estado ====================


def _abort_config_error(roles=None):
    get_failure_tracker().abort(
        LLMFailure(FailureClass.configuracion, "task", "AuthenticationError"), "test"
    )


class TestBaselineOnly:
    @staticmethod
    def _stub(valset, testset, student, metric):
        stub = SimpleNamespace(
            setup_models=lambda roles=None: None,
            load_data=lambda: None,
            create_module_and_metric=lambda: None,
            config=SimpleNamespace(
                raw_config={"case": {"name": "caso"}, "optimization": {"num_threads": 1}}
            ),
            valset=valset,
            testset=testset,
            student=student,
            metric=metric,
            task_config=SimpleNamespace(model="anthropic/claude-sonnet-5-5"),
            reflection_config=SimpleNamespace(model="azure/gpt-4.1"),
        )
        stub.abort_message = lambda exc: ReflexioDeclarativa.abort_message(stub, exc)
        return stub

    def test_reports_n_evaluados_over_n_total_for_val_and_test(
        self,
        monkeypatch,
        task_lm,  # noqa: F811
        capsys,
    ):
        FakeLLM({SEED: _on("q1", answer=_answer_yes)}).install(monkeypatch)
        student, metric = guard_program_and_metric(_seed_student(), _metric)
        stub = self._stub(_dataset(4, "val"), _dataset(3, "test"), student, metric)

        assert baseline_only._run_baseline(stub) == 0

        out = capsys.readouterr().out
        assert "3/4 casos evaluados" in out  # val: q1 es NE en un caso de 4
        assert "2/3 casos evaluados" in out  # test: q1 es NE en un caso de 3
        assert "3/4" in out.split("RESUMEN")[1]

    def test_run_baseline_stops_on_abort_with_a_message(
        self,
        monkeypatch,
        task_lm,  # noqa: F811
        capsys,
    ):
        calls = FakeLLM({SEED: lambda u: _ok(answer="yes")}).install(monkeypatch)
        student, metric = guard_program_and_metric(_seed_student(), _metric)
        stub = self._stub(_dataset(4, "val"), _dataset(3, "test"), student, metric)
        stub.setup_models = _abort_config_error

        class Factory:
            case_results = staticmethod(ReflexioDeclarativa.case_results)

            def __new__(cls, path):
                return stub

        monkeypatch.setattr(baseline_only, "ReflexioDeclarativa", Factory)

        code = baseline_only.run_baseline("ignorado.yaml")

        assert code == 1
        captured = capsys.readouterr()
        assert "configuracion" in captured.out + captured.err
        assert calls.calls == {}  # el estado abortado corta antes de llamar al LLM

    def test_abort_during_val_skips_test_evaluation(self, monkeypatch, task_lm, capsys):  # noqa: F811
        def auth_error(user_text):
            import litellm

            return litellm.AuthenticationError(
                message="bad key", llm_provider="openai", model="openai/gpt-4o-mini"
            )

        FakeLLM({SEED: auth_error}).install(monkeypatch)
        student, metric = guard_program_and_metric(_seed_student(), _metric)
        stub = self._stub(_dataset(4, "val"), _dataset(3, "test"), student, metric)

        with pytest.raises(RunAborted, match="configuracion"):
            baseline_only._run_baseline(stub)

        assert "BASELINE EN TEST SET" not in capsys.readouterr().out

    def test_baseline_only_aborts_cleanly_above_max_errors(
        self,
        monkeypatch,
        task_lm,  # noqa: F811
        capsys,
    ):
        """H-01: con valset > max_errors (10), baseline_only captura RunAborted y retorna 1."""
        import litellm

        def auth_on_q0(user_text):
            if "q0" in user_text:
                return litellm.AuthenticationError(
                    message="bad key", llm_provider="openai", model="openai/gpt-4o-mini"
                )
            return _ok(answer="yes")

        fake = FakeLLM({SEED: auth_on_q0}).install(monkeypatch)
        student, metric = guard_program_and_metric(_seed_student(), _metric)
        stub = self._stub(_dataset(12, "val"), _dataset(3, "test"), student, metric)

        class Factory:
            case_results = staticmethod(ReflexioDeclarativa.case_results)

            def __new__(cls, path):
                return stub

        monkeypatch.setattr(baseline_only, "ReflexioDeclarativa", Factory)

        code = baseline_only.run_baseline("ignorado.yaml")

        assert code == 1
        captured = capsys.readouterr()
        assert "configuracion" in captured.out + captured.err
        assert fake.calls == {SEED: 1}

    def test_run_baseline_flushes_pending_abort_error_log(
        self,
        monkeypatch,
        task_lm,  # noqa: F811
        caplog,
    ):
        """H-05: un aborto pendiente sin `record` en baseline_only igual emite su ERROR."""
        FakeLLM({SEED: lambda u: _ok(answer="yes")}).install(monkeypatch)
        student, metric = guard_program_and_metric(_seed_student(), _metric)
        stub = self._stub(_dataset(4, "val"), _dataset(3, "test"), student, metric)
        stub.setup_models = _abort_config_error

        class Factory:
            case_results = staticmethod(ReflexioDeclarativa.case_results)

            def __new__(cls, path):
                return stub

        monkeypatch.setattr(baseline_only, "ReflexioDeclarativa", Factory)

        with caplog.at_level(logging.ERROR, logger="shared.llm.failures"):
            code = baseline_only.run_baseline("ignorado.yaml")

        assert code == 1
        errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
        assert len(errors) == 1
        assert "Corrida abortada: clase=configuracion" in errors[0]

    def test_eval_repeated_stops_between_repeats_on_threshold_abort(
        self,
        monkeypatch,
        task_lm,  # noqa: F811
    ):
        """H-01: si la primera repeticion supera el umbral, `_eval_repeated` no corre la 2da."""
        get_failure_tracker().configure(min_attempts={"task": 4})
        fake = FakeLLM({SEED: _on("q")}).install(monkeypatch)
        student, metric = guard_program_and_metric(_seed_student(), _metric)
        evaluator = _evaluator(_dataset(4), metric)

        with pytest.raises(RunAborted, match="infraestructura"):
            _orchestrator(2)._eval_repeated(evaluator, student)

        # 4 casos x (1 intento + 3 reintentos) = 16 llamadas en la 1a repeticion; 0 de la 2da.
        assert fake.calls[SEED] == 16

    def test_setup_models_resets_the_failure_counter(self, monkeypatch):
        _abort_config_error()
        orchestrator = _orchestrator()
        orchestrator.config = SimpleNamespace(raw_config={})
        stop = RuntimeError("llego a configurar los LLM")
        monkeypatch.setattr(
            "dspy_gepa_poc.reflexio_declarativa.LLMConfig",
            SimpleNamespace(from_env=MagicMock(side_effect=stop)),
        )

        with pytest.raises(RuntimeError, match="llego a configurar"):
            orchestrator.setup_models()

        assert not get_failure_tracker().aborted


class TestAbortMessage:
    @staticmethod
    def _aborted(clase):
        return RunAborted(LLMFailure(clase, "task", "length"), "umbral superado", 3, 20)

    def test_presupuesto_suggests_effort_only_when_the_role_model_accepts_it(self):
        orchestrator = _orchestrator()
        orchestrator.task_config = SimpleNamespace(model="anthropic/claude-sonnet-5-5")
        message = orchestrator.abort_message(self._aborted(FailureClass.presupuesto))
        assert "baseline tambien se corta" in message and "max_tokens" in message
        assert "effort" in message

        orchestrator.task_config = SimpleNamespace(model="azure/gpt-4.1-mini")
        message = orchestrator.abort_message(self._aborted(FailureClass.presupuesto))
        assert "max_tokens" in message and "effort" not in message


# ==================== FR-005 / FR-013: callback de reflexion ====================


class TestReflectionCallbackWiring:
    @staticmethod
    def _config():
        return GEPAConfig(
            max_metric_calls=24,
            reflection_minibatch_size=2,
            skip_perfect_score=False,
            use_merge=False,
        )

    def test_reflection_proposer_is_instruction_proposer_and_callback(self):
        # SPEC-105 FR-010: la reflexion es del repo; dspy.GEPA solo recibe el proposer.
        lm = _lm(REFLECTION_MODEL, "reflection")
        optimizer = GEPAOptimizer(metric=_metric, reflection_lm=lm, config=self._config())
        proposer = optimizer.reflection_proposer
        assert isinstance(proposer, ReflectionProposer)
        assert optimizer.optimizer.custom_instruction_proposer is proposer
        assert optimizer.optimizer.gepa_kwargs["callbacks"] == [proposer]
        assert optimizer.optimizer.reflection_lm is lm

    def test_any_reflection_lm_gets_the_repo_proposer(self):
        plain = MagicMock(spec=["__call__"])
        optimizer = GEPAOptimizer(metric=_metric, reflection_lm=plain, config=self._config())
        assert isinstance(optimizer.optimizer.custom_instruction_proposer, ReflectionProposer)

    def test_failed_proposals_use_the_gepa_iteration_as_case_id(
        self,
        monkeypatch,
        task_lm,  # noqa: F811
        caplog,
    ):
        # La semilla responde mal (GEPA reflexiona) y la reflexion no trae bloque.
        FakeLLM({SEED: lambda u: _ok(answer="no")}, reflection="sin bloque").install(monkeypatch)
        student, metric = guard_program_and_metric(_seed_student(), _metric)
        optimizer = GEPAOptimizer(
            metric=metric, reflection_lm=_lm(REFLECTION_MODEL, "reflection"), config=self._config()
        )
        data = _dataset(4)

        with caplog.at_level(logging.WARNING):
            optimizer.compile(student, trainset=data, valset=data)

        counts = get_failure_tracker().snapshot()["counts"]
        assert counts["formato"]["reflection"] >= 1
        warned = [
            r.getMessage()
            for r in caplog.records
            if "rol=reflection" in r.getMessage() and "clave=formato" in r.getMessage()
        ]
        assert warned
        assert all("case_id=iteracion:" in message for message in warned)


# ==================== run(): estado consultado tras cada paso ====================


class TestRunChecksStateAfterEachStep:
    @staticmethod
    def _run_orchestrator(monkeypatch, compile_side_effect):
        import dspy_gepa_poc.reflexio_declarativa as module

        student, metric = guard_program_and_metric(_seed_student(), _metric)
        orchestrator = _orchestrator()
        orchestrator.config = SimpleNamespace(
            raw_config={
                "case": {"name": "caso"},
                "optimization": {"num_threads": 1, "eval_repeats": 1},
            },
            gepa=SimpleNamespace(max_metric_calls=4),
        )
        orchestrator.valset = _dataset(4, "val")
        orchestrator.testset = _dataset(3, "test")
        orchestrator.trainset = _dataset(2, "train")
        orchestrator.reflection_lm = None
        orchestrator.setup_models = lambda: None
        orchestrator.load_data = lambda: None
        orchestrator.create_module_and_metric = lambda: setattr(orchestrator, "student", student)
        orchestrator.metric = metric
        orchestrator.save_results = MagicMock()
        orchestrator.task_config = SimpleNamespace(model="openai/gpt-4o-mini")
        orchestrator.reflection_config = SimpleNamespace(model="openai/gpt-4o")

        class FakeOptimizer:
            def __init__(self, **kwargs):
                pass

            def compile(self, student, trainset, valset):
                compile_side_effect()
                return student

            def get_detailed_results(self):
                return None

        monkeypatch.setattr(module, "GEPAOptimizer", FakeOptimizer)
        return orchestrator

    def test_abort_during_optimization_stops_before_val_test_and_save(
        self,
        monkeypatch,
        task_lm,  # noqa: F811
    ):
        fake = FakeLLM({SEED: _answer_yes}).install(monkeypatch)
        orchestrator = self._run_orchestrator(monkeypatch, _abort_config_error)

        with pytest.raises(RunAborted, match="configuracion"):
            orchestrator.run()

        assert fake.calls[SEED] == 4  # solo el baseline sobre val; ni val optimizado ni test
        orchestrator.save_results.assert_not_called()

    def test_completed_run_reports_summaries_and_saves_them_in_evaluate_units(
        self,
        monkeypatch,
        task_lm,  # noqa: F811
        capsys,
    ):
        FakeLLM({SEED: _on("q1", answer=_answer_yes)}).install(monkeypatch)
        orchestrator = self._run_orchestrator(monkeypatch, lambda: None)

        orchestrator.run()

        summaries = orchestrator.metric_summaries
        assert [s.ratio_label() for s in summaries.values()] == ["3/4", "3/4", "2/3"]
        assert orchestrator.save_results.call_args.args == (100.0, 100.0, 100.0)
        out = capsys.readouterr().out
        assert "Improvement (pareado)" in out
        assert "3 casos pareados" in out


# ==================== D-034(b): creacion perezosa de run_dir ====================


class TestLazyRunDirectory:
    """D-034(b): `dspy_gepa_poc` no deja carpetas vacias si falla antes de `run.json`."""

    @staticmethod
    def _make_config(tmp_path, monkeypatch):
        from dspy_gepa_poc.config import AppConfig
        from shared.paths import dspy_paths

        root = tmp_path / "dspy_root"
        paths = dspy_paths.DSPyPaths(root_override=root)
        monkeypatch.setattr(dspy_paths, "_dspy_paths_instance", paths)
        monkeypatch.setattr(AppConfig, "DATASETS_DIR", str(paths.datasets))

        (paths.datasets / "mini.csv").write_text(
            "split,text,label\ntrain,a,x\nval,b,x\ntest,c,x\n", encoding="utf-8"
        )
        cfg = tmp_path / "mini.yaml"
        cfg.write_text(
            "case: {name: mini_case, title: Mini}\n"
            "module: {type: dynamic}\n"
            "signature:\n"
            '  instruction: "Classify."\n'
            "  inputs: [{name: text, desc: text}]\n"
            "  outputs: [{name: label, desc: label}]\n"
            "data: {csv_filename: mini.csv, input_column: text}\n"
            "optimization: {max_metric_calls: 4}\n",
            encoding="utf-8",
        )
        return paths, cfg

    def test_init_does_not_create_run_dir(self, tmp_path, monkeypatch):
        paths, cfg = self._make_config(tmp_path, monkeypatch)

        orchestrator = ReflexioDeclarativa(str(cfg))

        assert not orchestrator.results_dir.exists()
        assert not (paths.root / "results" / "runs").exists()

    def test_early_failure_leaves_no_empty_run_dir(self, tmp_path, monkeypatch):
        paths, cfg = self._make_config(tmp_path, monkeypatch)
        orchestrator = ReflexioDeclarativa(str(cfg))
        orchestrator.setup_models = MagicMock(side_effect=RuntimeError("fallo de conexion"))

        with pytest.raises(RuntimeError, match="fallo de conexion"):
            orchestrator.run()

        assert not orchestrator.results_dir.exists()
        assert not (paths.root / "results" / "runs").exists()

    def test_failure_after_mkdir_cleans_up_empty_run_dir(self, tmp_path, monkeypatch):
        _, cfg = self._make_config(tmp_path, monkeypatch)
        orchestrator = ReflexioDeclarativa(str(cfg))

        def create_then_fail():
            orchestrator.results_dir.mkdir(parents=True, exist_ok=True)
            raise RuntimeError("fallo antes de persistir run.json")

        orchestrator._run_pipeline = create_then_fail

        with pytest.raises(RuntimeError, match="fallo antes de persistir"):
            orchestrator.run()

        assert not orchestrator.results_dir.exists()

    def test_aborted_run_preserves_run_dir_with_run_json(self, tmp_path, monkeypatch):
        _, cfg = self._make_config(tmp_path, monkeypatch)
        orchestrator = ReflexioDeclarativa(str(cfg))
        orchestrator.seed = 7
        orchestrator.task_config = SimpleNamespace(
            model="openai/gpt-4o-mini", effective_params=lambda mt=None: {}
        )
        orchestrator.reflection_config = SimpleNamespace(
            model="openai/gpt-4o", effective_params=lambda mt=None: {}
        )

        def abort_pipeline():
            _abort_config_error()
            get_failure_tracker().check_abort()

        orchestrator._run_pipeline = abort_pipeline

        with pytest.raises(RunAborted):
            orchestrator.run()

        assert (orchestrator.results_dir / "run.json").exists()

    def test_save_results_creates_lazy_run_dir(self, tmp_path, monkeypatch):
        _, cfg = self._make_config(tmp_path, monkeypatch)
        orchestrator = ReflexioDeclarativa(str(cfg))
        assert not orchestrator.results_dir.exists()

        orchestrator.seed = 1
        orchestrator.task_config = SimpleNamespace(
            model="openai/gpt-4o-mini", effective_params=lambda mt=None: {}
        )
        orchestrator.reflection_config = SimpleNamespace(
            model="openai/gpt-4o", effective_params=lambda mt=None: {}
        )
        orchestrator.optimized_student = MagicMock()
        orchestrator.logger = MagicMock()

        orchestrator.save_results(50.0, 80.0, 75.0)

        assert (orchestrator.results_dir / "config_snapshot.yaml").exists()
        assert (orchestrator.results_dir / "run.json").exists()
