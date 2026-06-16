"""Etapa 4 (Fast Gate): regla determinista del Marco. Color derivado de P1..P5.

El Fast Gate del Marco de Gobierno de IA son 5 preguntas Si/No; se cuentan los "Si":
0-1 -> Verde, 2-3 -> Amarillo, 4-5 -> Rojo. Negro = P5=Si Y alto impacto (override del
conteo: aplica con independencia de la suma; ver TC-N-06, 11001 -> Negro).

El juicio de cada pregunta (P1..P5) y de "alto impacto" lo emite el LLM; aqui solo se
combina de forma deterministica. SSOT de la regla de color; sin dependencias de DSPy
ni I/O. Trazabilidad en SPEC-102 (D-013).

Las 5 preguntas (la descripcion completa, con el default de P3, vive en el YAML):
- P1: usa datos personales o de clientes.
- P2: influye en una decision que afecta directamente a un cliente o empleado.
- P3: usa herramientas/proveedores fuera del catalogo aprobado (default: sin dato es
  intent nuevo -> homologado -> No; "sistema ya implementado" o herramienta externa/no
  homologada -> Si).
- P4: el resultado podria generar riesgo legal o danar la reputacion si falla.
- P5: toma o ejecuta decisiones sin que ningun humano las revise.

Alto impacto (al menos uno): (a) escala (>=10% de la base o >=100.000 clientes),
(b) naturaleza (decision financiera, corte de servicio, denegacion de acceso o
restriccion de derechos), (c) irreversibilidad sin intervencion manual, (d) exposicion
a sancion regulatoria directa, (e) perfilamiento automatizado de personas.
"""

from __future__ import annotations

from collections.abc import Mapping

from .ficha import _is_true

# Campos que el LLM debe emitir (las 5 preguntas + el juicio de alto impacto).
FAST_GATE_QUESTION_FIELDS: tuple[str, ...] = ("p1", "p2", "p3", "p4", "p5")
ALTO_IMPACTO_FIELD = "alto_impacto"


def derive_color(
    p1: object, p2: object, p3: object, p4: object, p5: object, alto_impacto: object
) -> str:
    """Deriva el color del Fast Gate a partir de las 5 preguntas Si/No y alto impacto.

    Acepta valores en cualquier forma reconocida por `ficha._is_true`
    ('si'/'No'/'true'/'1'/bool). Negro tiene prioridad sobre el conteo.

    Returns:
        Uno de: 'Verde', 'Amarillo', 'Rojo', 'Negro'.
    """
    sies = [_is_true(v) for v in (p1, p2, p3, p4, p5)]
    if sies[4] and _is_true(alto_impacto):
        return "Negro"
    total = sum(sies)
    if total <= 1:
        return "Verde"
    if total <= 3:
        return "Amarillo"
    return "Rojo"


def derive_color_from_row(row: Mapping[str, object]) -> str:
    """Como `derive_color` pero leyendo `p1..p5` y `alto_impacto` de un dict/fila."""
    return derive_color(
        row.get("p1"),
        row.get("p2"),
        row.get("p3"),
        row.get("p4"),
        row.get("p5"),
        row.get(ALTO_IMPACTO_FIELD),
    )
