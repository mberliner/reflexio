"""Renderiza un CandidateSpec a prosa extensa estilo modelos_cv.

Secciones: encabezado, Objetivo, Educacion, Habilidades Tecnicas, Experiencia
(uno o mas puestos con bullets), Proyectos, Certificaciones, Idiomas, mas lineas
basura de distraccion. Todo elegido con un Random sembrado por candidato para
reproducibilidad. Los hechos decisivos del spec aparecen SIEMPRE en el texto
(posiblemente con ruido de forma), de modo que la extraccion sea justa.
"""

from __future__ import annotations

import random
import unicodedata

from . import components as comp
from . import noise
from .spec import CandidateSpec


def _slug(name: str) -> str:
    norm = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return norm.lower().replace(" ", "")

_MONTHS = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _rng_for(spec: CandidateSpec) -> random.Random:
    return random.Random(spec.seed)


def _objective(spec: CandidateSpec, rng: random.Random) -> str:
    tmpl = rng.choice(comp.OBJECTIVE_TEMPLATES)
    disc = comp.DISCIPLINE_LABEL.get(spec.discipline, spec.discipline)
    fw = " y ".join(spec.frameworks[:2]) if spec.frameworks else spec.primary_language
    db = spec.databases[0] if spec.databases else "bases de datos relacionales"
    sen = (spec.seniority or "Profesional").replace("_", " ").capitalize()
    return tmpl.format(
        sen=sen,
        y=spec.years_total,
        disc=disc,
        disc_cap=disc.capitalize(),
        lang=spec.primary_language,
        fw=fw,
        db=db,
        sector=spec.industria_previa,
    )


def _education(spec: CandidateSpec) -> list[str]:
    edu = spec.education
    return [
        "Educacion",
        edu.degree,
        edu.institution,
        f"Graduado: {edu.year}",
    ]


def _skills(spec: CandidateSpec, rng: random.Random) -> list[str]:
    langs = [spec.primary_language]
    # Distractor: a veces agrega un lenguaje secundario real del perfil.
    if spec.extra_skills:
        langs.extend(s for s in spec.extra_skills if s in {"SQL", "Bash", "JavaScript", "Go"})
    frameworks = list(spec.frameworks)
    tools = [s for s in spec.extra_skills if s not in langs]
    lines = ["Habilidades Tecnicas"]
    lines.append(f"- Lenguajes: {', '.join(dict.fromkeys(langs))}")
    if frameworks:
        lines.append(f"- Frameworks: {', '.join(frameworks)}")
    if spec.databases:
        lines.append(f"- Bases de Datos: {', '.join(spec.databases)}")
    if tools:
        lines.append(f"- Herramientas: {', '.join(tools)}")
    return lines


def _experience(spec: CandidateSpec, rng: random.Random) -> list[str]:
    lines = ["Experiencia"]
    bullets_pool = comp.BULLETS.get(spec.discipline, comp.BULLETS["backend"])
    for exp in spec.experiences:
        end = "Presente" if exp.end_year is None else str(exp.end_year)
        lines.append(exp.role)
        # El sector se imprime aqui para que industria_previa sea recuperable del
        # texto (el primer puesto, el actual, lleva el sector == industria_previa).
        lines.append(f"{exp.company} - {exp.sector}, {spec.city}, {spec.country}")
        lines.append(f"{rng.choice(_MONTHS)} {exp.start_year} - {end}")
        k = rng.randint(2, min(4, len(bullets_pool)))
        fw = spec.frameworks[0] if spec.frameworks else spec.primary_language
        db = spec.databases[0] if spec.databases else "PostgreSQL"
        for b in rng.sample(bullets_pool, k):
            lines.append(f"- {b.format(fw=fw, db=db)}")
    return lines


def _projects(spec: CandidateSpec, rng: random.Random) -> list[str]:
    if not spec.projects:
        return []
    lines = ["Proyectos"]
    fw = spec.frameworks[0] if spec.frameworks else spec.primary_language
    db = spec.databases[0] if spec.databases else "PostgreSQL"
    for p in spec.projects:
        lines.append(f"- {p.name}: {p.description.format(fw=fw, db=db)}")
    return lines


def _certs(spec: CandidateSpec) -> list[str]:
    if not spec.certifications:
        return []
    return ["Certificaciones", *[f"- {c}" for c in spec.certifications]]


def _languages(spec: CandidateSpec) -> list[str]:
    lines = ["Idiomas"]
    # Español nativo explicito por convencion (CV en español), salvo que
    # other_languages ya declare español. Asi el gold idiomas es recuperable.
    if not any(lang.lower().startswith("espa") for lang, _ in spec.other_languages):
        lines.append("Español: nativo.")
    lines.append(comp.ENGLISH_PHRASES.get(spec.english_level.lower(), "Ingles B2."))
    for lang, level in spec.other_languages:
        lines.append(f"{lang.capitalize()}: {level}.")
    return lines


def render(spec: CandidateSpec) -> str:
    """Devuelve el CV completo como un unico string multilinea con ruido aplicado."""
    rng = _rng_for(spec)
    blocks: list[list[str]] = []

    # Encabezado estilo modelos_cv: nombre / localidad | telefono | email | red.
    # El honorifico (Dr./Ing./Lic.) se muestra en la prosa pero NO forma parte del
    # gold de nombre; la localidad (gold ubicacion) se mantiene tal cual del spec.
    email = noise.obfuscate_email(spec.email, rng, 0.3)
    display_name = f"{spec.honorific} {spec.nombre}".strip() if spec.honorific else spec.nombre
    phone = f"+{rng.randint(1, 99)} {rng.randint(100, 999)} {rng.randint(1000, 9999)}"
    network = rng.choice(["LinkedIn: linkedin.com/in/", "GitHub: github.com/"])
    contact = f"{spec.city}, {spec.country} | {phone} | {email} | {network}{_slug(spec.nombre)}"
    header = [
        display_name.upper() if rng.random() < 0.3 else display_name,
        contact,
    ]
    blocks.append(header)

    blocks.append(["Objetivo", _objective(spec, rng)])
    blocks.append(_education(spec))
    blocks.append(_skills(spec, rng))
    blocks.append(_experience(spec, rng))
    proj = _projects(spec, rng)
    if proj:
        blocks.append(proj)
    certs = _certs(spec)
    if certs:
        blocks.append(certs)
    blocks.append(_languages(spec))

    # Lineas basura de distraccion (cantidad segun nivel de ruido).
    n_junk = {"low": 0, "med": 1, "high": 2}.get(spec.noise_level, 1)
    if n_junk and comp.JUNK_LINES:
        junk = rng.sample(comp.JUNK_LINES, min(n_junk, len(comp.JUNK_LINES)))
        if spec.extra_lines:
            junk = [*junk, *spec.extra_lines]
        blocks.append(junk)
    elif spec.extra_lines:
        blocks.append(list(spec.extra_lines))

    # Aplanar a lineas, aplicar ruido de forma por linea, unir con dobles saltos
    # entre secciones.
    rendered_sections: list[str] = []
    for block in blocks:
        noisy = [noise.apply_line_noise(line, rng, spec.noise_level) for line in block]
        rendered_sections.append("\n".join(noisy))
    return "\n\n".join(rendered_sections)
