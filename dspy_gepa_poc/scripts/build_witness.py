"""Construye el set de casos testigo de fast_gate (validacion externa).

Uso (desde la raiz del repo):
    python -m dspy_gepa_poc.scripts.build_witness

Genera `dspy_gepa_poc/datasets/flujo_intents_fast_gate_witness.csv`: los splits
train/val originales de `flujo_intents_fast_gate.csv` (intactos, para que los
few-shot sean identicos) + 14 casos testigo como `test`.

Los testigo se etiquetan con un marco INDEPENDIENTE de la rubrica interna del
proyecto (rompe la circularidad train/val<->criterios): EU AI Act (Art. 5
practicas prohibidas; Anexo III sistemas de alto riesgo) anclado a reguladores
AR (BCRA, ENACOM, AAIP/Ley 25.326, SSN, Defensa del Consumidor). Regla de mapeo
graduada por impacto (no por categoria sola) para la frontera Rojo/Amarillo de
"dominio de alto riesgo + revision humana": Rojo si naturaleza financiera/
restrictiva sobre datos personales, datos sensibles, escala masiva o acceso a
servicio esencial; Amarillo si impacto acotado y reversible. Ver
`docs/LECCIONES_APRENDIDAS.md` seccion 11.

NOTA (2026-06-16): estas etiquetas COINCIDEN con el conteo canonico del Marco
(Fast Gate de 5 preguntas Si/No; 0-1 Verde / 2-3 Amarillo / 4-5 Rojo; Negro =
P5=Si + alto impacto). Ej.: W-06/W-08 dan 4 sies con P3 ("fuera del catalogo
aprobado") en su default Si -> Rojo. El etiquetado por impacto no contradice el
conteo; el error Rojo->Amarillo del programa base venia del prompt (no contaba y
tenia el default de P3 invertido), no del etiquetado. Ver D-013.
"""

import csv
from collections import Counter
from pathlib import Path

from dspy_gepa_poc.flujo_intents.ficha import serialize_ficha
from dspy_gepa_poc.flujo_intents.make_variations import case

_DATASETS = Path(__file__).resolve().parent.parent / "datasets"
_SRC = _DATASETS / "flujo_intents_fast_gate.csv"
_OUT = _DATASETS / "flujo_intents_fast_gate_witness.csv"


def _witness_rows() -> list[dict]:
    rows: list[dict] = []

    def w(cid, tipo, datos, label, decl, src, **kw):
        rows.append(case(cid, tipo, datos, label, "test", decl, razonamiento=src, **kw))

    # ===== NEGRO: Art.5 prohibido  o  Anexo III alto riesgo + autonomo =====
    w(
        "W-01",
        "negocio",
        ["personales"],
        "Negro",
        "Sistema que calcula un puntaje social de cada cliente combinando historial de pago, "
        "actividad en redes sociales y patrones de consumo, y restringe automaticamente su "
        "acceso a productos y promociones segun ese puntaje, sin intervencion.",
        "AI Act Art.5(c) social scoring (prohibido) + autonomo. "
        "AR: AAIP/Ley 25.326, Def. Consumidor.",
        nombre="Score social de clientes",
        area="Marketing",
        metricas="Aumento de conversion del 12%",
        impacto="Toda la base de clientes; el puntaje condiciona su acceso.",
        riesgo="Decision autonoma sobre acceso a partir de perfilado social.",
        restr="Uso de datos personales y de redes.",
    )
    w(
        "W-02",
        "negocio",
        ["personales"],
        "Negro",
        "Sistema que evalua el riesgo crediticio y aprueba o rechaza la solicitud de credito de "
        "forma automatica, notificando el resultado al cliente sin intervencion humana.",
        "AI Act Anexo III 5(b) creditworthiness + autonomo. AR: BCRA, Ley 25.326.",
        nombre="Decision automatica de credito",
        area="Riesgo Crediticio",
        metricas="Reduccion del tiempo de aprobacion a minutos",
        impacto="Solicitantes de credito; el sistema decide el acceso.",
        riesgo="Decision financiera autonoma sin revision.",
        restr="Cumplimiento BCRA.",
    )
    w(
        "W-03",
        "operativo",
        ["personales"],
        "Negro",
        "Herramienta que infiere el estado emocional de los empleados a partir de camara y voz "
        "durante la jornada y ajusta automaticamente sus metas y asignaciones segun ese analisis.",
        "AI Act Art.5(f) reconocimiento de emociones en el trabajo (prohibido). AR: Ley 25.326.",
        nombre="Analisis emocional de empleados",
        area="Recursos Humanos",
        metricas="Mejora de productividad del equipo",
        impacto="Empleados monitoreados; afecta sus metas.",
        riesgo="Inferencia emocional automatica que dispara acciones.",
        restr="Datos personales de empleados.",
    )
    w(
        "W-04",
        "operativo",
        ["personales"],
        "Negro",
        "Agente que evalua el desempeno de cada empleado con un score y ejecuta automaticamente "
        "la terminacion del vinculo laboral al caer bajo el umbral, sin intervencion previa.",
        "AI Act Anexo III 4(b) gestion laboral / despido + autonomo. AR: LCT, Ley 25.326.",
        nombre="Baja automatica por desempeno",
        area="Recursos Humanos",
        metricas="Reduccion de costos de personal",
        impacto="Empleados; el sistema decide la desvinculacion.",
        riesgo="Terminacion laboral autonoma e irreversible.",
        restr="Cumplimiento laboral.",
    )
    w(
        "W-05",
        "operativo",
        ["personales"],
        "Negro",
        "Agente que ejecuta el corte del servicio a los clientes con facturas vencidas de forma "
        "autonoma segun un umbral, sin revision ni aprobacion posterior.",
        "Denegacion de acceso a servicio esencial + autonomo. AR: ENACOM, Def. Consumidor.",
        nombre="Corte automatico por impago",
        area="Cobranzas",
        metricas="Reduccion de mora del 8%",
        impacto="Clientes cortados; perdida de acceso al servicio.",
        riesgo="Corte de servicio autonomo sin revision.",
        restr="Cumplimiento ENACOM.",
    )
    # ===== ROJO: Anexo III alto riesgo + revision humana =====
    # (graduado por impacto: financiero/datos sensibles/acceso esencial -> Rojo)
    w(
        "W-06",
        "negocio",
        ["personales"],
        "Rojo",
        "Sistema que calcula un score de riesgo crediticio y lo propone, pero un analista de "
        "credito revisa y decide cada solicitud antes de notificar al cliente.",
        "AI Act Anexo III 5(b) + revision humana; "
        "impacto financiero sobre datos personales. AR: BCRA.",
        nombre="Scoring crediticio asistido",
        area="Riesgo Crediticio",
        metricas="Reduccion del tiempo de analisis",
        impacto="Solicitantes; un analista decide.",
        riesgo="Apoyo a la decision; humano valida cada caso.",
        restr="Cumplimiento BCRA; revision humana.",
    )
    w(
        "W-07",
        "operativo",
        ["personales"],
        "Amarillo",
        "Sistema que ordena y puntua los candidatos a una busqueda laboral para el reclutador, "
        "que entrevista y decide a quien avanzar.",
        "AI Act Anexo III 4(a) + revision humana; "
        "impacto acotado y reversible (no sensible). AR: Ley 25.326.",
        nombre="Ranking de candidatos",
        area="Recursos Humanos",
        metricas="Reduccion del tiempo de screening",
        impacto="Postulantes; el reclutador decide.",
        riesgo="Ranking asistivo; humano decide.",
        restr="Datos personales de postulantes.",
    )
    w(
        "W-08",
        "negocio",
        ["personales"],
        "Rojo",
        "Sistema que sugiere la prima de un seguro de salud segun el perfil de riesgo; un "
        "actuario revisa y aprueba el valor final antes de ofrecerlo.",
        "AI Act Anexo III 5(c) + revision humana; datos de salud sensibles. AR: SSN, Ley 25.326.",
        nombre="Pricing asistido de seguros",
        area="Actuarial",
        metricas="Mejora de la precision del pricing",
        impacto="Asegurados; un actuario aprueba.",
        riesgo="Sugerencia de prima con validacion humana.",
        restr="Cumplimiento Superintendencia de Seguros.",
    )
    w(
        "W-09",
        "negocio",
        ["personales"],
        "Rojo",
        "Sistema que evalua la elegibilidad a un beneficio de asistencia y arma un dictamen que "
        "un agente revisa y confirma antes de comunicar la resolucion.",
        "AI Act Anexo III 5(a) + revision humana; "
        "acceso a beneficio esencial, datos sensibles. AR: Ley 25.326.",
        nombre="Pre-evaluacion de beneficios",
        area="Atencion Social",
        metricas="Reduccion de tiempos de resolucion",
        impacto="Beneficiarios; un agente confirma.",
        riesgo="Dictamen asistido con revision humana.",
        restr="Datos personales sensibles.",
    )
    # ===== AMARILLO: fuera de Anexo III, influye en clientes o modelo externo =====
    w(
        "W-10",
        "negocio",
        ["personales"],
        "Amarillo",
        "Chatbot de atencion que responde consultas frecuentes de clientes y deriva a un humano "
        "cualquier caso fuera de su alcance; usa un modelo de un proveedor externo aun no "
        "homologado.",
        "AI Act riesgo limitado (transparencia) + modelo externo. AR: Def. Consumidor.",
        nombre="Chatbot de atencion",
        area="Atencion al Cliente",
        metricas="Resolucion del 60% de consultas en primer contacto",
        impacto="Clientes consultantes; deriva a humano.",
        riesgo="No toma decisiones; modelo externo no homologado.",
        restr="Proveedor externo.",
    )
    w(
        "W-11",
        "operativo",
        ["personales"],
        "Amarillo",
        "Asistente que redacta respuestas sugeridas a reclamos de clientes; un agente las revisa, "
        "edita y envia. Usa un proveedor externo no homologado.",
        "AI Act riesgo limitado + modelo externo; el humano envia. AR: Def. Consumidor.",
        nombre="Sugeridor de respuestas",
        area="Atencion al Cliente",
        metricas="Reduccion del tiempo de respuesta",
        impacto="Clientes; un agente envia la respuesta final.",
        riesgo="Sugerencia con revision humana; modelo externo.",
        restr="Proveedor externo no homologado.",
    )
    w(
        "W-12",
        "negocio",
        ["publicos"],
        "Amarillo",
        "Servicio que resume noticias publicas del sector y las envia a los clientes en un "
        "boletin, usando un modelo de un proveedor externo no homologado.",
        "AI Act riesgo limitado + modelo externo expuesto a clientes. AR: n/a.",
        nombre="Boletin de noticias",
        area="Marketing",
        metricas="Aumento de apertura del boletin",
        impacto="Clientes lectores; contenido informativo.",
        riesgo="Contenido a clientes via modelo externo.",
        restr="Fuentes publicas.",
    )
    # ===== VERDE: interno, sin datos personales, con revision =====
    w(
        "W-13",
        "capacidad",
        ["ninguno"],
        "Verde",
        "Asistente que resume documentacion tecnica interna del equipo para acelerar el "
        "onboarding; el autor revisa antes de publicar. No usa datos personales.",
        "AI Act riesgo minimo. Interno, sin datos personales, revision humana.",
        nombre="Resumen de docs tecnicas",
        area="Ingenieria",
        metricas="Reduccion del tiempo de onboarding",
        impacto="Empleados como usuarios; sin decision sobre personas.",
        riesgo="Uso interno; revision humana previa.",
        restr="Sin datos personales.",
    )
    w(
        "W-14",
        "capacidad",
        ["ninguno"],
        "Verde",
        "Generador de borradores de comunicados internos a partir de notas del equipo; el autor "
        "edita y aprueba antes de difundir. No usa datos personales.",
        "AI Act riesgo minimo. Interno, sin datos personales, revision humana.",
        nombre="Borradores de comunicados",
        area="Comunicacion Interna",
        metricas="Reduccion del tiempo de redaccion",
        impacto="Empleados como usuarios; sin decision sobre personas.",
        riesgo="Uso interno; autor aprueba.",
        restr="Sin datos personales.",
    )
    return rows


def build() -> Path:
    src_rows = list(csv.DictReader(open(_SRC, encoding="utf-8")))
    cols = list(src_rows[0].keys())  # split,case_id,ficha,p1..p5,clasificacion,razonamiento
    out_rows = [r for r in src_rows if r["split"] in ("train", "val")]
    for r in _witness_rows():
        out_rows.append(
            {
                "split": "test",
                "case_id": r["id"],
                "ficha": serialize_ficha(r),
                "p1": "",
                "p2": "",
                "p3": "",
                "p4": "",
                "p5": "",
                "clasificacion": r["label"],
                "razonamiento": r["razonamiento"],
            }
        )
    with open(_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for r in out_rows:
            writer.writerow({c: r.get(c, "") for c in cols})

    test_labels = Counter(r["clasificacion"] for r in out_rows if r["split"] == "test")
    splits = Counter(r["split"] for r in out_rows)
    print(f"[witness] {_OUT}")
    print(f"  splits={dict(splits)}  test_labels={dict(test_labels)}")
    return _OUT


if __name__ == "__main__":
    build()
