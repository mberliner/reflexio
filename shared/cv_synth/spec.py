"""Modelo de datos: la fuente unica de verdad por candidato.

Un ``CandidateSpec`` describe a un candidato en forma ESTRUCTURADA. De el se
derivan deterministicamente las tres salidas del pipeline (ver paquete):

    - render.py  : prosa extensa estilo modelos_cv (el input del modelo).
    - gold.py    : gold de extraccion (cv_profile_v3).
    - rubric.py  : label de triage fit_alto/fit_medio/no_fit (cv_triage_v3).

Como el gold se DERIVA del spec (no se anota a mano sobre la prosa), es correcto
por construccion: desaparece el caveat gold_verificado="no" de los datasets v2.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Orden de niveles de ingles para comparaciones del rubric (B2 = umbral 4).
ENGLISH_ORDER: dict[str, int] = {
    "a1": 1,
    "a2": 2,
    "b1": 3,
    "b2": 4,
    "c1": 5,
    "c2": 6,
    "nativo": 7,
    "native": 7,
}


@dataclass(frozen=True)
class Education:
    """Formacion academica mas alta del candidato."""

    degree: str  # ej. "Licenciatura en Ciencias de la Computacion"
    institution: str  # ej. "Universidad de Buenos Aires"
    year: int


@dataclass(frozen=True)
class Experience:
    """Un puesto en la trayectoria. Las bullets se generan en render desde pools."""

    role: str
    company: str
    sector: str  # industria del puesto (ej. "Fintech", "E-commerce")
    start_year: int
    end_year: int | None  # None = "Presente"
    tech: tuple[str, ...] = ()  # tecnologias usadas en ese puesto


@dataclass(frozen=True)
class Project:
    """Proyecto destacado (nombre + descripcion breve)."""

    name: str
    description: str


@dataclass(frozen=True)
class CandidateSpec:
    """Verdad estructurada de un candidato. Inmutable (frozen)."""

    # Identidad y contacto
    nombre: str  # nombre limpio (sin honorificos): este es el gold de extraccion
    email: str
    city: str
    country: str
    gmt: int  # offset horario, ej. -3
    region: str  # "LATAM" | "USA" | "Europa" | ...

    # Perfil tecnico decisivo (lo que el rubric evalua)
    discipline: str  # "backend" | "frontend" | "data_science" | "devops" | ...
    primary_language: str  # "Python" | "Java" | "PHP" | ...
    years_total: int
    years_relevant: int  # años en backend del lenguaje primario
    frameworks: tuple[str, ...]  # ej. ("Django", "FastAPI")
    databases: tuple[str, ...]  # ej. ("PostgreSQL", "Redis")
    english_level: str  # clave de ENGLISH_ORDER ("a2".."c1"/"nativo")

    # Campos de extraccion / contexto
    seniority: str  # "junior"|"semi_senior"|"senior"|"lead"|"" (declarado)
    education: Education
    experiences: tuple[Experience, ...]
    industria_previa: str  # sector o disciplina principal (gold profile)
    extra_skills: tuple[str, ...] = ()  # herramientas/skills adicionales (distractores)
    projects: tuple[Project, ...] = ()
    certifications: tuple[str, ...] = ()
    other_languages: tuple[tuple[str, str], ...] = ()  # (idioma, nivel) ademas de ingles

    # Metadatos de dataset
    split: str = "train"  # "train" | "val" | "test"
    noise_level: str = "med"  # "low" | "med" | "high"
    seed: int = 0  # semilla por candidato para render/noise reproducibles
    extra_lines: tuple[str, ...] = field(default=())  # lineas basura inyectables
    honorific: str = ""  # honorifico mostrado en la prosa (Dr./Ing./Lic.); NO va al gold

    def english_rank(self) -> int:
        return ENGLISH_ORDER.get(self.english_level.lower(), 0)
