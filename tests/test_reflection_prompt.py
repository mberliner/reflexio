"""
SPEC-105 FR-010: el prompt de reflexion del repo es el que usaban `gepa.optimize`
(gepa 0.0.27) y `dspy.GEPA` (dspy 3.2.1) hasta D-018.

`tests/fixtures/reflection_prompt_gepa_0_0_27.json` se genero con el codigo real
de `gepa==0.0.27` (`InstructionProposalSignature.prompt_renderer` y
`output_extractor`, wheel descargado y aislado, 2026-11-25): datasets con dicts
anidados, listas, vacios, no-str y backticks, y respuestas con y sin bloque. Si
este test falla, el prompt cambio: es un cambio de optimizacion que va con
`REFLECTION_PROMPT_ID` nuevo y medicion con N seeds (SPEC-100), no un ajuste.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.llm.reflection import (
    REFLECTION_PROMPT_ID,
    extract_instruction,
    render_reflection_prompt,
)

GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures" / "reflection_prompt_gepa_0_0_27.json").read_text(
        encoding="utf-8"
    )
)


def test_prompt_id_names_the_historical_template() -> None:
    assert REFLECTION_PROMPT_ID == "gepa-0.0.27-default"
    assert GOLDEN["source"].startswith("gepa==0.0.27")


@pytest.mark.parametrize("case", GOLDEN["prompts"], ids=lambda c: f"n={len(c['dataset'])}")
def test_rendered_prompt_is_byte_identical(case: dict) -> None:
    assert render_reflection_prompt(case["instruction"], case["dataset"]) == case["rendered"]


@pytest.mark.parametrize("case", GOLDEN["texts"], ids=lambda c: repr(c["text"][:20]))
def test_extracted_instruction_is_identical(case: dict) -> None:
    # GEPA aplica strip() antes de extraer (Signature.run).
    assert extract_instruction(case["text"].strip()) == case["extracted"]


@pytest.mark.parametrize("bad", ["texto", b"bytes", None, 42])
def test_dataset_must_be_a_sequence_of_records(bad) -> None:
    with pytest.raises(TypeError):
        render_reflection_prompt("instr", bad)


def test_instruction_must_be_str() -> None:
    with pytest.raises(TypeError):
        render_reflection_prompt(None, [])  # type: ignore[arg-type]
