"""Contrato unificado de la seccion `case:` en ambos subproyectos.

Garantiza que todos los YAML de configuracion cumplan el criterio unico:
- `case.name`  -> slug corto (sin espacios), alimenta run dir / experiment_name
- `case.title` -> titulo semantico no vacio, alimenta la columna `Caso` del CSV

SSOT del criterio: docs/YAML_CONFIG_REFERENCE.md (seccion "Criterio unificado case").
"""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIRS = [
    REPO_ROOT / "dspy_gepa_poc" / "configs",
    REPO_ROOT / "gepa_standalone" / "experiments" / "configs",
]


def _all_config_files() -> list[Path]:
    files: list[Path] = []
    for d in CONFIG_DIRS:
        if d.exists():
            files.extend(sorted(d.glob("*.yaml")))
    return files


CONFIG_FILES = _all_config_files()


def test_config_dirs_have_files():
    """Sanity: encontramos configs en ambos subproyectos."""
    assert CONFIG_FILES, "No se encontraron YAML de configuracion"


@pytest.mark.parametrize("config_path", CONFIG_FILES, ids=lambda p: p.name)
def test_case_has_unified_name_and_title(config_path: Path):
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    case = config.get("case", {})

    name = case.get("name")
    title = case.get("title")

    assert isinstance(name, str) and name.strip(), f"{config_path.name}: falta case.name"
    assert isinstance(title, str) and title.strip(), f"{config_path.name}: falta case.title"

    # name es un slug: sin espacios (el titulo legible va en title).
    assert " " not in name, (
        f"{config_path.name}: case.name='{name}' debe ser slug sin espacios; "
        "el texto legible va en case.title"
    )
