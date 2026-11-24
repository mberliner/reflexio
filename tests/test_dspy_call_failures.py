"""
SPEC-104 3e: fallas clasificadas de la tarea en `dspy_gepa_poc` (D5, D6).

Verifica, contra dspy 3.2.1 y GEPA 0.0.27 y sin red, el comportamiento que
fija la spec para la tarea de DSPy:

- FR-002 / SC-001: con fallas inyectadas de cada clase (payloads HTTP reales de
  `tests/litellm_failure_payloads.py`) ningun caso desaparece: cada uno queda
  evaluado o NE, con su clase, y se cuenta una vez.
- FR-004: `entrada`/`presupuesto` de un candidato se atribuyen contra el
  baseline (una ejecucion por caso, cacheada salvo `infraestructura`), con el
  `finish_reason` de ambas llamadas; el baseline no cuenta ni ensucia la traza.
- FR-007: una sola falla registrada por caso (un WARNING), aunque haya fallback
  de adapters, copias de `dspy.GEPA` o `bootstrap_trace_data`.
- FR-010: `AdapterParseError` tras el fallback es `formato` (score 0).
- FR-012 / SC-008: un caso NE nunca llega al Profesor como error del prompt.

Las respuestas 200 salen de `make_completion_response` (`tests/conftest.py`) y
las fallas de LiteLLM son sus excepciones reales.
"""

from __future__ import annotations

import logging
import threading

import dspy
import litellm
import pytest
from dspy.evaluate import Evaluate
from dspy.teleprompt.gepa.gepa_utils import DspyAdapter

from dspy_gepa_poc.call_failures import (
    FailedCallPrediction,
    guard_program_and_metric,
    tolerate_call_failures,
)
from shared.llm import FailureClass, LLMConfig, LLMFailure, RunAborted, get_failure_tracker
from tests.conftest import make_completion_response, project_warnings
from tests.litellm_failure_payloads import ALL_FAILURE_CASES, PROVIDER_KWARGS, FailurePayloadCase
from tests.test_litellm_failure_mapping import intercept_httpx

TASK_MODEL = "openai/gpt-4o-mini"
REFLECTION_MODEL = "openai/gpt-4o"
SEED = "Answer the question."
CANDIDATE = "Answer briefly."
OTHER_CANDIDATE = "Answer with one word."
VALID_PROPOSAL = f"```\n{CANDIDATE}\n```"

FAILING_CASES: tuple[FailurePayloadCase, ...] = tuple(
    c for c in ALL_FAILURE_CASES if c.spec104_class != "ok"
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("shared.llm.call.time.sleep", lambda s: None)


def _lm(model: str = TASK_MODEL, role: str = "task"):
    return LLMConfig(model=model, api_key="key", role=role, cache=False).get_dspy_lm()


@pytest.fixture
def task_lm():
    with dspy.context(lm=_lm()):
        yield


def _text(**fields: str) -> str:
    body = "".join(f"[[ ## {k} ## ]]\n{v}\n\n" for k, v in fields.items())
    return body + "[[ ## completed ## ]]"


def _ok(**fields: str):
    return make_completion_response(_text(**fields), "stop")


def _system(request) -> str:
    return str(request["messages"][0]["content"])


def _user(request) -> str:
    return " ".join(str(m.get("content")) for m in request["messages"][1:])


class FakeLLM:
    """`litellm_completion` de `dspy.clients.lm` por instruccion y caso.

    `rules[instruccion]` es un callable `(texto) -> respuesta | excepcion`, con el
    texto de usuario (o el prompt completo si `full_text`). Registra las llamadas
    por instruccion (las del baseline son las de `SEED`).
    """

    def __init__(self, rules, reflection=None, full_text=False):
        self.rules = rules
        self.reflection = reflection
        self.full_text = full_text
        self.calls: dict[str, int] = {}
        self.reflection_prompts: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, request, num_retries, cache=None):
        if request["model"] == REFLECTION_MODEL:
            self.reflection_prompts.append(" ".join(str(m["content"]) for m in request["messages"]))
            return make_completion_response(self.reflection or VALID_PROPOSAL, "stop")
        system = _system(request)
        instruction = next(i for i in self.rules if i in system)
        with self._lock:
            self.calls[instruction] = self.calls.get(instruction, 0) + 1
        text = f"{system} {_user(request)}" if self.full_text else _user(request)
        result = self.rules[instruction](text)
        if isinstance(result, Exception):
            raise result
        return result

    def install(self, monkeypatch):
        monkeypatch.setattr("dspy.clients.lm.litellm_completion", self)
        return self


def _answer_yes(_user_text):
    return _ok(answer="yes")


def _length_on_q1(user_text):
    if "q1" in user_text:
        return make_completion_response(None, "length")
    return _ok(answer="yes")


def _content_policy(_user_text):
    return litellm.ContentPolicyViolationError(
        message="blocked by policy", model=TASK_MODEL, llm_provider="openai"
    )


def _policy_on_q1(user_text):
    return _content_policy(user_text) if "q1" in user_text else _ok(answer="yes")


def _server_error(_user_text):
    return litellm.InternalServerError(
        message="server error", llm_provider="openai", model=TASK_MODEL
    )


def _dataset(n: int = 4, split: str = "val"):
    return [
        dspy.Example(case_id=f"{split}:{i}", question=f"q{i}", answer="yes").with_inputs("question")
        for i in range(n)
    ]


def _metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
    score = float(getattr(pred, "answer", None) == gold.answer)
    if pred_name is not None or pred_trace is not None:
        return dspy.Prediction(score=score, feedback="ok" if score else "respuesta incorrecta")
    return score


def _seed_student():
    return dspy.Predict(dspy.Signature("question -> answer", SEED))


def _adapter(student, metric):
    return DspyAdapter(
        student_module=student, metric_fn=metric, feedback_map={}, failure_score=0.0, num_threads=1
    )


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


# ==================== SC-001: cada clase, payloads HTTP reales ====================


def _evaluate_payload(case: FailurePayloadCase):
    cfg = LLMConfig(**PROVIDER_KWARGS[case.provider], role="task", cache=False)
    student, metric = guard_program_and_metric(_seed_student(), _metric)
    devset = _dataset(1)
    with dspy.context(lm=cfg.get_dspy_lm()), intercept_httpx(case) as calls:
        result = Evaluate(devset=devset, metric=metric, num_threads=1)(student)
    return result, len(calls)


class TestEveryClassIsCountedOnce:
    @pytest.mark.parametrize("case", FAILING_CASES, ids=lambda c: c.id)
    def test_case_is_ne_with_its_class(self, case, caplog):
        with caplog.at_level(logging.DEBUG):
            result, calls = _evaluate_payload(case)

        assert len(result.results) == 1
        example, pred, score = result.results[0]
        assert isinstance(pred, FailedCallPrediction), f"{case.id}: {pred!r}"
        assert pred.failure.clase.value == case.spec104_class
        assert pred.failure.case_id == example.case_id
        # Programa baseline: atribucion externa sin llamar al baseline otra vez.
        assert pred.attributed
        expected_attr = "externa" if case.spec104_class in ("entrada", "presupuesto") else None
        assert pred.failure.atribucion == expected_attr
        assert pred.evaluated is False
        assert score == 0.0
        attempts = 4 if case.spec104_class == "infraestructura" else 1
        assert calls == attempts

        snapshot = get_failure_tracker().snapshot()
        assert sum(sum(by_role.values()) for by_role in snapshot["counts"].values()) == 1
        assert snapshot["attempts"]["task"] == 1
        warnings = project_warnings(caplog, include_errors=False)
        assert len(warnings) == 1, [r.message for r in warnings]
        assert f"case_id={example.case_id}" in warnings[0].message
        assert snapshot["aborted"] is (case.spec104_class == "configuracion")


# ==================== FR-004: atribucion contra el baseline ====================


class TestAttribution:
    @pytest.mark.parametrize("capture_traces", [False, True])
    def test_budget_of_candidate_scores_zero(self, monkeypatch, caplog, task_lm, capture_traces):
        fake = FakeLLM({SEED: _answer_yes, CANDIDATE: _length_on_q1}).install(monkeypatch)
        adapter = _adapter(*guard_program_and_metric(_seed_student(), _metric))
        with caplog.at_level(logging.DEBUG):
            result = adapter.evaluate(_dataset(), {"self": CANDIDATE}, capture_traces)

        assert result.scores == [1.0, 0.0, 1.0, 1.0]
        failed = result.outputs[1]
        assert failed.failure.clase == FailureClass.presupuesto
        assert failed.failure.atribucion == "candidato"
        assert failed.evaluated is True
        assert failed.failure.finish_reason == "length"
        assert failed.failure.baseline_finish_reason == "stop"
        assert fake.calls[SEED] == 1
        snapshot = get_failure_tracker().snapshot()
        assert snapshot["counts"] == {"presupuesto_candidato": {"task": 1}}
        # La llamada de atribucion no cuenta como intento (D5).
        assert snapshot["attempts"]["task"] == 4
        [warning] = project_warnings(caplog)
        assert "clave=presupuesto_candidato atribucion=candidato" in warning.message
        assert "finish_reason=length case_id=val:1 baseline_finish_reason=stop" in warning.message
        if capture_traces:
            # El baseline corre con su propia traza: la del caso fallido queda vacia.
            assert result.trajectories[1]["trace"] == []
            assert all(len(t["trace"]) == 1 for i, t in enumerate(result.trajectories) if i != 1)

    def test_budget_also_in_baseline_is_external(self, monkeypatch, task_lm):
        FakeLLM({SEED: _length_on_q1, CANDIDATE: _length_on_q1}).install(monkeypatch)
        adapter = _adapter(*guard_program_and_metric(_seed_student(), _metric))
        result = adapter.evaluate(_dataset(), {"self": CANDIDATE})

        failure = result.outputs[1].failure
        assert (failure.clase, failure.atribucion) == (FailureClass.presupuesto, "externa")
        assert failure.baseline_finish_reason == "length"
        assert result.outputs[1].evaluated is False
        assert get_failure_tracker().snapshot()["counts"] == {"presupuesto": {"task": 1}}

    def test_input_rejection_candidate_vs_data(self, monkeypatch, task_lm):
        FakeLLM(
            {SEED: _policy_on_q1, CANDIDATE: _content_policy, OTHER_CANDIDATE: _policy_on_q1}
        ).install(monkeypatch)
        adapter = _adapter(*guard_program_and_metric(_seed_student(), _metric))
        by_candidate = adapter.evaluate(_dataset(), {"self": CANDIDATE})
        by_other = adapter.evaluate(_dataset(), {"self": OTHER_CANDIDATE})

        keys = [p.failure.atribucion for p in by_candidate.outputs]
        assert keys == ["candidato", "externa", "candidato", "candidato"]
        assert [p.evaluated for p in by_candidate.outputs] == [True, False, True, True]
        assert by_other.outputs[1].failure.atribucion == "externa"
        snapshot = get_failure_tracker().snapshot()
        assert snapshot["counts"] == {"entrada_candidato": {"task": 3}, "entrada_dato": {"task": 1}}
        # entrada_dato cuenta casos unicos: q1 fallo con los dos candidatos.
        assert snapshot["entrada_dato"] == ["val:1"]

    def test_baseline_failing_by_other_class_takes_its_class(self, monkeypatch, task_lm):
        """FR-004: si el baseline falla por otra clase, el caso queda NE con esa
        clase; `infraestructura` no se cachea y se reintenta la proxima vez."""
        fake = FakeLLM({SEED: _server_error, CANDIDATE: _length_on_q1}).install(monkeypatch)
        adapter = _adapter(*guard_program_and_metric(_seed_student(), _metric))
        first = adapter.evaluate(_dataset(), {"self": CANDIDATE})
        second = adapter.evaluate(_dataset(), {"self": CANDIDATE})

        for result in (first, second):
            failure = result.outputs[1].failure
            assert failure.clase == FailureClass.infraestructura
            assert failure.atribucion is None
            assert result.outputs[1].evaluated is False
        assert fake.calls[SEED] == 2 * 4  # sin cache: 1 + 3 reintentos por evaluacion
        assert get_failure_tracker().snapshot()["counts"] == {"infraestructura": {"task": 2}}

    def test_baseline_parse_error_is_no_layer1_failure(self, monkeypatch, task_lm):
        FakeLLM(
            {
                SEED: lambda u: make_completion_response("texto libre", "stop"),
                CANDIDATE: _length_on_q1,
            }
        ).install(monkeypatch)
        adapter = _adapter(*guard_program_and_metric(_seed_student(), _metric))
        result = adapter.evaluate(_dataset(), {"self": CANDIDATE})
        assert result.outputs[1].failure.atribucion == "candidato"
        assert result.outputs[1].failure.baseline_finish_reason == "stop"

    def test_baseline_cached_per_case_across_candidates_and_threads(self, monkeypatch, task_lm):
        def by_case(user_text):
            reason = "length" if "q3" in user_text else "stop"
            return make_completion_response(_text(answer="yes"), reason)

        always_cut = lambda u: make_completion_response(None, "length")  # noqa: E731
        fake = FakeLLM({SEED: by_case, CANDIDATE: always_cut, OTHER_CANDIDATE: always_cut})
        fake.install(monkeypatch)
        student, metric = guard_program_and_metric(_seed_student(), _metric)
        devset = _dataset(8)
        results = []
        for instruction in (CANDIDATE, OTHER_CANDIDATE):
            program = _adapter(student, metric).build_program({"self": instruction})
            results.append(Evaluate(devset=devset, metric=metric, num_threads=4)(program))

        assert fake.calls[SEED] == len(devset)
        for result in results:
            by_id = {ex.case_id: pred.failure for ex, pred, _ in result.results}
            assert by_id["val:3"].atribucion == "externa"
            assert by_id["val:3"].baseline_finish_reason == "length"
            others = [f for cid, f in by_id.items() if cid != "val:3"]
            assert all(f.atribucion == "candidato" for f in others)
            assert all(f.baseline_finish_reason == "stop" for f in others)


# ==================== FR-010: formato tras el fallback de adapters ====================


class TestFormat:
    def test_parse_error_is_format_scored_zero_with_single_warning(
        self, monkeypatch, caplog, task_lm
    ):
        fake = FakeLLM({SEED: lambda u: make_completion_response("sin campos", "stop")})
        fake.install(monkeypatch)
        student, metric = guard_program_and_metric(_seed_student(), _metric)
        # El logger de dspy no propaga a la raiz (caplog): se escucha directo.
        adapter_logger = logging.getLogger("dspy.adapters.json_adapter")
        adapter_records = _ListHandler()
        adapter_logger.addHandler(adapter_records)
        try:
            with caplog.at_level(logging.DEBUG):
                result = Evaluate(devset=_dataset(1), metric=metric, num_threads=1)(student)
        finally:
            adapter_logger.removeHandler(adapter_records)

        _, pred, score = result.results[0]
        assert pred.failure.clase == FailureClass.formato
        assert pred.failure.causa == "AdapterParseError"
        assert pred.evaluated is True
        assert score == 0.0
        assert fake.calls[SEED] > 1  # hubo fallback ChatAdapter -> JSONAdapter
        assert get_failure_tracker().snapshot()["counts"] == {"formato": {"task": 1}}
        # El aviso intermedio del fallback va a DEBUG (FR-007).
        fallback = [r for r in adapter_records.records if "structured output" in r.getMessage()]
        assert fallback and all(r.levelno == logging.DEBUG for r in fallback)
        [warning] = project_warnings(caplog)
        assert "clave=formato" in warning.message

    def test_layer1_configuracion_during_json_adapter_fallback_is_counted_once(
        self, monkeypatch, caplog, task_lm
    ):
        """H-04: si `JSONAdapter` (fallback tras `AdapterParseError`) recibe una falla
        `configuracion`, no cae a `json_object`: se registra 1 vez con 1 WARNING y 1 ERROR."""
        calls: list[object] = []

        def fake_completion(request, num_retries, cache=None):
            calls.append(request.get("response_format"))
            if len(calls) == 1:
                return make_completion_response("sin marcadores dspy", "stop")
            raise litellm.AuthenticationError(
                message="bad key", llm_provider="openai", model=TASK_MODEL
            )

        monkeypatch.setattr("dspy.clients.lm.litellm_completion", fake_completion)
        student, metric = guard_program_and_metric(_seed_student(), _metric)
        with caplog.at_level(logging.DEBUG):
            result = Evaluate(devset=_dataset(1), metric=metric, num_threads=1)(student)

        assert len(calls) == 2
        _, pred, score = result.results[0]
        assert isinstance(pred, FailedCallPrediction)
        assert pred.failure.clase == FailureClass.configuracion
        assert pred.failure.case_id == "val:0"
        assert score == 0.0
        snapshot = get_failure_tracker().snapshot()
        assert snapshot["counts"] == {"configuracion": {"task": 1}}
        assert snapshot["attempts"]["task"] == 1
        assert snapshot["abort"]["conteo"] == 1
        assert snapshot["abort"]["intentos"] == 1
        warnings = project_warnings(caplog, include_errors=False)
        errors = [
            r for r in caplog.records if r.levelno == logging.ERROR and r.name.startswith("shared.")
        ]
        assert len(warnings) == 1 and "clave=configuracion" in warnings[0].message
        assert len(errors) == 1 and "conteo=1/1" in errors[0].message

    def test_layer1_presupuesto_during_json_adapter_fallback_does_not_retry_json_object(
        self, monkeypatch, task_lm
    ):
        """H-04: falla de capa 1 (`presupuesto`) en structured output de `JSONAdapter`
        no dispara un tercer intento con `json_object` (SC-009)."""
        calls: list[object] = []

        def fake_completion(request, num_retries, cache=None):
            calls.append(request.get("response_format"))
            if len(calls) == 1:
                return make_completion_response("sin marcadores dspy", "stop")
            return make_completion_response(None, "length")

        monkeypatch.setattr("dspy.clients.lm.litellm_completion", fake_completion)
        student, metric = guard_program_and_metric(_seed_student(), _metric)
        result = Evaluate(devset=_dataset(1), metric=metric, num_threads=1)(student)

        assert len(calls) == 2
        _, pred, _ = result.results[0]
        assert isinstance(pred, FailedCallPrediction)
        assert pred.failure.clase == FailureClass.presupuesto
        assert get_failure_tracker().snapshot()["counts"] == {"presupuesto": {"task": 1}}


# ==================== FR-012: feedback de la metrica ====================


def _failed(failure: LLMFailure, instructions=None):
    return FailedCallPrediction(failure, instructions or {"self": SEED}, ["answer"])


class TestFeedback:
    def _metric(self):
        return guard_program_and_metric(_seed_student(), _metric)[1]

    def test_ne_feedback_says_external_and_does_not_count(self):
        metric = self._metric()
        gold = _dataset(1)[0]
        pred = _failed(LLMFailure(FailureClass.filtro_salida, "task", "content_filter"))
        assert metric(gold, pred) == 0.0
        attempts = get_failure_tracker().snapshot()["attempts"]["task"]

        fb = metric(gold, pred, None, "self", [])
        assert hasattr(fb, "feedback") and fb["score"] == 0.0
        assert "Falla externa al prompt" in fb.feedback
        assert "clase=filtro_salida" in fb.feedback
        assert metric(gold, pred, pred_name="self")["score"] == 0.0
        assert get_failure_tracker().snapshot()["attempts"]["task"] == attempts
        assert get_failure_tracker().snapshot()["counts"] == {"filtro_salida": {"task": 1}}

    def test_candidate_failure_feedback_is_prompt_error(self):
        metric = self._metric()
        gold = _dataset(1)[0]
        pred = _failed(LLMFailure(FailureClass.formato, "task", "AdapterParseError"))
        metric(gold, pred)
        fb = metric(gold, pred, None, "self", [])
        assert "El prompt provoco una falla de la tarea (clave=formato" in fb.feedback

    def test_normal_prediction_passes_to_metric(self):
        metric = self._metric()
        gold = _dataset(1)[0]
        assert metric(gold, dspy.Prediction(answer="yes")) == 1.0
        assert metric(gold, dspy.Prediction(answer="no"), None, "self", []) == dspy.Prediction(
            score=0.0,
            feedback="respuesta incorrecta",
        )

    def test_missing_case_id_is_value_error(self):
        gold = dspy.Example(question="q", answer="yes").with_inputs("question")
        with pytest.raises(ValueError, match="case_id"):
            self._metric()(gold, dspy.Prediction(answer="yes"))

    def test_attribution_needs_no_call_for_baseline_prediction(self, monkeypatch, task_lm):
        fake = FakeLLM({SEED: _answer_yes}).install(monkeypatch)
        metric = self._metric()
        pred = _failed(LLMFailure(FailureClass.entrada, "task", "ContentPolicyViolationError"))
        metric(_dataset(1)[0], pred)
        assert pred.failure.atribucion == "externa"
        assert fake.calls == {}


class TestRunAbortedPropagates:
    def test_forward_does_not_swallow_abort(self, monkeypatch, task_lm):
        fake = FakeLLM({SEED: _answer_yes}).install(monkeypatch)
        get_failure_tracker().abort(
            LLMFailure(FailureClass.configuracion, "task", "AuthenticationError"), "test"
        )
        with pytest.raises(RunAborted):
            tolerate_call_failures(_seed_student())(question="q0")
        assert fake.calls == {}


# ==================== dspy.GEPA real: copias, bootstrap y dataset reflexivo ====================


def _run_gepa(student, devset, budget):
    plain_metric = guard_program_and_metric(student, _metric)
    optimizer = dspy.GEPA(
        metric=plain_metric[1],
        reflection_lm=_lm(REFLECTION_MODEL, "reflection"),
        max_metric_calls=budget,
        reflection_minibatch_size=2,
        track_stats=True,
        seed=0,
    )
    return optimizer.compile(plain_metric[0], trainset=devset, valset=devset)


class TwoStep(dspy.Module):
    def __init__(self):
        super().__init__()
        self.draft = dspy.Predict(dspy.Signature("question -> draft", SEED))
        self.final = dspy.Predict(dspy.Signature("draft -> answer", "Finish the answer."))

    def forward(self, question):
        return self.final(draft=self.draft(question=question).draft)


class TestGepaEndToEnd:
    def test_candidate_budget_failure_attributed_through_copies(self, monkeypatch, task_lm):
        # La semilla responde mal (GEPA reflexiona) y el candidato se corta en q1.
        FakeLLM({SEED: lambda u: _ok(answer="no"), CANDIDATE: _length_on_q1}).install(monkeypatch)
        result = _run_gepa(_seed_student(), _dataset(), budget=16)

        assert CANDIDATE in [
            p.signature.instructions
            for prog in result.detailed_results.candidates
            for _, p in prog.named_predictors()
        ]
        counts = get_failure_tracker().snapshot()["counts"]
        assert set(counts) == {"presupuesto_candidato"}
        assert counts["presupuesto_candidato"]["task"] >= 1

    def test_ne_case_never_reaches_reflection(self, monkeypatch, task_lm):
        def filter_on_q1(user_text):
            if "q1" in user_text:
                return make_completion_response("", "content_filter")
            return _ok(answer="no")

        fake = FakeLLM({SEED: filter_on_q1, CANDIDATE: filter_on_q1}).install(monkeypatch)
        _run_gepa(_seed_student(), _dataset(), budget=16)

        assert fake.reflection_prompts
        # q1 entro en minibatches de reflexion (mas alla de la evaluacion inicial de val)...
        assert get_failure_tracker().snapshot()["counts"]["filtro_salida"]["task"] >= 2
        # ...y nunca llego al Profesor.
        assert all("q1" not in prompt for prompt in fake.reflection_prompts)

    def test_ne_feedback_reaches_reflection_as_external(self, monkeypatch, task_lm):
        """Programa de dos predictores: el primero tiene traza del caso NE y la
        reflexion recibe el feedback de falla externa, nunca de error del prompt."""

        def draft_then_fail(text):
            if "`answer`" in text:  # predictor final: la salida es `answer`
                if "d-q1" in text:
                    return make_completion_response("", "content_filter")
                return _ok(answer="no")
            question = "q1" if "q1" in text else "q0"
            return _ok(draft=f"d-{question}")

        instructions = (SEED, "Finish the answer.", CANDIDATE)
        fake = FakeLLM(dict.fromkeys(instructions, draft_then_fail), full_text=True)
        fake.install(monkeypatch)
        _run_gepa(TwoStep(), _dataset(2), budget=12)

        with_q1 = [p for p in fake.reflection_prompts if "q1" in p]
        assert with_q1
        assert all("Falla externa al prompt" in p for p in with_q1)
        assert not any("El prompt provoco una falla" in p for p in fake.reflection_prompts)
