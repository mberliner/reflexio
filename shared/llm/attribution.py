"""
Atribucion de fallas de la tarea contra el baseline (SPEC-104, D5, FR-004).

Sin importar `dspy`, `gepa_standalone` ni `dspy_gepa_poc`. El nucleo es comun a
ambos subproyectos; cada uno aporta solo la forma de llamar al baseline sobre un
caso (`call_baseline`). La llamada de atribucion no cuenta como intento ni como
falla (D4): llama directo a la capa de llamada, que nunca cuenta; la unica falla
que se registra es la del candidato ya atribuida.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from typing import Any

from .failures import FailureClass, LLMCallFailure, LLMFailure, count_key

_ATTRIBUTABLE = (FailureClass.entrada, FailureClass.presupuesto)
_CANDIDATE_SCORED_KEYS = frozenset({"entrada_candidato", "presupuesto_candidato", "formato"})


@dataclass(frozen=True)
class BaselineOutcome:
    """
    Resultado de ejecutar el baseline sobre un caso. `clase` None = la llamada
    respondio sin falla de capa 1 (un `formato` de capa 2 tampoco interviene).
    """

    clase: FailureClass | None = None
    causa: str | None = None
    finish_reason: str | None = None


def attribute_failure(failure: LLMFailure, outcome: BaselineOutcome) -> LLMFailure:
    """
    Atribuye una falla `entrada`/`presupuesto` de la tarea contra el baseline.

    El baseline sin falla deja `candidato`; con la misma clase, `externa`; con otra
    clase, la falla del caso pasa a ser la del baseline (`clase` y `causa` del
    outcome; `externa` si es `entrada`/`presupuesto`, sin atribucion si no). En todos
    los casos `finish_reason` es el de la llamada del candidato y
    `baseline_finish_reason` el del baseline. Las demas clases y roles no se atribuyen.
    """
    if failure.rol != "task" or failure.clase not in _ATTRIBUTABLE:
        return failure
    if outcome.clase is None:
        atribucion, clase, causa = "candidato", failure.clase, failure.causa
    elif outcome.clase == failure.clase:
        atribucion, clase, causa = "externa", failure.clase, failure.causa
    else:
        clase = outcome.clase
        causa = outcome.causa or failure.causa
        atribucion = "externa" if clase in _ATTRIBUTABLE else None
    return replace(
        failure,
        clase=clase,
        causa=causa,
        atribucion=atribucion,
        baseline_finish_reason=outcome.finish_reason,
    )


class BaselineProbe:
    """
    Ejecuta el baseline sobre un caso y atribuye fallas de la tarea.

    `call_baseline(case)` corre el baseline con los mismos parametros que la tarea
    y lanza `LLMCallFailure` ante una falla de capa 1 (un `BaselineOutcome` devuelto
    aporta el `finish_reason` de la respuesta sana; otro retorno = sin falla).
    El resultado se cachea por `case_id` para toda la corrida, con una sola
    ejecucion por caso aun con hilos concurrentes, salvo `infraestructura`,
    que deja el caso NE esa vez y se vuelve a consultar la proxima.
    `RunAborted` y cualquier otra excepcion se propagan sin cachearse.
    """

    def __init__(self, call_baseline: Callable[[Any], Any]) -> None:
        self._call_baseline = call_baseline
        self._guard = threading.Lock()
        self._case_locks: dict[str, threading.Lock] = {}
        self._cache: dict[str, BaselineOutcome] = {}

    def outcome(self, case_id: str, case: Any) -> BaselineOutcome:
        """Resultado del baseline sobre el caso (cacheado salvo `infraestructura`)."""
        with self._guard:
            cached = self._cache.get(case_id)
            if cached is not None:
                return cached
            case_lock = self._case_locks.setdefault(case_id, threading.Lock())
        with case_lock:
            with self._guard:
                cached = self._cache.get(case_id)
            if cached is not None:
                return cached
            try:
                returned = self._call_baseline(case)
                result = returned if isinstance(returned, BaselineOutcome) else BaselineOutcome()
            except LLMCallFailure as exc:
                failure = exc.failure
                result = BaselineOutcome(failure.clase, failure.causa, failure.finish_reason)
            if result.clase != FailureClass.infraestructura:
                with self._guard:
                    self._cache[case_id] = result
            return result

    def attribute(
        self, failure: LLMFailure, case_id: str, case: Any, *, is_baseline: bool
    ) -> LLMFailure:
        """
        Falla ya atribuida y con `case_id`. Con `is_baseline` la atribucion es la
        causa externa sin llamar; las clases y roles no atribuibles no llaman.
        """
        failure = replace(failure, case_id=case_id)
        if failure.rol != "task" or failure.clase not in _ATTRIBUTABLE:
            return failure
        if is_baseline:
            return replace(failure, atribucion="externa")
        return attribute_failure(failure, self.outcome(case_id, case))


def is_evaluated(failure: LLMFailure | None) -> bool:
    """
    True si el caso cuenta como evaluado (tabla de tratamiento): sin falla, o falla
    de la tarea que es score 0 del candidato; el resto es NE.
    """
    if failure is None:
        return True
    return failure.rol == "task" and count_key(failure) in _CANDIDATE_SCORED_KEYS


def failure_to_dict(failure: LLMFailure) -> dict[str, Any]:
    """Dict serializable con todos los campos de la falla, `clase` como texto y `clave`."""
    data = asdict(failure)
    data["clase"] = failure.clase.value
    data["clave"] = count_key(failure)
    return data
