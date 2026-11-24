"""
Fallas clasificadas de la tarea en DSPy (SPEC-104, D6; reemplaza `empty_response.py`).

`CheckedLM` (`shared/llm/dspy_lm.py`) lanza `LLMCallFailure` (incluida
`EmptyResponseError`) ante toda falla de capa 1 y nunca cuenta (D4). Este modulo
es el unico lugar de `dspy_gepa_poc` que convierte esa falla en un resultado por
caso, la atribuye contra el baseline (FR-004) y la cuenta una sola vez (FR-007):

- `tolerate_call_failures(program)`: copia del programa cuyo `forward` atrapa
  `LLMCallFailure` y `AdapterParseError` (`formato` de FR-010, tras el fallback
  de adapters) y devuelve una `FailedCallPrediction`. No cuenta: `forward` no
  conoce el caso (`Evaluate` llama `program(**example.inputs())`). `RunAborted`
  y cualquier otra excepcion siguen su curso.
- `guard_metric(metric, probe, baseline_instructions)`: la llamada de puntaje
  (sin `pred_name`; una por caso evaluado en `Evaluate` y en
  `bootstrap_trace_data`) cuenta el intento y, para una `FailedCallPrediction`,
  atribuye, registra y devuelve 0.0 (valor tecnico si es NE). Las llamadas de
  feedback (`pred_name`/`pred_trace`, `DspyAdapter.make_reflective_dataset`) no
  cuentan y explican la falla: externa (NE, FR-012) o error del prompt.
- `guard_program_and_metric(program, metric)`: arma ambos con el probe del
  baseline (D5): una `deepcopy` del programa sin envolver y su snapshot de
  instrucciones, tomados antes de GEPA (`build_program` copia el `student` y
  solo cambia instrucciones).

Por que una subclase dinamica y no un modulo contenedor: `dspy.GEPA` copia el
programa (`deepcopy`) para cada candidato y `bootstrap_trace_data` llama a
`forward` directamente (no a `__call__`). Cambiar la clase conserva el arbol de
predictores (`named_predictors`, claves de candidatos y del JSON guardado), asi
el artefacto `optimized_program.json` se carga igual en el modulo sin envolver.
La metrica la guarda `dspy.GEPA` por referencia (`metric_fn`), asi que el probe
del cierre es uno solo para toda la corrida.

FR-007: el unico WARNING por falla es el de `FailureTracker.record`. El aviso de
`JSONAdapter` "Failed to use structured output format" es un intento intermedio
del fallback de adapters y se baja a DEBUG con un filtro sobre su logger.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import cache
from typing import Any

import dspy
from dspy.utils.exceptions import AdapterParseError

from shared.llm import (
    BaselineOutcome,
    BaselineProbe,
    FailureClass,
    LLMCallFailure,
    LLMFailure,
    get_failure_tracker,
    is_evaluated,
)
from shared.llm.failures import count_key

_JSON_ADAPTER_LOGGER = "dspy.adapters.json_adapter"
_JSON_ADAPTER_FALLBACK_MSG = "Failed to use structured output format"


class FailedCallPrediction(dspy.Prediction):
    """
    Prediccion de un caso cuya tarea fallo (D6): campos de salida en None.

    Los atributos con prefijo `_` no entran al store de `dspy.Example`.
    `instructions` es el snapshot del programa que la produjo; `failure` queda
    atribuida (con `case_id`) tras la llamada de puntaje de la metrica.
    """

    def __init__(self, failure: LLMFailure, instructions: dict[str, str], output_fields: list[str]):
        super().__init__(**dict.fromkeys(output_fields))
        self._failure = failure
        self._instructions = instructions
        self._attributed = False

    @property
    def failure(self) -> LLMFailure:
        return self._failure

    @property
    def instructions(self) -> dict[str, str]:
        return self._instructions

    @property
    def attributed(self) -> bool:
        return self._attributed

    @property
    def evaluated(self) -> bool:
        """True si el caso cuenta como evaluado (score 0 del candidato); False si es NE."""
        return is_evaluated(self._failure)

    def mark_attributed(self, failure: LLMFailure) -> None:
        """Guarda la falla ya atribuida y registrada (una sola vez por prediccion)."""
        self._failure = failure
        self._attributed = True


def instructions_snapshot(program: dspy.Module) -> dict[str, str]:
    """`{predictor: instructions}`: lo unico que `dspy.GEPA` cambia entre candidatos."""
    return {
        name: predictor.signature.instructions or ""
        for name, predictor in program.named_predictors()
    }


def _output_fields(program: dspy.Module) -> list[str]:
    fields: list[str] = []
    for predictor in program.predictors():
        fields.extend(f for f in predictor.signature.output_fields if f not in fields)
    return fields


class _FailureTolerantMixin:
    """Mixin de `tolerate_call_failures`: `forward` devuelve la falla como prediccion."""

    def forward(self, *args: Any, **kwargs: Any):
        try:
            return super().forward(*args, **kwargs)
        except LLMCallFailure as exc:
            failure = exc.failure
        except AdapterParseError as exc:
            failure = LLMFailure(clase=FailureClass.formato, rol="task", causa=type(exc).__name__)
        return FailedCallPrediction(failure, instructions_snapshot(self), _output_fields(self))


@cache
def _tolerant_class(base: type) -> type:
    return type(f"FailureTolerant{base.__name__}", (_FailureTolerantMixin, base), {})


def tolerate_call_failures(program: dspy.Module) -> dspy.Module:
    """Copia de `program` que convierte las fallas de la tarea en `FailedCallPrediction`.

    Idempotente. No modifica `program`.
    """
    if isinstance(program, _FailureTolerantMixin):
        return program
    wrapped = program.deepcopy()
    wrapped.__class__ = _tolerant_class(type(program))
    return wrapped


class _HistoryRecorder:
    """Receptor de `settings.caller_modules`: `dspy.LM.update_history` le agrega cada llamada."""

    def __init__(self) -> None:
        self.history: list[dict[str, Any]] = []

    def last_finish_reason(self) -> str | None:
        for entry in reversed(self.history):
            choices = getattr(entry.get("response"), "choices", None) or []
            if choices:
                return getattr(choices[0], "finish_reason", None)
        return None


def baseline_caller(baseline: dspy.Module) -> Callable[[Any], BaselineOutcome]:
    """
    `call_baseline` del probe (D5): corre el programa baseline sobre el caso con el LM
    configurado (mismo `CheckedLM`, mismo `max_tokens`), sin ensuciar la traza.

    Una falla de capa 1 se propaga como `LLMCallFailure` (la atrapa el probe);
    `AdapterParseError` es "sin falla de capa 1". El `finish_reason` de la respuesta
    sana sale del historial del LM: las llamadas hechas en este hilo dentro del bloque
    se agregan al `history` de cada modulo de `caller_modules` (dspy 3.2.1,
    `BaseLM.update_history`). Con `disable_history` o `max_history_size == 0` queda None.
    """

    def call_baseline(example: Any) -> BaselineOutcome:
        recorder = _HistoryRecorder()
        callers = [*(dspy.settings.caller_modules or []), recorder]
        with dspy.context(trace=[], caller_modules=callers):
            try:
                baseline(**example.inputs())
            except AdapterParseError:
                pass
        return BaselineOutcome(finish_reason=recorder.last_finish_reason())

    return call_baseline


def _is_feedback_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> bool:
    pred_name = kwargs.get("pred_name", args[1] if len(args) > 1 else None)
    pred_trace = kwargs.get("pred_trace", args[2] if len(args) > 2 else None)
    return pred_name is not None or pred_trace is not None


def _case_id(example: Any) -> str:
    """Identificador del caso (FR-013); su ausencia es un error de programacion."""
    case_id = example.get("case_id") if hasattr(example, "get") else None
    if case_id is None or str(case_id) == "":
        raise ValueError(
            "El ejemplo no tiene `case_id` (SPEC-104 FR-013): los loaders lo garantizan; "
            "sin el no hay cache del baseline ni casos unicos de entrada_dato."
        )
    return str(case_id)


def failure_feedback(pred: FailedCallPrediction) -> str:
    """Feedback para el Profesor: falla externa si es NE (FR-012), error del prompt si no."""
    failure = pred.failure
    if not pred.evaluated:
        return (
            f"Falla externa al prompt (rol={failure.rol}, clase={failure.clase.value}, "
            f"causa={failure.causa}): el caso no se evaluo. No es un error del prompt; "
            "no usar este caso para corregir la instruccion."
        )
    return (
        f"El prompt provoco una falla de la tarea (clave={count_key(failure)}, "
        f"causa={failure.causa}); es un error del prompt."
    )


def guard_metric(
    metric: Callable,
    probe: BaselineProbe,
    baseline_instructions: dict[str, str],
) -> Callable:
    """
    Metrica que cuenta cada caso una vez y trata la `FailedCallPrediction` (D6).

    Misma convencion de retorno que las metricas de `metrics.py`. Para una
    `FailedCallPrediction`, la llamada de feedback devuelve `dspy.Prediction(score=0.0,
    feedback=...)` (mapeo con `score` y `feedback`; `dspy.GEPA` lee `feedback` con
    `hasattr`). Las predicciones normales pasan a `metric` con los mismos argumentos.
    """
    tracker = get_failure_tracker()

    def failure_aware_metric(example, pred, *args: Any, **kwargs: Any):
        if _is_feedback_call(args, kwargs):
            if isinstance(pred, FailedCallPrediction):
                return dspy.Prediction(score=0.0, feedback=failure_feedback(pred))
            return metric(example, pred, *args, **kwargs)
        case_id = _case_id(example)
        tracker.record_attempt("task", case_id)
        if not isinstance(pred, FailedCallPrediction):
            return metric(example, pred, *args, **kwargs)
        if not pred.attributed:
            failure = probe.attribute(
                pred.failure,
                case_id,
                example,
                is_baseline=pred.instructions == baseline_instructions,
            )
            pred.mark_attributed(failure)
            tracker.record(failure)
        return 0.0

    return failure_aware_metric


def guard_program_and_metric(
    program: dspy.Module, metric: Callable
) -> tuple[dspy.Module, Callable]:
    """
    Programa tolerante y metrica con el probe del baseline, a partir del programa
    sin envolver (el baseline) y su metrica. No modifica `program`.
    """
    baseline = program.deepcopy()
    probe = BaselineProbe(baseline_caller(baseline))
    guarded = guard_metric(metric, probe, instructions_snapshot(program))
    return tolerate_call_failures(program), guarded


class _DemoteAdapterFallback(logging.Filter):
    """Baja a DEBUG el aviso intermedio del fallback de `JSONAdapter` (FR-007)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno == logging.WARNING and str(record.msg).startswith(
            _JSON_ADAPTER_FALLBACK_MSG
        ):
            record.levelno = logging.DEBUG
            record.levelname = logging.getLevelName(logging.DEBUG)
        return True


def _install_fallback_filter() -> None:
    target = logging.getLogger(_JSON_ADAPTER_LOGGER)
    if not any(isinstance(f, _DemoteAdapterFallback) for f in target.filters):
        target.addFilter(_DemoteAdapterFallback())


_install_fallback_filter()
