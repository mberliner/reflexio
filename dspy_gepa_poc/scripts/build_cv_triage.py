"""Construye cv_triage.csv leyendo cv_profile.csv y anotando fit_label + justificacion.

Cada CV se evalua contra una JD fija (la misma para todas las filas). Usa email
como clave estable: si cambia el texto de un CV en cv_profile.csv, el triage hereda.
"""
import csv
from pathlib import Path

DATASETS = Path(__file__).resolve().parents[1] / "datasets"
PROFILE_CSV = DATASETS / "cv_profile.csv"
TRIAGE_CSV = DATASETS / "cv_triage.csv"

JOB_DESCRIPTION = (
    "Puesto: Desarrollador/a Backend Senior\n"
    "Stack requerido: Python, FastAPI o Django, PostgreSQL, Docker\n"
    "Stack deseable: AWS, Kubernetes, experiencia en microservicios\n"
    "Experiencia minima: 4 anos en backend (idealmente 6+)\n"
    "Idiomas: espanol nativo, ingles intermedio (B2) excluyente para reuniones con HQ\n"
    "Ubicacion: remoto desde LATAM (Argentina, Mexico, Colombia, Chile, Uruguay, Peru)\n"
    "Industria valorada: fintech, e-commerce o SaaS B2B"
)

# Anotaciones por email (clave estable). label + justificacion corta basada en la JD.
TRIAGE = {
    # === ORIGINALES (mayoria no_fit; Juan Perez es fit_medio por Python+Docker+UNAM/MX) ===
    "juan.perez@email.com": ("fit_medio", "Python+Docker+AWS, 5 anos. Falta FastAPI/Django/PostgreSQL explicito e idiomas declarados."),  # noqa: E501
    "maria.g@company.com": ("no_fit", "Stack desalineado (React/Node, no backend Python)."),
    "r.chen@techcorp.com": ("no_fit", "Stack Java/Spring, no Python."),
    "sarah.w@devmail.com": ("no_fit", "Perfil de ciencia de datos, no backend de produccion."),
    "ahmed.hassan@email.net": ("no_fit", "Perfil DevOps, no backend Python. Solo 3 anos."),
    "j.lopez@marketing.com": ("no_fit", "Perfil de marketing, no tecnico."),
    "m.brown@consultant.com": ("no_fit", "Consultor de negocio (Excel/Tableau), no developer."),
    "emma.watson@design.io": ("no_fit", "Perfil de diseno UX, no tecnico."),
    "davidkim@techstart.com": ("no_fit", "Full-stack JavaScript, no backend Python."),
    "lisa.a@sales.com": ("no_fit", "Perfil de ventas, no tecnico."),
    "thomas.miller@cloudeng.com": ("no_fit", "Arquitecto cloud, no backend Python."),
    "sophia.r@biotech.org": ("no_fit", "Bioinformatica con Python, no backend web."),
    "j.taylor@finance.net": ("no_fit", "Analista cuantitativo, no backend de produccion."),
    "anna.kowalski@pm.com": ("no_fit", "Gerente de producto, no tecnico."),
    "carlos@dev.mx": ("no_fit", "Backend pero stack Go, no Python."),
    "elena.petrov@research.edu": ("no_fit", "Investigadora AI academica, no backend de produccion."),  # noqa: E501

    # === SINTETICOS CLAROS ===
    "martin.acosta@dev.com.ar": ("fit_alto", "Backend Python/FastAPI/PostgreSQL/Docker, 7 anos como Tech Lead, fintech, AR, ingles B2."),  # noqa: E501
    "lucia.fernandez@correo.mx": ("fit_alto", "Backend Senior Django, 6 anos, e-commerce MX, ingles C1. Stack completo."),  # noqa: E501
    "diego.ramirez@saas.co": ("fit_alto", "Python/FastAPI/PostgreSQL/Docker/K8s, 5 anos SaaS, CO, ingles B2."),  # noqa: E501
    "florencia.sosa@fintech.uy": ("fit_alto", "Tech Lead Backend, 8 anos en fintech UY, Django+FastAPI, ingles B2."),  # noqa: E501
    "andres.vargas@ecomm.cl": ("fit_alto", "Senior Backend Python/FastAPI/PostgreSQL/Docker, 6 anos e-commerce CL, ingles C1."),  # noqa: E501
    "pablo.gimenez@correo.com.ar": ("fit_medio", "Stack y seniority correctos, pero ingles A2 incumple el B2 excluyente."),  # noqa: E501
    "ines.mora@tech.es": ("fit_medio", "Perfil tecnico ideal pero reside en Espana, fuera de LATAM."),  # noqa: E501
    "tomas.herrera@dev.com.ar": ("fit_medio", "Stack alineado y LATAM, pero junior con solo 2 anos (la JD pide 4+)."),  # noqa: E501
    "camila.torres@shop.mx": ("fit_medio", "Backend Python en LATAM, pero stack Flask en vez de FastAPI/Django y sin Docker."),  # noqa: E501
    "nicolas.bravo@frontend.com.ar": ("no_fit", "Perfil frontend (React/TS/Next), no backend."),
    "romina.espinosa@web.mx": ("no_fit", "Perfil frontend (Vue/Nuxt), no backend."),
    "sebastian.pino@rails.cl": ("no_fit", "Stack Ruby on Rails, no Python."),
    "veronica.castro@laravel.co": ("no_fit", "Stack PHP/Laravel, no Python."),
    "mateo.salinas@ios.com.ar": ("no_fit", "Desarrollador iOS, no backend."),
    "gabriela.nunez@data.mx": ("no_fit", "Data engineer (Spark/Hadoop), no backend de APIs."),
    "federico.aguilar@qa.com.ar": ("no_fit", "Perfil QA, no developer backend."),
    "patricia.maldonado@pm.uy": ("no_fit", "Project Manager / Scrum Master, no tecnica."),

    # === AMBIGUOS ===
    "diego.salgado@dev.com.ar": ("fit_alto", "Backend Python/FastAPI/PostgreSQL/Docker/K8s, 8 anos como Tech Lead en fintech y SaaS, AR, ingles B2. Cumple todo."),  # noqa: E501
    "sofia.velez@tech.mx": ("fit_medio", "Stack alineado en MX con ingles B2, pero solo 3 anos pese a titulo Senior (la JD pide 4+)."),  # noqa: E501
    "karina.mendel@research.io": ("no_fit", "Perfil de investigacion academica (deep learning), no backend de produccion. Ubicacion en Boston, fuera de LATAM."),  # noqa: E501
    "joaquin.aravena@dev.cl": ("fit_alto", "Backend Python (Django/FastAPI/PostgreSQL/Docker/K8s), 9 anos, fintech y SaaS, CL, ingles C1."),  # noqa: E501
    "daniela.kohler@frontend.com.ar": ("no_fit", "Perfil frontend (React/TS/Next), no backend."),
    "hernan.cabezas@dev.com": ("fit_medio", "Stack y seniority perfectos con ingles B2, pero ubicacion solo declara 'Latinoamerica' sin pais especifico."),  # noqa: E501
    "ricardo.tanaka@mobile.com": ("no_fit", "Desarrollador mobile (Kotlin/Swift), no backend. Ubicacion solo 'remoto' sin pais."),  # noqa: E501
    "valentina.aguirre@data.uy": ("no_fit", "Data engineer (Spark/Hadoop/Airflow) en retail, no backend de APIs."),  # noqa: E501
    "r.espinoza@dev.pe": ("no_fit", "Stack PHP/Laravel, no Python. Ademas ingles B1 incumple el B2 excluyente."),  # noqa: E501
    "mauricio.esposito@correo.com.ar": ("fit_alto", "Backend Python/FastAPI/PostgreSQL/Docker/AWS, 6 anos, fintech, AR, ingles B2."),  # noqa: E501
    "lukas.mueller@design.de": ("no_fit", "Perfil UX/UI designer, no backend. Aleman nativo (no espanol)."),  # noqa: E501
    "constanza.rivas@correo.com.ar": ("fit_medio", "Stack ideal y ubicacion AR, pero ingles B1 incumple el B2 excluyente."),  # noqa: E501
}


def main():
    rows_in = list(csv.DictReader(open(PROFILE_CSV, encoding="utf-8")))
    if len(rows_in) != len(TRIAGE):
        print(f"WARN: cv_profile tiene {len(rows_in)} filas pero TRIAGE tiene {len(TRIAGE)}.")

    missing = [r["email"] for r in rows_in if r["email"] not in TRIAGE]
    if missing:
        print(f"ERROR: emails sin anotacion en TRIAGE: {missing}")
        return 1

    with open(TRIAGE_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["split", "cv_text", "job_description", "fit_label", "justificacion"])
        for r in rows_in:
            label, just = TRIAGE[r["email"]]
            w.writerow([r["split"], r["text"], JOB_DESCRIPTION, label, just])

    # Distribucion
    from collections import Counter
    labels = Counter(label for label, _ in TRIAGE.values())
    print(f"Escritas {len(rows_in)} filas en {TRIAGE_CSV}")
    print(f"Distribucion fit_label: {dict(labels)}")
    total = sum(labels.values())
    for k, v in sorted(labels.items()):
        print(f"  {k}: {v} ({100 * v / total:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
