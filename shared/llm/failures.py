"""
Clasificacion de fallas de LLM y contador por corrida (SPEC-104, D1 y D2).

Sin importar `dspy`, `gepa_standalone`, `dspy_gepa_poc` ni `shared.llm.errors`
(que importa este modulo). El clasificador de la capa 1 son funciones puras con
las reglas 1 a 6 de la spec; `FailureTracker` sigue el patron de `usage.py`
(`threading.Lock`, instancia de modulo, `reset()` por corrida).
"""

from __future__ import annotations

import copy
import logging
import threading
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)

ROLES = ("task", "judge", "reflection")


class FailureClass(StrEnum):
    """Clases de falla (valor = nombre)."""

    configuracion = "configuracion"
    entrada = "entrada"
    infraestructura = "infraestructura"
    filtro_salida = "filtro_salida"
    presupuesto = "presupuesto"
    sin_texto = "sin_texto"
    formato = "formato"


@dataclass(frozen=True)
class LLMFailure:
    """Una falla clasificada. `case_id` y `atribucion` los completa quien conoce el caso."""

    clase: FailureClass
    rol: str
    causa: str
    finish_reason: str | None = None
    case_id: str | None = None
    atribucion: str | None = None  # "candidato" | "externa" | None
    # `finish_reason` de la llamada baseline de la atribucion (FR-004); None sin atribuir.
    baseline_finish_reason: str | None = None


class LLMCallFailure(Exception):  # noqa: N818 - nombre fijado por D1
    """Falla de una llamada al LLM; `raise ... from exc` conserva la excepcion original."""

    def __init__(self, failure: LLMFailure, message: str | None = None):
        self.failure = failure
        default = (
            f"Falla de LLM (rol={failure.rol}, clase={failure.clase.value}, causa={failure.causa})"
        )
        super().__init__(message or default)


class RunAborted(Exception):  # noqa: N818 - nombre fijado por D1
    """
    Corrida abortada por estado. NO hereda de `LLMCallFailure`: un envoltorio que
    atrapa `LLMCallFailure` para marcar NE no debe tragarse el aborto.
    """

    def __init__(
        self,
        failure: LLMFailure,
        motivo: str,
        conteo: int = 0,
        intentos: int = 0,
        clave: str | None = None,
    ):
        self.failure = failure
        self.motivo = motivo
        self.conteo = conteo
        self.intentos = intentos
        self.clave = clave or count_key(failure)
        msg = (
            f"Corrida abortada: clase={self.clave} rol={failure.rol} "
            f"conteo={conteo}/{intentos} causa={failure.causa}. {motivo}"
        )
        if self.clave == "presupuesto":
            if failure.rol == "task":
                msg += " El baseline tambien se corta en esos casos."
            msg += " Subir `max_tokens`."
        super().__init__(msg)


# ==================== Clasificador de la capa 1 ====================

_ENTRADA_BODY_CODES = frozenset(
    {"content_filter", "content_policy_violation", "context_length_exceeded"}
)
_ENTRADA_CLASSES = frozenset({"ContentPolicyViolationError", "ContextWindowExceededError"})
_INFRA_CLASSES = frozenset(
    {
        "RateLimitError",
        "Timeout",
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
        "ServiceUnavailableError",
        "BadGatewayError",
    }
)
_INFRA_STATUS = frozenset({408, 409, 429})


def _is_api_exception(exc: BaseException) -> bool:
    mro = type(exc).__mro__
    return any(c.__module__.split(".")[0] in ("openai", "litellm") for c in mro)


def root_exception(exc: BaseException) -> BaseException:
    """Primera excepcion de `openai`/LiteLLM en la cadena `__cause__`, o `exc` si no hay."""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        if _is_api_exception(cur):
            return cur
        seen.add(id(cur))
        cur = cur.__cause__
    return exc


def _class_names(exc: BaseException) -> set[str]:
    return {c.__name__ for c in type(exc).__mro__}


def _body_dict(exc: BaseException) -> dict[str, Any]:
    body = getattr(exc, "body", None)
    return body if isinstance(body, dict) else {}


def _is_entrada(exc: BaseException) -> bool:
    names = _class_names(exc)
    if names & _ENTRADA_CLASSES:
        return True
    if "BadRequestError" in names:
        body = _body_dict(exc)
        if body.get("code") in _ENTRADA_BODY_CODES:
            return True
        inner = body.get("innererror")
        if isinstance(inner, dict) and inner.get("code") == "ResponsibleAIPolicyViolation":
            return True
    return "request_too_large" in str(exc)


def _is_infra(exc: BaseException) -> bool:
    if _class_names(exc) & _INFRA_CLASSES:
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and (status in _INFRA_STATUS or status >= 500)


def classify_exception(exc: BaseException) -> FailureClass:
    """Reglas 1 a 3 de la spec sobre la primera excepcion de API de la cadena."""
    root = root_exception(exc)
    if _is_entrada(root):
        return FailureClass.entrada
    if _is_infra(root):
        return FailureClass.infraestructura
    return FailureClass.configuracion


def _first_choice(response: Any) -> Any:
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    return choices[0] if choices else None


def classify_response(response: Any) -> FailureClass | None:
    """Reglas 3 (respuesta `None`) y 4 a 6 sobre una respuesta HTTP 200; None si es sana."""
    if response is None:
        return FailureClass.configuracion
    choice = _first_choice(response)
    if choice is None:
        return FailureClass.sin_texto
    message = getattr(choice, "message", None)
    finish_reason = getattr(choice, "finish_reason", None)
    if finish_reason == "content_filter" or bool(getattr(message, "refusal", None)):
        return FailureClass.filtro_salida
    if finish_reason == "length":
        return FailureClass.presupuesto
    content = getattr(message, "content", None)
    if content is None or not str(content).strip():
        return FailureClass.sin_texto
    return None


# ==================== Contador ====================

_THRESHOLD_KEYS = frozenset(
    {
        "presupuesto",
        "infraestructura",
        "sin_texto",
        "filtro_salida",
        "entrada_dato",
        "entrada",
        "formato",
        "total",
    }
)

DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "presupuesto": {"task": 0.05, "judge": 0.05, "reflection": 0.25},
    "infraestructura": {"task": 0.10, "judge": 0.10},
    "sin_texto": {"task": 0.10, "judge": 0.10},
    "filtro_salida": {"task": 0.10, "judge": 0.10},
    "entrada_dato": {"task": 0.10},
    "entrada": {"judge": 0.10},
    "formato": {"judge": 0.10},
    "total": {"reflection": 0.50},
}
DEFAULT_MIN_ATTEMPTS: dict[str, int] = {"task": 20, "judge": 20, "reflection": 4}
DEFAULT_INFRA_RETRIES = 3


def count_key(failure: LLMFailure) -> str:
    """Clave de conteo de una falla (nombres de la spec)."""
    clase = failure.clase.value
    if clase in ("entrada", "presupuesto"):
        if failure.atribucion == "candidato":
            return f"{clase}_candidato"
        if failure.atribucion == "externa" and clase == "entrada":
            return "entrada_dato"
    return clase


def _check_role(rol: str) -> None:
    if rol not in ROLES:
        raise ValueError(f"Rol desconocido: {rol!r} (validos: {', '.join(ROLES)})")


class FailureTracker:
    """Contador thread-safe de fallas por (clave, rol) con umbrales y estado de aborto."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._init_state()

    def _init_state(self) -> None:
        self._counts: dict[str, dict[str, int]] = {}
        self._attempts: dict[str, int] = dict.fromkeys(ROLES, 0)
        self._cases: dict[str, set[str]] = {rol: set() for rol in ROLES}
        self._dato_cases: set[str] = set()
        self._last: dict[tuple[str, str], LLMFailure] = {}
        self._abort: dict[str, Any] | None = None
        self._thresholds = copy.deepcopy(DEFAULT_THRESHOLDS)
        self._min_attempts = dict(DEFAULT_MIN_ATTEMPTS)
        self._infra_retries = DEFAULT_INFRA_RETRIES

    def reset(self) -> None:
        """Limpia conteos, intentos, casos y aborto, y restaura la configuracion por defecto."""
        with self._lock:
            self._init_state()

    @property
    def infra_retries(self) -> int:
        with self._lock:
            return self._infra_retries

    @property
    def aborted(self) -> bool:
        with self._lock:
            return self._abort is not None

    def configure(
        self,
        thresholds: dict[str, dict[str, float]] | None = None,
        min_attempts: dict[str, int] | None = None,
        infra_retries: int | None = None,
    ) -> None:
        """Mezcla parcial sobre los defaults; valores invalidos son `ValueError`."""
        for clave, by_role in (thresholds or {}).items():
            if clave not in _THRESHOLD_KEYS:
                raise ValueError(f"Clave de umbral desconocida: {clave!r}")
            for rol, rate in by_role.items():
                _check_role(rol)
                valid = isinstance(rate, (int, float)) and not isinstance(rate, bool)
                if not valid or not 0 <= rate <= 1:
                    raise ValueError(f"Umbral {clave}/{rol} fuera de [0, 1]: {rate!r}")
        for rol, n in (min_attempts or {}).items():
            _check_role(rol)
            if isinstance(n, bool) or not isinstance(n, int) or n < 0:
                raise ValueError(f"min_attempts {rol} debe ser un entero >= 0: {n!r}")
        bad_retries = infra_retries is not None and (
            not isinstance(infra_retries, int)
            or isinstance(infra_retries, bool)
            or infra_retries < 0
        )
        if bad_retries:
            raise ValueError(f"infra_retries debe ser un entero >= 0: {infra_retries!r}")
        with self._lock:
            new_thr = copy.deepcopy(self._thresholds)
            for clave, by_role in (thresholds or {}).items():
                for rol, rate in by_role.items():
                    new_thr.setdefault(clave, {})[rol] = float(rate)
            new_min = dict(self._min_attempts)
            for rol, n in (min_attempts or {}).items():
                new_min[rol] = n
            self._thresholds = new_thr
            self._min_attempts = new_min
            if infra_retries is not None:
                self._infra_retries = infra_retries

    # ---- registro ----

    def record_attempt(self, rol: str, case_id: str | None = None) -> None:
        """Suma un caso intentado del rol (una vez por caso y candidato, nunca por llamada HTTP)."""
        _check_role(rol)
        with self._lock:
            self._attempts[rol] += 1
            if case_id is not None:
                self._cases[rol].add(case_id)
            self._evaluate_locked(rol)

    def record(self, failure: LLMFailure) -> None:
        """Cuenta una falla (una vez por caso) y evalua los umbrales del rol."""
        rol = failure.rol
        _check_role(rol)
        clave = count_key(failure)
        with self._lock:
            if clave == "entrada_dato" and failure.case_id is not None:
                if failure.case_id in self._dato_cases:
                    logger.debug(
                        "Falla repetida (rol=%s, clave=%s, case_id=%s): no suma",
                        rol,
                        clave,
                        failure.case_id,
                    )
                    return
                self._dato_cases.add(failure.case_id)
            by_role = self._counts.setdefault(clave, {})
            by_role[rol] = by_role.get(rol, 0) + 1
            self._last[(clave, rol)] = failure
            self._last[("total", rol)] = failure
            logger.warning(
                "Falla de LLM: rol=%s clave=%s atribucion=%s causa=%s finish_reason=%s "
                "case_id=%s%s",
                rol,
                clave,
                failure.atribucion,
                failure.causa,
                failure.finish_reason,
                failure.case_id,
                (
                    f" baseline_finish_reason={failure.baseline_finish_reason}"
                    if failure.baseline_finish_reason is not None
                    else ""
                ),
            )
            self._settle_pending_locked(failure, clave)
            if failure.clase == FailureClass.configuracion and self._abort is None:
                self._abort_locked(failure, "Falla de configuracion", clave=clave)
            self._evaluate_locked(rol)

    # ---- umbrales y aborto ----

    def _rate_locked(self, clave: str, rol: str) -> tuple[int, int]:
        if clave == "total":
            num = sum(by_role.get(rol, 0) for by_role in self._counts.values())
            return num, self._attempts[rol]
        num = self._counts.get(clave, {}).get(rol, 0)
        if clave == "entrada_dato":
            return num, len(self._cases["task"])
        return num, self._attempts[rol]

    def _evaluate_locked(self, rol: str) -> None:
        if self._abort is not None:
            return
        for clave, by_role in self._thresholds.items():
            threshold = by_role.get(rol)
            if threshold is None:
                continue
            num, den = self._rate_locked(clave, rol)
            if den < self._min_attempts[rol] or den == 0 or num / den <= threshold:
                continue
            failure = self._last.get((clave, rol))
            if failure is None:
                continue
            motivo = f"Tasa {num}/{den} supera el umbral {threshold}"
            self._abort_locked(failure, motivo, clave=clave, conteo=num, intentos=den)
            return

    def _abort_locked(
        self,
        failure: LLMFailure,
        motivo: str,
        clave: str | None = None,
        conteo: int | None = None,
        intentos: int | None = None,
        pendiente: bool = False,
    ) -> None:
        if self._abort is not None:
            return
        clave = clave or count_key(failure)
        if conteo is None or intentos is None:
            known = failure.rol in ROLES
            conteo, intentos = self._rate_locked(clave, failure.rol) if known else (0, 0)
        self._abort = {
            "failure": failure,
            "motivo": motivo,
            "conteo": conteo,
            "intentos": intentos,
            "clave": clave,
            "pendiente": pendiente,
        }
        if not pendiente:
            self._log_abort_locked()

    def _log_abort_locked(self) -> None:
        state = self._abort
        state["pendiente"] = False
        logger.error(
            "Corrida abortada: clase=%s rol=%s conteo=%s/%s causa=%s. %s",
            state["clave"],
            state["failure"].rol,
            state["conteo"],
            state["intentos"],
            state["failure"].causa,
            state["motivo"],
        )

    def _settle_pending_locked(self, failure: LLMFailure, clave: str) -> None:
        """Completa el aborto fijado por la capa de llamada con la falla ya contada."""
        state = self._abort
        if state is None or not state["pendiente"]:
            return
        if state["clave"] != clave or state["failure"].rol != failure.rol:
            return
        state["failure"] = failure
        state["conteo"], state["intentos"] = self._rate_locked(clave, failure.rol)
        self._log_abort_locked()

    def abort(self, failure: LLMFailure, motivo: str) -> None:
        """
        Fija el estado de aborto (el primero gana). No cuenta la falla (D4).

        Lo llama la capa de llamada, que lanza la falla para que su envoltorio la
        cuente con `record`: el aborto queda pendiente y `record` de la misma
        (clave, rol) completa `conteo`, `intentos` y el caso antes de emitir el
        ERROR, asi el conteo incluye la falla que lo disparo. Si ningun envoltorio
        la cuenta, `snapshot` emite el ERROR con los valores vigentes.
        """
        with self._lock:
            self._abort_locked(failure, motivo, pendiente=True)

    def flush_abort(self) -> None:
        """Emite el ERROR de un aborto pendiente si ningun envoltorio llego a contarlo."""
        with self._lock:
            if self._abort is not None and self._abort["pendiente"]:
                self._log_abort_locked()

    def check_abort(self) -> None:
        """Lanza `RunAborted` si la corrida esta abortada."""
        with self._lock:
            state = self._abort
            if state is None:
                return
            exc = RunAborted(
                state["failure"],
                state["motivo"],
                conteo=state["conteo"],
                intentos=state["intentos"],
                clave=state["clave"],
            )
        raise exc

    def snapshot(self) -> dict[str, Any]:
        """Estado serializable para `run.json`."""
        with self._lock:
            state = self._abort
            abort = None
            if state is not None and state["pendiente"]:
                self._log_abort_locked()
            if state is not None:
                failure: LLMFailure = state["failure"]
                abort = {
                    "clase": state["clave"],
                    "rol": failure.rol,
                    "conteo": state["conteo"],
                    "intentos": state["intentos"],
                    "causa": failure.causa,
                    "motivo": state["motivo"],
                }
            return {
                "counts": {k: dict(v) for k, v in self._counts.items()},
                "attempts": dict(self._attempts),
                "unique_cases": {rol: len(ids) for rol, ids in self._cases.items()},
                "entrada_dato": sorted(self._dato_cases),
                "aborted": state is not None,
                "abort": abort,
            }


_tracker = FailureTracker()


def get_failure_tracker() -> FailureTracker:
    """Devuelve el `FailureTracker` compartido del proceso."""
    return _tracker


def with_case(
    failure: LLMFailure, case_id: str | None, atribucion: str | None = None
) -> LLMFailure:
    """Copia de `failure` con el caso y la atribucion que conoce el envoltorio."""
    return replace(failure, case_id=case_id, atribucion=atribucion)
