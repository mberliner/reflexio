"""
Llamada comun con reintento propio de infraestructura (SPEC-104, D3, FR-011).

Sin importar `dspy`. La capa de llamada solo lanza: nunca llama a `record` ni a
`record_attempt` del contador (D4); cuenta quien conoce el caso. La unica
excepcion es `configuracion`, que fija el estado de aborto antes de lanzar.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
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
    import litellm

    def _call() -> Any:
        return litellm.completion(messages=messages, **{**kwargs, "num_retries": 0})

    response = call_with_infra_retry(
        _call, role, infra_retries=infra_retries, backoff_base=backoff_base
    )
    if response is not None:
        record_usage(role, response)
    return raise_for_response(response, role)
