"""
Chequeo de entorno contra `requirements.txt`: el entorno local MUST ser el que
instala el CI desde cero (`uv pip install -r requirements.txt`).

El `.venv` local se actualiza encima de versiones previas y conserva paquetes que
la version nueva ya no exige. Con eso los tests pasan en local y fallan en CI
(dspy 3.5.0 movio `tenacity` a un extra; el `.venv` la conservaba de 3.2.1). Este
chequeo corre primero en `shared/utils/ci_local.sh` y en el job de tests del CI y
falla ante:

1. `pin`: un paquete de `requirements.txt` no instalado o fuera de su version.
2. `transitiva`: una dependencia de ese cierre no instalada o fuera de rango.
3. `import`: un modulo que importa el repo (produccion y tests) y que no instala
   `requirements.txt` (no esta en su cierre): en CI falla al importar.
4. `huerfano`: un paquete instalado fuera del cierre de `requirements.txt` y de
   las herramientas del pipeline (`PIPELINE_TOOLS`): codigo de librerias que lo
   importa en forma diferida pasaria en local y fallaria en CI.

Uso (desde la raiz del repo):

    python -m shared.utils.check_env_deps [--requirements requirements.txt]

Para alinear el `.venv` con lo que reporta: instalar lo que falta con
`pip install -r requirements.txt` y desinstalar los huerfanos con
`pip uninstall <paquete>`.
"""

from __future__ import annotations

import argparse
import ast
import importlib.metadata as metadata
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

REPO = Path(__file__).resolve().parents[2]

# Codigo que importa el repo y que el CI ejecuta (produccion y tests).
SCANNED_DIRS = ("shared", "dspy_gepa_poc", "gepa_standalone", "tests")

# Herramientas que el pipeline instala aparte de `requirements.txt` (job de
# security del CI, `docs/DEVELOPMENT.md`). Ni ellas ni sus dependencias son
# huerfanas, pero el repo no puede importarlas (no estan en el job de tests).
PIPELINE_TOOLS = ("pip", "bandit", "pip-audit")


@dataclass(frozen=True)
class Dist:
    """Paquete instalado: version y `Requires-Dist`."""

    version: str
    requires: tuple[str, ...] = ()


@dataclass
class Closure:
    """Cierre de dependencias: paquetes alcanzados y problemas encontrados."""

    names: set[str] = field(default_factory=set)
    problems: list[str] = field(default_factory=list)


def parse_requirements(text: str) -> list[Requirement]:
    """Lineas de `requirements.txt` (sin comentarios). Opciones (`-r`, `-e`) no se admiten."""
    requirements = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-"):
            raise ValueError(f"linea {number}: opcion no admitida por el chequeo: {line!r}")
        try:
            requirements.append(Requirement(line))
        except InvalidRequirement as exc:
            raise ValueError(f"linea {number}: {exc}") from exc
    return requirements


def _applies(requirement: Requirement, extras: Iterable[str], env: Mapping[str, str]) -> bool:
    if requirement.marker is None:
        return True
    return any(requirement.marker.evaluate({**env, "extra": extra}) for extra in (*extras, ""))


def _satisfies(requirement: Requirement, version: str) -> bool:
    try:
        return requirement.specifier.contains(Version(version), prereleases=True)
    except InvalidVersion:
        return False


def closure(
    roots: Iterable[Requirement],
    dists: Mapping[str, Dist],
    env: Mapping[str, str],
    *,
    origin: str = "requirements.txt",
) -> Closure:
    """
    Cierre de `roots` sobre los paquetes instalados (`dists`, nombres canonicos),
    con extras y markers. Reporta lo que falta o esta fuera de rango.
    """
    result = Closure()
    stack = [(req, origin) for req in roots if _applies(req, (), env)]
    seen: set[tuple[str, frozenset[str]]] = set()
    while stack:
        req, parent = stack.pop()
        name = canonicalize_name(req.name)
        kind = "pin" if parent == origin else "transitiva"
        dist = dists.get(name)
        if dist is None:
            result.problems.append(f"{kind}: falta {req} (lo pide {parent})")
            continue
        if req.specifier and not _satisfies(req, dist.version):
            result.problems.append(
                f"{kind}: {name}=={dist.version} no cumple {req} (lo pide {parent})"
            )
        key = (name, frozenset(req.extras))
        if key in seen:
            continue
        seen.add(key)
        result.names.add(name)
        for spec in dist.requires:
            child = Requirement(spec)
            if _applies(child, req.extras, env):
                stack.append((child, f"{name}=={dist.version}"))
    return result


def imported_modules(files: Iterable[Path], root: Path) -> dict[str, list[str]]:
    """Modulos de primer nivel importados (absolutos) -> `archivo:linea` donde aparecen."""
    found: dict[str, list[str]] = {}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            where = f"{path.relative_to(root).as_posix()}:{node.lineno}"
            for name in names:
                found.setdefault(name.split(".", 1)[0], []).append(where)
    return found


def undeclared_imports(
    imports: Mapping[str, list[str]],
    module_dists: Mapping[str, list[str]],
    declared: set[str],
    local: set[str],
    stdlib: frozenset[str] | set[str],
) -> list[str]:
    """Imports que no resuelve la stdlib, el repo ni un paquete del cierre declarado."""
    problems = []
    for module in sorted(imports):
        if module in stdlib or module in local or module == "__future__":
            continue
        providers = {canonicalize_name(d) for d in module_dists.get(module, [])}
        if providers & declared:
            continue
        where = ", ".join(imports[module][:3])
        source = (
            f"lo instala {', '.join(sorted(providers))}, fuera de requirements.txt"
            if providers
            else "no lo provee ningun paquete instalado"
        )
        problems.append(f"import: {module!r} ({where}): {source}")
    return problems


def orphans(installed: Iterable[str], allowed: set[str]) -> list[str]:
    return [
        f"huerfano: {name} instalado y fuera de requirements.txt "
        f"(no lo instala el CI; desinstalar: pip uninstall {name})"
        for name in sorted(set(installed) - allowed)
    ]


def check(
    requirements: list[Requirement],
    dists: Mapping[str, Dist],
    imports: Mapping[str, list[str]],
    module_dists: Mapping[str, list[str]],
    local: set[str],
    stdlib: frozenset[str] | set[str],
    env: Mapping[str, str],
    tools: Iterable[str] = PIPELINE_TOOLS,
) -> list[str]:
    """Todos los problemas del entorno respecto de `requirements` (vacio = alineado)."""
    declared = closure(requirements, dists, env)
    present_tools = [Requirement(t) for t in tools if canonicalize_name(t) in dists]
    tooling = closure(present_tools, dists, env, origin="pipeline")
    return [
        *declared.problems,
        *undeclared_imports(imports, module_dists, declared.names, local, stdlib),
        *orphans(dists, declared.names | tooling.names),
    ]


def installed_dists() -> dict[str, Dist]:
    dists = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name:
            dists[canonicalize_name(name)] = Dist(dist.version, tuple(dist.requires or ()))
    return dists


def local_modules(root: Path) -> set[str]:
    return {p.stem for p in root.glob("*.py")} | {
        p.name for p in root.iterdir() if p.is_dir() and (p / "__init__.py").exists()
    }


def scanned_files(root: Path, dirs: Iterable[str] = SCANNED_DIRS) -> list[Path]:
    return sorted(f for d in dirs for f in (root / d).rglob("*.py") if "__pycache__" not in f.parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    parser.add_argument("--requirements", type=Path, default=REPO / "requirements.txt")
    args = parser.parse_args(argv)

    requirements = parse_requirements(args.requirements.read_text(encoding="utf-8"))
    dists = installed_dists()
    problems = check(
        requirements,
        dists,
        imported_modules(scanned_files(REPO), REPO),
        metadata.packages_distributions(),
        local_modules(REPO),
        sys.stdlib_module_names,
        default_environment(),
    )
    if problems:
        print(f"Entorno desalineado con {args.requirements.name} ({len(problems)}):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"Entorno alineado con {args.requirements.name} ({len(dists)} paquetes instalados)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
