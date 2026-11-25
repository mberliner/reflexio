"""
LM de DSPy sobre el punto de llamada propio (SPEC-105 FR-001/FR-003/FR-004/FR-005).

`LLMConfig.get_dspy_lm()` devuelve un `CheckedLM`: una subclase de `dspy.BaseLM`
cuyo `forward` llama a `shared.llm.call.checked_response`, el mismo punto que usa
`gepa_standalone`. Ahi se hacen la llamada a LiteLLM (`num_retries=0`), el
reintento propio de `infraestructura` (SPEC-104 D3, FR-011), el registro del uso
de tokens del rol y del `finish_reason` (FR-004 de SPEC-104) y la clasificacion
de capa 1 sobre la respuesta y las excepciones crudas de LiteLLM. Ante una falla
lanza `LLMCallFailure` (o `EmptyResponseError`) en todo rol.

Superficie de DSPy que usa (publica): `dspy.BaseLM` con `forward(prompt,
messages, **kwargs)` devolviendo una respuesta con forma de OpenAI (la interfaz
de LM propio de dspy 3.2.1; dspy 3.4.x la mantiene como plugin legacy, sin
convertir excepciones ni reintentar), `BaseLM.__call__`, y las propiedades
`supports_*` / `supported_params`. No sobrescribe metodos privados de dspy.

- `reflection`: `__call__` pasa por `ReflectionGuard` (`reflection.py`): cuenta
  un intento por propuesta, registra la falla de capa 1 y descarta tambien la
  propuesta sin bloque de instruccion (`formato`). En `dspy.GEPA` la excepcion
  la atrapa GEPA y la iteracion se saltea (SPEC-104 FR-005).
- `task`: el programa y la metrica se envuelven con
  `dspy_gepa_poc.call_failures.guard_program_and_metric` (SPEC-104 3e).

Corte del fallback de adapters (SC-009 de SPEC-104): en dspy 3.2.1
`ChatAdapter` repite la llamada con `JSONAdapter` ante cualquier excepcion salvo
`dspy.utils.exceptions.ContextWindowExceededError`; por eso toda falla que lanza
este LM es ademas una subclase de esa excepcion publica (`DspyLLMCallFailure`,
`DspyEmptyResponseError`). Desde dspy 3.4 el fallback se dispara solo con
`AdapterParseError` y el corte queda sin efecto.

La cache de respuestas de DSPy no aplica a un LM propio: `cache=True` se rechaza
en `LLMConfig.get_dspy_lm()`. Vuelve con el engine propio de dspy 3.5 (D-018).

`aforward`/`acall` no se usan en el repo y este LM no los cubre.

Este modulo importa dspy; `config.py` lo importa de forma diferida.
"""

from typing import Any

import dspy
from dspy.utils.exceptions import ContextWindowExceededError

from .call import checked_response
from .errors import EmptyResponseError
from .failures import FailureClass, LLMCallFailure, LLMFailure
from .reflection import ReflectionGuard

# Kwargs de DSPy que no van al proveedor (LiteLLM ya recibe num_retries=0).
_DSPY_ONLY_KWARGS = ("cache", "rollout_id", "num_retries")


class DspyLLMCallFailure(LLMCallFailure, ContextWindowExceededError):  # noqa: N818 - como D1
    """`LLMCallFailure` que `ChatAdapter` (dspy 3.2.1) no reintenta con `JSONAdapter`."""

    def __init__(self, failure: LLMFailure, message: str | None = None, model: str | None = None):
        base = LLMCallFailure(failure, message)
        self.failure = failure
        self.model = model
        Exception.__init__(self, *base.args)


class DspyEmptyResponseError(EmptyResponseError, ContextWindowExceededError):
    """`EmptyResponseError` que `ChatAdapter` (dspy 3.2.1) no reintenta con `JSONAdapter`."""

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
    """Textos de las salidas de un LM de DSPy (str, o dict con "text")."""
    return [(o.get("text") or "") if isinstance(o, dict) else str(o) for o in outputs]


class CheckedLM(dspy.BaseLM):
    """LM de DSPy cuya unica llamada al proveedor es `checked_response` (SPEC-105)."""

    def __init__(
        self,
        model: str,
        role: str = "task",
        infra_retries: int | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ):
        kwargs.pop("cache", None)
        kwargs.pop("num_retries", None)
        super().__init__(
            model, temperature=temperature, max_tokens=max_tokens, cache=False, **kwargs
        )
        if "max_completion_tokens" in self.kwargs and self.kwargs.get("max_tokens") is None:
            del self.kwargs["max_tokens"]  # como dspy.LM en reasoning models
        self.num_retries = 0
        self.role = role
        self.infra_retries = infra_retries
        self._reflection_guard = ReflectionGuard()

    @property
    def _provider(self) -> str:
        return self.model.split("/", 1)[0] if "/" in self.model else "openai"

    @property
    def supports_function_calling(self) -> bool:
        import litellm

        return litellm.supports_function_calling(model=self.model)

    @property
    def supports_reasoning(self) -> bool:
        import litellm

        return litellm.supports_reasoning(self.model)

    @property
    def supports_response_schema(self) -> bool:
        import litellm

        return litellm.supports_response_schema(
            model=self.model, custom_llm_provider=self._provider
        )

    @property
    def supported_params(self) -> set[str]:
        import litellm

        params = litellm.get_supported_openai_params(
            model=self.model, custom_llm_provider=self._provider
        )
        return set(params) if params else set()

    def __call__(self, prompt: str | None = None, *, messages: list | None = None, **kwargs: Any):
        parent = super().__call__
        if self.role != "reflection":
            return parent(prompt, messages=messages, **kwargs)
        try:
            return self._reflection_guard.run(
                lambda: parent(prompt, messages=messages, **kwargs), _output_texts
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
        request = {**self.kwargs, **kwargs}
        for key in _DSPY_ONLY_KWARGS:
            request.pop(key, None)
        request["model"] = self.model
        try:
            return checked_response(
                request,
                messages or [{"role": "user", "content": prompt}],
                self.role,
                infra_retries=self.infra_retries,
                allow_tool_calls=True,
            )
        except LLMCallFailure as exc:
            cut = _cut_adapter_fallback(exc, self.model)
            if cut is exc:
                raise
            raise cut from exc
