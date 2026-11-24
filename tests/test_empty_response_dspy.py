"""
SPEC-103 FR-009 (2c) y SPEC-104 (2a): respuesta sin texto en el camino DSPy.

`LLMConfig.get_dspy_lm()` devuelve un `CheckedLM` (D8). Se verifica sin red,
contra dspy 3.2.1 y GEPA 0.0.27, interceptando `litellm_completion` de
`dspy.clients.lm`:

- reflexion: `CheckedLM` lanza `EmptyResponseError`; `dspy.GEPA` saltea la
  iteracion y no crea un candidato con instruccion vacia.
- tarea (RESOLUCION B-2c-1): `CheckedLM` tambien lanza; el envoltorio de
  `dspy_gepa_poc/empty_response.py` la convierte en prediccion fallida con 0.0
  en las dos rutas de `DspyAdapter.evaluate`, en `dspy.GEPA` y en `Evaluate`
  (sin "Execution cancelled" con mas de `max_errors` vacios), mientras un error
  tecnico real sigue contando para `max_errors`.
- SPEC-104 (2b): en reflexion la propuesta sin bloque de instruccion es
  `formato` y la respuesta sin texto deja un unico WARNING (el de
  `FailureTracker.record`); el detalle esta en `tests/test_reflection_guard.py`.
"""

import logging

import dspy
import pytest
from dspy.evaluate import Evaluate
from dspy.teleprompt.gepa.gepa_utils import DspyAdapter
from litellm import ModelResponse

from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory
from dspy_gepa_poc.empty_response import (
    EmptyResponsePrediction,
    tolerate_empty_responses,
    zero_on_empty_response,
)
from dspy_gepa_poc.metrics import create_dynamic_metric, create_dynamic_metric_with_feedback
from shared.llm import (
    EmptyResponseError,
    FailureClass,
    LLMCallFailure,
    LLMConfig,
    get_failure_tracker,
)
from shared.llm.dspy_lm import CheckedLM

TASK_MODEL = "openai/gpt-4o-mini"
REFLECTION_MODEL = "openai/gpt-4o"
SEED_INSTRUCTION = "Answer the question."
VALID_INSTRUCTION = "Always answer yes."
# LiteLLM normaliza el `stop_reason` "refusal" de Anthropic a "content_filter".
EMPTY_CASES = [(None, "length"), ("", "content_filter"), ("  \n", "stop")]


def _model_response(content, finish_reason="stop"):
    return ModelResponse(
        model="fake",
        choices=[
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content},
            }
        ],
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )


def _task_text(answer):
    return f"[[ ## answer ## ]]\n{answer}\n\n[[ ## completed ## ]]"


def _patch_dspy_completion(monkeypatch, task, reflection):
    """`task`/`reflection`: callables (request) -> (content, finish_reason)."""
    calls = {"task": 0, "reflection": 0}

    def fake_completion(request, num_retries, cache=None):
        role = "reflection" if request["model"] == REFLECTION_MODEL else "task"
        calls[role] += 1
        content, reason = (reflection if role == "reflection" else task)(request)
        return _model_response(content, reason)

    monkeypatch.setattr("dspy.clients.lm.litellm_completion", fake_completion)
    return calls


def _lm(model, role, *, checked=True):
    config = LLMConfig(model=model, api_key="key", role=role, cache=False)
    if checked:
        return config.get_dspy_lm()
    return dspy.LM(**{**config.to_kwargs(), "cache": False})


def _dataset(n=4):
    return [dspy.Example(question=f"q{i}", answer="yes").with_inputs("question") for i in range(n)]


def _metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
    return float(getattr(pred, "answer", None) == gold.answer)


def _plain_student():
    return dspy.Predict(dspy.Signature("question -> answer", SEED_INSTRUCTION))


def _student():
    return tolerate_empty_responses(_plain_student())


_guarded_metric = zero_on_empty_response(_metric)


def _run_gepa(reflection_lm, budget=16):
    optimizer = dspy.GEPA(
        metric=_guarded_metric,
        reflection_lm=reflection_lm,
        max_metric_calls=budget,
        reflection_minibatch_size=2,
        track_stats=True,
        seed=0,
    )
    data = _dataset()
    return optimizer.compile(_student(), trainset=data, valset=data)


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


# ==================== CheckedLM aislado ====================


class TestCheckedLM:
    def test_get_dspy_lm_returns_checked_lm_with_role(self):
        lm = _lm(REFLECTION_MODEL, "reflection")
        assert isinstance(lm, CheckedLM)
        assert isinstance(lm, dspy.LM)
        assert lm.role == "reflection"

    def test_from_env_role(self, mock_env):
        assert LLMConfig.from_env("reflection").get_dspy_lm().role == "reflection"
        assert LLMConfig.from_env("task").get_dspy_lm().role == "task"

    def test_copy_keeps_role(self):
        assert _lm(REFLECTION_MODEL, "reflection").copy(rollout_id=1).role == "reflection"

    def test_text_passes_through(self, monkeypatch):
        """SPEC-104 FR-005: en reflexion pasa la propuesta con bloque de
        instruccion; el texto sin bloque se descarta como `formato`."""
        proposal = f"```\n{VALID_INSTRUCTION}\n```"
        _patch_dspy_completion(monkeypatch, None, lambda r: (proposal, "stop"))
        assert _lm(REFLECTION_MODEL, "reflection")("hola") == [proposal]

    def test_reflection_without_block_is_format_failure(self, monkeypatch):
        _patch_dspy_completion(monkeypatch, None, lambda r: ("ok", "stop"))
        with pytest.raises(LLMCallFailure) as exc_info:
            _lm(REFLECTION_MODEL, "reflection")("hola")
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
            lm("hola")
        assert exc_info.value.role == "reflection"
        assert exc_info.value.finish_reason == reason
        call_layer = [r for r in caplog.records if "rol=reflection, finish_reason=" in r.message]
        assert [(r.levelno, r.message) for r in call_layer] == [
            (logging.DEBUG, f"Respuesta sin texto del LLM (rol=reflection, finish_reason={reason})")
        ]
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert "rol=reflection" in warnings[0].message
        assert f"finish_reason={reason}" in warnings[0].message
        # La llamada queda en history: su uso de tokens se sigue contando.
        assert len(lm.history) == 1

    @pytest.mark.parametrize(("content", "reason"), EMPTY_CASES)
    def test_task_raises_with_cause(self, monkeypatch, caplog, content, reason):
        _patch_dspy_completion(monkeypatch, lambda r: (content, reason), None)
        lm = _lm(TASK_MODEL, "task")
        # La capa de llamada va a DEBUG (SPEC-104 FR-007, 3c); el WARNING de la tarea de DSPy
        # lo emite la metrica que cuenta (3e).
        with caplog.at_level(logging.DEBUG), pytest.raises(EmptyResponseError) as exc_info:
            lm("hola")
        assert exc_info.value.role == "task"
        assert exc_info.value.finish_reason == reason
        assert f"rol=task, finish_reason={reason}" in caplog.text
        assert len(lm.history) == 1

    def test_task_empty_reaches_program_without_json_fallback(self, monkeypatch, task_lm_context):
        """La excepcion llega intacta al programa con 1 sola llamada: la falla de
        `CheckedLM` corta el fallback ChatAdapter -> JSONAdapter (SPEC-104 SC-009)."""
        calls = _patch_dspy_completion(monkeypatch, lambda r: (None, "length"), None)
        with pytest.raises(EmptyResponseError) as exc_info:
            _plain_student()(question="q0")
        assert calls["task"] == 1
        assert exc_info.value.failure.clase.value == "presupuesto"

    def test_task_bad_format_is_still_parse_error(self, monkeypatch, task_lm_context):
        """Un error de formato real no se confunde con la respuesta sin texto."""
        _patch_dspy_completion(monkeypatch, lambda r: ("texto sin formato", "stop"), None)
        with pytest.raises(dspy.utils.exceptions.AdapterParseError):
            _student()(question="q0")


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


class TestTolerateEmptyResponses:
    def test_keeps_predictors_and_does_not_modify_original(self):
        plain = _plain_student()
        wrapped = tolerate_empty_responses(plain)
        assert wrapped is not plain
        assert type(plain) is dspy.Predict
        assert isinstance(wrapped, dspy.Predict)
        assert [n for n, _ in wrapped.named_predictors()] == [
            n for n, _ in plain.named_predictors()
        ]

    def test_idempotent_and_survives_deepcopy(self):
        wrapped = _student()
        assert tolerate_empty_responses(wrapped) is wrapped
        assert type(wrapped.deepcopy()) is type(wrapped)
        assert type(wrapped.reset_copy()) is type(wrapped)

    def test_empty_task_returns_failed_prediction(self, monkeypatch, task_lm_context):
        _patch_dspy_completion(monkeypatch, lambda r: ("", "content_filter"), None)
        pred = _student()(question="q0")
        assert isinstance(pred, EmptyResponsePrediction)
        assert pred.answer is None
        assert pred.empty_error.finish_reason == "content_filter"

    def test_rule_derived_module_output_fields(self, monkeypatch, task_lm_context):
        _patch_dspy_completion(monkeypatch, lambda r: (None, "length"), None)
        module = tolerate_empty_responses(
            DynamicModuleFactory.create_rule_derived_module(_fast_gate_signature())
        )
        pred = module(ficha="x")
        assert isinstance(pred, EmptyResponsePrediction)
        assert pred.p1 is None and pred.alto_impacto is None

    def test_saved_program_loads_into_plain_module(self, tmp_path):
        signature = _fast_gate_signature()
        wrapped = tolerate_empty_responses(DynamicModuleFactory.create_module(signature))
        for _, predictor in wrapped.named_predictors():
            predictor.signature = predictor.signature.with_instructions(VALID_INSTRUCTION)
        path = tmp_path / "optimized_program.json"
        wrapped.save(str(path))

        plain = DynamicModuleFactory.create_module(signature)
        plain.load(str(path))
        assert [p.signature.instructions for _, p in plain.named_predictors()] == [
            VALID_INSTRUCTION
        ]
        assert "EmptyTolerant" not in path.read_text()


class TestZeroOnEmptyResponse:
    def _empty_pred(self):
        return EmptyResponsePrediction(EmptyResponseError("task", "length"), ["p1", "otros"])

    def test_empty_gold_would_get_credit_without_guard(self):
        """`score_field` trata None como "": sin guardia, gold vacio da credito."""
        gold = dspy.Example(p1="", otros="")
        metric = create_dynamic_metric_with_feedback(["p1", "otros"])
        assert metric(gold, self._empty_pred()) == 1.0
        assert zero_on_empty_response(metric)(gold, self._empty_pred()) == 0.0

    def test_simple_metric_guarded(self):
        gold = dspy.Example(p1="none", otros="")
        metric = create_dynamic_metric(["p1"], match_mode="normalized")
        assert metric(gold, self._empty_pred()) == 1.0  # str(None) == "None"
        assert zero_on_empty_response(metric)(gold, self._empty_pred()) == 0.0

    def test_feedback_path_returns_dict_with_cause(self):
        gold = dspy.Example(p1="Si", otros="")
        guarded = zero_on_empty_response(create_dynamic_metric_with_feedback(["p1", "otros"]))
        result = guarded(gold, self._empty_pred(), None, "self", [])
        assert result["score"] == 0.0
        assert "rol=task, finish_reason=length" in result["feedback"]
        assert guarded(gold, self._empty_pred(), pred_name="self")["score"] == 0.0

    def test_three_arg_metric_and_normal_pred_pass_through(self):
        def three_arg(gold, pred, trace=None):
            return float(pred.answer.lower() == gold.answer)

        guarded = zero_on_empty_response(three_arg)
        gold = dspy.Example(answer="yes")
        assert guarded(gold, dspy.Prediction(answer="YES")) == 1.0
        empty = EmptyResponsePrediction(EmptyResponseError("task"), ["answer"])
        assert guarded(gold, empty, None) == 0.0


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

    def test_guard_plain_lm_evaluates_empty_candidate(self, monkeypatch, task_lm_context):
        """Guardia de GEPA sin CheckedLM: el texto vacio se evalua como candidato.

        Es el gasto de evaluaciones que FR-009 evita. Si una actualizacion de
        GEPA/DSPy (D-018) cambia esto, revisar D8 y FR-009.
        """
        task = _TaskByInstruction()
        _patch_dspy_completion(monkeypatch, task, lambda r: ("", "stop"))
        _run_gepa(_lm(REFLECTION_MODEL, "reflection", checked=False))
        assert task.non_seed_calls > 0

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
    def test_adapter_scores_zero_and_keeps_length(
        self, monkeypatch, caplog, task_lm_context, capture_traces
    ):
        _patch_dspy_completion(monkeypatch, _task_empty_on_q1, None)
        adapter = DspyAdapter(
            student_module=_student(),
            metric_fn=_guarded_metric,
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
        assert "rol=task, finish_reason=length" in caplog.text

    def test_all_task_empty_does_not_stop_gepa(self, monkeypatch, caplog, task_lm_context):
        _patch_dspy_completion(
            monkeypatch,
            lambda r: (None, "length"),
            lambda r: (f"```\n{VALID_INSTRUCTION}\n```", "stop"),
        )
        with caplog.at_level(logging.DEBUG):
            result = _run_gepa(_lm(REFLECTION_MODEL, "reflection"), budget=24)
        assert result.detailed_results.val_aggregate_scores[0] == 0.0
        assert result.detailed_results.total_metric_calls >= 24
        assert "rol=task, finish_reason=length" in caplog.text


# ==================== Evaluate fuera de dspy.GEPA (max_errors por defecto) ====================

EVAL_SIZE = 12  # > dspy.settings.max_errors (10)


def _evaluate(program, metric=_guarded_metric):
    return Evaluate(devset=_dataset(EVAL_SIZE), metric=metric, num_threads=1)(program)


class TestTaskInEvaluate:
    def test_all_empty_scores_zero_without_cancel(self, monkeypatch, task_lm_context):
        assert dspy.settings.max_errors < EVAL_SIZE
        _patch_dspy_completion(monkeypatch, lambda r: (None, "length"), None)
        result = _evaluate(_student())
        assert result.score == 0.0
        # EvaluationResult.results (fix D-016): una entrada por ejemplo.
        assert len(result.results) == EVAL_SIZE
        assert all(isinstance(pred, EmptyResponsePrediction) for _, pred, _ in result.results)
        assert [score for _, _, score in result.results] == [0.0] * EVAL_SIZE

    def test_mixed_empty_counts_as_zero(self, monkeypatch, task_lm_context):
        _patch_dspy_completion(monkeypatch, _task_empty_on_q1, None)
        result = _evaluate(_student())
        empty = sum("q1" in f"q{i}" for i in range(EVAL_SIZE))  # q1, q10, q11
        assert result.score == pytest.approx(100.0 * (EVAL_SIZE - empty) / EVAL_SIZE)
        assert len(result.results) == EVAL_SIZE

    def test_guard_unwrapped_program_is_cancelled(self, monkeypatch, task_lm_context):
        """Sin envoltorio la tarea vacia cuenta para max_errors (B-2c-1)."""
        _patch_dspy_completion(monkeypatch, lambda r: (None, "length"), None)
        with pytest.raises(Exception, match="Execution cancelled"):
            _evaluate(_plain_student(), _metric)

    def test_technical_error_still_counts_for_max_errors(self, monkeypatch, task_lm_context):
        def broken(request):
            raise RuntimeError("fallo de red simulado")

        _patch_dspy_completion(monkeypatch, broken, None)
        with pytest.raises(Exception, match="Execution cancelled"):
            _evaluate(_student())


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
        empty = EmptyResponsePrediction(EmptyResponseError("task"), ["answer"])
        gold = dspy.Example(answer="yes")
        assert orchestrator.metric(gold, empty) == 0.0
        assert orchestrator.metric(gold, dspy.Prediction(answer="yes")) == 1.0
