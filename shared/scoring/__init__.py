"""Scoring primitives compartidos entre DSPy y GEPA.

Comparadores y scoring por campo (exact/normalized/fuzzy/set) sin dependencia de
ningun framework. Permite que `dspy_gepa_poc` y `gepa_standalone` apliquen la
misma logica de match sin que un paquete importe al otro (ver invariante de
paquetes hermanos en CLAUDE.md).
"""

from shared.scoring.field_match import (
    VALID_FIELD_MODES,
    compare_exact,
    compare_fuzzy,
    compare_normalized,
    normalize_text,
    score_field,
    score_set,
    strip_accents,
    tokenize_list,
)

__all__ = [
    "VALID_FIELD_MODES",
    "compare_exact",
    "compare_fuzzy",
    "compare_normalized",
    "normalize_text",
    "score_field",
    "score_set",
    "strip_accents",
    "tokenize_list",
]
