"""
Respuesta sin texto de la tarea en DSPy (SPEC-103, FR-009; RESOLUCION B-2c-1).

`CheckedLM` (`shared/llm/dspy_lm.py`) lanza `EmptyResponseError` en todo rol.
Este modulo es el unico lugar de `dspy_gepa_poc` que la convierte en una
prediccion fallida con score 0.0, sin tocar `max_errors`:

- `tolerate_empty_responses(program)`: copia del programa cuyo `forward` atrapa
  `EmptyResponseError` y devuelve una `EmptyResponsePrediction` (campos de
  salida en None). Cualquier otra excepcion sigue su curso y cuenta para
  `max_errors` de `Evaluate`.
- `zero_on_empty_response(metric)`: la metrica puntua 0.0 esa prediccion. Hace
  falta porque `shared.scoring.score_field` trata None como "" y daria credito
  a los campos cuyo gold es vacio (y en `rule_derived` el color derivado no es
  salida de ningun predictor).

`ChatAdapter` atrapa la excepcion y reintenta con `JSONAdapter` (dos intentos):
una respuesta de tarea sin texto cuesta 3 llamadas antes de llegar aca.

Por que una subclase dinamica y no un modulo contenedor: `dspy.GEPA` copia el
programa (`deepcopy`) para cada candidato y `bootstrap_trace_data` llama a
`forward` directamente (no a `__call__`). Cambiar la clase conserva el arbol de
predictores (`named_predictors`, claves de candidatos y del JSON guardado), asi
el artefacto `optimized_program.json` se carga igual en el modulo sin envolver.
"""

from collections.abc import Callable
from functools import cache
from typing import Any

import dspy

from shared.llm import EmptyResponseError


class EmptyResponsePrediction(dspy.Prediction):
    """Prediccion fallida por respuesta sin texto: campos de salida en None."""

    def __init__(self, error: EmptyResponseError, output_fields: list[str]):
        super().__init__(**dict.fromkeys(output_fields))
        self._empty_error = error

    @property
    def empty_error(self) -> EmptyResponseError:
        return self._empty_error


class _EmptyTolerantMixin:
    """Mixin de `tolerate_empty_responses`: `forward` atrapa `EmptyResponseError`."""

    def forward(self, *args: Any, **kwargs: Any):
        try:
            return super().forward(*args, **kwargs)
        except EmptyResponseError as error:
            return EmptyResponsePrediction(error, _output_fields(self))


def _output_fields(program: dspy.Module) -> list[str]:
    fields: list[str] = []
    for predictor in program.predictors():
        fields.extend(f for f in predictor.signature.output_fields if f not in fields)
    return fields


@cache
def _tolerant_class(base: type) -> type:
    return type(f"EmptyTolerant{base.__name__}", (_EmptyTolerantMixin, base), {})


def tolerate_empty_responses(program: dspy.Module) -> dspy.Module:
    """Copia de `program` que convierte `EmptyResponseError` en prediccion fallida.

    Idempotente. No modifica `program`.
    """
    if isinstance(program, _EmptyTolerantMixin):
        return program
    wrapped = program.deepcopy()
    wrapped.__class__ = _tolerant_class(type(program))
    return wrapped


def zero_on_empty_response(metric: Callable) -> Callable:
    """Metrica que puntua 0.0 una `EmptyResponsePrediction`, sin llamar a `metric`.

    Misma convencion de retorno que las metricas de `metrics.py`: con
    `pred_name`/`pred_trace` (feedback para la reflexion de GEPA) devuelve
    `{"score": 0.0, "feedback": <causa>}`; si no, 0.0. Las demas predicciones
    pasan a `metric` con los mismos argumentos.
    """

    def metric_with_empty_guard(example, pred, *args: Any, **kwargs: Any):
        if not isinstance(pred, EmptyResponsePrediction):
            return metric(example, pred, *args, **kwargs)
        pred_name = kwargs.get("pred_name", args[1] if len(args) > 1 else None)
        pred_trace = kwargs.get("pred_trace", args[2] if len(args) > 2 else None)
        if pred_name is None and pred_trace is None:
            return 0.0
        return {"score": 0.0, "feedback": f"{pred.empty_error}: prediccion fallida."}

    return metric_with_empty_guard
