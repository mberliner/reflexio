"""SPEC-103 FR-012: UniversalOptimizer arma una sola vez las configs LLM."""

from unittest.mock import patch

from gepa_standalone.universal_optimizer import UniversalOptimizer
from shared.llm import LLMConfig


def _cfg(role):
    return LLMConfig(
        model="anthropic/claude-haiku-4-5",
        api_key="x",
        temperature=0.5,
        max_tokens=1000,
        role=role,
    )


def _optimizer(models):
    opt = UniversalOptimizer()
    opt.config = {"models": models}
    with (
        patch(
            "gepa_standalone.universal_optimizer.get_task_config",
            side_effect=lambda: _cfg("task"),
        ),
        patch(
            "gepa_standalone.universal_optimizer.get_reflection_config",
            side_effect=lambda: _cfg("reflection"),
        ),
    ):
        opt.build_llm_configs()
    return opt


def test_yaml_overrides_applied_to_both_configs():
    opt = _optimizer({"temperature": 0.2, "max_tokens": 777, "cache": False})

    assert opt.active_temperature == 0.2
    assert opt.task_config.temperature == 0.2
    assert opt.reflection_config.temperature == 0.2
    assert opt.task_config.max_tokens == 777
    assert opt.reflection_config.max_tokens == 777
    assert opt.reflection_config.cache is False


def test_defaults_without_yaml_models():
    opt = _optimizer({})

    assert opt.active_temperature == 0.0
    assert opt.task_config.temperature == 0.0
    assert opt.reflection_config.temperature == 0.5
    assert opt.reflection_config.max_tokens == 2000
    assert opt.task_config.max_tokens == 1000


def test_configs_are_distinct_roles():
    opt = _optimizer({})

    assert opt.task_config is not opt.reflection_config
    assert opt.task_config.role == "task"
    assert opt.reflection_config.role == "reflection"


def test_reflection_lm_function_uses_given_config():
    from gepa_standalone.core.llm_factory import create_reflection_lm_function

    cfg = _cfg("reflection")
    with patch.object(LLMConfig, "get_lm_function", autospec=True) as get_fn:
        create_reflection_lm_function(config=cfg, temperature=0.9, max_tokens=5)

    assert get_fn.call_args.args[0] is cfg
    assert cfg.temperature == 0.5
    assert cfg.max_tokens == 1000


# ==================== SPEC-104 4c: seccion `failures` y run.json ====================

import json  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

from dspy_gepa_poc.reflexio_declarativa import ReflexioDeclarativa  # noqa: E402
from shared.llm import (  # noqa: E402
    FailureClass,
    LLMFailure,
    RunAborted,
    get_failure_tracker,
)
from shared.logging.metadata import MetadataManager  # noqa: E402
from shared.scoring import paired_delta, summarize  # noqa: E402

FAILURES_YAML = {
    "infra_retries": 1,
    "judge_retries": 4,
    "min_attempts": {"task": 3},
    "thresholds": {"presupuesto": {"task": 0.25}},
}


def _presupuesto(case_id):
    return LLMFailure(FailureClass.presupuesto, "task", "length", case_id=case_id)


def _exercise_tracker_thresholds():
    """Con min_attempts=3 y umbral 0.25: 1 falla en 3 intentos (0.33) aborta."""
    tracker = get_failure_tracker()
    for i in range(3):
        tracker.record_attempt("task", f"c{i}")
    assert not tracker.aborted
    tracker.record(_presupuesto("c0"))
    return tracker


class TestFailuresSectionWiringGepa:
    @staticmethod
    def _opt(**config):
        opt = UniversalOptimizer()
        opt.config = config
        return opt

    def test_yaml_section_configures_the_counter(self):
        self._opt(failures=FAILURES_YAML).configure_failure_tracker()

        assert get_failure_tracker().infra_retries == 1
        assert _exercise_tracker_thresholds().aborted

    def test_without_section_the_spec_defaults_apply(self):
        self._opt().configure_failure_tracker()

        tracker = get_failure_tracker()
        assert tracker.infra_retries == 3
        for i in range(3):
            tracker.record_attempt("task", f"c{i}")
        tracker.record(_presupuesto("c0"))
        assert not tracker.aborted  # min_attempts 20 por defecto

    def test_configure_clears_the_state_of_a_previous_run(self):
        get_failure_tracker().abort(_presupuesto("x"), "otra corrida")
        self._opt().configure_failure_tracker()
        assert not get_failure_tracker().aborted

    def test_judge_retries_from_yaml_reach_the_rag_judge(self, mock_env):
        opt = self._opt(
            case={"name": "rag"},
            adapter={"type": "rag"},
            models={},
            failures={"judge_retries": 4},
        )
        opt.build_llm_configs()
        opt.initialize_adapter()
        assert opt.adapter.judge_retries == 4

    def test_judge_retries_default_without_yaml(self, mock_env):
        from gepa_standalone.adapters.simple_rag_adapter import DEFAULT_JUDGE_RETRIES

        opt = self._opt(case={"name": "rag"}, adapter={"type": "rag"}, models={})
        opt.build_llm_configs()
        opt.initialize_adapter()
        assert opt.adapter.judge_retries == DEFAULT_JUDGE_RETRIES


class TestRunJsonGepa:
    @staticmethod
    def _ready(tmp_path):
        opt = _optimizer({})
        opt.config.update(case={"name": "caso"}, data={"csv_filename": "x.csv"})
        opt.metadata_mgr = MetadataManager(tmp_path / "results")
        opt.seed = 7
        opt.adapter = SimpleNamespace(task_max_tokens=100, model="m")
        paths = SimpleNamespace(
            results=tmp_path / "results",
            run_dir=lambda name, run_id=None: tmp_path / "runs" / f"{name}_{run_id}",
            dataset=lambda name: tmp_path / name,
        )
        return opt, paths

    def test_aborted_run_writes_run_json_with_status_and_no_csv_row(self, tmp_path, monkeypatch):
        opt, paths = self._ready(tmp_path)
        monkeypatch.setattr("gepa_standalone.universal_optimizer.get_paths", lambda: paths)
        csv_row = MagicMock()
        monkeypatch.setattr("gepa_standalone.universal_optimizer.log_experiment_result", csv_row)
        for name in ("validate_config", "build_llm_configs", "validate_llm_connections"):
            monkeypatch.setattr(opt, name, lambda: None)
        monkeypatch.setattr(opt, "load_data", lambda: None)
        monkeypatch.setattr(opt, "initialize_adapter", lambda: None)
        monkeypatch.setattr(opt, "load_prompt", lambda: {"system_prompt": "P"})
        monkeypatch.setattr("gepa_standalone.universal_optimizer.Config", MagicMock())
        opt.adapter.set_baseline = lambda *_: None
        opt.config_path = None
        monkeypatch.setattr(opt, "run_wizard", lambda: opt.config)

        def pipeline(initial_prompt, verbose=False):
            tracker = get_failure_tracker()
            for i in range(4):
                tracker.record_attempt("task", f"c{i}")
            tracker.record(_presupuesto("c0"))
            tracker.record(
                LLMFailure(
                    FailureClass.entrada,
                    "task",
                    "ContentPolicy",
                    case_id="c1",
                    atribucion="externa",
                )
            )
            tracker.abort(_presupuesto("c2"), "umbral superado")

        monkeypatch.setattr(opt, "execute_gepa_pipeline", pipeline)

        with pytest.raises(RunAborted):
            opt.run()

        run_jsons = list((tmp_path / "runs").glob("*/run.json"))
        assert len(run_jsons) == 1
        data = json.loads(run_jsons[0].read_text(encoding="utf-8"))
        assert data["status"] == "aborted"
        assert data["abort"]["clase"] == "presupuesto" and data["abort"]["rol"] == "task"
        assert data["failures"]["counts"]["presupuesto"]["task"] == 1
        assert data["failures"]["entrada_dato"] == ["c1"]
        csv_row.assert_not_called()

    def test_completed_run_json_has_status_counts_and_coverage(self, tmp_path, monkeypatch):
        opt, paths = self._ready(tmp_path)
        monkeypatch.setattr("gepa_standalone.universal_optimizer.get_paths", lambda: paths)
        monkeypatch.setattr(
            "gepa_standalone.universal_optimizer.log_experiment_result", MagicMock()
        )
        monkeypatch.setattr(
            "gepa_standalone.universal_optimizer.save_run_details",
            lambda **kw: paths.run_dir("caso", "ok"),
        )
        opt.config["adapter"] = {"type": "classifier"}
        opt.config["optimization"] = {"max_metric_calls": 10}
        opt.results = {
            "initial_prompt": "a",
            "final_prompt": "b",
            "baseline_score": 0.5,
            "optimized_score": 0.7,
            "test_score": None,
        }
        opt.metric_summaries = {
            "baseline": summarize([[("a", 1.0, True), ("b", 0.0, False)]]),
            "optimized": summarize([[("a", 1.0, True), ("b", 1.0, True)]]),
            "test": summarize([]),
        }
        opt.paired_delta = paired_delta(
            opt.metric_summaries["baseline"], opt.metric_summaries["optimized"]
        )
        tracker = get_failure_tracker()
        tracker.record_attempt("task", "a")
        tracker.record(_presupuesto("b"))

        run_dir = opt.save_results()

        data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        assert data["status"] == "completed"
        assert data["abort"] is None
        assert data["failures"]["counts"] == {"presupuesto": {"task": 1}}
        assert data["metrics"]["baseline"] == {"n_evaluados": 1, "n_total": 2}
        assert data["metrics"]["test"] == {"n_evaluados": 0, "n_total": 0}
        assert data["paired_delta"] == {
            "delta": pytest.approx(0.0),
            "baseline_score": pytest.approx(1.0),
            "optimized_score": pytest.approx(1.0),
            "n_pareados": 1,
            "sin_casos_evaluados": False,
        }


class TestFailuresSectionWiringDspy:
    @staticmethod
    def _orchestrator(raw_config):
        orchestrator = ReflexioDeclarativa.__new__(ReflexioDeclarativa)
        orchestrator.config = SimpleNamespace(raw_config=raw_config)
        return orchestrator

    def test_yaml_section_configures_the_counter(self):
        self._orchestrator({"failures": FAILURES_YAML}).configure_failure_tracker()

        assert get_failure_tracker().infra_retries == 1
        assert _exercise_tracker_thresholds().aborted

    def test_without_section_the_spec_defaults_apply(self):
        self._orchestrator({}).configure_failure_tracker()
        assert get_failure_tracker().infra_retries == 3

    def test_setup_models_applies_the_section(self, monkeypatch):
        orchestrator = self._orchestrator({"failures": {"infra_retries": 2}})
        stop = RuntimeError("llego a configurar los LLM")
        monkeypatch.setattr(
            "dspy_gepa_poc.reflexio_declarativa.LLMConfig",
            SimpleNamespace(from_env=MagicMock(side_effect=stop)),
        )
        with pytest.raises(RuntimeError, match="llego a configurar"):
            orchestrator.setup_models()
        assert get_failure_tracker().infra_retries == 2

    def test_aborted_run_writes_run_json_with_status_and_no_csv_row(self, tmp_path):
        orchestrator = self._orchestrator({"case": {"name": "caso"}})
        orchestrator.results_dir = tmp_path / "run"
        orchestrator.metadata_mgr = MetadataManager(tmp_path / "results")
        orchestrator.seed = 3
        orchestrator.task_config = SimpleNamespace(
            model="openai/gpt-4o-mini", effective_params=lambda mt=None: {}
        )
        orchestrator.reflection_config = SimpleNamespace(
            model="openai/gpt-4o", effective_params=lambda mt=None: {}
        )
        orchestrator.task_lm = orchestrator.reflection_lm = None
        orchestrator.logger = MagicMock()
        orchestrator.save_results = MagicMock()

        def pipeline():
            tracker = get_failure_tracker()
            for i in range(4):
                tracker.record_attempt("task", f"c{i}")
            tracker.record(
                LLMFailure(
                    FailureClass.entrada,
                    "task",
                    "ContentPolicy",
                    case_id="c1",
                    atribucion="externa",
                )
            )
            tracker.abort(_presupuesto("c2"), "umbral superado")
            tracker.check_abort()

        orchestrator._run_pipeline = pipeline

        with pytest.raises(RunAborted):
            orchestrator.run()

        data = json.loads((tmp_path / "run" / "run.json").read_text(encoding="utf-8"))
        assert data["status"] == "aborted"
        assert data["abort"]["clase"] == "presupuesto" and data["abort"]["rol"] == "task"
        assert data["failures"]["entrada_dato"] == ["c1"]
        orchestrator.logger.log_run.assert_not_called()
        orchestrator.save_results.assert_not_called()

    def test_completed_run_json_has_status_counts_and_coverage(self, tmp_path):
        orchestrator = self._orchestrator(
            {"case": {"name": "caso"}, "module": {"type": "dynamic"}, "optimization": {}}
        )
        orchestrator.config.dataset_path = str(tmp_path / "d.csv")
        orchestrator.config.gepa = SimpleNamespace(auto_budget="light", max_metric_calls=4)
        orchestrator.results_dir = tmp_path / "run"
        orchestrator.results_dir.mkdir()
        orchestrator.optimized_student = MagicMock()
        orchestrator.metadata_mgr = MetadataManager(tmp_path / "results")
        orchestrator.seed = 0
        orchestrator.task_config = SimpleNamespace(
            model="openai/gpt-4o-mini", effective_params=lambda mt=None: {}
        )
        orchestrator.reflection_config = SimpleNamespace(
            model="openai/gpt-4o", effective_params=lambda mt=None: {}
        )
        orchestrator.task_lm = orchestrator.reflection_lm = None
        orchestrator.logger = MagicMock()
        orchestrator.metric_summaries = {
            "baseline": summarize([[("a", 0.0, True), ("b", 0.0, False)]]),
            "optimized": summarize([[("a", 1.0, True), ("b", 1.0, True)]]),
            "test": summarize([]),
        }
        orchestrator.paired_delta = paired_delta(
            orchestrator.metric_summaries["baseline"],
            orchestrator.metric_summaries["optimized"],
        )
        tracker = get_failure_tracker()
        tracker.record_attempt("task", "a")
        tracker.record(_presupuesto("b"))

        orchestrator.save_results(50.0, 60.0, None)

        data = json.loads((tmp_path / "run" / "run.json").read_text(encoding="utf-8"))
        assert data["status"] == "completed"
        assert data["abort"] is None
        assert data["failures"]["counts"] == {"presupuesto": {"task": 1}}
        assert data["metrics"]["baseline"] == {"n_evaluados": 1, "n_total": 2}
        assert data["metrics"]["test"] == {"n_evaluados": 0, "n_total": 0}
        assert data["paired_delta"] == {
            "delta": pytest.approx(1.0),
            "baseline_score": pytest.approx(0.0),
            "optimized_score": pytest.approx(1.0),
            "n_pareados": 1,
            "sin_casos_evaluados": False,
        }
