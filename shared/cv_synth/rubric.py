"""Deriva el label de triage (cv_triage_v3) desde el CandidateSpec + la vacante.

Rubric determinista para la vacante 'Backend Senior (Python) - LATAM'. El label
es correcto POR CONSTRUCCION: se computa de los atributos decisivos del spec, no
se anota a mano. Devuelve tambien una justificacion autogenerada citando que
requisitos pasaron o fallaron.

Reglas (excluyentes de la vacante):
  - Disciplina backend/fullstack y lenguaje primario Python (alineacion critica).
  - years_relevant >= 5.
  - Algun framework en {Django, FastAPI}.
  - PostgreSQL entre las bases.
  - Ingles >= B2.
  - Residencia LATAM con GMT en [-6, -3].

Decision:
  - Disciplina/lenguaje desalineado o disciplina excluida -> no_fit.
  - 0 requisitos fallidos -> fit_alto.
  - exactamente 1 requisito fallido -> fit_medio.
  - 2 o mas requisitos fallidos -> no_fit.
"""

from __future__ import annotations

from .spec import CandidateSpec

JOB_TITLE = "Backend Senior (Python) - Equipo distribuido LATAM"

JOB_DESCRIPTION = (
    "Backend Senior (Python) - Equipo distribuido LATAM\n\n"
    "Buscamos backend senior con foco en Python para un equipo distribuido en LATAM.\n\n"
    "Requisitos excluyentes:\n"
    "- 5+ años de experiencia en backend con Python.\n"
    "- Solidez en Django y/o FastAPI.\n"
    "- PostgreSQL y diseño de APIs REST.\n"
    "- Ingles tecnico B2 o superior (equipo internacional, docs en ingles).\n"
    "- Residencia en LATAM (zona horaria GMT-3 a GMT-6).\n\n"
    "Deseable: Docker, AWS, Celery, microservicios.\n"
    "No aplica para perfiles de frontend, mobile, data science ni QA."
)

REQUIRED_YEARS = 5
REQUIRED_FRAMEWORKS = {"Django", "FastAPI"}
REQUIRED_DB = "PostgreSQL"
REQUIRED_ENGLISH_RANK = 4  # B2
ALIGNED_DISCIPLINES = {"backend", "fullstack"}
EXCLUDED_DISCIPLINES = {"frontend", "mobile", "data_science", "qa", "pm", "embedded", "devops"}


def _check_failures(spec: CandidateSpec) -> list[tuple[str, str]]:
    """Devuelve [(eje, motivo)] de los requisitos NO criticos fallidos."""
    fails: list[tuple[str, str]] = []
    if spec.years_relevant < REQUIRED_YEARS:
        fails.append(("seniority", f"{spec.years_relevant} años Python < 5 requeridos"))
    if not (set(spec.frameworks) & REQUIRED_FRAMEWORKS):
        fw = ", ".join(spec.frameworks) or "ninguno"
        fails.append(("stack", f"usa {fw}, no Django ni FastAPI"))
    if REQUIRED_DB not in spec.databases:
        fails.append(("db", "no acredita PostgreSQL"))
    if spec.english_rank() < REQUIRED_ENGLISH_RANK:
        fails.append(("idioma", f"ingles {spec.english_level.upper()} < B2"))
    if not (spec.region == "LATAM" and -6 <= spec.gmt <= -3):
        fails.append(("ubicacion", f"reside en {spec.country} (fuera de LATAM/huso)"))
    return fails


def triage_label(spec: CandidateSpec) -> tuple[str, str]:
    """Devuelve (label, justificacion) para una fila de cv_triage_v3."""
    # Alineacion critica de disciplina / lenguaje.
    misaligned = (
        spec.discipline not in ALIGNED_DISCIPLINES
        or spec.primary_language != "Python"
    )
    if misaligned:
        if spec.discipline in EXCLUDED_DISCIPLINES:
            motivo = f"disciplina {spec.discipline} excluida por el aviso"
        else:
            motivo = f"lenguaje primario {spec.primary_language}, no Python"
        return "no_fit", f"Perfil desalineado: {motivo}."

    fails = _check_failures(spec)
    if not fails:
        return (
            "fit_alto",
            f"Cumple todos los excluyentes: {spec.years_relevant} años Python, "
            f"{'/'.join(spec.frameworks)}, PostgreSQL, ingles "
            f"{spec.english_level.upper()}, {spec.country} (LATAM).",
        )
    if len(fails) == 1:
        eje, motivo = fails[0]
        return "fit_medio", f"Cumple el nucleo tecnico pero falla en {eje}: {motivo}."
    motivos = "; ".join(m for _, m in fails)
    return "no_fit", f"Falla en multiples requisitos criticos: {motivos}."
