"""
Base Adapter

Clase base abstracta para todos los adaptadores de GEPA.
Usa LiteLLM para conexion con LLMs.

Resultado por caso (SPEC-104, D6): cada elemento de `outputs` (y de
`trajectories`) lleva `case_id`, `evaluated` y `failure` (dict o None). Un caso
no evaluado (NE) recibe score 0.0 solo como valor tecnico para GEPA y nunca entra
al dataset reflexivo.
"""

from dataclasses import replace
from typing import Any

from gepa_standalone.core.llm_factory import call_llm, get_task_config
from shared.llm import (
    BaselineOutcome,
    BaselineProbe,
    FailureClass,
    LLMCallFailure,
    LLMFailure,
    capture_finish_reason,
    failure_to_dict,
    get_failure_tracker,
    is_evaluated,
)

_ATTRIBUTABLE = (FailureClass.entrada, FailureClass.presupuesto)


class BaseAdapter:
    """Clase base para adaptadores GEPA que usan LiteLLM."""

    # Atributo requerido por GEPAAdapter
    propose_new_texts = None

    # max_tokens fijado por llamada de tarea (SPEC-103 FR-010); None = el de LLMConfig.
    task_max_tokens: int | None = None

    def __init__(self, temperature: float = 0.0):
        self.temperature = temperature
        self._config = get_task_config()
        # Modelo en formato LiteLLM (ej: "azure/gpt-4.1-mini")
        self.model = self._config.model
        self._baseline_prompt: str | None = None
        self._probe: BaselineProbe | None = None

    def call_model(self, system_prompt: str, user_content: str, max_tokens: int = 100) -> str:
        """
        Llama al modelo de chat usando LiteLLM.

        Args:
            system_prompt: Prompt del sistema.
            user_content: Contenido del usuario.
            max_tokens: Maximo de tokens en la respuesta.

        Returns:
            Respuesta del modelo como string.
        """
        return call_llm(
            prompt=user_content,
            model_name="task",
            system_prompt=system_prompt,
            temperature=self.temperature,
            max_tokens=max_tokens,
        )

    # ==================== SPEC-104: resultado por caso y atribucion ====================

    def _task_call(self, system_prompt: str, example: dict[str, Any]) -> str:
        """Llamada de la tarea sobre un ejemplo; la misma que usa `evaluate` y el baseline."""
        raise NotImplementedError("Cada adaptador debe implementar su propio _task_call()")

    def set_baseline(self, system_prompt: str) -> None:
        """
        Fija el prompt baseline (D5) y crea el probe de atribucion con los mismos
        parametros de la tarea. El orquestador lo llama una vez tras cargar el prompt.
        """
        self._baseline_prompt = system_prompt

        def call_baseline(example: dict[str, Any]) -> BaselineOutcome:
            with capture_finish_reason() as sink:
                self._task_call(system_prompt, example)
            return BaselineOutcome(finish_reason=sink[0] if sink else None)

        self._probe = BaselineProbe(call_baseline)

    @staticmethod
    def _case_id(example: dict[str, Any]) -> str:
        """Identificador del caso (FR-013); su ausencia es un error de programacion."""
        case_id = example.get("case_id")
        if case_id is None or str(case_id) == "":
            raise ValueError(
                "El ejemplo no tiene `case_id` (SPEC-104 FR-013): los loaders lo garantizan; "
                "sin el no hay cache del baseline ni casos unicos de entrada_dato."
            )
        return str(case_id)

    @staticmethod
    def _case_meta(case_id: str, failure: LLMFailure | None) -> dict[str, Any]:
        """Claves comunes del resultado por caso (D6)."""
        return {
            "case_id": case_id,
            "evaluated": is_evaluated(failure),
            "failure": failure_to_dict(failure) if failure is not None else None,
        }

    def _attribute(
        self, failure: LLMFailure, case_id: str, example: dict[str, Any], system_prompt: str
    ) -> LLMFailure:
        """Falla de la tarea con `case_id` y, si aplica, atribuida contra el baseline (D5)."""
        if failure.rol != "task" or failure.clase not in _ATTRIBUTABLE:
            return replace(failure, case_id=case_id)
        if self._probe is None:
            raise RuntimeError(
                "Falla de tarea que requiere atribucion contra el baseline "
                f"(clase={failure.clase.value}, caso={case_id}) sin baseline fijado: "
                "llamar a `set_baseline(system_prompt)` antes de evaluar."
            )
        return self._probe.attribute(
            failure, case_id, example, is_baseline=system_prompt == self._baseline_prompt
        )

    def _run_task_case(
        self, system_prompt: str, example: dict[str, Any], case_id: str
    ) -> tuple[str | None, LLMFailure | None]:
        """
        Un caso de la tarea: cuenta el intento, llama y, ante una falla de capa 1,
        la atribuye y la registra una sola vez. Devuelve `(texto, None)` o
        `(None, falla)`. `RunAborted` y toda excepcion que no sea `LLMCallFailure` se
        propagan (D6).
        """
        tracker = get_failure_tracker()
        tracker.record_attempt("task", case_id)
        try:
            return self._task_call(system_prompt, example), None
        except LLMCallFailure as exc:
            failure = self._attribute(exc.failure, case_id, example, system_prompt)
            tracker.record(failure)
            return None, failure

    @staticmethod
    def _record_format_failure(case_id: str, causa: str) -> LLMFailure:
        """`formato` de capa 2 de la tarea (FR-010): se registra y puntua 0."""
        failure = LLMFailure(clase=FailureClass.formato, rol="task", causa=causa, case_id=case_id)
        get_failure_tracker().record(failure)
        return failure

    @staticmethod
    def _case_evaluated(eval_batch: Any, index: int, data: dict[str, Any]) -> bool:
        """False si `outputs[index]` o la trayectoria marcan el caso como NE (FR-012)."""
        outputs = eval_batch.outputs
        if index < len(outputs) and not outputs[index].get("evaluated", True):
            return False
        return bool(data.get("evaluated", True))

    @staticmethod
    def _failure_feedback(data: dict[str, Any]) -> str | None:
        """Feedback de un caso con falla del candidato (error del prompt), o None."""
        failure = data.get("failure")
        if not failure:
            return None
        return (
            f"El prompt provoco una falla de la tarea (clave={failure['clave']}, "
            f"causa={failure['causa']}); es un error del prompt."
        )

    def evaluate(self, batch, candidate, capture_traces=False):
        """Método abstracto que debe ser implementado por las subclases."""
        raise NotImplementedError("Cada adaptador debe implementar su propio método evaluate()")

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        """Método abstracto que debe ser implementado por las subclases."""
        raise NotImplementedError(
            "Cada adaptador debe implementar su propio método make_reflective_dataset()"
        )
