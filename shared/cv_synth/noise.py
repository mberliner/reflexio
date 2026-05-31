"""Inyeccion de ruido realista en la prosa del CV.

Todo el ruido se aplica con un ``random.Random`` sembrado por candidato, asi la
salida es reproducible. El ruido NUNCA destruye los hechos decisivos (años,
frameworks, base de datos, ingles, ubicacion): solo cambia forma, no contenido,
para que la extraccion siga siendo justa pero mas dificil.
"""

from __future__ import annotations

import random

# Mapa de acentos para "comerse" tildes (typo comun en CVs reales).
_ACCENTS = str.maketrans("áéíóúÁÉÍÓÚñÑ", "aeiouAEIOUnN")

_INTENSITY = {"low": 0.05, "med": 0.15, "high": 0.30}


def _maybe(rng: random.Random, p: float) -> bool:
    return rng.random() < p


def strip_some_accents(text: str, rng: random.Random, p: float) -> str:
    """Quita tildes de algunas palabras (no todas) para simular escritura descuidada."""
    out = []
    for word in text.split(" "):
        if _maybe(rng, p):
            out.append(word.translate(_ACCENTS))
        else:
            out.append(word)
    return " ".join(out)


def maybe_lowercase_line(line: str, rng: random.Random, p: float) -> str:
    """A veces convierte una linea entera a minusculas (casing inconsistente)."""
    if _maybe(rng, p):
        return line.lower()
    return line


def obfuscate_email(email: str, rng: random.Random, p: float) -> str:
    """A veces escribe el email con formato raro: 'user (arroba) dom.com'."""
    if "@" not in email or not _maybe(rng, p):
        return email
    user, dom = email.split("@", 1)
    style = rng.choice([" (arroba) ", " arroba ", " @ "])
    return f"{user}{style}{dom}"


def apply_line_noise(line: str, rng: random.Random, level: str) -> str:
    """Aplica el conjunto de transformaciones de ruido a una linea."""
    p = _INTENSITY.get(level, 0.15)
    line = strip_some_accents(line, rng, p)
    line = maybe_lowercase_line(line, rng, p * 0.4)
    return line
