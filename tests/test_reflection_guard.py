"""
SPEC-104 subfase 2b: descarte de la propuesta de reflexion en el envoltorio
del `reflection_lm` (FR-005, SC-003), en ambos subproyectos.

Verificado contra `gepa==0.0.27` y `dspy==3.2.1`, sin red:

- GEPA extrae la instruccion con `InstructionProposalSignature.output_extractor`,
  que nunca falla: sin bloque de triple backtick devuelve el texto entero como
  instruccion. Por eso el envoltorio detecta `formato` (sin bloque o instruccion
  vacia) y lanza; `ReflectiveMutationProposer.propose` atrapa la excepcion y
  saltea la iteracion: el candidato vigente no cambia.
- Toda falla de capa 1 del rol `reflection` (payloads HTTP de
  `tests/litellm_failure_payloads.py`) se lanza, se cuenta una vez por
  propuesta con su clase y `case_id`, y `configuracion` deja el contador
  abortado.
- `gepa_standalone`: `create_reflection_lm_function` -> `ReflectionLM` dentro
  de `gepa.optimize`. `dspy_gepa_poc`: `CheckedLM` con rol `reflection` dentro
  de `dspy.GEPA`.

Respuestas 200 reales con `make_completion_response` (`litellm.ModelResponse`).
"""

from __future__ import annotations

import logging
import re
from typing import Any

import dspy
import litellm
import pytest
from dspy.utils.exceptions import ContextWindowExceededError
from gepa import EvaluationBatch, optimize
from gepa.strategies.instruction_proposal import InstructionProposalSignature

from gepa_standalone.core.llm_factory import ReflectionLM, create_reflection_lm_function
from shared.llm import LLMCallFailure, LLMConfig, RunAborted, get_failure_tracker
from shared.llm.failures import DEFAULT_INFRA_RETRIES, FailureClass, LLMFailure
from shared.llm.reflection import reflection_format_failure
from tests.conftest import make_completion_response
from tests.litellm_failure_payloads import (
    ALL_FAILURE_CASES,
    PROVIDER_KWARGS,
    FailurePayloadCase,
)
from tests.test_litellm_failure_mapping import intercept_httpx

SEED = "Answer the question."
VALID = "Always answer yes."
VALID_PROPOSAL = f"Nueva instruccion:\n```\n{VALID}\n```"
REFLECTION_MODEL = "openai/gpt-4o"
TASK_MODEL = "openai/gpt-4o-mini"

FAILING_CASES: tuple[FailurePayloadCase, ...] = tuple(
    c for c in ALL_FAILURE_CASES if c.spec104_class != "ok"
)

# (contenido, finish_reason) de respuestas 200 con falla -> clase esperada.
HTTP_200_FAILURES = [
    (None, "length", FailureClass.presupuesto),
    (VALID_PROPOSAL, "length", FailureClass.presupuesto),
    ("", "content_filter", FailureClass.filtro_salida),
    (VALID_PROPOSAL, "content_filter", FailureClass.filtro_salida),
    ("  \n", "stop", FailureClass.sin_texto),
    ("Always answer yes, sin bloque.", "stop", FailureClass.formato),
    ("```\n   \n```", "stop", FailureClass.formato),
]


@pytest.fixture(autouse=True)
def _litellm_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(litellm, "drop_params", False)
    monkeypatch.setattr(litellm, "num_retries", None)
    monkeypatch.setattr(litellm, "suppress_debug_info", True)


def _counts() -> dict[str, dict[str, int]]:
    return get_failure_tracker().snapshot()["counts"]


def _attempts() -> int:
    return get_failure_tracker().snapshot()["attempts"]["reflection"]


def _assert_reflection_threshold_abort(http_calls: int, clase: FailureClass) -> None:
    """
    Fallas persistentes de reflexion con los umbrales por defecto (`presupuesto`
    0.25, `total` 0.50, minimo 4): 3 propuestas fallan y se cuentan; el cuarto
    intento alcanza el minimo y aborta (3/4) antes de llamar al LLM, y no hay
    mas llamadas de reflexion en la corrida.
    """
    snapshot = get_failure_tracker().snapshot()
    assert http_calls == 3
    assert snapshot["attempts"]["reflection"] == 4
    assert snapshot["counts"] == {clase.value: {"reflection": 3}}
    expected_key = "presupuesto" if clase == FailureClass.presupuesto else "total"
    assert snapshot["abort"]["rol"] == "reflection"
    assert snapshot["abort"]["clase"] == expected_key
    assert (snapshot["abort"]["conteo"], snapshot["abort"]["intentos"]) == (3, 4)


def _assert_iterations_logged(log_text: str, iterations: list[int]) -> None:
    """Las 3 fallas registradas llevan la iteracion de GEPA de su propuesta; tras
    el aborto por umbral las propuestas siguientes no llaman ni registran."""
    logged = [int(i) for i in re.findall(r"case_id=iteracion:(\d+)", log_text)]
    assert len(logged) == 3
    assert logged == iterations[:3]
    assert len(iterations) > 3


def _assert_single_warning(caplog: pytest.LogCaptureFixture) -> None:
    """FR-007: un unico WARNING por falla de reflexion, el de `record`; el log de
    respuesta sin texto de la capa de llamada queda en DEBUG."""
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].startswith("Falla de LLM: rol=reflection")


def _expected_calls(case: FailurePayloadCase) -> int:
    return 1 + DEFAULT_INFRA_RETRIES if case.spec104_class == "infraestructura" else 1


def _patch_completion(monkeypatch: pytest.MonkeyPatch, content, finish_reason="stop") -> list:
    calls: list[dict[str, Any]] = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return make_completion_response(content, finish_reason)

    monkeypatch.setattr(litellm, "completion", fake_completion)
    return calls


def _standalone_lm(provider: str = "openai") -> ReflectionLM:
    cfg = LLMConfig(**PROVIDER_KWARGS[provider], role="reflection", cache=False)
    return create_reflection_lm_function(config=cfg)


def _dspy_lm(model: str, role: str, provider: str = "openai"):
    kwargs = {**PROVIDER_KWARGS[provider], "model": model}
    return LLMConfig(**kwargs, role=role, cache=False).get_dspy_lm()


# ==================== formato: verificacion contra GEPA 0.0.27 ====================


class TestFormatFailure:
    @pytest.mark.parametrize(
        "text",
        [
            f"```\n{VALID}\n```",
            f"Prefacio\n```text\n{VALID}\n```\nCierre",
            f"  ```markdown\n{VALID}\n```  \n",
        ],
    )
    def test_block_with_instruction_is_valid(self, text: str) -> None:
        assert reflection_format_failure(text) is None
        assert InstructionProposalSignature.output_extractor(text.strip()) == {
            "new_instruction": VALID
        }

    @pytest.mark.parametrize(
        ("text", "causa"),
        [
            (VALID, "sin_bloque_instruccion"),
            (f"```\n{VALID}", "sin_bloque_instruccion"),
            (f"{VALID}\n```", "sin_bloque_instruccion"),
            ("``````", "sin_bloque_instruccion"),
            ("```\n```", "instruccion_vacia"),
            ("```python\n   \n```", "instruccion_vacia"),
        ],
    )
    def test_without_block_or_empty_is_formato(self, text: str, causa: str) -> None:
        failure = reflection_format_failure(text)
        assert failure == LLMFailure(FailureClass.formato, "reflection", causa)

    @pytest.mark.parametrize("text", [VALID, f"```\n{VALID}", f"{VALID}\n```"])
    def test_gepa_would_adopt_text_without_block(self, text: str) -> None:
        # Evidencia de que hace falta el envoltorio: GEPA no falla sin bloque y
        # toma el texto (o lo que queda de el) como instruccion nueva.
        assert InstructionProposalSignature.output_extractor(text)["new_instruction"] == VALID


# ==================== gepa_standalone: ReflectionLM ====================


class TestStandaloneReflectionLM:
    def test_valid_proposal_passes_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch_completion(monkeypatch, VALID_PROPOSAL)
        assert _standalone_lm()("prompt") == VALID_PROPOSAL
        assert len(calls) == 1
        assert calls[0]["num_retries"] == 0
        assert _attempts() == 1
        assert _counts() == {}

    @pytest.mark.parametrize(("content", "reason", "clase"), HTTP_200_FAILURES)
    def test_http_200_failure_raises_and_counts_once(
        self, monkeypatch: pytest.MonkeyPatch, caplog, content, reason, clase
    ) -> None:
        calls = _patch_completion(monkeypatch, content, reason)
        with caplog.at_level(logging.WARNING), pytest.raises(LLMCallFailure) as exc_info:
            _standalone_lm()("prompt")
        failure = exc_info.value.failure
        assert (failure.clase, failure.rol) == (clase, "reflection")
        assert len(calls) == 1
        assert _attempts() == 1
        assert _counts() == {clase.value: {"reflection": 1}}
        assert "case_id=propuesta:1" in caplog.text
        assert not get_failure_tracker().aborted
        _assert_single_warning(caplog)

    @pytest.mark.parametrize("case", FAILING_CASES, ids=lambda c: c.id)
    def test_layer1_payload_counts_once_per_proposal(self, case: FailurePayloadCase) -> None:
        # get_lm_function activa litellm.drop_params: el 422 de OpenAI da 2
        # llamadas por intento y None (limite conocido), `configuracion`.
        per_attempt = (case.expected_http_calls or {}).get("num_retries_0", 1)
        lm = _standalone_lm(case.provider)
        with intercept_httpx(case) as calls, pytest.raises(LLMCallFailure) as exc_info:
            lm("prompt")
        assert exc_info.value.failure.clase.value == case.spec104_class
        assert len(calls) == _expected_calls(case) * per_attempt
        assert _attempts() == 1
        assert _counts() == {case.spec104_class: {"reflection": 1}}
        assert get_failure_tracker().aborted == (case.spec104_class == "configuracion")

    def test_aborted_tracker_does_not_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch_completion(monkeypatch, VALID_PROPOSAL)
        get_failure_tracker().abort(
            LLMFailure(FailureClass.configuracion, "task", "AuthenticationError"), "test"
        )
        with pytest.raises(RunAborted):
            _standalone_lm()("prompt")
        assert calls == []
        assert _attempts() == 0
        assert _counts() == {}

    def test_gepa_iteration_is_case_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_completion(monkeypatch, "sin bloque")
        lm = _standalone_lm()
        lm.on_proposal_start({"iteration": 7})
        for _ in range(2):  # dos componentes en la misma iteracion
            with pytest.raises(LLMCallFailure) as exc_info:
                lm("prompt")
            assert exc_info.value.failure.case_id == "iteracion:7"
        assert _attempts() == 1

    def test_verbose_is_guarded(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        _patch_completion(monkeypatch, "sin bloque")
        cfg = LLMConfig(**PROVIDER_KWARGS["openai"], role="reflection", cache=False)
        with pytest.raises(LLMCallFailure):
            create_reflection_lm_function(verbose=True, config=cfg)("prompt")
        assert "[REFLECTION LM]" in capsys.readouterr().out
        assert _counts() == {"formato": {"reflection": 1}}


# ==================== gepa_standalone: dentro de gepa.optimize ====================


class _YesAdapter:
    """Adapter minimo de GEPA: puntua 1.0 solo si la instruccion es VALID."""

    propose_new_texts = None

    def __init__(self) -> None:
        self.evaluated: list[str] = []

    def evaluate(self, batch, candidate, capture_traces=False):
        text = candidate["system_prompt"]
        self.evaluated.append(text)
        scores = [1.0 if text == VALID else 0.0 for _ in batch]
        trajectories = [{"input": x} for x in batch] if capture_traces else None
        return EvaluationBatch(outputs=list(batch), scores=scores, trajectories=trajectories)

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        records = [
            {"Inputs": t["input"], "Feedback": "Debe decir yes"} for t in eval_batch.trajectories
        ]
        return {"system_prompt": records}


class _ProposalIterations:
    """Callback de GEPA que anota la iteracion de cada propuesta."""

    def __init__(self) -> None:
        self.iterations: list[int] = []

    def on_proposal_start(self, event) -> None:
        self.iterations.append(event["iteration"])


def _optimize(reflection_lm, callbacks=None):
    adapter = _YesAdapter()
    data = [f"q{i}" for i in range(4)]
    result = optimize(
        seed_candidate={"system_prompt": SEED},
        trainset=data,
        valset=data,
        adapter=adapter,
        reflection_lm=reflection_lm,
        max_metric_calls=16,
        reflection_minibatch_size=2,
        display_progress_bar=False,
        callbacks=callbacks,
        seed=0,
    )
    return result, adapter


def _candidate_texts(result) -> list[str]:
    return [c["system_prompt"] for c in result.candidates]


class TestStandaloneInGepaOptimize:
    def test_valid_proposal_creates_candidate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_completion(monkeypatch, VALID_PROPOSAL)
        result, _ = _optimize(_standalone_lm())
        assert VALID in _candidate_texts(result)
        assert _counts() == {}

    @pytest.mark.parametrize(("content", "reason", "clase"), HTTP_200_FAILURES)
    def test_failed_proposal_keeps_current_candidate(
        self, monkeypatch: pytest.MonkeyPatch, content, reason, clase
    ) -> None:
        calls = _patch_completion(monkeypatch, content, reason)
        result, adapter = _optimize(_standalone_lm())
        # SC-003: ninguna propuesta con falla produce (ni evalua) un candidato.
        assert _candidate_texts(result) == [SEED]
        assert set(adapter.evaluated) == {SEED}
        _assert_reflection_threshold_abort(len(calls), clase)

    def test_configuracion_aborts_and_stops_calls(self) -> None:
        case = next(
            c
            for c in FAILING_CASES
            if c.provider == "openai" and c.spec104_class == "configuracion"
        )
        with intercept_httpx(case) as calls:
            result, _ = _optimize(_standalone_lm())
        assert len(calls) == 1
        assert _candidate_texts(result) == [SEED]
        assert get_failure_tracker().aborted
        assert _counts() == {"configuracion": {"reflection": 1}}

    def test_callback_sets_gepa_iteration_as_case_id(
        self, monkeypatch: pytest.MonkeyPatch, caplog
    ) -> None:
        _patch_completion(monkeypatch, "sin bloque")
        lm = _standalone_lm()
        probe = _ProposalIterations()
        with caplog.at_level(logging.WARNING):
            _optimize(lm, callbacks=[probe, lm])
        _assert_iterations_logged(caplog.text, probe.iterations)


# ==================== dspy_gepa_poc: CheckedLM con rol reflection ====================


def _patch_dspy_completion(monkeypatch: pytest.MonkeyPatch, reflection, task_answer="no") -> dict:
    calls = {"task": 0, "reflection": 0}

    def fake_completion(request, num_retries, cache=None):
        if request["model"] == REFLECTION_MODEL:
            calls["reflection"] += 1
            return make_completion_response(*reflection)
        calls["task"] += 1
        system = str(request["messages"][0]["content"])
        answer = "yes" if VALID in system else task_answer
        return make_completion_response(f"[[ ## answer ## ]]\n{answer}\n\n[[ ## completed ## ]]")

    monkeypatch.setattr("dspy.clients.lm.litellm_completion", fake_completion)
    return calls


def _metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
    return float(getattr(pred, "answer", None) == gold.answer)


def _run_dspy_gepa(reflection_lm, gepa_kwargs=None):
    data = [dspy.Example(question=f"q{i}", answer="yes").with_inputs("question") for i in range(4)]
    optimizer = dspy.GEPA(
        metric=_metric,
        reflection_lm=reflection_lm,
        max_metric_calls=16,
        reflection_minibatch_size=2,
        track_stats=True,
        seed=0,
        gepa_kwargs=gepa_kwargs,
    )
    student = dspy.Predict(dspy.Signature("question -> answer", SEED))
    with dspy.context(lm=_dspy_lm(TASK_MODEL, "task")):
        result = optimizer.compile(student, trainset=data, valset=data)
    return [
        pred.signature.instructions
        for program in result.detailed_results.candidates
        for _, pred in program.named_predictors()
    ]


class TestDspyCheckedLMReflection:
    def test_valid_proposal_passes_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_dspy_completion(monkeypatch, (VALID_PROPOSAL, "stop"))
        assert _dspy_lm(REFLECTION_MODEL, "reflection")("prompt") == [VALID_PROPOSAL]
        assert _attempts() == 1
        assert _counts() == {}

    @pytest.mark.parametrize(("content", "reason", "clase"), HTTP_200_FAILURES)
    def test_http_200_failure_raises_and_counts_once(
        self, monkeypatch: pytest.MonkeyPatch, caplog, content, reason, clase
    ) -> None:
        calls = _patch_dspy_completion(monkeypatch, (content, reason))
        with caplog.at_level(logging.WARNING), pytest.raises(LLMCallFailure) as exc_info:
            _dspy_lm(REFLECTION_MODEL, "reflection")("prompt")
        # Corta el fallback de adapters de DSPy como toda falla de CheckedLM.
        assert isinstance(exc_info.value, ContextWindowExceededError)
        failure = exc_info.value.failure
        assert (failure.clase, failure.rol) == (clase, "reflection")
        assert calls["reflection"] == 1
        assert _counts() == {clase.value: {"reflection": 1}}
        assert "case_id=propuesta:1" in caplog.text
        _assert_single_warning(caplog)

    @pytest.mark.parametrize("case", FAILING_CASES, ids=lambda c: c.id)
    def test_layer1_payload_counts_once_per_proposal(self, case: FailurePayloadCase) -> None:
        lm = _dspy_lm(PROVIDER_KWARGS[case.provider]["model"], "reflection", case.provider)
        with intercept_httpx(case) as calls, pytest.raises(LLMCallFailure) as exc_info:
            lm("prompt")
        assert exc_info.value.failure.clase.value == case.spec104_class
        assert len(calls) == _expected_calls(case)
        assert _attempts() == 1
        assert _counts() == {case.spec104_class: {"reflection": 1}}

    def test_task_role_is_not_guarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_dspy_completion(monkeypatch, ("sin bloque", "stop"))
        assert _dspy_lm(REFLECTION_MODEL, "task")("prompt") == ["sin bloque"]
        assert _attempts() == 0

    def test_aborted_tracker_does_not_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch_dspy_completion(monkeypatch, (VALID_PROPOSAL, "stop"))
        get_failure_tracker().abort(
            LLMFailure(FailureClass.configuracion, "task", "AuthenticationError"), "test"
        )
        with pytest.raises(RunAborted):
            _dspy_lm(REFLECTION_MODEL, "reflection")("prompt")
        assert calls["reflection"] == 0
        assert _attempts() == 0


class TestDspyGepaReflection:
    def test_valid_proposal_creates_candidate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_dspy_completion(monkeypatch, (VALID_PROPOSAL, "stop"))
        assert VALID in _run_dspy_gepa(_dspy_lm(REFLECTION_MODEL, "reflection"))
        assert _counts() == {}

    @pytest.mark.parametrize(("content", "reason", "clase"), HTTP_200_FAILURES)
    def test_failed_proposal_keeps_current_candidate(
        self, monkeypatch: pytest.MonkeyPatch, content, reason, clase
    ) -> None:
        calls = _patch_dspy_completion(monkeypatch, (content, reason))
        instructions = _run_dspy_gepa(_dspy_lm(REFLECTION_MODEL, "reflection"))
        assert instructions == [SEED]
        _assert_reflection_threshold_abort(calls["reflection"], clase)

    def test_callback_sets_gepa_iteration_as_case_id(
        self, monkeypatch: pytest.MonkeyPatch, caplog
    ) -> None:
        _patch_dspy_completion(monkeypatch, ("sin bloque", "stop"))
        lm = _dspy_lm(REFLECTION_MODEL, "reflection")
        probe = _ProposalIterations()
        with caplog.at_level(logging.WARNING):
            _run_dspy_gepa(lm, gepa_kwargs={"callbacks": [probe, lm]})
        _assert_iterations_logged(caplog.text, probe.iterations)
