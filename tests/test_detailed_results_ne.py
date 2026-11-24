"""
Tabla de detalle de `gepa_standalone` con casos no evaluados (SPEC-104, FR-002).

Un caso NE lleva score 0.0 solo como valor tecnico para GEPA: la tabla MUST
mostrarlo como "NE" con la clave de su falla y no como 0% / "NO", para no
confundirlo con un error del prompt. Los casos evaluados se muestran como antes.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from shared.display import print_detailed_results


def _ne(**fields: Any) -> dict[str, Any]:
    return {
        **fields,
        "case_id": "test:2",
        "evaluated": False,
        "failure": {"clase": "infraestructura", "clave": "infraestructura", "rol": "task"},
    }


def _ok(**fields: Any) -> dict[str, Any]:
    return {**fields, "case_id": "test:1", "evaluated": True, "failure": None}


def _rows(capsys: pytest.CaptureFixture[str], outputs: list[dict], scores: list[float]) -> list:
    print_detailed_results(SimpleNamespace(outputs=outputs, scores=scores))
    lines = capsys.readouterr().out.splitlines()
    return [line for line in lines if line.count("|") >= 2][1:]  # sin encabezado


class TestDetailedResultsShowNE:
    def test_classifier(self, capsys: pytest.CaptureFixture[str]) -> None:
        rows = _rows(
            capsys,
            [
                _ok(text="hola", predicted="spam", expected="spam"),
                _ne(text="chau", predicted="", expected="ham"),
                _ok(text="otro", predicted="spam", expected="ham"),
            ],
            [1.0, 0.0, 0.0],
        )
        assert rows[0].rstrip().endswith("| SI")
        assert rows[1].rstrip().endswith("| NE (infraestructura)")
        assert rows[2].rstrip().endswith("| NO")

    def test_sql(self, capsys: pytest.CaptureFixture[str]) -> None:
        rows = _rows(
            capsys,
            [
                _ok(question="q1", predicted="SELECT 1"),
                _ne(question="q2", predicted=""),
            ],
            [1.0, 0.0],
        )
        assert "| SI " in rows[0]
        assert "| NE " in rows[1]
        assert rows[1].rstrip().endswith("no evaluado (infraestructura)")

    def test_extractor(self, capsys: pytest.CaptureFixture[str]) -> None:
        comparisons = {"nombre": {"correct": True, "expected": "Ana", "extracted": "Ana"}}
        rows = _rows(
            capsys,
            [
                _ok(text="cv 1", field_comparisons=comparisons),
                _ne(text="cv 2", field_comparisons={}),
            ],
            [1.0, 0.0],
        )
        assert "| 100%" in rows[0]
        assert rows[0].rstrip().endswith("CORRECTO")
        assert "| NE " in rows[1]
        assert "0%" not in rows[1]
        assert rows[1].rstrip().endswith("no evaluado (infraestructura)")

    def test_output_without_spec104_fields_is_evaluated(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rows = _rows(capsys, [{"text": "x", "predicted": "a", "expected": "b"}], [0.0])
        assert rows[0].rstrip().endswith("| NO")
