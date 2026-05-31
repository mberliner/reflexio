"""Constructor de CandidateSpec: declara los ejes decisivos, rellena el resto.

El catalogo solo especifica los atributos que determinan el label (años, stack,
db, ingles, ubicacion, disciplina). builder.make_candidate completa de forma
determinista (sembrado por indice) la identidad, educacion, experiencias,
proyectos y certificaciones desde los pools de components.py.
"""

from __future__ import annotations

import random
import unicodedata

from . import components as comp
from .spec import CandidateSpec, Education, Experience, Project

_CITY_BY_NAME = {c[0]: c for c in comp.CITIES}
_EMAIL_DOMAINS = ["gmail.com", "outlook.com", "proton.me", "correo.com", "mail.com"]


def _slug(name: str) -> str:
    norm = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return norm.lower().replace(" ", ".")


def _email_for(name: str, rng: random.Random) -> str:
    return f"{_slug(name)}@{rng.choice(_EMAIL_DOMAINS)}"


def _experiences(
    discipline: str,
    primary_language: str,
    frameworks: tuple[str, ...],
    years_total: int,
    industria: str,
    rng: random.Random,
) -> tuple[Experience, ...]:
    """Genera 1-3 puestos coherentes con la trayectoria, el ultimo 'a Presente'."""
    n = 1 if years_total <= 3 else (2 if years_total <= 7 else rng.randint(2, 3))
    titles = comp.ROLE_TITLES.get(discipline, comp.ROLE_TITLES["backend"])
    current = 2025
    remaining = years_total
    exps: list[Experience] = []
    sectors = [industria, *rng.sample([s for s in _SECTORS if s != industria], k=2)]
    for i in range(n):
        span = max(1, remaining // (n - i))
        start = current - span
        end = None if i == 0 else current
        exps.append(
            Experience(
                role=rng.choice(titles),
                company=rng.choice(comp.COMPANIES),
                sector=sectors[i % len(sectors)],
                start_year=start,
                end_year=end,
                tech=tuple(frameworks) or (primary_language,),
            )
        )
        current = start
        remaining -= span
    return tuple(exps)


_SECTORS = ["Fintech", "E-commerce", "SaaS B2B", "Retail", "Logistica", "Salud", "EdTech"]


def make_candidate(
    *,
    idx: int,
    split: str,
    discipline: str,
    primary_language: str,
    years_total: int,
    years_relevant: int,
    frameworks: tuple[str, ...],
    databases: tuple[str, ...],
    english: str,
    city: str,
    seniority: str,
    industria: str,
    extra_skills: tuple[str, ...] = (),
    other_languages: tuple[tuple[str, str], ...] = (),
    noise_level: str = "med",
    name: str | None = None,
    honorific: str = "",
) -> CandidateSpec:
    """Construye un CandidateSpec completo desde los ejes decisivos + pools."""
    rng = random.Random(1000 + idx)
    nombre = name or comp.NAMES[idx % len(comp.NAMES)]
    city_name, country, gmt, region = _CITY_BY_NAME[city]

    edu = Education(
        degree=rng.choice(comp.DEGREES),
        institution=rng.choice(comp.UNIVERSITIES),
        year=2025 - years_total - rng.randint(0, 2),
    )
    experiences = _experiences(
        discipline, primary_language, frameworks, years_total, industria, rng
    )
    proj_pool = comp.PROJECTS.get(discipline, [])
    projects = tuple(
        Project(name=n, description=d)
        for n, d in (rng.sample(proj_pool, min(2, len(proj_pool))) if proj_pool else [])
    )
    cert_pool = comp.CERTIFICATIONS.get(discipline, [])
    certifications = tuple(rng.sample(cert_pool, min(1, len(cert_pool)))) if cert_pool else ()

    return CandidateSpec(
        nombre=nombre,
        email=_email_for(nombre, rng),
        city=city_name,
        country=country,
        gmt=gmt,
        region=region,
        discipline=discipline,
        primary_language=primary_language,
        years_total=years_total,
        years_relevant=years_relevant,
        frameworks=frameworks,
        databases=databases,
        english_level=english,
        seniority=seniority,
        education=edu,
        experiences=experiences,
        industria_previa=industria,
        extra_skills=extra_skills,
        projects=projects,
        certifications=certifications,
        other_languages=other_languages,
        split=split,
        noise_level=noise_level,
        seed=2000 + idx,
        honorific=honorific,
    )
