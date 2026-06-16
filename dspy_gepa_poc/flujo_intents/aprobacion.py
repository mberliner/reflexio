"""Etapa 5: aprobacion. Mapeo determinista color -> decision/nivel/dictamen (§9.1).

No se entrena: la regla vive en la config maestra (`flujo_intents.yaml`, seccion
`aprobacion.mapping`). Cambiar la politica de aprobacion = editar ese YAML, sin tocar
codigo. Fiel al §5.4: Verde se auto-aprueba; Amarillo/Rojo/Negro emiten recomendacion
no vinculante con el nivel de revision requerido.
"""

from __future__ import annotations

from collections.abc import Mapping

from .ficha import PALETA_COLORES


def resolve_aprobacion(
    clasificacion: str, mapping: Mapping[str, Mapping[str, str]]
) -> dict[str, str]:
    """Devuelve {decision, nivel_requerido, dictamen} para un color.

    Args:
        clasificacion: color del Fast Gate (Verde/Amarillo/Rojo/Negro).
        mapping: seccion `aprobacion.mapping` de la config maestra.

    Raises:
        ValueError: si el color no esta en la paleta o falta en el mapping.
    """
    color = str(clasificacion).strip()
    if color not in PALETA_COLORES:
        raise ValueError(f"clasificacion no es un color de la paleta: {color!r}")
    if color not in mapping:
        raise ValueError(f"falta el color {color!r} en aprobacion.mapping")
    entry = mapping[color]
    return {
        "decision": str(entry.get("decision", "")),
        "nivel_requerido": str(entry.get("nivel_requerido", "")),
        "dictamen": str(entry.get("dictamen", "")),
    }
