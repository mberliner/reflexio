"""
Envoltorio de reflexion de SPEC-104 (FR-005, D4), comun a ambos subproyectos.

`reflection_format_failure` detecta la propuesta sin bloque de instruccion
(`formato`) y `ReflectionGuard` cuenta un intento por propuesta, registra la
falla con su `case_id` y lanza para que GEPA saltee la iteracion. Lo usan
`gepa_standalone.core.llm_factory.ReflectionLM` y `CheckedLM` (`dspy_lm.py`)
con rol `reflection`. No importa `dspy`; `gepa` se importa de forma diferida.
"""

from collections.abc import Callable
from typing import Any

from .failures import FailureClass, LLMCallFailure, LLMFailure, get_failure_tracker, with_case


def reflection_format_failure(text: str) -> LLMFailure | None:
    """
    `formato` de una propuesta de reflexion (SPEC-104 FR-005): sin el bloque de
    triple backtick que GEPA 0.0.27 extrae como instruccion, o con la
    instruccion extraida vacia. La extraccion es la de GEPA (`output_extractor`),
    que sin bloque devuelve el texto entero en vez de fallar. None si sirve.
    """
    from gepa.strategies.instruction_proposal import InstructionProposalSignature

    out = text.strip()  # GEPA aplica strip() antes de extraer (Signature.run)
    start, end = out.find("```"), out.rfind("```")
    if start == -1 or start + 3 >= end:
        causa = "sin_bloque_instruccion"
    elif not InstructionProposalSignature.output_extractor(out)["new_instruction"]:
        causa = "instruccion_vacia"
    else:
        return None
    return LLMFailure(clase=FailureClass.formato, rol="reflection", causa=causa)


class ReflectionGuard:
    """
    Envoltorio del `reflection_lm` en ambos subproyectos (SPEC-104 FR-005, D4).

    Por propuesta: consulta el aborto antes de llamar, suma un intento de
    `reflection` y, ante una falla de capa 1 (`LLMCallFailure`) o de `formato`,
    la registra en el contador con su `case_id` y lanza. GEPA 0.0.27
    (`ReflectiveMutationProposer.propose`) atrapa la excepcion y saltea la
    iteracion: el candidato vigente no cambia. `RunAborted` no se registra.

    `case_id` es la iteracion de GEPA (FR-013) si el envoltorio recibe el
    callback `on_proposal_start` (`callbacks` de `gepa.optimize`); si no, el
    numero de propuesta de este envoltorio. Con iteracion conocida cuenta un
    intento por iteracion aunque se actualicen varios componentes. El cableado
    del callback en los orquestadores es de 4b.
    """

    def __init__(self) -> None:
        self._proposals = 0
        self._iteration: int | None = None
        self._counted: int | None = None

    def on_proposal_start(self, event: Any) -> None:
        """Callback de GEPA (`ProposalStartEvent`): fija la iteracion en curso."""
        self._iteration = event["iteration"]

    def _attempt(self) -> str:
        tracker = get_failure_tracker()
        if self._iteration is None:
            self._proposals += 1
            tracker.record_attempt("reflection", f"propuesta:{self._proposals}")
            return f"propuesta:{self._proposals}"
        case_id = f"iteracion:{self._iteration}"
        if self._counted != self._iteration:
            self._counted = self._iteration
            tracker.record_attempt("reflection", case_id)
        return case_id

    def run[T](self, call: Callable[[], T], texts: Callable[[T], list[str]]) -> T:
        """Ejecuta `call` y revisa cada texto de su resultado (`texts`)."""
        tracker = get_failure_tracker()
        tracker.check_abort()
        case_id = self._attempt()
        try:
            result = call()
        except LLMCallFailure as exc:
            tracker.record(with_case(exc.failure, case_id))
            raise
        for text in texts(result):
            failure = reflection_format_failure(text)
            if failure is not None:
                failure = with_case(failure, case_id)
                tracker.record(failure)
                raise LLMCallFailure(failure)
        return result
