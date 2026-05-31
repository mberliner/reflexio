"""Catalogo de candidatos: la definicion del dataset.

Solo declara los ejes DECISIVOS por candidato (años, stack, db, ingles,
ubicacion, disciplina); builder.make_candidate rellena el resto desde pools. El
label de triage NO se escribe a mano: lo deriva rubric.triage_label, y aqui se
ASERTA que coincide con la intencion para atrapar errores de diseño.

Modular: cambiar los conteos por split en SPLIT_PLAN, o agregar un tipo de
fallo/disciplina en las funciones generadoras.
"""

from __future__ import annotations

from . import components as comp
from . import rubric
from .builder import make_candidate
from .spec import CandidateSpec

_LATAM = [c[0] for c in comp.CITIES if c[3] == "LATAM"]
_NONLATAM = [c[0] for c in comp.CITIES if c[3] != "LATAM"]
_CITY_COUNTRY = {c[0]: c[1] for c in comp.CITIES}

# Candidatos por clase y por split.
SPLIT_PLAN = {"train": 6, "val": 5, "test": 8}

# --- Pools de variedad para extraccion (NO afectan los ejes del rubric) ---
# Sectores rotados para industria_previa (antes fijo en Fintech/E-commerce).
_SECTORS = [
    "Fintech", "E-commerce", "SaaS B2B", "Retail", "Logistica",
    "Salud", "EdTech", "Gaming", "AdTech",
]
# Combos de frameworks: todos incluyen Django o FastAPI (el rubric exige uno).
_FW_COMBOS = [
    ("Django", "FastAPI"), ("Django",), ("FastAPI",),
    ("Django", "DRF"), ("FastAPI", "Celery"),
]
# Bases: PostgreSQL SIEMPRE presente (excluyente); varia la secundaria.
_DB_COMBOS = [
    ("PostgreSQL", "Redis"), ("PostgreSQL",), ("PostgreSQL", "MongoDB"),
    ("PostgreSQL", "Redis", "Elasticsearch"),
]
# Ingles dentro de la banda que APRUEBA (>= B2): variedad sin romper el rubric.
_ENG_PASS = ["b2", "c1", "c2", "nativo"]
_EXTRA_VARIANTS = [
    ("Docker", "AWS", "Git"),
    ("Docker", "Kubernetes", "CI/CD"),
    ("AWS", "Terraform", "Redis"),
    ("GCP", "Celery", "RabbitMQ"),
    ("Docker", "Linux", "Nginx"),
]


def _other_langs(city: str, i: int) -> tuple[tuple[str, str], ...]:
    base = comp.PORTUGUESE if _CITY_COUNTRY.get(city) == "Brasil" else ()
    return base + comp.EXTRA_LANGS[i % len(comp.EXTRA_LANGS)]


def _honorific(i: int) -> str:
    return comp.HONORIFICS[i % len(comp.HONORIFICS)] if i % 4 == 0 else ""


def _alto(idx: int, split: str, i: int) -> CandidateSpec:
    city = _LATAM[i % len(_LATAM)]
    years = 5 + (i % 5)
    return make_candidate(
        idx=idx, split=split, discipline="backend", primary_language="Python",
        years_total=years, years_relevant=years,
        frameworks=_FW_COMBOS[i % len(_FW_COMBOS)],
        databases=_DB_COMBOS[i % len(_DB_COMBOS)],
        english=_ENG_PASS[i % len(_ENG_PASS)], city=city,
        seniority="senior", industria=_SECTORS[i % len(_SECTORS)],
        extra_skills=_EXTRA_VARIANTS[i % len(_EXTRA_VARIANTS)],
        other_languages=_other_langs(city, i), honorific=_honorific(i),
    )


_MEDIO_FAILS = ["seniority", "stack", "db", "idioma", "ubicacion"]


def _medio(idx: int, split: str, i: int) -> CandidateSpec:
    fail = _MEDIO_FAILS[i % len(_MEDIO_FAILS)]
    city = _LATAM[i % len(_LATAM)]
    kw: dict = {
        "idx": idx, "split": split, "discipline": "backend", "primary_language": "Python",
        "years_total": 6, "years_relevant": 6,
        "frameworks": _FW_COMBOS[i % len(_FW_COMBOS)],
        "databases": _DB_COMBOS[i % len(_DB_COMBOS)],
        "english": _ENG_PASS[i % len(_ENG_PASS)], "city": city,
        "seniority": "senior", "industria": _SECTORS[(i + 3) % len(_SECTORS)],
        "extra_skills": _EXTRA_VARIANTS[i % len(_EXTRA_VARIANTS)],
        "other_languages": _other_langs(city, i), "honorific": _honorific(i),
    }
    # Inyecta EXACTAMENTE un fallo (el resto de los ejes queda aprobando).
    if fail == "seniority":
        kw.update(years_total=4, years_relevant=4)
    elif fail == "stack":
        kw.update(frameworks=("Flask",))
    elif fail == "db":
        kw.update(databases=("MySQL", "MongoDB"))
    elif fail == "idioma":
        kw.update(english="a2")
    elif fail == "ubicacion":
        non = _NONLATAM[i % len(_NONLATAM)]
        kw.update(city=non, other_languages=_other_langs(non, i))
    return make_candidate(**kw)


# (discipline, primary_language, frameworks, industria, extra_skills)
_NOFIT_TYPES: list[tuple[str, str, tuple[str, ...], str, tuple[str, ...]]] = [
    ("frontend", "JavaScript", ("React", "Angular"), "Frontend", ("TypeScript", "CSS")),
    ("data_science", "Python", ("Pandas", "Scikit-learn"), "Ciencia de Datos", ("NumPy", "SQL")),
    ("devops", "Bash", ("Terraform", "Ansible"), "DevOps", ("Kubernetes", "Python")),
    ("mobile", "Kotlin", ("Jetpack Compose",), "Mobile", ("Swift",)),
    ("qa", "Python", ("Selenium",), "QA", ("Cypress", "Jira")),
    ("backend", "Java", ("Spring Boot",), "Backend", ("Maven", "Hibernate")),
    ("backend", "PHP", ("Laravel",), "Backend", ("Composer", "MySQL")),
    ("backend", "Go", ("Gin",), "Backend", ("gRPC", "Docker")),
]


def _nofit(idx: int, split: str, i: int) -> CandidateSpec:
    disc, lang, fw, industria, extras = _NOFIT_TYPES[i % len(_NOFIT_TYPES)]
    city = _LATAM[i % len(_LATAM)]
    years = 6 + (i % 4)
    return make_candidate(
        idx=idx, split=split, discipline=disc, primary_language=lang,
        years_total=years, years_relevant=years, frameworks=fw,
        databases=("PostgreSQL",), english=_ENG_PASS[i % len(_ENG_PASS)], city=city,
        seniority="senior", industria=industria, extra_skills=extras,
        other_languages=_other_langs(city, i), honorific=_honorific(i),
    )


_GENERATORS = {"fit_alto": _alto, "fit_medio": _medio, "no_fit": _nofit}


def build_catalog() -> list[CandidateSpec]:
    """Materializa todos los candidatos y verifica que el label derivado coincida."""
    candidates: list[CandidateSpec] = []
    idx = 0
    for intent, gen in _GENERATORS.items():
        per_class_i = 0
        for split, n in SPLIT_PLAN.items():
            for _ in range(n):
                spec = gen(idx, split, per_class_i)
                derived, _just = rubric.triage_label(spec)
                if derived != intent:
                    raise AssertionError(
                        f"Candidato idx={idx} ({spec.nombre}) intent={intent} "
                        f"pero rubric derivo {derived}. Revisar ejes decisivos."
                    )
                candidates.append(spec)
                idx += 1
                per_class_i += 1
    return candidates


CANDIDATES: list[CandidateSpec] = build_catalog()
