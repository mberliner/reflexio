"""flujo-intents: atencion multipaso de intents del Marco de Gobierno IA.

5 etapas DSPy agnosticas (intake, triage_solidez, triage_factibilidad, fast_gate,
aprobacion) optimizadas por GEPA por separado y encadenadas por un orquestador.

Ver el plan y `specs/SPEC-013-flujo-intents.md`. La logica de negocio vive en los
prompts optimizados y en los casos etiquetados, no en codigo: si el Marco cambia, se
reetiquetan casos y se re-optimiza, sin reescribir el programa.
"""

from .ficha import (
    FICHA_INPUT_COLUMNS,
    PALETA_COLORES,
    normalize_color,
    serialize_ficha,
)

__all__ = [
    "FICHA_INPUT_COLUMNS",
    "PALETA_COLORES",
    "normalize_color",
    "serialize_ficha",
]
