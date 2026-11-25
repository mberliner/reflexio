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
messages, **kwargs)` devolviendo una respuesta con forma de OpenAI (en dspy 3.4.x
corre como plugin legacy deprecado, sin convertir excepciones ni reintentar; dspy
3.5 la elimina y hay que pasar al engine propio, D-018 b3), `BaseLM.__call__`, y las propiedades
`supports_*` / `supported_params`. No sobrescribe metodos privados de dspy.

- `reflection`: transporte del `ReflectionProposer` (`reflection.py`), conectado
  con `dspy_reflection_proposer` como `instruction_proposer` de `dspy.GEPA`
  (SPEC-105 FR-010): el prompt, el guard y la extraccion son del repo, no de dspy.
- `task`: el programa y la metrica se envuelven con
  `dspy_gepa_poc.call_failures.guard_program_and_metric` (SPEC-104 3e).

Fallback de adapters (SC-009 de SPEC-104): desde dspy 3.4 `ChatAdapter` cae a
`JSONAdapter` solo ante `AdapterParseError`, asi que una `LLMCallFailure` no
repite la llamada y se propaga tal cual (sin el corte por
`ContextWindowExceededError` que hacia falta en dspy 3.2.1; ademas `ReAct` trata
esa excepcion como ventana excedida y truncaria la trayectoria).

La cache de respuestas de DSPy no aplica a un LM propio: `cache=True` se rechaza
en `LLMConfig.get_dspy_lm()`. Vuelve con el engine propio de dspy 3.5 (D-018).

`aforward`/`acall` no se usan en el repo y este LM no los cubre.

Este modulo importa dspy; `config.py` lo importa de forma diferida.
"""

from typing import Any

import dspy

from .call import checked_response
from .reflection import ReflectionProposer

# Kwargs de DSPy que no van al proveedor (LiteLLM ya recibe num_retries=0).
_DSPY_ONLY_KWARGS = ("cache", "rollout_id", "num_retries")


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

    def forward(self, prompt: str | None = None, messages: list | None = None, **kwargs: Any):
        request = {**self.kwargs, **kwargs}
        for key in _DSPY_ONLY_KWARGS:
            request.pop(key, None)
        request["model"] = self.model
        return checked_response(
            request,
            messages or [{"role": "user", "content": prompt}],
            self.role,
            infra_retries=self.infra_retries,
            allow_tool_calls=True,
        )


def dspy_reflection_proposer(lm: Any) -> ReflectionProposer:
    """
    `ReflectionProposer` sobre un LM de DSPy (`CheckedLM` con rol `reflection`).

    Llama al LM con el prompt como texto y toma la primera salida, como hacia
    `DspyAdapter.stripped_lm_call` en dspy 3.2.1. Se pasa a `dspy.GEPA` como
    `instruction_proposer` y como callback (`gepa_kwargs={"callbacks": [...]}`).
    """

    def complete(prompt: str) -> str:
        return _output_texts(lm(prompt))[0]

    return ReflectionProposer(complete)
