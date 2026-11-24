"""
LM de DSPy que clasifica las fallas de la llamada (SPEC-103 FR-009, SPEC-104).

`LLMConfig.get_dspy_lm()` devuelve un `CheckedLM` en lugar de un `dspy.LM`.
Ante una falla de capa 1 lanza `LLMCallFailure` (una respuesta sin texto,
`EmptyResponseError`, con su causa en DEBUG) en todo rol. El tipo de excepcion
separa la falla de la llamada de un error de formato real (`AdapterParseError`),
sin heuristicas sobre el parseo.

- `reflection`: en `dspy.GEPA` (GEPA 0.0.27, dspy 3.2.1) la excepcion sale de
  `DspyAdapter.propose_new_texts`, la atrapa `ReflectiveMutationProposer.propose`
  y la iteracion se saltea sin crear un candidato con instruccion vacia.
  SPEC-104 (2b, FR-005): en este rol `__call__` pasa por `ReflectionGuard`
  (`reflection.py`): cuenta un intento por propuesta, registra la falla de capa
  1 y descarta tambien la propuesta sin bloque de instruccion (`formato`). El
  log de capa 1 va a DEBUG en `raise_for_response` (FR-007).
- `task`: el programa y la metrica se envuelven con
  `dspy_gepa_poc.call_failures.guard_program_and_metric`: el `forward` devuelve
  una `FailedCallPrediction` con la falla clasificada y la metrica decide NE o
  score 0 segun su clase (SPEC-104 3e). Sin envoltorio, la excepcion cuenta
  como error del ejemplo (`max_errors` de `Evaluate`).

SPEC-104 (2a, D3, FR-001/FR-011/FR-015): `CheckedLM` se construye con
`num_retries=0` (LiteLLM no reintenta) y `forward` envuelve a `dspy.LM.forward`
con `call_with_infra_retry` (reintento propio solo de `infraestructura`). La
revision de la respuesta va en `_process_lm_response` (despues de que DSPy
guarda la entrada en `history`, asi el uso de tokens se sigue contando) y
delega en `raise_for_response`. Son metodos internos de dspy 3.2.1: si D-018
actualiza DSPy, revalidar con `tests/test_empty_response_dspy.py` y
`tests/test_single_call_point.py`.

Corte del fallback de adapters (SC-009 por caso): `dspy.Predict` con
`ChatAdapter` repite la llamada con `JSONAdapter` ante cualquier excepcion salvo
`dspy.utils.exceptions.ContextWindowExceededError` (dspy 3.2.1,
`ChatAdapter.__call__`). Por eso toda falla que lanza `CheckedLM` es una
subclase de esa excepcion: `DspyLLMCallFailure` y `DspyEmptyResponseError`
siguen siendo `LLMCallFailure` / `EmptyResponseError` para el resto del repo.
Ningun modulo de DSPy usado en el repo la trata de forma especial (solo `ReAct`
e `infer_rules`, que el repo no usa).

`aforward`/`acall` no se usan en el repo y este LM no los cubre.

Este modulo importa dspy; `config.py` lo importa de forma diferida.
"""

from typing import Any

import dspy
from dspy.utils.exceptions import ContextWindowExceededError

from .call import call_with_infra_retry, raise_for_response
from .errors import EmptyResponseError
from .failures import FailureClass, LLMCallFailure, LLMFailure
from .reflection import ReflectionGuard


class DspyLLMCallFailure(LLMCallFailure, ContextWindowExceededError):  # noqa: N818 - como D1
    """`LLMCallFailure` que `ChatAdapter` no reintenta con `JSONAdapter`."""

    def __init__(self, failure: LLMFailure, message: str | None = None, model: str | None = None):
        base = LLMCallFailure(failure, message)
        self.failure = failure
        self.model = model
        Exception.__init__(self, *base.args)


class DspyEmptyResponseError(EmptyResponseError, ContextWindowExceededError):
    """`EmptyResponseError` que `ChatAdapter` no reintenta con `JSONAdapter`."""

    def __init__(
        self,
        role: str,
        finish_reason: str | None = None,
        clase: FailureClass = FailureClass.sin_texto,
        model: str | None = None,
    ):
        base = EmptyResponseError(role, finish_reason, clase)
        self.role = role
        self.finish_reason = finish_reason
        self.failure = base.failure
        self.model = model
        Exception.__init__(self, *base.args)


def _cut_adapter_fallback(exc: LLMCallFailure, model: str) -> LLMCallFailure:
    """Copia de `exc` que es `ContextWindowExceededError` (corta el fallback de DSPy)."""
    if isinstance(exc, ContextWindowExceededError):
        return exc
    if isinstance(exc, EmptyResponseError):
        return DspyEmptyResponseError(exc.role, exc.finish_reason, exc.failure.clase, model)
    return DspyLLMCallFailure(exc.failure, str(exc), model)


def _output_texts(outputs: list) -> list[str]:
    """Textos de las salidas de `dspy.LM` (str, o dict con "text", como `stripped_lm_call`)."""
    return [(o.get("text") or "") if isinstance(o, dict) else str(o) for o in outputs]


class CheckedLM(dspy.LM):
    """`dspy.LM` con llamada comun de SPEC-104: sin reintento de LiteLLM y con falla clasificada."""

    def __init__(
        self,
        model: str,
        role: str = "task",
        infra_retries: int | None = None,
        **kwargs: Any,
    ):
        kwargs["num_retries"] = 0
        super().__init__(model, **kwargs)
        self.role = role
        self.infra_retries = infra_retries
        self._reflection_guard = ReflectionGuard()

    def __call__(self, prompt: str | None = None, messages: list | None = None, **kwargs: Any):
        parent = super().__call__
        if self.role != "reflection":
            return parent(prompt, messages, **kwargs)
        try:
            return self._reflection_guard.run(
                lambda: parent(prompt, messages, **kwargs), _output_texts
            )
        except LLMCallFailure as exc:
            cut = _cut_adapter_fallback(exc, self.model)
            if cut is exc:
                raise
            raise cut from exc

    def on_proposal_start(self, event: Any) -> None:
        """Callback de GEPA (`gepa_kwargs={"callbacks": [lm]}` en `dspy.GEPA`)."""
        self._reflection_guard.on_proposal_start(event)

    def forward(self, prompt: str | None = None, messages: list | None = None, **kwargs: Any):
        try:
            return call_with_infra_retry(
                lambda: super(CheckedLM, self).forward(prompt=prompt, messages=messages, **kwargs),
                self.role,
                infra_retries=self.infra_retries,
            )
        except LLMCallFailure as exc:
            cut = _cut_adapter_fallback(exc, self.model)
            if cut is exc:
                raise
            raise cut from exc

    def _check_truncation(self, results: Any) -> None:
        # SPEC-104: `raise_for_response` clasifica `finish_reason="length"` como
        # `presupuesto` y `None` como `configuracion`. El metodo base de dspy 3.2.1
        # lee `self.kwargs["max_tokens"]` (KeyError en modelos reasoning que usan
        # `max_completion_tokens`), falla con TypeError si `results is None` y
        # duplica un WARNING en `length` (FR-007).
        return

    def _process_lm_response(self, response, prompt, messages, **kwargs):
        outputs: Any = []
        if response is not None:
            outputs = super()._process_lm_response(response, prompt, messages, **kwargs)
            if self._has_tool_calls(response):
                return outputs
        try:
            raise_for_response(response, self.role)
        except LLMCallFailure as exc:
            raise _cut_adapter_fallback(exc, self.model) from exc
        return outputs

    @staticmethod
    def _has_tool_calls(response: Any) -> bool:
        return any(
            getattr(getattr(choice, "message", None), "tool_calls", None)
            for choice in getattr(response, "choices", None) or []
        )
