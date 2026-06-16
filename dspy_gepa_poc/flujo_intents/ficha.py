"""Serializacion de la Ficha de Intent a texto y utilidades de etiqueta.

SSOT del shape de la ficha (las 21 columnas de entrada compartidas por
`intake_clasificacion.csv` y `triage_rechazos.csv` del proyecto original) y de la
normalizacion del color del Fast Gate. Sin dependencias de DSPy ni I/O.

El texto producido por `serialize_ficha` es el unico input (`ficha`) que reciben las
etapas LLM: agnostico a la implementacion, legible y estable.
"""

from __future__ import annotations

from collections.abc import Mapping

# Las 4 categorias de tipo de intent (booleanas en el CSV).
TIPO_INTENT_FLAGS: tuple[tuple[str, str], ...] = (
    ("tipo_intent_negocio", "Negocio"),
    ("tipo_intent_operativo", "Operativo"),
    ("tipo_intent_capacidad_equipos", "Capacidad de Equipo"),
    ("tipo_intent_tecnico_arquitectural", "Tecnico/Arquitectural"),
)

# Las 6 categorias de datos requeridos (booleanas en el CSV).
DATOS_FLAGS: tuple[tuple[str, str], ...] = (
    ("datos_requeridos_ninguno", "ninguno sensible"),
    ("datos_requeridos_datos_publicos", "publicos"),
    ("datos_requeridos_datos_operativos", "operativos"),
    ("datos_requeridos_datos_personales", "personales"),
    ("datos_requeridos_datos_confidenciales", "confidenciales"),
    ("datos_requeridos_otros", "otros"),
)

# Campos de texto libre de la ficha, en el orden en que se presentan.
TEXT_FIELDS: tuple[tuple[str, str], ...] = (
    ("declaracion_intent", "Declaracion del intent"),
    ("area_proponente", "Area proponente"),
    ("flujo_de_valor", "Flujo de valor o area afectada"),
    ("metricas_de_exito", "Metricas de exito"),
    ("impacto_personas", "Impacto en personas"),
    ("supuesto_riesgo", "Supuesto de riesgo inicial"),
    ("restricciones", "Restricciones explicitas"),
    ("sponsor", "Sponsor"),
)

# Todas las columnas de entrada (las que describen la ficha; no incluye labels).
FICHA_INPUT_COLUMNS: tuple[str, ...] = (
    "nombre_iniciativa",
    *[k for k, _ in TIPO_INTENT_FLAGS],
    "declaracion_intent",
    "area_proponente",
    "flujo_de_valor",
    "metricas_de_exito",
    "impacto_personas",
    *[k for k, _ in DATOS_FLAGS],
    "supuesto_riesgo",
    "restricciones",
    "sponsor",
)

PALETA_COLORES: tuple[str, ...] = ("Verde", "Amarillo", "Rojo", "Negro")


def _is_true(value: object) -> bool:
    """Interpreta el booleano del CSV ('true'/'false', '1'/'0', bool)."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "si", "sí", "x"}


def _active_labels(row: Mapping[str, object], flags: tuple[tuple[str, str], ...]) -> list[str]:
    return [label for key, label in flags if _is_true(row.get(key))]


def serialize_ficha(row: Mapping[str, object]) -> str:
    """Convierte una fila de ficha (dict de columnas) en el texto `ficha`.

    Incluye nombre, tipo(s) de intent, los campos de texto y las categorias de datos
    activas. No incluye id ni mail_contacto (no son relevantes para la decision).
    """
    lines: list[str] = []

    nombre = str(row.get("nombre_iniciativa", "")).strip()
    if nombre:
        lines.append(f"Nombre de la iniciativa: {nombre}")

    tipos = _active_labels(row, TIPO_INTENT_FLAGS)
    lines.append(f"Tipo de intent: {', '.join(tipos) if tipos else '(no declarado)'}")

    for key, label in TEXT_FIELDS:
        value = str(row.get(key, "")).strip()
        lines.append(f"{label}: {value if value else '(vacio)'}")

    datos = _active_labels(row, DATOS_FLAGS)
    otros_msg = str(row.get("datos_otros_mensaje", "")).strip()
    if datos and otros_msg and otros_msg.upper() != "N/A" and "otros" in datos:
        datos = [d if d != "otros" else f"otros ({otros_msg})" for d in datos]
    lines.append(f"Datos requeridos: {', '.join(datos) if datos else '(ninguno declarado)'}")

    return "\n".join(lines)


def normalize_color(value: object) -> str:
    """Normaliza `clasificacion_esperada` al color canonico (primer token de la paleta).

    Los originales traen anotaciones como 'Negro (escalada §7.3 desde Rojo)' o
    'Verde (caso pre-clasificado §7.4)'. Devuelve solo Verde/Amarillo/Rojo/Negro.

    Raises:
        ValueError: si el texto no empieza por un color de la paleta.
    """
    text = str(value).strip()
    for color in PALETA_COLORES:
        if text.startswith(color):
            return color
    raise ValueError(f"clasificacion sin color canonico reconocible: {text!r}")
