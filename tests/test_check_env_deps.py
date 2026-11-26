"""
`shared/utils/check_env_deps.py`: el entorno local MUST ser el que instala el CI
desde `requirements.txt` (pins, cierre transitivo, imports declarados, sin
huerfanos). Datos sinteticos: no depende del `.venv` real salvo el test de
integracion, que es el mismo chequeo que corre el pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from packaging.markers import default_environment
from packaging.requirements import Requirement

from shared.utils import check_env_deps as ced
from shared.utils.check_env_deps import Dist

ENV = default_environment()
STDLIB = frozenset({"json", "os"})


def _reqs(*lines: str) -> list[Requirement]:
    return [Requirement(line) for line in lines]


def _check(
    requirements: list[Requirement],
    dists: dict[str, Dist],
    imports: dict[str, list[str]] | None = None,
    module_dists: dict[str, list[str]] | None = None,
    tools: tuple[str, ...] = (),
) -> list[str]:
    return ced.check(
        requirements,
        dists,
        imports or {},
        module_dists or {},
        local={"shared", "tests"},
        stdlib=STDLIB,
        env=ENV,
        tools=tools,
    )


# El caso real (2026-11-26): dspy 3.5.0 movio tenacity al extra `litellm`.
DSPY_35 = {
    "dspy": Dist("3.5.0", ("tenacity>=8.2.3; extra == 'litellm'", "gepa<0.2,>=0.1.4")),
    "gepa": Dist("0.1.4"),
    "tenacity": Dist("9.2.1"),
}


class TestParseRequirements:
    def test_skips_comments_and_blank_lines(self) -> None:
        text = "# DSPy\ndspy==3.5.0  # fijado\n\nlitellm[proxy]==1.108.5\n"
        assert [str(r) for r in ced.parse_requirements(text)] == [
            "dspy==3.5.0",
            "litellm[proxy]==1.108.5",
        ]

    @pytest.mark.parametrize("line", ["-r otros.txt", "-e .", "dspy=="])
    def test_rejects_options_and_invalid_lines(self, line: str) -> None:
        with pytest.raises(ValueError, match="linea 1"):
            ced.parse_requirements(line)

    def test_repo_requirements_parse(self) -> None:
        text = (ced.REPO / "requirements.txt").read_text(encoding="utf-8")
        names = {r.name for r in ced.parse_requirements(text)}
        assert {"dspy", "gepa", "litellm", "tenacity"} <= names


class TestClosure:
    def test_extra_dependency_is_orphan_without_the_extra(self) -> None:
        problems = _check(_reqs("dspy==3.5.0"), DSPY_35)
        assert problems == [
            "huerfano: tenacity instalado y fuera de requirements.txt "
            "(no lo instala el CI; desinstalar: pip uninstall tenacity)"
        ]

    def test_extra_requested_pulls_its_dependencies(self) -> None:
        assert _check(_reqs("dspy[litellm]==3.5.0"), DSPY_35) == []

    def test_declared_directly_is_aligned(self) -> None:
        assert _check(_reqs("dspy==3.5.0", "tenacity==9.2.1"), DSPY_35) == []

    def test_pin_mismatch_and_missing_pin(self) -> None:
        problems = _check(_reqs("dspy==3.4.1", "openai==3.57.0"), DSPY_35)
        assert "pin: dspy==3.5.0 no cumple dspy==3.4.1 (lo pide requirements.txt)" in problems
        assert "pin: falta openai==3.57.0 (lo pide requirements.txt)" in problems

    def test_transitive_missing_and_out_of_range(self) -> None:
        dists = {"dspy": Dist("3.5.0", ("gepa<0.2,>=0.1.4", "orjson"))}
        assert _check(_reqs("dspy"), dists) == [
            "transitiva: falta orjson (lo pide dspy==3.5.0)",
            "transitiva: falta gepa<0.2,>=0.1.4 (lo pide dspy==3.5.0)",
        ]
        dists = {**dists, "gepa": Dist("0.0.27"), "orjson": Dist("3.0")}
        assert _check(_reqs("dspy"), dists) == [
            "transitiva: gepa==0.0.27 no cumple gepa<0.2,>=0.1.4 (lo pide dspy==3.5.0)"
        ]

    def test_marker_for_other_platform_is_ignored(self) -> None:
        dists = {"a": Dist("1", ("pywin32; sys_platform == 'never'",))}
        assert _check(_reqs("a"), dists) == []

    def test_cycles_terminate(self) -> None:
        dists = {"a": Dist("1", ("b",)), "b": Dist("1", ("a",))}
        assert _check(_reqs("a"), dists) == []

    def test_pipeline_tools_and_their_deps_are_not_orphans(self) -> None:
        dists = {"a": Dist("1"), "bandit": Dist("1.8", ("stevedore",)), "stevedore": Dist("5")}
        assert _check(_reqs("a"), dists, tools=("bandit", "pip-audit")) == []
        assert _check(_reqs("a"), dists) != []


class TestImports:
    def test_import_only_reachable_as_orphan_is_reported(self) -> None:
        problems = _check(
            _reqs("dspy==3.5.0"),
            DSPY_35,
            imports={"tenacity": ["tests/test_x.py:52"], "dspy": ["shared/a.py:1"]},
            module_dists={"tenacity": ["tenacity"], "dspy": ["dspy"]},
        )
        assert problems[0] == (
            "import: 'tenacity' (tests/test_x.py:52): "
            "lo instala tenacity, fuera de requirements.txt"
        )

    def test_import_through_pipeline_tool_is_reported(self) -> None:
        # `rich` llega por pip-audit en local, pero el job de tests no lo instala.
        dists = {"a": Dist("1"), "pip-audit": Dist("2", ("rich",)), "rich": Dist("13")}
        problems = _check(
            _reqs("a"),
            dists,
            imports={"rich": ["shared/b.py:3"]},
            module_dists={"rich": ["rich"]},
            tools=("pip-audit",),
        )
        assert problems == [
            "import: 'rich' (shared/b.py:3): lo instala rich, fuera de requirements.txt"
        ]

    def test_unknown_module_is_reported(self) -> None:
        problems = _check(_reqs(), {}, imports={"nada": ["shared/c.py:1"]})
        assert problems == ["import: 'nada' (shared/c.py:1): no lo provee ningun paquete instalado"]

    def test_stdlib_local_and_future_are_ignored(self) -> None:
        imports = {m: ["x.py:1"] for m in ("json", "shared", "tests", "__future__")}
        assert _check(_reqs(), {}, imports=imports) == []

    def test_imported_modules_scans_absolute_imports(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "m.py").write_text(
            "import os.path\nfrom dspy.lm15 import Request\nfrom . import x\n"
            "def f():\n    import litellm\n",
            encoding="utf-8",
        )
        found = ced.imported_modules(ced.scanned_files(tmp_path, ["pkg"]), tmp_path)
        assert found == {"os": ["pkg/m.py:1"], "dspy": ["pkg/m.py:2"], "litellm": ["pkg/m.py:5"]}
        assert ced.local_modules(tmp_path) == {"pkg"}


class TestMain:
    def test_repo_environment_is_aligned(self, capsys: pytest.CaptureFixture[str]) -> None:
        # El mismo chequeo que corre el pipeline (ci_local.sh y job de tests del CI).
        assert ced.main([]) == 0, capsys.readouterr().out

    def test_reports_and_fails_when_misaligned(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        requirements = tmp_path / "requirements.txt"
        requirements.write_text("paquete-que-no-existe==1.0\n", encoding="utf-8")
        assert ced.main(["--requirements", str(requirements)]) == 1
        out = capsys.readouterr().out
        assert "pin: falta paquete-que-no-existe==1.0" in out
        assert "huerfano: dspy" in out
