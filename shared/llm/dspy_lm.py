"""
LM de DSPy que revisa la respuesta sin texto (SPEC-103, FR-009 / D8).

`LLMConfig.get_dspy_lm()` devuelve un `CheckedLM` en lugar de un `dspy.LM`.
Ante una respuesta sin texto registra la causa (rol y `finish_reason`) y lanza
`EmptyResponseError` en todo rol (D8 corregida por la RESOLUCION B-2c-1). El
tipo de excepcion separa la respuesta sin texto de un error de formato real
(`AdapterParseError`), sin heuristicas sobre el parseo.

- `reflection`: en `dspy.GEPA` (GEPA 0.0.27, dspy 3.2.1) la excepcion sale de
  `DspyAdapter.propose_new_texts`, la atrapa `ReflectiveMutationProposer.propose`
  y la iteracion se saltea sin crear un candidato con instruccion vacia.
- `task`: el programa DSPy debe envolverse con
  `dspy_gepa_poc.empty_response.tolerate_empty_responses`, que convierte la
  excepcion en una prediccion fallida con score 0.0. Sin envoltorio, la
  excepcion cuenta como error del ejemplo (`max_errors` de `Evaluate`).

La revision va en `_process_lm_response` (despues de que DSPy guarda la entrada
en `history`), asi el uso de tokens de una respuesta sin texto se sigue
contando (`record_dspy_history`). Es un metodo interno de dspy 3.2.1: si D-018
actualiza DSPy, revalidar con `tests/test_empty_response_dspy.py`.

Este modulo importa dspy; `config.py` lo importa de forma diferida.
"""

from typing import Any

import dspy

from .config import is_empty_text, log_empty_response
from .errors import EmptyResponseError


class CheckedLM(dspy.LM):
    """`dspy.LM` que registra y rechaza (`EmptyResponseError`) las respuestas sin texto."""

    def __init__(self, model: str, role: str = "task", **kwargs: Any):
        super().__init__(model, **kwargs)
        self.role = role

    def _process_lm_response(self, response, prompt, messages, **kwargs):
        outputs = super()._process_lm_response(response, prompt, messages, **kwargs)
        self._check_empty(response)
        return outputs

    def _check_empty(self, response: Any) -> None:
        for choice in getattr(response, "choices", None) or []:
            message = getattr(choice, "message", None)
            if message is None or getattr(message, "tool_calls", None):
                continue
            if not is_empty_text(getattr(message, "content", None)):
                continue
            finish_reason = getattr(choice, "finish_reason", None)
            log_empty_response(self.role, finish_reason)
            raise EmptyResponseError(self.role, finish_reason)
