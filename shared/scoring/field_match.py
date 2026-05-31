"""Comparadores y scoring por campo, sin dependencia de framework.

Logica de match reutilizada por las metricas DSPy (`dspy_gepa_poc.metrics`) y por
el extractor de GEPA (`gepa_standalone.adapters.simple_extractor_adapter`). Mantener
una sola fuente evita que GEPA y DSPy diverjan en como puntuan un campo.

Modos soportados:
  - exact: igualdad tras strip/lower.
  - normalized: igualdad tras quitar tildes, puntuacion y normalizar espacios.
  - fuzzy: normalized o, si falla, SequenceMatcher sobre un umbral.
  - set: Jaccard de cobertura sobre el esperado (listas separadas por coma/;).
"""

import re
import unicodedata
from difflib import SequenceMatcher

# Modos de comparacion soportados por field_configs.
VALID_FIELD_MODES = {"exact", "normalized", "fuzzy", "set"}


def compare_exact(expected: str, actual: str) -> bool:
    """Comparacion exacta (asume strip/lower previo)."""
    return expected == actual


def strip_accents(text: str) -> str:
    """Elimina diacriticos (tildes) preservando caracteres base."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def normalize_text(text: str) -> str:
    """Elimina puntuacion, tildes y normaliza espacios + case."""
    text = strip_accents(text).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compare_normalized(expected: str, actual: str) -> bool:
    """Comparacion tras normalizar puntuacion y espacios."""
    return normalize_text(expected) == normalize_text(actual)


def compare_fuzzy(expected: str, actual: str, threshold: float) -> bool:
    """Comparacion por similitud con umbral. Intenta normalized primero."""
    if compare_normalized(expected, actual):
        return True
    ratio = SequenceMatcher(None, normalize_text(expected), normalize_text(actual)).ratio()
    return ratio >= threshold


def tokenize_list(text: str, separators: str = ",;") -> set[str]:
    """
    Tokeniza una cadena tipo lista en un set normalizado.

    Acepta varios separadores (default coma o punto y coma) y normaliza cada
    elemento (lower, sin tildes, sin puntuacion interna). Items vacios se
    descartan. Para items con sufijo ':valor' (p.ej. 'Python:5', 'ingles:b2')
    se conserva solo la clave para tolerar diferencias en el valor.
    """
    if not text:
        return set()
    pattern = f"[{re.escape(separators)}]"
    tokens = re.split(pattern, text)
    out: set[str] = set()
    for tok in tokens:
        norm = normalize_text(tok)
        if not norm:
            continue
        # Conservar solo la 'clave' antes del primer ':' para Python:5 -> python.
        # Sin ':', conservar el texto normalizado completo (ej. Vue.js -> vue js).
        key = norm if ":" not in tok else normalize_text(tok.split(":", 1)[0])
        out.add(key or norm)
    return out


def score_set(
    expected: str, actual: str, separators: str = ",;"
) -> tuple[float, set[str], set[str]]:
    """
    Score de Jaccard-like: |intersect| / |expected|. Retorna (score, missing, extra).
    Si expected esta vacio, se considera match perfecto solo si actual tambien lo esta.
    """
    exp = tokenize_list(expected, separators)
    act = tokenize_list(actual, separators)
    if not exp:
        return (1.0 if not act else 0.0, set(), act)
    inter = exp & act
    missing = exp - act
    extra = act - exp
    return (len(inter) / len(exp), missing, extra)


def score_field(
    expected_raw: str,
    actual_raw: str,
    mode: str,
    fuzzy_threshold: float,
    separators: str,
) -> tuple[float, str]:
    """
    Calcula score [0,1] y mensaje de diagnostico para un campo.

    Returns:
        (score, diag): diag es '' si match perfecto.
    """
    expected = str(expected_raw or "").strip().lower()
    actual = str(actual_raw or "").strip().lower()

    if mode == "set":
        score, missing, extra = score_set(expected, actual, separators)
        if score == 1.0 and not extra:
            return 1.0, ""
        parts = []
        if missing:
            parts.append(f"faltan: {sorted(missing)}")
        if extra:
            parts.append(f"sobran: {sorted(extra)}")
        return score, f"esperado '{expected_raw}' vs obtenido '{actual_raw}' ({'; '.join(parts)})"

    if mode == "normalized":
        ok = compare_normalized(expected, actual)
    elif mode == "fuzzy":
        ok = compare_fuzzy(expected, actual, fuzzy_threshold)
    else:  # exact
        ok = compare_exact(expected, actual)

    if ok:
        return 1.0, ""
    return 0.0, f"esperado '{expected_raw}' vs obtenido '{actual_raw}'"
