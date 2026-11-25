"""
SPEC-105 FR-005 / FR-007 / SC-005 / SC-006: el repo usa solo API publica de
`dspy`, `gepa` y `litellm`, y cada superficie de la que depende la reflexion y
la construccion del optimizador tiene un contrato que falla en CI si un upgrade
la cambia.

- SC-005: ningun modulo de produccion importa simbolos privados (prefijo `_`) de
  esas librerias ni accede a atributos privados por la ruta del modulo.
- Contratos de parametros: `dspy.GEPA` (`instruction_proposer`, `gepa_kwargs`, ...)
  y `gepa.optimize` (`custom_candidate_proposer`, `callbacks`). El comportamiento
  (proposer llamado con `(candidate, reflective_dataset, components_to_update)`,
  evento `on_proposal_start` con `iteration`, reintento de la reflexion fallida
  de GEPA 0.1.4) lo cubren los e2e de `tests/test_reflection_guard.py`; el
  fallback de adapters, `tests/test_single_call_point.py`.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import dspy
import gepa
import pytest

REPO = Path(__file__).resolve().parents[1]
PRODUCTION_DIRS = ("shared", "dspy_gepa_poc", "gepa_standalone")
LIBS = frozenset({"dspy", "gepa", "litellm"})


def _production_files() -> list[Path]:
    return sorted(
        f for d in PRODUCTION_DIRS for f in (REPO / d).rglob("*.py") if "__pycache__" not in f.parts
    )


def _private_lib_uses(tree: ast.AST) -> list[str]:
    """Usos de simbolos privados de `LIBS` en un modulo (imports y atributos)."""
    found: list[str] = []
    lib_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] in LIBS:
                    lib_aliases.add(alias.asname or parts[0])
                    if any(p.startswith("_") for p in parts):
                        found.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            parts = node.module.split(".")
            if parts[0] not in LIBS:
                continue
            if any(p.startswith("_") for p in parts):
                found.append(f"from {node.module} import ...")
            found.extend(
                f"from {node.module} import {a.name}" for a in node.names if a.name.startswith("_")
            )
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            base = node.value
            while isinstance(base, ast.Attribute):
                base = base.value
            if (
                isinstance(base, ast.Name)
                and base.id in lib_aliases
                and not node.attr.startswith("__")
            ):
                found.append(f"{ast.unparse(node)}")
    return found


class TestNoPrivateLibrarySymbols:
    def test_production_code_uses_only_public_symbols(self) -> None:
        offenders = {
            str(f.relative_to(REPO)): uses
            for f in _production_files()
            if (uses := _private_lib_uses(ast.parse(f.read_text(encoding="utf-8"))))
        }
        assert offenders == {}

    @pytest.mark.parametrize(
        "source",
        [
            "from dspy.adapters.json_adapter import _get_structured_outputs_response_format",
            "from litellm._logging import verbose_logger",
            "import dspy\ndspy.clients.lm._private()",
            "import gepa._internal",
        ],
    )
    def test_detector_flags_private_use(self, source: str) -> None:
        # SC-005: agregar un import privado hace fallar el test de arriba.
        assert _private_lib_uses(ast.parse(source))

    @pytest.mark.parametrize(
        "source",
        [
            "from dspy.utils.exceptions import AdapterParseError",
            "from dspy_gepa_poc.metrics import _score_field",
            "import dspy\ndspy.Predict.__init__",
        ],
    )
    def test_detector_ignores_public_and_repo_symbols(self, source: str) -> None:
        assert not _private_lib_uses(ast.parse(source))


def _params(fn) -> set[str]:
    return set(inspect.signature(fn).parameters)


class TestOptimizerConstructionContracts:
    def test_dspy_gepa_accepts_the_parameters_the_repo_passes(self) -> None:
        # `GEPAOptimizer` y `tests/conftest.py::repo_dspy_gepa`.
        assert {
            "metric",
            "reflection_lm",
            "instruction_proposer",
            "gepa_kwargs",
            "max_metric_calls",
            "auto",
            "track_stats",
            "reflection_minibatch_size",
            "skip_perfect_score",
            "candidate_selection_strategy",
            "use_merge",
            "max_merge_invocations",
        } <= _params(dspy.GEPA.__init__)

    def test_gepa_optimize_accepts_the_parameters_the_repo_passes(self) -> None:
        # `gepa_standalone/universal_optimizer.py`.
        assert {
            "seed_candidate",
            "trainset",
            "valset",
            "adapter",
            "task_lm",
            "custom_candidate_proposer",
            "max_metric_calls",
            "skip_perfect_score",
            "display_progress_bar",
            "callbacks",
        } <= _params(gepa.optimize)

    def test_proposal_fn_protocol_matches_the_repo_proposer(self) -> None:
        from gepa.core.adapter import ProposalFn

        from shared.llm.reflection import ReflectionProposer

        expected = ["candidate", "reflective_dataset", "components_to_update"]
        assert list(inspect.signature(ProposalFn.__call__).parameters)[1:] == expected
        assert list(inspect.signature(ReflectionProposer.__call__).parameters)[1:] == expected

    def test_dspy_gepa_rejects_unknown_parameters(self) -> None:
        # Sin filtro por firma en `GEPAOptimizer`: un parametro que desaparece falla.
        with pytest.raises(TypeError):
            dspy.GEPA(metric=lambda *a, **k: 0.0, auto="light", parametro_inexistente=1)
