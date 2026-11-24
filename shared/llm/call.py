"""
Llamada comun con reintento propio de infraestructura (SPEC-104, D3, FR-011).

Sin importar `dspy`. La capa de llamada solo lanza: nunca llama a `record` ni a
`record_attempt` del contador (D4); cuenta quien conoce el caso. La unica
excepcion es `configuracion`, que fija el estado de aborto antes de lanzar.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from .errors import EmptyResponseError
from .failures import (
    FailureClass,
    LLMCallFailure,
    LLMFailure,
    RunAborted,
    classify_exception,
    classify_response,
    get_failure_tracker,
    root_exception,
)
from .usage import record_usage

logger = logging.getLogger(__name__)

# Receptor opcional del finish_reason de la ultima respuesta sana del contexto actual.
_finish_reason_sink: ContextVar[list[str | None] | None] = ContextVar(
    "finish_reason_sink", default=None
)


@contextmanager
def capture_finish_reason() -> Iterator[list[str | None]]:
    """
    Captura el `finish_reason` de la respuesta sana de las llamadas hechas dentro
    del bloque (SPEC-104 FR-004: el de la llamada baseline sana). La lista cede el
    de la ultima llamada, o queda vacia si ninguna respondio sana.
    """
    sink: list[str | None] = []
    token = _finish_reason_sink.set(sink)
    try:
        yield sink
    finally:
        _finish_reason_sink.reset(token)


def call_with_infra_retry[T](
    fn: Callable[[], T],
    role: str,
    *,
    infra_retries: int | None = None,
    backoff_base: float = 1.0,
) -> T:
    """
    Ejecuta `fn` reintentando solo fallas de `infraestructura` (espera 1, 2, 4 s).

    Con el contador abortado lanza `RunAborted` sin llamar. `configuracion` fija
    el aborto y lanza; cualquier otra clase lanza `LLMCallFailure` desde la
    excepcion original.
    """
    tracker = get_failure_tracker()
    retries = tracker.infra_retries if infra_retries is None else infra_retries
    attempt = 0
    while True:
        tracker.check_abort()
        try:
            return fn()
        except (RunAborted, LLMCallFailure):
            raise
        except Exception as exc:
            clase = classify_exception(exc)
            failure = LLMFailure(
                clase=clase,
                rol=role,
                causa=type(root_exception(exc)).__name__,
                finish_reason=None,
            )
            if clase == FailureClass.infraestructura and attempt < retries:
                wait = backoff_base * 2**attempt
                logger.debug(
                    "Reintento de infraestructura %d/%d (rol=%s, causa=%s) en %.1fs",
                    attempt + 1,
                    retries,
                    role,
                    failure.causa,
                    wait,
                )
                time.sleep(wait)
                attempt += 1
                continue
            if clase == FailureClass.configuracion:
                tracker.abort(failure, f"{failure.causa}: {exc}")
            raise LLMCallFailure(
                failure,
                f"Falla de LLM (rol={role}, clase={clase.value}, causa={failure.causa}): {exc}",
            ) from exc


def raise_for_response(response: Any, role: str) -> str:
    """
    Devuelve el texto de una respuesta sana (sin strip) o lanza la falla de capa 1.

    Lanza `EmptyResponseError` si no hay texto y `LLMCallFailure` en los demas
    casos; una respuesta `None` es `configuracion` y fija el aborto. No reintenta.
    """
    clase = classify_response(response)
    if clase is None:
        return response.choices[0].message.content
    if response is None:
        failure = LLMFailure(clase=clase, rol=role, causa="NoneResponse")
        get_failure_tracker().abort(failure, "litellm.completion devolvio None")
        raise LLMCallFailure(failure, f"Respuesta None del LLM (rol={role})")
    choice = response.choices[0] if getattr(response, "choices", None) else None
    finish_reason = getattr(choice, "finish_reason", None)
    content = getattr(getattr(choice, "message", None), "content", None)
    logger.debug(
        "Falla de respuesta (rol=%s, clase=%s, finish_reason=%s)", role, clase.value, finish_reason
    )
    if content is None or not str(content).strip():
        raise EmptyResponseError(role, finish_reason, clase)
    failure = LLMFailure(
        clase=clase, rol=role, causa=str(finish_reason), finish_reason=finish_reason
    )
    raise LLMCallFailure(failure)


def checked_completion(
    kwargs: dict[str, Any],
    messages: list[dict[str, Any]],
    role: str,
    *,
    infra_retries: int | None = None,
    backoff_base: float = 1.0,
) -> str:
    """
    Unica llamada a `litellm.completion` de produccion: `num_retries=0`, reintento
    propio de infraestructura, uso de tokens y clasificacion de la respuesta.

    Recibe los kwargs ya restringidos (`apply_constraints` sigue en el llamador).
    """
    return checked_completion_with_reason(
        kwargs, messages, role, infra_retries=infra_retries, backoff_base=backoff_base
    )[0]


def checked_completion_with_reason(
    kwargs: dict[str, Any],
    messages: list[dict[str, Any]],
    role: str,
    *,
    infra_retries: int | None = None,
    backoff_base: float = 1.0,
) -> tuple[str, str | None]:
    """
    Como `checked_completion`, pero devuelve `(texto, finish_reason)` de la
    respuesta sana; ademas lo publica en `capture_finish_reason` si hay un bloque
    activo. Las fallas se lanzan igual que en `checked_completion`.
    """
    import litellm

    def _call() -> Any:
        return litellm.completion(messages=messages, **{**kwargs, "num_retries": 0})

    response = call_with_infra_retry(
        _call, role, infra_retries=infra_retries, backoff_base=backoff_base
    )
    if response is not None:
        record_usage(role, response)
    text = raise_for_response(response, role)
    finish_reason = getattr(response.choices[0], "finish_reason", None)
    sink = _finish_reason_sink.get()
    if sink is not None:
        sink[:] = [finish_reason]
    return text, finish_reason
