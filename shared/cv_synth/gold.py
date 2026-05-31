"""Deriva el gold de extraccion (cv_profile_v3) desde el CandidateSpec.

El formato de cada campo replica las convenciones de cv_profile.csv para que el
config dynamic_cv_profile_v3.yaml pueda reutilizar los mismos field_configs.
"""

from __future__ import annotations

from .spec import CandidateSpec


def _stack_principal(spec: CandidateSpec) -> str:
    """'Python:5; Django; FastAPI; PostgreSQL' (lenguaje primario con años)."""
    parts = [f"{spec.primary_language}:{spec.years_relevant}"]
    parts.extend(spec.frameworks)
    parts.extend(spec.databases)
    return "; ".join(parts)


def _skills(spec: CandidateSpec) -> str:
    """Lista de skills separadas por coma: frameworks + bases + extras."""
    items: list[str] = [spec.primary_language, *spec.frameworks, *spec.databases]
    items.extend(spec.extra_skills)
    # Dedup preservando orden.
    return ", ".join(dict.fromkeys(items))


def _idiomas(spec: CandidateSpec) -> str:
    """'español:nativo; ingles:b2' (ingles siempre presente)."""
    parts: list[str] = []
    for lang, level in spec.other_languages:
        parts.append(f"{lang.lower()}:{level.lower()}")
    parts.append(f"ingles:{spec.english_level.lower()}")
    # Si no se declaro español como otro idioma, asumir nativo (convencion del dataset).
    if not any(p.startswith("español") or p.startswith("espanol") for p in parts):
        parts.insert(0, "español:nativo")
    return "; ".join(parts)


def extraction_gold(spec: CandidateSpec) -> dict[str, str]:
    """Devuelve el dict de campos de extraccion para una fila de cv_profile_v3."""
    edu = spec.education
    return {
        "nombre": spec.nombre,
        "email": spec.email,
        "años_experiencia": str(spec.years_total),
        "skills": _skills(spec),
        "educacion_principal": f"{edu.degree}, {edu.institution}",
        "seniority_declarado": spec.seniority,
        "stack_principal": _stack_principal(spec),
        "idiomas": _idiomas(spec),
        "ubicacion": f"{spec.city}, {spec.country}",
        "industria_previa": spec.industria_previa,
    }
