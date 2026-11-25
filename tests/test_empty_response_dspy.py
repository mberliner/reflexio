"""
SPEC-103 FR-009 (2c) y SPEC-104 (2a): respuesta sin texto en el camino DSPy.

`LLMConfig.get_dspy_lm()` devuelve un `CheckedLM` (D8). Se verifica sin red,
contra dspy 3.4.1 y GEPA 0.1.4, interceptando `litellm.completion`:

- reflexion: `CheckedLM` lanza `EmptyResponseError`, el `ReflectionProposer` del
  repo (SPEC-105 FR-010) la registra y `dspy.GEPA` saltea la iteracion sin crear
  un candidato con instruccion vacia.
- tarea: `CheckedLM` tambien lanza; desde SPEC-104 (3e) el envoltorio de
  `dspy_gepa_poc/call_failures.py` la convierte en una `FailedCallPrediction`
  que la metrica cuenta una vez y, si es NE, puntua 0.0 solo como valor tecnico,
  en las dos rutas de `DspyAdapter.evaluate`, en `dspy.GEPA` y en `Evaluate`
  (sin "Execution cancelled" con mas de `max_errors` fallas). Una excepcion no
  clasificada es `configuracion`: aborta la corrida tras 1 llamada HTTP.
- SPEC-104 (2b): en reflexion la propuesta sin bloque de instruccion es
  `formato` y la respuesta sin texto deja un unico WARNING (el de
  `FailureTracker.record`); el detalle esta en `tests/test_reflection_guard.py`.
  El detalle de 3e (atribucion, feedback, conteo) esta en
  `tests/test_dspy_call_failures.py`.
"""

import logging

import dspy
import pytest
from dspy.evaluate import Evaluate
from dspy.teleprompt.gepa.gepa_utils import DspyAdapter

from dspy_gepa_poc.call_failures import (
    FailedCallPrediction,
    guard_program_and_metric,
    tolerate_call_failures,
)
from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory
from shared.llm import (
    EmptyResponseError,
    FailureClass,
    LLMCallFailure,
    LLMConfig,
    RunAborted,
    get_failure_tracker,
)
from shared.llm.dspy_lm import CheckedEngine, dspy_reflection_proposer
from shared.llm.usage import get_tracker as get_usage_tracker
from tests.conftest import (
    make_completion_response,
    patch_litellm_completion,
    project_warnings,
    repo_dspy_gepa,
)

TASK_MODEL = "openai/gpt-4o-mini"
REFLECTION_MODEL = "openai/gpt-4o"
SEED_INSTRUCTION = "Answer the question."
VALID_INSTRUCTION = "Always answer yes."
# LiteLLM normaliza el `stop_reason` "refusal" de Anthropic a "content_filter".
EMPTY_CASES = [(None, "length"), ("", "content_filter"), ("  \n", "stop")]


def _task_text(answer):
    return f"[[ ## answer ## ]]\n{answer}\n\n[[ ## completed ## ]]"


def _patch_dspy_completion(monkeypatch, task, reflection):
    """`task`/`reflection`: callables (request) -> (content, finish_reason)."""
    calls = {"task": 0, "reflection": 0}

    def fake_completion(request, num_retries, cache=None):
        role = "reflection" if request["model"] == REFLECTION_MODEL else "task"
        calls[role] += 1
        content, reason = (reflection if role == "reflection" else task)(request)
        return make_completion_response(content, reason)

    patch_litellm_completion(monkeypatch, fake_completion)
    return calls


def _lm(model, role):
    return LLMConfig(model=model, api_key="key", role=role, cache=False).get_dspy_lm()


def _dataset(n=4):
    return [
        dspy.Example(case_id=f"val:{i}", question=f"q{i}", answer="yes").with_inputs("question")
        for i in range(n)
    ]


def _metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
    return float(getattr(pred, "answer", None) == gold.answer)


def _plain_student():
    return dspy.Predict(dspy.Signature("question -> answer", SEED_INSTRUCTION))


def _guarded():
    """Programa y metrica como los arma `create_module_and_metric` (D5/D6)."""
    return guard_program_and_metric(_plain_student(), _metric)


def _student():
    return _guarded()[0]


def _run_gepa(reflection_lm, budget=16):
    student, metric = _guarded()
    optimizer = repo_dspy_gepa(
        reflection_lm,
        metric=metric,
        max_metric_calls=budget,
        reflection_minibatch_size=2,
        track_stats=True,
        seed=0,
    )
    data = _dataset()
    return optimizer.compile(student, trainset=data, valset=data)


def _instructions(result):
    return [
        pred.signature.instructions
        for program in result.detailed_results.candidates
        for _, pred in program.named_predictors()
    ]


class _TaskByInstruction:
    """Tarea falsa: responde "yes" solo con la instruccion propuesta valida.

    Cuenta las llamadas hechas con una instruccion distinta de la semilla, es
    decir, las evaluaciones de candidatos propuestos por la reflexion.
    """

    def __init__(self):
        self.non_seed_calls = 0

    def __call__(self, request):
        system = str(request["messages"][0]["content"])
        if SEED_INSTRUCTION not in system:
            self.non_seed_calls += 1
        answer = "yes" if VALID_INSTRUCTION in system else "no"
        return _task_text(answer), "stop"


@pytest.fixture
def task_lm_context():
    with dspy.context(lm=_lm(TASK_MODEL, "task")):
        yield


def _propose(reflection_lm):
    """Una propuesta del `ReflectionProposer` del repo sobre `reflection_lm`."""
    proposer = dspy_reflection_proposer(reflection_lm)
    return proposer({"p": SEED_INSTRUCTION}, {"p": [{"Feedback": "x"}]}, ["p"])


# ==================== CheckedLM aislado ====================


class TestCheckedEngine:
    def test_get_dspy_lm_returns_checked_lm_with_role(self):
        lm = _lm(REFLECTION_MODEL, "reflection")
        assert isinstance(lm, dspy.LM)
        assert isinstance(lm.engine, CheckedEngine)
        assert lm.engine.role == "reflection"

    def test_from_env_role(self, mock_env):
        assert LLMConfig.from_env("reflection").get_dspy_lm().engine.role == "reflection"
        assert LLMConfig.from_env("task").get_dspy_lm().engine.role == "task"

    def test_copy_keeps_role(self):
        assert _lm(REFLECTION_MODEL, "reflection").copy(rollout_id=1).engine.role == "reflection"

    def test_text_passes_through(self, monkeypatch):
        """SPEC-104 FR-005: en reflexion pasa la propuesta con bloque de
        instruccion; el texto sin bloque se descarta como `formato`."""
        proposal = f"```\n{VALID_INSTRUCTION}\n```"
        _patch_dspy_completion(monkeypatch, None, lambda r: (proposal, "stop"))
        assert _lm(REFLECTION_MODEL, "reflection")("hola") == [proposal]

    def test_reflection_without_block_is_format_failure(self, monkeypatch):
        # El guard de formato es del ReflectionProposer (SPEC-105 FR-010), no del LM.
        _patch_dspy_completion(monkeypatch, None, lambda r: ("ok", "stop"))
        with pytest.raises(LLMCallFailure) as exc_info:
            _propose(_lm(REFLECTION_MODEL, "reflection"))
        assert exc_info.value.failure.clase == FailureClass.formato
        assert get_failure_tracker().snapshot()["counts"]["formato"]["reflection"] == 1

    def test_task_text_without_block_passes_through(self, monkeypatch):
        """El descarte por `formato` es solo de reflexion: en tarea "ok" pasa."""
        _patch_dspy_completion(monkeypatch, lambda r: ("ok", "stop"), None)
        assert _lm(TASK_MODEL, "task")("hola") == ["ok"]

    @pytest.mark.parametrize(("content", "reason"), EMPTY_CASES)
    def test_reflection_raises_with_cause(self, monkeypatch, caplog, content, reason):
        """SPEC-104 FR-007: un unico WARNING por falla de reflexion (el de
        `FailureTracker.record`); el log de la capa de llamada va a DEBUG."""
        _patch_dspy_completion(monkeypatch, None, lambda r: (content, reason))
        lm = _lm(REFLECTION_MODEL, "reflection")
        with caplog.at_level(logging.DEBUG), pytest.raises(EmptyResponseError) as exc_info:
            _propose(lm)
        assert exc_info.value.role == "reflection"
        assert exc_info.value.finish_reason == reason
        call_layer = [
            r
            for r in caplog.records
            if r.levelno == logging.DEBUG and r.name.startswith("shared.llm")
        ]
        assert [r.getMessage() for r in call_layer] == [
            f"Falla de respuesta (rol=reflection, clase={exc_info.value.failure.clase.value}, "
            f"finish_reason={reason})"
        ]
        warnings = project_warnings(caplog)
        assert len(warnings) == 1
        assert "rol=reflection" in warnings[0].message
        assert f"finish_reason={reason}" in warnings[0].message
        # SPEC-105 FR-004: el uso de tokens de la respuesta fallida se cuenta igual.
        assert get_usage_tracker().snapshot()["reflection"]["calls"] == 1

    @pytest.mark.parametrize(("content", "reason"), EMPTY_CASES)
    def test_task_raises_with_cause(self, monkeypatch, caplog, content, reason):
        _patch_dspy_completion(monkeypatch, lambda r: (content, reason), None)
        lm = _lm(TASK_MODEL, "task")
        # La capa de llamada deja un unico DEBUG (sin duplicar, H-09) y no cuenta
        # (SPEC-104 FR-007, D4): el WARNING lo emite la metrica que conoce el caso.
        with caplog.at_level(logging.DEBUG), pytest.raises(EmptyResponseError) as exc_info:
            lm("hola")
        assert exc_info.value.role == "task"
        assert exc_info.value.finish_reason == reason
        call_layer = [
            r
            for r in caplog.records
            if r.levelno == logging.DEBUG and r.name.startswith("shared.llm")
        ]
        assert [r.getMessage() for r in call_layer] == [
            f"Falla de respuesta (rol=task, clase={exc_info.value.failure.clase.value}, "
            f"finish_reason={reason})"
        ]
        assert project_warnings(caplog) == []
        assert get_failure_tracker().snapshot()["counts"] == {}
        assert get_usage_tracker().snapshot()["task"]["calls"] == 1

    def test_task_empty_reaches_program_without_json_fallback(self, monkeypatch, task_lm_context):
        """La excepcion llega intacta al programa con 1 sola llamada: la falla de
        `CheckedLM` corta el fallback ChatAdapter -> JSONAdapter (SPEC-104 SC-009)."""
        calls = _patch_dspy_completion(monkeypatch, lambda r: (None, "length"), None)
        with pytest.raises(EmptyResponseError) as exc_info:
            _plain_student()(question="q0")
        assert calls["task"] == 1
        assert exc_info.value.failure.clase.value == "presupuesto"

    def test_task_bad_format_is_parse_error_not_empty(self, monkeypatch, task_lm_context):
        """Un error de formato real no se confunde con la respuesta sin texto: sin
        envoltorio es `AdapterParseError`; envuelto es `formato` (FR-010)."""
        _patch_dspy_completion(monkeypatch, lambda r: ("texto sin formato", "stop"), None)
        with pytest.raises(dspy.utils.exceptions.AdapterParseError):
            _plain_student()(question="q0")
        pred = _student()(question="q0")
        assert isinstance(pred, FailedCallPrediction)
        assert pred.failure.clase == FailureClass.formato

    @pytest.mark.parametrize("model", ["openai/gpt-5-mini", "openai/o3-mini"])
    @pytest.mark.parametrize("content", [None, "texto truncado"])
    def test_reasoning_model_length_is_presupuesto_not_configuracion(
        self, monkeypatch, model, content
    ):
        """H-02: en modelos reasoning (que usan `max_completion_tokens` sin
        `max_tokens`), `finish_reason='length'` es `presupuesto`, nunca
        `KeyError`/`configuracion`, sin WARNING duplicado de dspy."""
        calls = 0

        def truncated(request, num_retries, cache=None):
            nonlocal calls
            calls += 1
            return make_completion_response(content, "length")

        patch_litellm_completion(monkeypatch, truncated)
        dspy_lm_logger = logging.getLogger("dspy.clients.lm")
        dspy_records: list[logging.LogRecord] = []

        class _Cap(logging.Handler):
            def emit(self, record):
                dspy_records.append(record)

        handler = _Cap(level=logging.WARNING)
        dspy_lm_logger.addHandler(handler)
        try:
            lm = _lm(model, "task")
            with pytest.raises(LLMCallFailure) as exc_info:
                lm("hola")
        finally:
            dspy_lm_logger.removeHandler(handler)

        assert calls == 1
        assert exc_info.value.failure.clase == FailureClass.presupuesto
        assert exc_info.value.failure.finish_reason == "length"
        assert not get_failure_tracker().aborted
        assert get_usage_tracker().snapshot()["task"]["calls"] == 1
        assert dspy_records == []

    def test_none_response_is_configuracion_with_none_response_cause(self, monkeypatch):
        """H-02: si LiteLLM devuelve `None`, es `configuracion` con causa
        `NoneResponse` (no `TypeError`) y corta fallback."""
        calls = 0

        def return_none(request, num_retries, cache=None):
            nonlocal calls
            calls += 1
            return None

        patch_litellm_completion(monkeypatch, return_none)
        lm = _lm(TASK_MODEL, "task")
        with dspy.context(lm=lm), pytest.raises(LLMCallFailure) as exc_info:
            _plain_student()(question="q0")

        assert calls == 1
        assert exc_info.value.failure.clase == FailureClass.configuracion
        assert exc_info.value.failure.causa == "NoneResponse"
        assert get_failure_tracker().aborted
        assert get_usage_tracker().snapshot()["task"]["calls"] == 0


# ==================== Envoltorio del programa y guardia de metrica ====================


def _fast_gate_signature():
    return {
        "instruction": "Responde.",
        "inputs": [{"name": "ficha", "desc": "Ficha."}],
        "outputs": [
            {"name": n, "desc": "Si/No"}
            for n in ("p1", "p2", "p3", "p4", "p5", "alto_impacto", "razonamiento")
        ]
        + [{"name": "clasificacion", "desc": "Color derivado."}],
    }


class TestTolerateCallFailures:
    def test_keeps_predictors_and_does_not_modify_original(self):
        plain = _plain_student()
        wrapped = tolerate_call_failures(plain)
        assert wrapped is not plain
        assert type(plain) is dspy.Predict
        assert isinstance(wrapped, dspy.Predict)
        assert [n for n, _ in wrapped.named_predictors()] == [
            n for n, _ in plain.named_predictors()
        ]

    def test_idempotent_and_survives_deepcopy(self):
        wrapped = _student()
        assert tolerate_call_failures(wrapped) is wrapped
        assert type(wrapped.deepcopy()) is type(wrapped)
        assert type(wrapped.reset_copy()) is type(wrapped)

    def test_empty_task_returns_failed_prediction(self, monkeypatch, task_lm_context):
        _patch_dspy_completion(monkeypatch, lambda r: ("", "content_filter"), None)
        pred = _student()(question="q0")
        assert isinstance(pred, FailedCallPrediction)
        assert pred.answer is None
        assert pred.failure.clase == FailureClass.filtro_salida
        assert pred.failure.finish_reason == "content_filter"
        assert pred.instructions == {"self": SEED_INSTRUCTION}
        # `forward` no conoce el caso: no cuenta (D4); cuenta la metrica.
        assert get_failure_tracker().snapshot()["attempts"]["task"] == 0

    def test_rule_derived_module_output_fields(self, monkeypatch, task_lm_context):
        _patch_dspy_completion(monkeypatch, lambda r: (None, "length"), None)
        module = tolerate_call_failures(
            DynamicModuleFactory.create_rule_derived_module(_fast_gate_signature())
        )
        pred = module(ficha="x")
        assert isinstance(pred, FailedCallPrediction)
        assert pred.p1 is None and pred.alto_impacto is None
        assert pred.failure.clase == FailureClass.presupuesto

    def test_saved_program_loads_into_plain_module(self, tmp_path):
        signature = _fast_gate_signature()
        wrapped = tolerate_call_failures(DynamicModuleFactory.create_module(signature))
        for _, predictor in wrapped.named_predictors():
            predictor.signature = predictor.signature.with_instructions(VALID_INSTRUCTION)
        path = tmp_path / "optimized_program.json"
        wrapped.save(str(path))

        plain = DynamicModuleFactory.create_module(signature)
        plain.load(str(path))
        assert [p.signature.instructions for _, p in plain.named_predictors()] == [
            VALID_INSTRUCTION
        ]
        assert "FailureTolerant" not in path.read_text()


# ==================== (a) reflexion vacia en dspy.GEPA ====================


class TestReflectionInGepa:
    def test_empty_reflection_skips_iteration(self, monkeypatch, caplog, task_lm_context):
        task = _TaskByInstruction()
        calls = _patch_dspy_completion(monkeypatch, task, lambda r: ("", "content_filter"))
        with caplog.at_level(logging.WARNING):
            result = _run_gepa(_lm(REFLECTION_MODEL, "reflection"))
        assert calls["reflection"] >= 1
        # Ningun candidato nuevo: ni aceptado ni evaluado en el minibatch.
        assert _instructions(result) == [SEED_INSTRUCTION]
        assert task.non_seed_calls == 0
        # SPEC-104 FR-007: la causa queda en el WARNING de `record`, uno por propuesta.
        recorded = [
            r.message
            for r in caplog.records
            if r.levelno == logging.WARNING and r.message.startswith("Falla de LLM: rol=reflection")
        ]
        assert recorded
        assert all("finish_reason=content_filter" in m for m in recorded)
        assert "Respuesta sin texto del LLM (rol=reflection" not in caplog.text

    def test_valid_reflection_creates_candidate(self, monkeypatch, task_lm_context):
        _patch_dspy_completion(
            monkeypatch,
            _TaskByInstruction(),
            lambda r: (f"```\n{VALID_INSTRUCTION}\n```", "stop"),
        )
        result = _run_gepa(_lm(REFLECTION_MODEL, "reflection"))
        assert VALID_INSTRUCTION in _instructions(result)


# ==================== (b) tarea vacia: 0.0 sin cortar la corrida ====================


def _task_empty_on_q1(request):
    prompt = " ".join(str(m.get("content")) for m in request["messages"])
    if "q1" in prompt:
        return None, "length"
    return _task_text("yes"), "stop"


class TestTaskInGepa:
    @pytest.mark.parametrize("capture_traces", [False, True])
    def test_adapter_case_is_ne_and_counted_once(
        self, monkeypatch, caplog, task_lm_context, capture_traces
    ):
        """Baseline cortado por `max_tokens`: `presupuesto` externa, NE con 0.0
        tecnico, un intento por caso y un unico WARNING (FR-004, FR-007)."""
        _patch_dspy_completion(monkeypatch, _task_empty_on_q1, None)
        student, metric = _guarded()
        adapter = DspyAdapter(
            student_module=student,
            metric_fn=metric,
            feedback_map={},
            failure_score=0.0,
            num_threads=1,
        )
        batch = _dataset()
        with caplog.at_level(logging.DEBUG):
            result = adapter.evaluate(
                batch, {"self": SEED_INSTRUCTION}, capture_traces=capture_traces
            )
        assert result.scores == [1.0, 0.0, 1.0, 1.0]
        assert len(result.outputs) == len(batch)
        if capture_traces:
            assert len(result.trajectories) == len(batch)
        failed = result.outputs[1]
        assert isinstance(failed, FailedCallPrediction)
        assert failed.evaluated is False
        assert failed.failure.atribucion == "externa"
        assert failed.failure.case_id == "val:1"
        snapshot = get_failure_tracker().snapshot()
        assert snapshot["counts"] == {"presupuesto": {"task": 1}}
        assert snapshot["attempts"]["task"] == len(batch)
        warnings = project_warnings(caplog)
        assert len(warnings) == 1
        assert "rol=task clave=presupuesto atribucion=externa" in warnings[0].message
        assert "finish_reason=length case_id=val:1" in warnings[0].message

    def test_all_task_budget_failures_abort_by_threshold(self, monkeypatch, task_lm_context):
        """FR-006: `presupuesto` externa en todos los casos supera el umbral de
        tarea (0.05, minimo 20) y la corrida queda abortada sin mas llamadas."""
        calls = _patch_dspy_completion(
            monkeypatch,
            lambda r: (None, "length"),
            lambda r: (f"```\n{VALID_INSTRUCTION}\n```", "stop"),
        )
        _run_gepa(_lm(REFLECTION_MODEL, "reflection"), budget=40)
        snapshot = get_failure_tracker().snapshot()
        assert snapshot["aborted"] is True
        assert snapshot["abort"]["clase"] == "presupuesto"
        assert snapshot["abort"]["rol"] == "task"
        assert snapshot["attempts"]["task"] == 20
        tasks_at_abort = calls["task"]
        with pytest.raises(RunAborted):
            _plain_student()(question="q0")
        assert calls["task"] == tasks_at_abort


# ==================== Evaluate fuera de dspy.GEPA (max_errors por defecto) ====================

EVAL_SIZE = 12  # > dspy.settings.max_errors (10)


def _evaluate(program, metric):
    return Evaluate(devset=_dataset(EVAL_SIZE), metric=metric, num_threads=1)(program)


class TestTaskInEvaluate:
    def test_all_empty_are_ne_without_cancel(self, monkeypatch, task_lm_context):
        assert dspy.settings.max_errors < EVAL_SIZE
        _patch_dspy_completion(monkeypatch, lambda r: (None, "length"), None)
        result = _evaluate(*_guarded())
        assert result.score == 0.0
        # EvaluationResult.results (fix D-016): una entrada por ejemplo (FR-002).
        assert len(result.results) == EVAL_SIZE
        assert all(isinstance(pred, FailedCallPrediction) for _, pred, _ in result.results)
        assert all(pred.evaluated is False for _, pred, _ in result.results)
        assert [score for _, _, score in result.results] == [0.0] * EVAL_SIZE
        assert get_failure_tracker().snapshot()["counts"] == {"presupuesto": {"task": EVAL_SIZE}}

    def test_mixed_empty_only_failed_cases_are_ne(self, monkeypatch, task_lm_context):
        _patch_dspy_completion(monkeypatch, _task_empty_on_q1, None)
        result = _evaluate(*_guarded())
        empty = sum("q1" in f"q{i}" for i in range(EVAL_SIZE))  # q1, q10, q11
        assert len(result.results) == EVAL_SIZE
        ne = [ex.case_id for ex, pred, _ in result.results if not getattr(pred, "evaluated", True)]
        assert ne == ["val:1", "val:10", "val:11"]
        assert result.score == pytest.approx(100.0 * (EVAL_SIZE - empty) / EVAL_SIZE)

    def test_guard_unwrapped_program_is_cancelled(self, monkeypatch, task_lm_context):
        """Sin envoltorio la tarea vacia cuenta para max_errors (B-2c-1)."""
        _patch_dspy_completion(monkeypatch, lambda r: (None, "length"), None)
        with pytest.raises(Exception, match="Execution cancelled"):
            _evaluate(_plain_student(), _metric)

    def test_unclassified_error_aborts_after_one_call(self, monkeypatch, task_lm_context):
        """Una excepcion no clasificada es `configuracion` (regla 3): 1 llamada
        HTTP, se registra una vez y aborta; los casos siguientes no llaman."""

        def broken(request):
            raise RuntimeError("fallo inesperado")

        calls = _patch_dspy_completion(monkeypatch, broken, None)
        with pytest.raises(Exception, match="Execution cancelled"):
            _evaluate(*_guarded())
        assert calls["task"] == 1
        snapshot = get_failure_tracker().snapshot()
        assert snapshot["counts"] == {"configuracion": {"task": 1}}
        assert snapshot["abort"]["clase"] == "configuracion"


class TestReflexioDeclarativaWrapsProgram:
    def test_create_module_and_metric_wraps_student_and_metric(self, monkeypatch):
        from dspy_gepa_poc import reflexio_declarativa as rd

        orchestrator = object.__new__(rd.ReflexioDeclarativa)
        plain = _plain_student()

        def fake_build(self):
            self.student = plain
            self.metric = _metric

        monkeypatch.setattr(rd.ReflexioDeclarativa, "_build_module_and_metric", fake_build)
        orchestrator.create_module_and_metric()

        assert orchestrator.student is not plain
        assert isinstance(orchestrator.student, dspy.Predict)
        gold = dspy.Example(case_id="val:0", question="q0", answer="yes").with_inputs("question")
        failed = FailedCallPrediction(
            EmptyResponseError("task", "length", FailureClass.presupuesto).failure,
            {"self": SEED_INSTRUCTION},
            ["answer"],
        )
        # Prediccion del baseline: atribucion externa sin llamar al LLM.
        assert orchestrator.metric(gold, failed) == 0.0
        assert failed.failure.atribucion == "externa"
        assert orchestrator.metric(gold, dspy.Prediction(answer="yes")) == 1.0
        assert get_failure_tracker().snapshot()["attempts"]["task"] == 2
