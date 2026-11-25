"""
Reflexion propia, comun a ambos subproyectos (SPEC-105 FR-010; SPEC-104 FR-005, D4).

El repo es dueno del paso de reflexion de GEPA: la plantilla del prompt, el
renderizado de los ejemplos con feedback, la extraccion de la instruccion nueva
y la deteccion de `formato`. Asi un cambio de los defaults de `dspy` o `gepa`
(dspy 3.4.1 reemplazo el prompt de reflexion de `dspy.GEPA` por uno propio en
JSON) no cambia la optimizacion en silencio: cambiar el prompt es una decision
explicita (`REFLECTION_PROMPT_ID` nuevo) que se mide con N seeds (SPEC-100).

- `REFLECTION_PROMPT_TEMPLATE` / `render_reflection_prompt` /
  `extract_instruction`: copia byte a byte de la plantilla por defecto,
  `prompt_renderer` y `output_extractor` de `gepa==0.0.27`
  (`InstructionProposalSignature`), lo que usaban `gepa.optimize` y `dspy.GEPA`
  (dspy 3.2.1) hasta D-018. Verificado contra la copia en
  `tests/test_reflection_prompt.py`.
- `reflection_format_failure`: la propuesta sin bloque de triple backtick o con
  instruccion vacia es `formato` (el extractor nunca falla: sin bloque devuelve
  el texto entero).
- `ReflectionGuard`: un intento por propuesta, registro de la falla con su
  `case_id` y descarte (lanza; GEPA saltea la iteracion).
- `ReflectionProposer`: el `ProposalFn` publico de GEPA
  (`(candidate, reflective_dataset, components_to_update) -> dict[str, str]`).
  Se conecta como `instruction_proposer` de `dspy.GEPA` y como
  `custom_candidate_proposer` de `gepa.optimize`, y es tambien el callback
  `on_proposal_start` de ambos.

No importa `dspy` ni `gepa`.
"""

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .failures import FailureClass, LLMCallFailure, LLMFailure, get_failure_tracker, with_case

REFLECTION_PROMPT_ID = "gepa-0.0.27-default"

REFLECTION_PROMPT_TEMPLATE = """I provided an assistant with the following instructions to perform a task for me:
```
<curr_instructions>
```

The following are examples of different task inputs provided to the assistant along with the assistant's response for each of them, and some feedback on how the assistant's response could be better:
```
<inputs_outputs_feedback>
```

Your task is to write a new instruction for the assistant.

Read the inputs carefully and identify the input format and infer detailed task description about the task I wish to solve with the assistant.

Read all the assistant responses and the corresponding feedback. Identify all niche and domain specific factual information about the task and include it in the instruction, as a lot of it may not be available to the assistant in the future. The assistant may have utilized a generalizable strategy to solve the task, if so, include that in the instruction as well.

Provide the new instructions within ``` blocks."""  # noqa: E501 - texto del prompt, byte a byte


def _render_value(value: Any, level: int = 3) -> str:
    """Valor de un ejemplo en markdown; `level` es la profundidad del encabezado."""
    if isinstance(value, dict):
        s = ""
        for k, v in value.items():
            s += f"{'#' * level} {k}\n"
            s += _render_value(v, min(level + 1, 6))
        if not value:
            s += "\n"
        return s
    if isinstance(value, list | tuple):
        s = ""
        for i, item in enumerate(value):
            s += f"{'#' * level} Item {i + 1}\n"
            s += _render_value(item, min(level + 1, 6))
        if not value:
            s += "\n"
        return s
    return f"{str(value).strip()}\n\n"


def _render_example(sample: Mapping[str, Any], number: int) -> str:
    s = f"# Example {number}\n"
    for key, val in sample.items():
        s += f"## {key}\n"
        s += _render_value(val, level=3)
    return s


def render_reflection_prompt(
    current_instruction: str, dataset_with_feedback: Sequence[Mapping[str, Any]]
) -> str:
    """Prompt de reflexion para un componente (plantilla `REFLECTION_PROMPT_ID`)."""
    if not isinstance(current_instruction, str):
        raise TypeError("current_instruction debe ser str")
    if not isinstance(dataset_with_feedback, Sequence) or isinstance(
        dataset_with_feedback, str | bytes
    ):
        raise TypeError("dataset_with_feedback debe ser una secuencia de registros")
    samples = "\n\n".join(
        _render_example(sample, i + 1) for i, sample in enumerate(dataset_with_feedback)
    )
    prompt = REFLECTION_PROMPT_TEMPLATE.replace("<curr_instructions>", current_instruction)
    return prompt.replace("<inputs_outputs_feedback>", samples)


def extract_instruction(text: str) -> str:
    """
    Instruccion nueva de la respuesta del LLM (sobre el texto ya con `strip()`).

    Entre el primer y el ultimo triple backtick, sin el especificador de lenguaje.
    Con bloque incompleto o sin bloque devuelve lo que queda del texto: no falla
    (por eso `reflection_format_failure` decide si la propuesta sirve).
    """
    start = text.find("```") + 3
    end = text.rfind("```")
    if start >= end:
        stripped = text.strip()
        if stripped.startswith("```"):
            match = re.match(r"^```\S*\n?", text)
            if match:
                return text[match.end() :].strip()
        elif stripped.endswith("```"):
            return stripped[:-3].strip()
        return stripped
    content = text[start:end]
    match = re.match(r"^\S*\n", content)
    if match:
        content = content[match.end() :]
    return content.strip()


def reflection_format_failure(text: str) -> LLMFailure | None:
    """
    `formato` de una propuesta de reflexion (SPEC-104 FR-005): sin bloque de triple
    backtick, o con la instruccion extraida vacia. None si sirve.
    """
    out = text.strip()
    start, end = out.find("```"), out.rfind("```")
    if start == -1 or start + 3 >= end:
        causa = "sin_bloque_instruccion"
    elif not extract_instruction(out):
        causa = "instruccion_vacia"
    else:
        return None
    return LLMFailure(clase=FailureClass.formato, rol="reflection", causa=causa)


class ReflectionGuard:
    """
    Envoltorio de cada llamada de reflexion (SPEC-104 FR-005, D4).

    Por propuesta: consulta el aborto antes de llamar, suma un intento de
    `reflection` y, ante una falla de capa 1 (`LLMCallFailure`) o de `formato`,
    la registra en el contador con su `case_id` y lanza. GEPA atrapa la excepcion
    y saltea la iteracion: el candidato vigente no cambia. `RunAborted` no se
    registra.

    `case_id` es la iteracion de GEPA (FR-013) si el envoltorio recibe el
    callback `on_proposal_start`; si no, el numero de propuesta. Con iteracion
    conocida cuenta un intento por iteracion aunque se actualicen varios
    componentes, y una iteracion que ya fallo no vuelve a llamar: GEPA 0.1.4
    (`_propose_texts_batch_safe`) reintenta una vez la reflexion fallida, y ese
    reintento relanza la misma falla sin llamar ni registrar (la propuesta ya
    se descarto; el unico reintento es el de infraestructura, SPEC-104 FR-011).
    """

    def __init__(self) -> None:
        self._proposals = 0
        self._iteration: int | None = None
        self._counted: int | None = None
        self._failed: tuple[int, LLMFailure] | None = None

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

    def _record(self, failure: LLMFailure) -> None:
        get_failure_tracker().record(failure)
        if self._iteration is not None:
            self._failed = (self._iteration, failure)

    def run[T](self, call: Callable[[], T], texts: Callable[[T], list[str]]) -> T:
        """Ejecuta `call` y revisa cada texto de su resultado (`texts`)."""
        tracker = get_failure_tracker()
        tracker.check_abort()
        if self._failed is not None and self._failed[0] == self._iteration:
            raise LLMCallFailure(self._failed[1])
        case_id = self._attempt()
        try:
            result = call()
        except LLMCallFailure as exc:
            self._record(with_case(exc.failure, case_id))
            raise
        for text in texts(result):
            failure = reflection_format_failure(text)
            if failure is not None:
                failure = with_case(failure, case_id)
                self._record(failure)
                raise LLMCallFailure(failure)
        return result


class ReflectionProposer:
    """
    Proposer de instrucciones de GEPA sobre un LM de texto (SPEC-105 FR-010).

    `lm` es el transporte del rol `reflection` (prompt -> texto) y lanza
    `LLMCallFailure` ante una falla de capa 1. Por componente con datos en el
    dataset reflexivo: renderiza el prompt, llama por el `ReflectionGuard` y
    extrae la instruccion. Un componente sin datos se omite (como GEPA 0.0.27).
    """

    prompt_id = REFLECTION_PROMPT_ID

    def __init__(self, lm: Callable[[str], str]):
        self._lm = lm
        self._guard = ReflectionGuard()

    def on_proposal_start(self, event: Any) -> None:
        """Callback de GEPA: la iteracion es el `case_id` de las fallas (FR-013)."""
        self._guard.on_proposal_start(event)

    def __call__(
        self,
        candidate: dict[str, str],
        reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
        components_to_update: list[str],
    ) -> dict[str, str]:
        new_texts: dict[str, str] = {}
        for name in components_to_update:
            records = reflective_dataset.get(name)
            if not records:
                continue
            prompt = render_reflection_prompt(candidate[name], records)
            text = self._guard.run(lambda p=prompt: self._lm(p), lambda t: [t])
            new_texts[name] = extract_instruction(text.strip())
        return new_texts
