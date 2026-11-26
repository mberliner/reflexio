"""
LM de DSPy sobre el punto de llamada propio (SPEC-105 FR-001/FR-002/FR-003/FR-004/FR-005).

`LLMConfig.get_dspy_lm()` devuelve un `dspy.LM` con un engine propio
(`CheckedEngine`), el contrato publico de dspy 3.5 para backends propios:
`dspy.LM(model, engine=<objeto con complete(Request) -> Response>)`. El engine
traduce el `Request` de dspy a mensajes y kwargs de Chat Completions y llama a
`shared.llm.call.checked_response`, el mismo punto que usa `gepa_standalone`.
Ahi se hacen la llamada a LiteLLM (`num_retries=0`), el reintento propio de
`infraestructura` (SPEC-104 D3, FR-011), el registro del uso de tokens del rol y
del `finish_reason` (FR-004 de SPEC-104) y la clasificacion de capa 1 sobre la
respuesta y las excepciones crudas de LiteLLM. dspy no reintenta
(`num_retries=0`) ni cachea (`cache=False`, ver FR-009).

El engine es dueno de la conexion y de los parametros de generacion de la
config (`params`: `temperature`, `max_tokens` / `max_completion_tokens`,
`api_key`, `api_base`, `api_version`, `timeout`, `output_config`, `thinking`):
`dspy.LM` no recibe ninguno, asi dspy no aplica reglas propias de modelo
(p. ej. su chequeo de reasoning models) sobre lo que ya resolvio
`LLMConfig.apply_constraints`. El `Request` solo aporta los mensajes y lo que el
adapter pide por llamada (`response_format` de `JSONAdapter`), que pisa a
`params` como hacia `CheckedLM`.

Traduccion propia y estricta (lm15 no expone un conversor publico de salida):
mensajes `user`/`assistant` con texto, `system` de texto y los campos de
`Config` de `_CONFIG_PARAMS`. Cualquier otra cosa (herramientas, imagenes,
`continuation`, `reasoning`, cache de prompt, un campo nuevo de `Config`) lanza
`dspy.lm15.UnsupportedFeatureError` antes de llamar: falla fuerte, no se
descarta en silencio.

Fallas (SPEC-104 sin cambio observable, FR-006): dspy 3.5 corre el engine dentro
de `error_boundary(unexpected=True)` y convierte toda excepcion que no sea un
`dspy.LMError` en `LMUnexpectedError`; las `dspy.LMError` pasan por identidad.
Por eso el engine relanza `LLMCallFailure` (incluida `EmptyResponseError`) y
`RunAborted` como una subclase de su misma clase y de `dspy.LMError`
(`dspy_visible`): los `except LLMCallFailure` / `except RunAborted` del repo las
siguen atrapando, con el mismo `failure`, mensaje y causa.

- `reflection`: transporte del `ReflectionProposer` (`reflection.py`), conectado
  con `dspy_reflection_proposer` como `instruction_proposer` de `dspy.GEPA`
  (SPEC-105 FR-010): el prompt, el guard y la extraccion son del repo, no de dspy.
- `task`: el programa y la metrica se envuelven con
  `dspy_gepa_poc.call_failures.guard_program_and_metric` (SPEC-104 3e).

Adapter (FR-012): dspy 3.5 cambia el adapter por defecto de `ChatAdapter` a
`XMLAdapter`, otro formato de prompt de la tarea. `configure_dspy` fija
`dspy.ChatAdapter()` (mismo prompt que dspy 3.2.1 / 3.4.1); cambiarlo es un
cambio de optimizacion, no un ajuste.

Este modulo importa dspy; `config.py` lo importa de forma diferida.
"""

from __future__ import annotations

import dataclasses
from functools import cache
from typing import Any

import dspy
from dspy.lm15 import (
    Config,
    Message,
    Request,
    Response,
    TextPart,
    UnsupportedFeatureError,
    Usage,
)

from .call import checked_response
from .failures import LLMCallFailure, RunAborted
from .reflection import ReflectionProposer

# Campos de `Config` que el engine envia, con su nombre en Chat Completions.
# `max_tokens` va aparte (su nombre depende del modelo, ver `CheckedEngine`).
_CONFIG_PARAMS = {
    "temperature": "temperature",
    "top_p": "top_p",
    "seed": "seed",
    "frequency_penalty": "frequency_penalty",
    "presence_penalty": "presence_penalty",
    "response_format": "response_format",
}
_CONFIG_HANDLED = frozenset({*_CONFIG_PARAMS, "max_tokens", "stop", "extensions"})
_ROLES = frozenset({"user", "assistant"})


def _unset(value: Any) -> bool:
    return value is None or value == () or value == {}


def _text(parts: tuple, where: str) -> str | list[dict[str, str]]:
    """Contenido de Chat Completions de partes de texto: str si es una, bloques si son varias."""
    for part in parts:
        if not isinstance(part, TextPart) or part.continuation:
            raise UnsupportedFeatureError(
                f"CheckedEngine solo envia texto: {where} trae una parte "
                f"{getattr(part, 'type', type(part).__name__)!r}"
                f"{' con continuation' if isinstance(part, TextPart) else ''}"
            )
    if len(parts) == 1:
        return parts[0].text
    return [{"type": "text", "text": part.text} for part in parts]


def chat_response_format(value: dict[str, Any]) -> dict[str, Any]:
    """
    `response_format` canonico de lm15 -> el de Chat Completions.

    lm15 lo escribe `{"type": "json_schema", "schema", "name"?, "strict"?}`; Chat
    Completions (y LiteLLM, que lo pasa tal cual) espera el esquema dentro de
    `json_schema`. Mismo dict, con el mismo orden de claves, que LiteLLM armaba
    desde el modelo pydantic que mandaba `JSONAdapter` en dspy 3.4.1
    (`schema`, `name`, `strict`; golden SC-008, D-018 c2).
    """
    if value.get("type") != "json_schema":
        return value
    inner: dict[str, Any] = {"schema": value["schema"], "name": value.get("name") or "response"}
    if "strict" in value:
        inner["strict"] = value["strict"]
    return {"type": "json_schema", "json_schema": inner}


def request_to_chat(
    request: Request, max_tokens_param: str = "max_tokens"
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    `(messages, params)` de Chat Completions para un `dspy.lm15.Request`.

    `params` trae solo los campos de `Config` presentes en el request (los que
    pisan a los de la config). Lanza `UnsupportedFeatureError` ante lo que el
    engine no sabe enviar.
    """
    if request.tools:
        raise UnsupportedFeatureError("CheckedEngine no envia herramientas (Request.tools)")
    messages: list[dict[str, Any]] = []
    if request.system is not None:
        system = request.system
        content = system if isinstance(system, str) else _text(system, "Request.system")
        messages.append({"role": "system", "content": content})
    for index, message in enumerate(request.messages):
        where = f"Request.messages[{index}]"
        if message.role not in _ROLES or message.continuation:
            raise UnsupportedFeatureError(
                f"CheckedEngine no envia {where} (role={message.role!r}"
                f"{', con continuation' if message.continuation else ''})"
            )
        messages.append({"role": message.role, "content": _text(message.parts, where)})

    config = request.config
    params: dict[str, Any] = {}
    for field in dataclasses.fields(Config):
        value = getattr(config, field.name)
        if _unset(value):
            continue
        if field.name not in _CONFIG_HANDLED:
            raise UnsupportedFeatureError(
                f"CheckedEngine no envia Config.{field.name} (valor {value!r})"
            )
        if field.name == "response_format":
            value = chat_response_format(value)
        if field.name in _CONFIG_PARAMS:
            params[_CONFIG_PARAMS[field.name]] = value
    if config.max_tokens is not None:
        params[max_tokens_param] = config.max_tokens
    if config.stop:
        params["stop"] = list(config.stop)
    params.update(config.extensions or {})
    return messages, params


def _token_count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def chat_response(response: Any, model: str) -> Response:
    """
    `dspy.lm15.Response` de una respuesta sana de LiteLLM (`checked_response`).

    Una respuesta sana ya paso la capa 1 (texto no vacio, sin `length` ni
    filtro), asi que su `finish_reason` es `stop` para dspy; el crudo lo
    registra el punto de llamada (`capture_finish_reason`).
    """
    usage = getattr(response, "usage", None)
    response_id = getattr(response, "id", None)
    return Response(
        id=response_id if isinstance(response_id, str) and response_id else None,
        model=model,
        message=Message.assistant(response.choices[0].message.content),
        finish_reason="stop",
        usage=Usage(
            input_tokens=_token_count(getattr(usage, "prompt_tokens", None)),
            output_tokens=_token_count(getattr(usage, "completion_tokens", None)),
        ),
    )


@cache
def _dspy_visible_class(cls: type[BaseException]) -> type[BaseException]:
    return type(cls.__name__, (cls, dspy.LMError), {"__module__": cls.__module__})


def dspy_visible(exc: LLMCallFailure | RunAborted, model: str) -> BaseException:
    """
    Copia de `exc` que dspy deja pasar sin convertir: misma clase (subclase) y
    mismos atributos, mas `dspy.LMError` (dspy 3.5 preserva sus errores por
    identidad en `error_boundary`). Conserva causa y traceback.
    """
    if isinstance(exc, dspy.LMError):
        return exc
    cls = _dspy_visible_class(type(exc))
    visible = cls.__new__(cls, *exc.args)
    visible.__dict__.update(exc.__dict__)
    visible.args = exc.args
    defaults = {
        "message": str(exc),
        "code": dspy.LMError.default_code,
        "model": model,
        "provider": None,
        "provider_code": None,
        "status": None,
        "request_id": None,
        "retry_after": None,
    }
    for name, value in defaults.items():
        if name not in visible.__dict__:
            setattr(visible, name, value)
    visible.__cause__ = exc.__cause__
    visible.__suppress_context__ = exc.__suppress_context__
    return visible.with_traceback(exc.__traceback__)


class CheckedEngine:
    """
    Engine de dspy (`complete(Request) -> Response`) cuya unica llamada al
    proveedor es `checked_response` (SPEC-105 FR-002).

    `params` son los kwargs de LiteLLM de la config, ya restringidos por modelo
    (`LLMConfig.apply_constraints`), sin `model`. El nombre del tope de tokens
    que pide un `Request` es el de `params` (`max_completion_tokens` en los
    reasoning models de OpenAI/Azure, `max_tokens` si no).
    """

    def __init__(
        self,
        model: str,
        role: str = "task",
        params: dict[str, Any] | None = None,
        infra_retries: int | None = None,
    ):
        self.model = model
        self.role = role
        self.params = dict(params or {})
        self.infra_retries = infra_retries
        self.max_tokens_param = (
            "max_completion_tokens" if "max_completion_tokens" in self.params else "max_tokens"
        )

    @property
    def _provider(self) -> str:
        return self.model.split("/", 1)[0] if "/" in self.model else "openai"

    # Pistas de capacidad que dspy lee del engine (adapters: `response_format`).
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

    def request_kwargs(self, request: Request) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """`(messages, kwargs)` que recibe `checked_response` para `request`."""
        messages, overrides = request_to_chat(request, self.max_tokens_param)
        return messages, {**self.params, **overrides, "model": self.model}

    def complete(self, request: Request) -> Response:
        messages, kwargs = self.request_kwargs(request)
        try:
            response = checked_response(
                kwargs, messages, self.role, infra_retries=self.infra_retries
            )
        except (LLMCallFailure, RunAborted) as exc:
            raise dspy_visible(exc, self.model) from exc.__cause__
        return chat_response(response, request.model)

    def __repr__(self) -> str:
        return f"CheckedEngine(model={self.model!r}, role={self.role!r})"


def checked_lm(engine: CheckedEngine) -> dspy.LM:
    """`dspy.LM` sobre `engine`, sin reintentos ni cache de dspy."""
    return dspy.LM(engine.model, engine=engine, model_type="chat", cache=False, num_retries=0)


def configure_dspy(lm: dspy.LM, **settings: Any) -> None:
    """`dspy.configure` con el LM y el adapter del repo (`dspy.ChatAdapter()`, FR-012)."""
    dspy.configure(lm=lm, adapter=dspy.ChatAdapter(), **settings)


def chain_of_thought(signature: Any, **config: Any) -> dspy.ChainOfThought:
    """
    `dspy.ChainOfThought` con el campo `reasoning` de texto (`str`), como en dspy
    3.4.1 (FR-012).

    dspy 3.5.0 cambia sin aviso el tipo por defecto del campo a `dspy.Reasoning`:
    con un LM que declara `supports_reasoning` (gpt-5.x) quita el campo del prompt
    y pide razonamiento nativo (`reasoning_effort="low"`, `Config.reasoning`), que
    es otro prompt de tarea y otro parametro de generacion. Con `str` el prompt es
    el de 3.4.1 (golden SC-008) y el `Request` no lleva `reasoning`.
    """
    return dspy.ChainOfThought(signature, rationale_field_type=str, **config)


def _output_texts(outputs: list) -> list[str]:
    """Textos de las salidas de un LM de DSPy (str, o dict con "text")."""
    return [(o.get("text") or "") if isinstance(o, dict) else str(o) for o in outputs]


def dspy_reflection_proposer(lm: Any) -> ReflectionProposer:
    """
    `ReflectionProposer` sobre un LM de DSPy (`dspy.LM` con `CheckedEngine` de rol
    `reflection`).

    Llama al LM con el prompt como texto (un mensaje `user`) y toma la primera
    salida, como hacia `DspyAdapter.stripped_lm_call` en dspy 3.2.1. Se pasa a
    `dspy.GEPA` como `instruction_proposer` y como callback
    (`gepa_kwargs={"callbacks": [...]}`).
    """

    def complete(prompt: str) -> str:
        return _output_texts(lm(prompt))[0]

    return ReflectionProposer(complete)
