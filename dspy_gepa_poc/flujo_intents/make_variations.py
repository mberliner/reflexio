"""Casos train/val hechos a mano para flujo-intents (sin generador).

Cada caso es una ficha explicita, inspirada en el estilo de los originales del
proyecto de gobierno pero con contenido distinto, etiquetada para una etapa. Este
modulo es la SSOT del train/val; al ejecutarse escribe los CSV de variaciones que
`dataset.py` consume:

    python -m dspy_gepa_poc.flujo_intents.make_variations

Los 42 originales NO se tocan: son el holdout de test (recortado a 30 por etapa).
Aqui se autoran train (30) + val (15) por etapa, balanceados por clase. El helper
`case` defaultea los campos no decisivos para mantener cada caso compacto; el texto
se concentra en los campos que definen la clase de esa etapa.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

# tipo de intent -> columna booleana
_TIPO = {
    "negocio": "tipo_intent_negocio",
    "operativo": "tipo_intent_operativo",
    "capacidad": "tipo_intent_capacidad_equipos",
    "tecnico": "tipo_intent_tecnico_arquitectural",
}
# categoria de datos -> columna booleana
_DATOS = {
    "ninguno": "datos_requeridos_ninguno",
    "publicos": "datos_requeridos_datos_publicos",
    "operativos": "datos_requeridos_datos_operativos",
    "personales": "datos_requeridos_datos_personales",
    "confidenciales": "datos_requeridos_datos_confidenciales",
    "otros": "datos_requeridos_otros",
}

_FICHA_COLS = [
    "id",
    "nombre_iniciativa",
    *_TIPO.values(),
    "declaracion_intent",
    "area_proponente",
    "flujo_de_valor",
    "metricas_de_exito",
    "impacto_personas",
    *_DATOS.values(),
    "supuesto_riesgo",
    "restricciones",
    "sponsor",
]

# Defaults de los campos NO decisivos (se sobreescriben solo cuando importan).
_DEF_IMPACTO = "Empleados como usuarios; no decide sobre personas. Criticidad baja."
_DEF_RIESGO = "El modelo del catalogo es adecuado; hay revision humana previa."
_DEF_RESTR = "Sin datos personales; revision humana previa; presupuesto acotado."
_DEF_METRICAS = "Reduccion de tiempo >= 40% (linea base 10h/mes; meta 6h/mes)"
_DEF_SPONSOR = "Gerente de Area (persona accountable)"


def case(
    cid: str,
    tipo: str,
    datos: Iterable[str],
    label: str,
    split: str,
    decl: str,
    *,
    nombre: str | None = None,
    area: str = "Operaciones",
    flujo: str = "Proceso interno del area",
    metricas: str = _DEF_METRICAS,
    impacto: str = _DEF_IMPACTO,
    riesgo: str = _DEF_RIESGO,
    restr: str = _DEF_RESTR,
    sponsor: str = _DEF_SPONSOR,
    razonamiento: str = "",
) -> dict[str, str]:
    row: dict[str, str] = dict.fromkeys(_TIPO.values(), "false")
    row.update(dict.fromkeys(_DATOS.values(), "false"))
    row[_TIPO[tipo]] = "true"
    for d in datos:
        row[_DATOS[d]] = "true"
    row.update(
        id=cid,
        nombre_iniciativa=nombre or cid,
        declaracion_intent=decl,
        area_proponente=area,
        flujo_de_valor=flujo,
        metricas_de_exito=metricas,
        impacto_personas=impacto,
        supuesto_riesgo=riesgo,
        restricciones=restr,
        sponsor=sponsor,
        label=label,
        split=split,
        razonamiento=razonamiento,
    )
    return row


# ===========================================================================
# INTAKE: admitida vs incompleta (campo minimo ausente o contradiccion interna)
# ===========================================================================
INTAKE = [
    # --- incompleta: campo de texto minimo ausente (override a "") ---
    case(
        "VAR-INT-I01",
        "operativo",
        ["operativos"],
        "incompleta",
        "train",
        "",
        nombre="Clasificador de tickets",
        area="Soporte",
        metricas="Reduccion del tiempo de primera respuesta de 8h a 2h",
        impacto="Agentes de soporte como usuarios; el cliente recibe la derivacion. Criticidad media.",
        sponsor="Jefe de Mesa de Ayuda (persona accountable)",
    ),
    case(
        "VAR-INT-I02",
        "negocio",
        ["personales"],
        "incompleta",
        "train",
        "Sistema que recomienda ofertas al cliente.",
        sponsor="",
    ),
    case(
        "VAR-INT-I03",
        "operativo",
        ["confidenciales"],
        "incompleta",
        "train",
        "Sistema que resume reportes financieros internos.",
        metricas="",
    ),
    case(
        "VAR-INT-I04",
        "operativo",
        ["operativos"],
        "incompleta",
        "train",
        "Sistema que prioriza ordenes de trabajo.",
        impacto="",
    ),
    case(
        "VAR-INT-I05",
        "capacidad",
        ["ninguno"],
        "incompleta",
        "train",
        "Asistente que redacta minutas internas.",
        flujo="",
    ),
    case(
        "VAR-INT-I06",
        "operativo",
        ["operativos"],
        "incompleta",
        "train",
        "Detector de anomalias en logs de red.",
        area="",
    ),
    case(
        "VAR-INT-I07",
        "negocio",
        ["personales"],
        "incompleta",
        "train",
        "Motor de scoring de clientes.",
        riesgo="",
    ),
    case(
        "VAR-INT-I08",
        "operativo",
        ["confidenciales"],
        "incompleta",
        "train",
        "Resumen de contratos internos.",
        restr="",
    ),
    case(
        "VAR-INT-I09",
        "operativo",
        ["operativos"],
        "incompleta",
        "train",
        "",
        nombre="Asistente de inventario",
        area="Logistica",
        metricas="Reduccion de quiebres de stock del 15% al 5%",
        impacto="Equipo de logistica como usuario; no decide sobre personas. Criticidad baja.",
        riesgo="Modelo de pronostico estandar; el planner valida los pedidos sugeridos.",
        sponsor="Gerente de Logistica (persona accountable)",
    ),
    case(
        "VAR-INT-I10",
        "negocio",
        ["personales"],
        "incompleta",
        "train",
        "Recomendador de planes.",
        sponsor="",
    ),
    # --- incompleta: contradiccion interna irreconciliable ---
    case(
        "VAR-INT-I11",
        "negocio",
        ["ninguno"],
        "incompleta",
        "train",
        "Sistema que analiza historial de pagos y perfil crediticio del cliente para recomendar productos.",
        restr="Sin datos personales.",
    ),
    case(
        "VAR-INT-I12",
        "operativo",
        ["ninguno"],
        "incompleta",
        "train",
        "Agente que procesa datos personales de empleados para asignar turnos.",
        impacto="Empleados afectados.",
    ),
    case(
        "VAR-INT-I13",
        "negocio",
        ["personales"],
        "incompleta",
        "train",
        "Sistema puramente informativo que no accede a ningun dato del cliente ni de terceros.",
        restr="No usa datos.",
    ),
    case(
        "VAR-INT-I14",
        "operativo",
        ["confidenciales"],
        "incompleta",
        "train",
        "Herramienta que no procesa informacion alguna, solo muestra un calendario fijo.",
    ),
    case(
        "VAR-INT-I15",
        "operativo",
        ["operativos"],
        "incompleta",
        "train",
        "",
        nombre="Bot de reportes",
        area="Finanzas",
        metricas="Cierre mensual en 1 dia en lugar de 4",
        impacto="Analistas de finanzas como usuarios; reportes internos. Criticidad media.",
        restr="Datos financieros confidenciales; acceso restringido al equipo de Finanzas.",
        sponsor="Gerente de Finanzas (persona accountable)",
    ),
    # incompleta val
    case(
        "VAR-INT-I16",
        "negocio",
        ["personales"],
        "incompleta",
        "val",
        "Asistente comercial.",
        metricas="",
    ),
    case(
        "VAR-INT-I17",
        "operativo",
        ["operativos"],
        "incompleta",
        "val",
        "Clasificador de correos.",
        sponsor="",
    ),
    case(
        "VAR-INT-I18",
        "operativo",
        ["confidenciales"],
        "incompleta",
        "val",
        "",
        nombre="Analizador de costos",
        area="Finanzas",
        metricas="Identificacion del 90% de desvios de costo > 5%",
        impacto="Controllers como usuarios; marca desvios para revision. Criticidad media.",
        riesgo="Reglas de deteccion auditadas; control de gestion revisa cada alerta.",
        restr="Informacion de costos confidencial; segregacion de funciones.",
        sponsor="Controller (persona accountable)",
    ),
    case(
        "VAR-INT-I19",
        "negocio",
        ["ninguno"],
        "incompleta",
        "val",
        "Sistema que usa datos de facturacion y consumo del cliente para segmentar.",
        restr="Sin datos personales.",
    ),
    case(
        "VAR-INT-I20",
        "capacidad",
        ["ninguno"],
        "incompleta",
        "val",
        "Asistente de documentacion.",
        flujo="",
    ),
    case(
        "VAR-INT-I21",
        "operativo",
        ["operativos"],
        "incompleta",
        "val",
        "Optimizador de rutas.",
        impacto="",
    ),
    case(
        "VAR-INT-I22", "negocio", ["personales"], "incompleta", "val", "Motor de upsell.", riesgo=""
    ),
    # --- admitida: ficha completa y consistente (riesgo variado, todo declarado) ---
    case(
        "VAR-INT-A01",
        "capacidad",
        ["ninguno"],
        "admitida",
        "train",
        "Asistente que genera borradores de documentacion tecnica a partir de notas del equipo; el autor revisa.",
        nombre="Asistente de docs",
        area="Ingenieria",
    ),
    case(
        "VAR-INT-A02",
        "operativo",
        ["confidenciales"],
        "admitida",
        "train",
        "Sistema que resume reportes de gestion confidenciales y marca desvios; la gerencia valida.",
        nombre="Resumen gerencial",
        area="Planificacion",
    ),
    case(
        "VAR-INT-A03",
        "negocio",
        ["personales"],
        "admitida",
        "train",
        "Sistema que sugiere ofertas al representante segun el consumo del cliente; el representante decide.",
        nombre="Recomendador asistido",
        area="Ventas",
        impacto="Clientes via representante; el representante decide. Criticidad media.",
        restr="Cumplimiento Ley 25.326; el representante decide.",
    ),
    case(
        "VAR-INT-A04",
        "operativo",
        ["operativos"],
        "admitida",
        "train",
        "Sistema que prioriza incidencias por severidad para el equipo tecnico; el equipo decide.",
        nombre="Triage de incidencias",
        area="Soporte",
    ),
    case(
        "VAR-INT-A05",
        "operativo",
        ["confidenciales"],
        "admitida",
        "train",
        "Sistema que detecta anomalias de costos y las marca para revision de Finanzas.",
        nombre="Anomalias de costos",
        area="Finanzas",
    ),
    case(
        "VAR-INT-A06",
        "capacidad",
        ["ninguno"],
        "admitida",
        "train",
        "Asistente que redacta borradores de comunicados internos; el responsable aprueba antes de publicar.",
        nombre="Asistente comunicados",
        area="Comunicaciones",
    ),
    case(
        "VAR-INT-A07",
        "negocio",
        ["personales"],
        "admitida",
        "train",
        "Chatbot que responde consultas del cliente sobre su plan en plataforma interna homologada; escala a humano.",
        nombre="Chatbot de plan",
        area="Atencion",
        impacto="Clientes que interactuan. Criticidad alta.",
        restr="Cumplimiento Ley 25.326; escalada a humano fuera de dominio.",
    ),
    case(
        "VAR-INT-A08",
        "operativo",
        ["operativos"],
        "admitida",
        "train",
        "Sistema de monitoreo que alerta al equipo de red ante desvios; el equipo decide intervenir.",
        nombre="Monitoreo de red",
        area="Infraestructura",
    ),
    case(
        "VAR-INT-A09",
        "tecnico",
        ["operativos"],
        "admitida",
        "train",
        "Pipeline que clasifica logs de plataforma para mejorar la observabilidad interna.",
        nombre="Clasificador de logs",
        area="Plataforma",
    ),
    case(
        "VAR-INT-A10",
        "operativo",
        ["confidenciales"],
        "admitida",
        "train",
        "Sistema que analiza contratos internos e identifica clausulas de riesgo; el abogado valida.",
        nombre="Analizador de clausulas",
        area="Legal",
        impacto="Abogados como consumidores. Criticidad alta.",
        restr="Confidencialidad contractual; el abogado valida cada hallazgo.",
    ),
    case(
        "VAR-INT-A11",
        "negocio",
        ["personales"],
        "admitida",
        "train",
        "Sistema que calcula score crediticio con API externa por homologar; el analista registra la decision.",
        nombre="Scoring credito",
        area="Credito",
        impacto="Clientes solicitantes; el score condiciona el acceso. Criticidad muy alta.",
        riesgo="La API externa sera homologada antes de produccion.",
        restr="Cumplimiento BCRA; el analista decide; sin variables discriminatorias.",
    ),
    case(
        "VAR-INT-A12",
        "operativo",
        ["personales"],
        "admitida",
        "train",
        "Agente que envia comunicaciones de bienvenida predefinidas al activar un plan; contenido aprobado.",
        nombre="Onboarding",
        area="Activacion",
        impacto="Clientes nuevos. Criticidad media.",
        restr="Cumplimiento Ley 25.326; plantillas aprobadas.",
    ),
    case(
        "VAR-INT-A13",
        "operativo",
        ["operativos"],
        "admitida",
        "train",
        "Sistema que sugiere asignacion de turnos al supervisor; el supervisor aprueba.",
        nombre="Asignacion de turnos",
        area="Operaciones",
    ),
    case(
        "VAR-INT-A14",
        "capacidad",
        ["ninguno"],
        "admitida",
        "train",
        "Asistente que genera consultas SQL a partir de pedidos en lenguaje natural del analista interno.",
        nombre="Asistente SQL",
        area="Datos",
    ),
    case(
        "VAR-INT-A15",
        "operativo",
        ["confidenciales"],
        "admitida",
        "train",
        "Sistema que resume actas de directorio para los participantes; ellos validan antes de distribuir.",
        nombre="Resumen de actas",
        area="Secretaria",
        restr="Confidencial; participantes validan.",
    ),
    # admitida val
    case(
        "VAR-INT-A16",
        "capacidad",
        ["ninguno"],
        "admitida",
        "val",
        "Asistente que propone respuestas a tickets internos; el agente revisa antes de enviar.",
        nombre="Asistente tickets",
        area="Soporte",
    ),
    case(
        "VAR-INT-A17",
        "operativo",
        ["confidenciales"],
        "admitida",
        "val",
        "Sistema que genera tableros de costos para gerentes; ninguna decision sobre personas depende del output.",
        nombre="Tablero de costos",
        area="Finanzas",
    ),
    case(
        "VAR-INT-A18",
        "negocio",
        ["personales"],
        "admitida",
        "val",
        "Sistema que recomienda upgrades al representante; el representante decide que ofrecer.",
        nombre="Recomendador upgrade",
        area="Atencion",
        impacto="Clientes via representante. Criticidad media.",
        restr="Cumplimiento Defensa del Consumidor; el representante decide.",
    ),
    case(
        "VAR-INT-A19",
        "operativo",
        ["operativos"],
        "admitida",
        "val",
        "Sistema que detecta fraude potencial y lo marca para el equipo de riesgos; el equipo decide.",
        nombre="Deteccion de fraude",
        area="Riesgos",
    ),
    case(
        "VAR-INT-A20",
        "tecnico",
        ["operativos"],
        "admitida",
        "val",
        "Pipeline que evalua la calidad de datos de ingestion y reporta al equipo de datos.",
        nombre="Calidad de datos",
        area="Datos",
    ),
    case(
        "VAR-INT-A21",
        "capacidad",
        ["ninguno"],
        "admitida",
        "val",
        "Asistente que resume papers tecnicos para el equipo de investigacion interna.",
        nombre="Resumen tecnico",
        area="I+D",
    ),
    case(
        "VAR-INT-A22",
        "operativo",
        ["confidenciales"],
        "admitida",
        "val",
        "Sistema que analiza encuestas internas de clima y reporta tendencias agregadas a RRHH.",
        nombre="Analisis de clima",
        area="RRHH",
        restr="Datos agregados; sin identificar individuos.",
    ),
    case(
        "VAR-INT-A23",
        "operativo",
        ["personales"],
        "admitida",
        "val",
        "Sistema que genera un resumen del historial del cliente para el representante; es informativo.",
        nombre="Resumen de historial",
        area="Atencion",
        impacto="Representantes como usuarios; informativo. Criticidad media.",
        restr="Cumplimiento Ley 25.326; el representante decide.",
    ),
]


# ===========================================================================
# TRIAGE_SOLIDEZ: solido / devolucion_reformulacion (2 clases del Marco; salida Si/No)
# (la ficha ya fue admitida: completa; aqui se juzga la solidez del intent)
# devolucion_no_ia ("no requiere IA") y "valor real" se retiraron: no son criterios de
# solidez del Marco; van a etapas nuevas (diferidas, D-014).
# ===========================================================================
def _sol(cid, tipo, datos, label, split, decl, **kw):  # noqa: ANN001, ANN003
    return case(cid, tipo, datos, label, split, decl, **kw)


SOLIDEZ = [
    # solido (10 train + 5 val): resultado claro, sponsor individual, metricas medibles, requiere IA
    _sol(
        "VAR-SOL-S01",
        "operativo",
        ["confidenciales"],
        "solido",
        "train",
        "Sistema que detecta anomalias de costos por centro y las marca para Finanzas; reduce el tiempo de revision.",
        metricas="Deteccion de anomalias >= 80% (linea base 55%); tiempo -50%",
    ),
    _sol(
        "VAR-SOL-S02",
        "capacidad",
        ["ninguno"],
        "solido",
        "train",
        "Asistente que genera borradores de minutas a partir de transcripciones; el autor valida.",
        metricas="Tiempo de documentacion -60% (de 90 a 36 min); satisfaccion >= 4/5",
    ),
    _sol(
        "VAR-SOL-S03",
        "negocio",
        ["personales"],
        "solido",
        "train",
        "Sistema que resume el historial del cliente para el representante antes de la llamada; es informativo.",
        metricas="Tiempo de preparacion -50%; satisfaccion del representante >= 4/5",
    ),
    _sol(
        "VAR-SOL-S04",
        "operativo",
        ["operativos"],
        "solido",
        "train",
        "Sistema que prioriza tickets por severidad y los rutea al equipo correcto; el equipo decide.",
        metricas="Tiempo de primera respuesta -40% (de 8h a 5h)",
    ),
    _sol(
        "VAR-SOL-S05",
        "operativo",
        ["confidenciales"],
        "solido",
        "train",
        "Sistema que resume reportes de gestion y marca desvios para la gerencia; la gerencia valida.",
        metricas="Tiempo de resumen < 2h; precision de desvios >= 85%",
    ),
    _sol(
        "VAR-SOL-S06",
        "tecnico",
        ["operativos"],
        "solido",
        "train",
        "Pipeline que clasifica logs para mejorar la observabilidad del equipo de plataforma.",
        metricas="Cobertura de clasificacion >= 90%; MTTR -30%",
    ),
    _sol(
        "VAR-SOL-S07",
        "negocio",
        ["personales"],
        "solido",
        "train",
        "Chatbot que responde consultas del cliente sobre su plan; escala a humano fuera de dominio.",
        metricas="Resolucion sin escalada >= 70%; CSAT >= 4/5",
    ),
    _sol(
        "VAR-SOL-S08",
        "operativo",
        ["confidenciales"],
        "solido",
        "train",
        "Sistema que identifica clausulas de riesgo en contratos para el equipo legal; el abogado valida.",
        metricas="Cobertura de clausulas >= 90%; falsos negativos < 5%",
    ),
    _sol(
        "VAR-SOL-S09",
        "capacidad",
        ["ninguno"],
        "solido",
        "train",
        "Asistente que genera consultas SQL desde lenguaje natural para el analista; el analista revisa.",
        metricas="Tiempo de consulta -55%; consultas correctas >= 85%",
    ),
    _sol(
        "VAR-SOL-S10",
        "operativo",
        ["operativos"],
        "solido",
        "train",
        "Sistema que predice demanda de stock para sugerir reposicion al comprador; el comprador decide.",
        metricas="Quiebres de stock -35%; exactitud de pronostico >= 80%",
    ),
    _sol(
        "VAR-SOL-S11",
        "operativo",
        ["confidenciales"],
        "solido",
        "val",
        "Sistema que resume encuestas internas y reporta tendencias agregadas a RRHH.",
        metricas="Tiempo de analisis -50%; cobertura de encuestas 100%",
    ),
    _sol(
        "VAR-SOL-S12",
        "negocio",
        ["personales"],
        "solido",
        "val",
        "Sistema que sugiere ofertas al representante segun consumo; el representante decide.",
        metricas="Conversion >= 12%; NPS sin deterioro",
    ),
    _sol(
        "VAR-SOL-S13",
        "operativo",
        ["operativos"],
        "solido",
        "val",
        "Sistema que detecta fraude potencial y lo marca para el equipo de riesgos; el equipo decide.",
        metricas="Deteccion de fraude +20%; falsos positivos < 8%",
    ),
    _sol(
        "VAR-SOL-S14",
        "capacidad",
        ["ninguno"],
        "solido",
        "val",
        "Asistente que redacta borradores de comunicados internos; el responsable aprueba.",
        metricas="Tiempo de redaccion -50%; aprobacion sin cambios >= 70%",
    ),
    _sol(
        "VAR-SOL-S15",
        "tecnico",
        ["operativos"],
        "solido",
        "val",
        "Pipeline que evalua calidad de datos de ingestion y reporta al equipo de datos.",
        metricas="Registros inconsistentes -80%; cobertura 100%",
    ),
    # solido -- ampliacion balanceada (4 train + 5 val + 10 test) para 2 clases del Marco
    _sol(
        "VAR-SOL-S16",
        "operativo",
        ["confidenciales"],
        "solido",
        "train",
        "Sistema que clasifica correos de clientes por intencion y los rutea al equipo; el equipo decide.",
        metricas="Precision de ruteo >= 85%; tiempo de derivacion -40%",
    ),
    _sol(
        "VAR-SOL-S17",
        "capacidad",
        ["ninguno"],
        "solido",
        "train",
        "Asistente que resume documentacion tecnica para el equipo de I+D; el investigador valida.",
        metricas="Tiempo de revision -50%; satisfaccion >= 4/5",
    ),
    _sol(
        "VAR-SOL-S18",
        "negocio",
        ["personales"],
        "solido",
        "train",
        "Sistema que detecta churn potencial y lo marca para el equipo de retencion; el equipo decide.",
        metricas="Deteccion de churn >= 75%; falsos positivos < 10%",
    ),
    _sol(
        "VAR-SOL-S19",
        "operativo",
        ["operativos"],
        "solido",
        "train",
        "Sistema que predice fallas de equipos para mantenimiento preventivo; el tecnico valida.",
        metricas="Fallas no planificadas -30%; exactitud >= 80%",
    ),
    _sol(
        "VAR-SOL-S20",
        "operativo",
        ["confidenciales"],
        "solido",
        "val",
        "Sistema que extrae datos clave de facturas de proveedores para el contador; el contador valida.",
        metricas="Exactitud de extraccion >= 90%; tiempo -50%",
    ),
    _sol(
        "VAR-SOL-S21",
        "capacidad",
        ["ninguno"],
        "solido",
        "val",
        "Asistente que genera casos de prueba a partir de requisitos para QA; el QA revisa.",
        metricas="Cobertura de pruebas +25%; tiempo de diseno -40%",
    ),
    _sol(
        "VAR-SOL-S22",
        "negocio",
        ["personales"],
        "solido",
        "val",
        "Sistema que segmenta clientes y sugiere campanias al responsable de marketing; el responsable decide.",
        metricas="Conversion +10%; sin deterioro de NPS",
    ),
    _sol(
        "VAR-SOL-S23",
        "operativo",
        ["operativos"],
        "solido",
        "val",
        "Sistema que detecta anomalias de trafico de red y alerta al SOC; el SOC decide.",
        metricas="Deteccion >= 80%; falsos positivos < 8%",
    ),
    _sol(
        "VAR-SOL-S24",
        "tecnico",
        ["operativos"],
        "solido",
        "val",
        "Sistema que clasifica logs de error por causa raiz para el equipo de plataforma.",
        metricas="Tiempo de diagnostico -45%; precision >= 85%",
    ),
    _sol(
        "TST-SOL-S01",
        "operativo",
        ["confidenciales"],
        "solido",
        "test",
        "Sistema que resume contratos para el area legal; el abogado valida cada resumen.",
        metricas="Tiempo de revision -55%; cobertura de clausulas >= 90%",
    ),
    _sol(
        "TST-SOL-S02",
        "capacidad",
        ["ninguno"],
        "solido",
        "test",
        "Asistente que documenta codigo para los desarrolladores; el dev revisa.",
        metricas="Tiempo de documentacion -50%; aceptacion >= 80%",
    ),
    _sol(
        "TST-SOL-S03",
        "negocio",
        ["personales"],
        "solido",
        "test",
        "Sistema que prioriza leads para el vendedor segun probabilidad de cierre; el vendedor decide.",
        metricas="Tasa de cierre +15%; tiempo de calificacion -40%",
    ),
    _sol(
        "TST-SOL-S04",
        "operativo",
        ["operativos"],
        "solido",
        "test",
        "Sistema que pronostica demanda para el planificador; el planificador decide la reposicion.",
        metricas="Error de pronostico < 15%; quiebres de stock -30%",
    ),
    _sol(
        "TST-SOL-S05",
        "operativo",
        ["confidenciales"],
        "solido",
        "test",
        "Sistema que detecta gastos atipicos para el equipo de auditoria; el auditor valida.",
        metricas="Deteccion >= 80%; falsos positivos < 10%",
    ),
    _sol(
        "TST-SOL-S06",
        "capacidad",
        ["ninguno"],
        "solido",
        "test",
        "Asistente que traduce documentacion tecnica para el equipo; el autor valida.",
        metricas="Tiempo de traduccion -60%; calidad >= 4/5",
    ),
    _sol(
        "TST-SOL-S07",
        "negocio",
        ["personales"],
        "solido",
        "test",
        "Sistema que resume interacciones del cliente para el agente antes del contacto; es informativo.",
        metricas="Tiempo de preparacion -50%; CSAT >= 4/5",
    ),
    _sol(
        "TST-SOL-S08",
        "operativo",
        ["operativos"],
        "solido",
        "test",
        "Sistema que clasifica incidentes por severidad para el NOC; el NOC decide.",
        metricas="Tiempo de triage -40%; precision >= 85%",
    ),
    _sol(
        "TST-SOL-S09",
        "tecnico",
        ["operativos"],
        "solido",
        "test",
        "Sistema que detecta degradacion de performance y alerta al equipo de plataforma.",
        metricas="MTTR -30%; deteccion temprana >= 80%",
    ),
    _sol(
        "TST-SOL-S10",
        "operativo",
        ["confidenciales"],
        "solido",
        "test",
        "Sistema que identifica clausulas faltantes en contratos para revision legal; el abogado decide.",
        metricas="Cobertura >= 90%; falsos negativos < 5%",
    ),
    # devolucion_reformulacion (10 train + 5 val): tecnologia-no-resultado / sponsor colectivo / metricas no medibles
    _sol(
        "VAR-SOL-R01",
        "negocio",
        ["personales"],
        "devolucion_reformulacion",
        "train",
        "Implementar GPT-4 en el canal de atencion para automatizar respuestas.",
        metricas="Implementacion en Q3; adopcion >= 80%",
    ),
    _sol(
        "VAR-SOL-R02",
        "operativo",
        ["operativos"],
        "devolucion_reformulacion",
        "train",
        "Implementar un modelo de Hugging Face en el area de soporte.",
        metricas="Despliegue completo en Q2",
    ),
    _sol(
        "VAR-SOL-R03",
        "negocio",
        ["personales"],
        "devolucion_reformulacion",
        "train",
        "Adoptar Llama 3 para el equipo comercial.",
        metricas="Uso del modelo >= 80%",
    ),
    _sol(
        "VAR-SOL-R04",
        "operativo",
        ["confidenciales"],
        "devolucion_reformulacion",
        "train",
        "Sistema que mejora la experiencia y reduce tiempos del proceso de reclamos.",
        metricas="Mejorar la experiencia; reducir tiempos; aumentar la eficiencia",
    ),
    _sol(
        "VAR-SOL-R05",
        "operativo",
        ["operativos"],
        "devolucion_reformulacion",
        "train",
        "Sistema que optimiza la gestion de inventario.",
        metricas="Optimizar el inventario; mejorar la disponibilidad",
    ),
    _sol(
        "VAR-SOL-R06",
        "negocio",
        ["personales"],
        "devolucion_reformulacion",
        "train",
        "Sistema que aumenta las ventas y la satisfaccion del cliente.",
        metricas="Aumentar ventas; mejorar satisfaccion",
    ),
    _sol(
        "VAR-SOL-R07",
        "operativo",
        ["confidenciales"],
        "devolucion_reformulacion",
        "train",
        "Sistema que analiza datos de gestion para la toma de decisiones.",
        sponsor="El equipo de Transformacion Digital",
    ),
    _sol(
        "VAR-SOL-R08",
        "operativo",
        ["operativos"],
        "devolucion_reformulacion",
        "train",
        "Sistema que clasifica solicitudes de servicio.",
        sponsor="El comite de Operaciones",
    ),
    _sol(
        "VAR-SOL-R09",
        "negocio",
        ["personales"],
        "devolucion_reformulacion",
        "train",
        "Sistema que recomienda productos a clientes.",
        sponsor="El area de Marketing en su conjunto",
    ),
    _sol(
        "VAR-SOL-R10",
        "operativo",
        ["confidenciales"],
        "devolucion_reformulacion",
        "train",
        "Implementar una plataforma de IA generativa para documentos.",
        metricas="Implementacion exitosa de la plataforma",
    ),
    _sol(
        "VAR-SOL-R11",
        "negocio",
        ["personales"],
        "devolucion_reformulacion",
        "val",
        "Desplegar un LLM propio en atencion al cliente.",
        metricas="Despliegue en produccion",
    ),
    _sol(
        "VAR-SOL-R12",
        "operativo",
        ["operativos"],
        "devolucion_reformulacion",
        "val",
        "Sistema que mejora la calidad y agiliza el proceso de compras.",
        metricas="Mejorar calidad; agilizar el proceso",
    ),
    _sol(
        "VAR-SOL-R13",
        "operativo",
        ["confidenciales"],
        "devolucion_reformulacion",
        "val",
        "Sistema de analisis financiero.",
        sponsor="La direccion de Finanzas en general",
    ),
    _sol(
        "VAR-SOL-R14",
        "operativo",
        ["operativos"],
        "devolucion_reformulacion",
        "val",
        "Sistema que hace mas eficiente la logistica.",
        metricas="Hacer mas eficiente la operacion",
    ),
    _sol(
        "VAR-SOL-R15",
        "negocio",
        ["personales"],
        "devolucion_reformulacion",
        "val",
        "Instalar un chatbot con tecnologia de OpenAI.",
        metricas="Chatbot operativo en Q4",
    ),
    # devolucion_reformulacion -- ampliacion balanceada (4 train + 5 val + 10 test).
    # devolucion_no_ia ("no requiere IA") se RETIRO de solidez: no es criterio de
    # solidez del Marco; va a una etapa nueva (diferida, D-014). Idem "valor real".
    _sol(
        "VAR-SOL-R16",
        "operativo",
        ["operativos"],
        "devolucion_reformulacion",
        "train",
        "Adoptar Gemini para el area de operaciones.",
        metricas="Uso del modelo >= 80%",
    ),
    _sol(
        "VAR-SOL-R17",
        "negocio",
        ["personales"],
        "devolucion_reformulacion",
        "train",
        "Sistema que mejora la atencion y reduce costos.",
        metricas="Mejorar la atencion; reducir costos",
    ),
    _sol(
        "VAR-SOL-R18",
        "operativo",
        ["confidenciales"],
        "devolucion_reformulacion",
        "train",
        "Sistema que automatiza reportes de gestion.",
        sponsor="El comite de Direccion",
    ),
    _sol(
        "VAR-SOL-R19",
        "capacidad",
        ["ninguno"],
        "devolucion_reformulacion",
        "train",
        "Implementar RAG sobre los documentos del area.",
        metricas="Implementacion en Q2",
    ),
    _sol(
        "VAR-SOL-R20",
        "operativo",
        ["operativos"],
        "devolucion_reformulacion",
        "val",
        "Sistema que agiliza y mejora la gestion de proyectos.",
        metricas="Agilizar la gestion; mejorar el seguimiento",
    ),
    _sol(
        "VAR-SOL-R21",
        "operativo",
        ["confidenciales"],
        "devolucion_reformulacion",
        "val",
        "Sistema que clasifica documentos legales.",
        sponsor="El area Legal en su conjunto",
    ),
    _sol(
        "VAR-SOL-R22",
        "negocio",
        ["personales"],
        "devolucion_reformulacion",
        "val",
        "Desplegar un agente de IA en soporte tecnico.",
        metricas="Agente en produccion en Q3",
    ),
    _sol(
        "VAR-SOL-R23",
        "operativo",
        ["operativos"],
        "devolucion_reformulacion",
        "val",
        "Sistema que optimiza la experiencia del empleado.",
        metricas="Optimizar la experiencia del empleado",
    ),
    _sol(
        "VAR-SOL-R24",
        "operativo",
        ["operativos"],
        "devolucion_reformulacion",
        "val",
        "Sistema que prioriza tareas operativas.",
        sponsor="El equipo de Operaciones en general",
    ),
    _sol(
        "TST-SOL-R01",
        "negocio",
        ["personales"],
        "devolucion_reformulacion",
        "test",
        "Implementar Claude en el canal de ventas.",
        metricas="Adopcion >= 80%",
    ),
    _sol(
        "TST-SOL-R02",
        "operativo",
        ["operativos"],
        "devolucion_reformulacion",
        "test",
        "Sistema que mejora la productividad del equipo.",
        metricas="Mejorar la productividad",
    ),
    _sol(
        "TST-SOL-R03",
        "operativo",
        ["confidenciales"],
        "devolucion_reformulacion",
        "test",
        "Sistema que analiza la satisfaccion del cliente.",
        sponsor="El comite de Calidad",
    ),
    _sol(
        "TST-SOL-R04",
        "negocio",
        ["personales"],
        "devolucion_reformulacion",
        "test",
        "Adoptar una plataforma de IA generativa para marketing.",
        metricas="Plataforma operativa en Q4",
    ),
    _sol(
        "TST-SOL-R05",
        "operativo",
        ["operativos"],
        "devolucion_reformulacion",
        "test",
        "Sistema que hace mas eficiente el proceso de ventas.",
        metricas="Hacer mas eficiente el proceso",
    ),
    _sol(
        "TST-SOL-R06",
        "operativo",
        ["confidenciales"],
        "devolucion_reformulacion",
        "test",
        "Sistema que detecta riesgos operativos.",
        sponsor="La direccion de Riesgos en general",
    ),
    _sol(
        "TST-SOL-R07",
        "tecnico",
        ["operativos"],
        "devolucion_reformulacion",
        "test",
        "Desplegar un modelo de vision para control de calidad.",
        metricas="Modelo desplegado",
    ),
    _sol(
        "TST-SOL-R08",
        "operativo",
        ["operativos"],
        "devolucion_reformulacion",
        "test",
        "Sistema que mejora la toma de decisiones.",
        metricas="Mejorar la toma de decisiones",
    ),
    _sol(
        "TST-SOL-R09",
        "negocio",
        ["personales"],
        "devolucion_reformulacion",
        "test",
        "Sistema que automatiza la atencion de consultas.",
        sponsor="El area de Atencion en su conjunto",
    ),
    _sol(
        "TST-SOL-R10",
        "capacidad",
        ["ninguno"],
        "devolucion_reformulacion",
        "test",
        "Implementar un LLM open source en el area de datos.",
        metricas="Implementacion exitosa",
    ),
]


# ===========================================================================
# TRIAGE_FACTIBILIDAD: avanza_fast_gate / avanza_con_redisenio / no_avanza (3 clases del Marco)
# ===========================================================================
def _fac(cid, tipo, datos, label, split, decl, **kw):  # noqa: ANN001, ANN003
    return case(cid, tipo, datos, label, split, decl, **kw)


FACTIBILIDAD = [
    # avanza_fast_gate (8 train + 4 val): factible, plataforma homologada, revision humana
    _fac(
        "VAR-FAC-V01",
        "operativo",
        ["confidenciales"],
        "avanza_fast_gate",
        "train",
        "Sistema que resume reportes sobre plataforma interna homologada; la gerencia valida.",
        riesgo="Plataforma interna homologada; gerencia valida.",
    ),
    _fac(
        "VAR-FAC-V02",
        "negocio",
        ["personales"],
        "avanza_fast_gate",
        "train",
        "Recomendador que sugiere ofertas al representante en plataforma homologada; el representante decide.",
        impacto="Clientes via representante. Criticidad media.",
        riesgo="Plataforma homologada.",
        restr="Cumplimiento Ley 25.326; el representante decide.",
    ),
    _fac(
        "VAR-FAC-V03",
        "capacidad",
        ["ninguno"],
        "avanza_fast_gate",
        "train",
        "Asistente de minutas con modelo del catalogo corporativo; el autor valida.",
        riesgo="Modelo del catalogo; revision previa.",
    ),
    _fac(
        "VAR-FAC-V04",
        "operativo",
        ["operativos"],
        "avanza_fast_gate",
        "train",
        "Sistema que prioriza incidencias para el equipo tecnico; el equipo decide.",
        riesgo="Plataforma interna; el equipo decide.",
    ),
    _fac(
        "VAR-FAC-V05",
        "operativo",
        ["confidenciales"],
        "avanza_fast_gate",
        "train",
        "Analizador de clausulas con plataforma homologada; el abogado valida cada hallazgo.",
        impacto="Abogados como consumidores. Criticidad alta.",
        riesgo="Plataforma homologada.",
    ),
    _fac(
        "VAR-FAC-V06",
        "tecnico",
        ["operativos"],
        "avanza_fast_gate",
        "train",
        "Clasificador de logs sobre infraestructura interna homologada.",
        riesgo="Infraestructura interna homologada.",
    ),
    _fac(
        "VAR-FAC-V07",
        "operativo",
        ["confidenciales"],
        "avanza_fast_gate",
        "train",
        "Deteccion de anomalias de costos con plataforma interna; el analista valida.",
        riesgo="Plataforma interna homologada.",
    ),
    _fac(
        "VAR-FAC-V08",
        "negocio",
        ["personales"],
        "avanza_fast_gate",
        "train",
        "Resumen informativo del historial del cliente para el representante en CRM interno.",
        impacto="Representantes como usuarios; informativo. Criticidad media.",
        riesgo="CRM interno homologado.",
        restr="Cumplimiento Ley 25.326; el representante decide.",
    ),
    _fac(
        "VAR-FAC-V09",
        "operativo",
        ["operativos"],
        "avanza_fast_gate",
        "val",
        "Sistema que sugiere reposicion al comprador; el comprador decide.",
        riesgo="Plataforma interna; el comprador decide.",
    ),
    _fac(
        "VAR-FAC-V10",
        "capacidad",
        ["ninguno"],
        "avanza_fast_gate",
        "val",
        "Asistente SQL con modelo del catalogo; el analista revisa.",
        riesgo="Modelo del catalogo.",
    ),
    _fac(
        "VAR-FAC-V11",
        "operativo",
        ["confidenciales"],
        "avanza_fast_gate",
        "val",
        "Resumen de actas internas con plataforma homologada; los participantes validan.",
        riesgo="Plataforma homologada.",
    ),
    _fac(
        "VAR-FAC-V12",
        "operativo",
        ["operativos"],
        "avanza_fast_gate",
        "val",
        "Monitoreo que alerta al equipo NOC; el equipo decide intervenir.",
        riesgo="Plataforma interna; el equipo decide.",
    ),
    # avanza_con_redisenio (8 train + 4 val): autonomia reducible con etapa de revision humana previa
    _fac(
        "VAR-FAC-D01",
        "operativo",
        ["personales"],
        "avanza_con_redisenio",
        "train",
        "Agente que actualiza automaticamente datos del cliente en dos sistemas sin revision previa, miles por ciclo.",
        impacto="Clientes cuyos datos cambian. Criticidad alta.",
        riesgo="Revision del log ex-post (posterior al efecto).",
        restr="Cumplimiento Ley 25.326; sin modificar datos financieros.",
    ),
    _fac(
        "VAR-FAC-D02",
        "negocio",
        ["personales"],
        "avanza_con_redisenio",
        "train",
        "Sistema que aplica descuentos a clientes automaticamente sin aprobacion previa.",
        impacto="Clientes con descuentos. Criticidad media.",
        restr="Cumplimiento Defensa del Consumidor.",
    ),
    _fac(
        "VAR-FAC-D03",
        "operativo",
        ["personales"],
        "avanza_con_redisenio",
        "train",
        "Agente que cierra tickets y notifica al cliente automaticamente sin revision por caso.",
        impacto="Clientes notificados. Criticidad media.",
    ),
    _fac(
        "VAR-FAC-D04",
        "operativo",
        ["confidenciales"],
        "avanza_con_redisenio",
        "train",
        "Sistema que publica reportes a un tablero externo automaticamente sin validacion previa.",
        impacto="Audiencia interna amplia. Criticidad media.",
    ),
    _fac(
        "VAR-FAC-D05",
        "negocio",
        ["personales"],
        "avanza_con_redisenio",
        "train",
        "Agente que ajusta limites de servicio del cliente de forma automatica sin revision por caso.",
        impacto="Clientes afectados. Criticidad alta.",
        restr="Cumplimiento regulatorio.",
    ),
    _fac(
        "VAR-FAC-D06",
        "operativo",
        ["personales"],
        "avanza_con_redisenio",
        "train",
        "Agente que reasigna casos entre equipos automaticamente y comunica al cliente sin revision.",
        impacto="Clientes con cambios. Criticidad media.",
    ),
    _fac(
        "VAR-FAC-D07",
        "operativo",
        ["operativos"],
        "avanza_con_redisenio",
        "train",
        "Agente que ejecuta reinicios de servicios productivos de forma autonoma ante alertas.",
        impacto="Continuidad del servicio. Criticidad alta.",
    ),
    _fac(
        "VAR-FAC-D08",
        "negocio",
        ["personales"],
        "avanza_con_redisenio",
        "train",
        "Sistema que aprueba reintegros menores y los ejecuta automaticamente sin revision por caso.",
        impacto="Clientes con reintegros. Criticidad media.",
    ),
    _fac(
        "VAR-FAC-D09",
        "operativo",
        ["personales"],
        "avanza_con_redisenio",
        "val",
        "Agente que actualiza la direccion del cliente en sistemas core de forma automatica sin validacion.",
        impacto="Clientes cuyos datos cambian. Criticidad alta.",
    ),
    _fac(
        "VAR-FAC-D10",
        "negocio",
        ["personales"],
        "avanza_con_redisenio",
        "val",
        "Sistema que aplica bonificaciones automaticas a la factura sin aprobacion previa.",
        impacto="Clientes con bonificaciones. Criticidad media.",
    ),
    _fac(
        "VAR-FAC-D11",
        "operativo",
        ["operativos"],
        "avanza_con_redisenio",
        "val",
        "Agente que modifica configuraciones de red de forma autonoma ante desvios.",
        impacto="Continuidad del servicio. Criticidad alta.",
    ),
    _fac(
        "VAR-FAC-D12",
        "operativo",
        ["personales"],
        "avanza_con_redisenio",
        "val",
        "Agente que envia comunicaciones no estandar a clientes generadas y enviadas sin revision por caso.",
        impacto="Clientes destinatarios. Criticidad media.",
    ),
    # no_avanza (7 train + 4 val): factibilidad insuficiente (proveedor unico fuera de jurisdiccion, etc.)
    _fac(
        "VAR-FAC-N01",
        "operativo",
        ["confidenciales"],
        "no_avanza",
        "train",
        "Agente que analiza expedientes confidenciales con el unico proveedor capaz, que procesa fuera de jurisdiccion.",
        impacto="Abogados como usuarios. Criticidad alta.",
        riesgo="Proveedor unico fuera de jurisdiccion sin opcion local; sin alternativa viable.",
        restr="Secreto profesional; prohibido transferir a jurisdicciones sin proteccion equivalente.",
    ),
    _fac(
        "VAR-FAC-N02",
        "negocio",
        ["personales"],
        "no_avanza",
        "train",
        "Sistema que requiere un proveedor externo sin homologacion posible en el plazo del proyecto.",
        riesgo="Unico proveedor no cumple los requisitos de seguridad en el plazo; sin alternativa.",
        restr="Cumplimiento BCRA; sin proveedor homologado disponible.",
    ),
    _fac(
        "VAR-FAC-N03",
        "operativo",
        ["personales"],
        "no_avanza",
        "train",
        "Sistema de salud que necesita datos sensibles en un proveedor que no garantiza residencia local.",
        riesgo="Proveedor fuera de jurisdiccion; sin opcion on-premise ni region local.",
        restr="Datos de salud; prohibida la transferencia internacional.",
    ),
    _fac(
        "VAR-FAC-N04",
        "operativo",
        ["confidenciales"],
        "no_avanza",
        "train",
        "Sistema que depende de una tecnologia experimental no disponible para produccion en el plazo.",
        riesgo="Tecnologia inmadura; no hay version productiva disponible.",
        restr="Plazo del proyecto no negociable.",
    ),
    _fac(
        "VAR-FAC-N05",
        "negocio",
        ["personales"],
        "no_avanza",
        "train",
        "Sistema que exige integrar un core legacy sin API y sin posibilidad de modificacion ahora.",
        riesgo="Integracion tecnicamente inviable con el core actual; sin alternativa en el plazo.",
        restr="Sin presupuesto para reemplazar el core.",
    ),
    _fac(
        "VAR-FAC-N06",
        "operativo",
        ["confidenciales"],
        "no_avanza",
        "train",
        "Sistema que necesita un volumen de datos curados que no existe ni puede generarse en el plazo.",
        riesgo="No hay datos de calidad suficientes; su generacion excede el plazo.",
        restr="Sin dataset disponible.",
    ),
    _fac(
        "VAR-FAC-N07",
        "negocio",
        ["personales"],
        "no_avanza",
        "train",
        "Sistema que requiere una certificacion regulatoria que no estara disponible en el horizonte del proyecto.",
        riesgo="Certificacion pendiente sin fecha; bloquea el despliegue.",
        restr="Cumplimiento obligatorio antes de produccion.",
    ),
    _fac(
        "VAR-FAC-N08",
        "operativo",
        ["confidenciales"],
        "no_avanza",
        "val",
        "Agente legal con el unico proveedor capaz fuera de jurisdiccion, sin alternativa local.",
        riesgo="Proveedor unico fuera de jurisdiccion; sin alternativa.",
        restr="Secreto profesional; prohibida la transferencia.",
    ),
    _fac(
        "VAR-FAC-N09",
        "negocio",
        ["personales"],
        "no_avanza",
        "val",
        "Scoring que depende de un bureau externo sin acuerdo de proteccion de datos vigente.",
        riesgo="Proveedor sin acuerdo de proteccion; sin alternativa en el plazo.",
        restr="Cumplimiento Ley 25.326.",
    ),
    _fac(
        "VAR-FAC-N10",
        "operativo",
        ["confidenciales"],
        "no_avanza",
        "val",
        "Sistema que requiere infraestructura GPU no disponible ni adquirible en el plazo del proyecto.",
        riesgo="Sin capacidad de computo disponible en el plazo.",
        restr="Presupuesto y plazo fijos.",
    ),
    _fac(
        "VAR-FAC-N11",
        "operativo",
        ["personales"],
        "no_avanza",
        "val",
        "Sistema que necesita consentimiento explicito de clientes que no puede recolectarse a tiempo.",
        riesgo="Sin base de consentimiento; recolectarlo excede el plazo.",
        restr="Cumplimiento Ley 25.326.",
    ),
    # ── Ampliacion balanceada (3 clases del Marco) ──────────────────────────
    # Objetivo: train 12 / val 8 / test 8 por clase (macro-F1 medible). Se elimino
    # rechazo_formal (admisibilidad §9.2 / dedup §7.4 -> etapa futura). Frontera D/N:
    # D = autonomo REVERSIBLE de impacto medio (un ajuste acotado basta);
    # N = (a) inviable tecnico o (b) riesgo no aceptable (autonomo IRREVERSIBLE de alto
    # impacto sobre personas, donde el ajuste no alcanza).
    #
    # avanza_fast_gate (nuevos: 4 train + 4 val + 8 test)
    _fac(
        "VAR-FAC-V13",
        "operativo",
        ["confidenciales"],
        "avanza_fast_gate",
        "train",
        "Clasificador que enruta tickets entrantes al equipo en plataforma homologada; el equipo decide.",
        riesgo="Plataforma interna homologada; el equipo decide.",
    ),
    _fac(
        "VAR-FAC-V14",
        "capacidad",
        ["ninguno"],
        "avanza_fast_gate",
        "train",
        "Busqueda semantica sobre documentacion interna homologada; el usuario consulta y decide.",
        riesgo="Plataforma homologada; sin decision automatica.",
    ),
    _fac(
        "VAR-FAC-V15",
        "negocio",
        ["personales"],
        "avanza_fast_gate",
        "train",
        "Asistente que redacta respuestas a consultas frecuentes; el agente edita y envia.",
        impacto="Clientes via agente. Criticidad media.",
        restr="Cumplimiento Ley 25.326; el agente envia.",
    ),
    _fac(
        "VAR-FAC-V16",
        "operativo",
        ["operativos"],
        "avanza_fast_gate",
        "train",
        "Extractor de datos de facturas a un borrador que el contador revisa antes de cargar.",
        riesgo="Plataforma interna; el contador valida.",
    ),
    _fac(
        "VAR-FAC-V17",
        "operativo",
        ["confidenciales"],
        "avanza_fast_gate",
        "val",
        "Resumen de llamadas para el supervisor en plataforma homologada; informativo.",
        riesgo="Plataforma homologada.",
    ),
    _fac(
        "VAR-FAC-V18",
        "capacidad",
        ["ninguno"],
        "avanza_fast_gate",
        "val",
        "Traductor interno de documentacion con modelo del catalogo; el autor valida.",
        riesgo="Modelo del catalogo; revision previa.",
    ),
    _fac(
        "VAR-FAC-V19",
        "negocio",
        ["personales"],
        "avanza_fast_gate",
        "val",
        "Resumen del historial del cliente para el representante en CRM interno homologado; informativo.",
        impacto="Representantes como usuarios. Criticidad media.",
        restr="Cumplimiento Ley 25.326; informativo.",
    ),
    _fac(
        "VAR-FAC-V20",
        "operativo",
        ["operativos"],
        "avanza_fast_gate",
        "val",
        "Deteccion de anomalias de inventario que alerta al equipo; el equipo decide intervenir.",
        riesgo="Plataforma interna; el equipo decide.",
    ),
    _fac(
        "TST-FAC-V01",
        "operativo",
        ["confidenciales"],
        "avanza_fast_gate",
        "test",
        "Transcripcion de reuniones para los participantes en plataforma homologada.",
        riesgo="Plataforma homologada.",
    ),
    _fac(
        "TST-FAC-V02",
        "capacidad",
        ["ninguno"],
        "avanza_fast_gate",
        "test",
        "Buscador de jurisprudencia interna para el abogado, que valida cada cita.",
        riesgo="Consulta asistiva; el abogado decide.",
    ),
    _fac(
        "TST-FAC-V03",
        "operativo",
        ["operativos"],
        "avanza_fast_gate",
        "test",
        "Clasificador de correos internos que los enruta al area; el area decide.",
        riesgo="Plataforma interna; el area decide.",
    ),
    _fac(
        "TST-FAC-V04",
        "capacidad",
        ["ninguno"],
        "avanza_fast_gate",
        "test",
        "Generador de tests unitarios sugeridos para el desarrollador, que revisa y acepta.",
        riesgo="Modelo del catalogo; el dev revisa.",
    ),
    _fac(
        "TST-FAC-V05",
        "negocio",
        ["personales"],
        "avanza_fast_gate",
        "test",
        "Resumen de feedback de clientes para el equipo de producto; informativo.",
        impacto="Equipo de producto como usuario. Criticidad media.",
        restr="Cumplimiento Ley 25.326; informativo.",
    ),
    _fac(
        "TST-FAC-V06",
        "operativo",
        ["confidenciales"],
        "avanza_fast_gate",
        "test",
        "Asistente que indexa contratos para busqueda del abogado; consulta sin decision.",
        riesgo="Plataforma homologada; consulta.",
    ),
    _fac(
        "TST-FAC-V07",
        "capacidad",
        ["ninguno"],
        "avanza_fast_gate",
        "test",
        "Asistente de codigo con catalogo corporativo; el desarrollador acepta o descarta.",
        riesgo="Modelo del catalogo; el dev decide.",
    ),
    _fac(
        "TST-FAC-V08",
        "operativo",
        ["operativos"],
        "avanza_fast_gate",
        "test",
        "Priorizador de alertas de monitoreo para el NOC; el NOC decide la intervencion.",
        riesgo="Plataforma interna; el NOC decide.",
    ),
    # avanza_con_redisenio (nuevos: 4 train + 4 val + 8 test) -- autonomo REVERSIBLE,
    # impacto medio; agregar un control acotado basta.
    _fac(
        "VAR-FAC-D13",
        "operativo",
        ["personales"],
        "avanza_con_redisenio",
        "train",
        "Agente que cancela suscripciones de clientes automaticamente sin revision por caso.",
        impacto="Clientes con suscripcion. Criticidad media; reversible.",
    ),
    _fac(
        "VAR-FAC-D14",
        "negocio",
        ["personales"],
        "avanza_con_redisenio",
        "train",
        "Sistema que aplica recargos por mora a la factura de forma automatica sin revision.",
        impacto="Clientes facturados. Criticidad media; reversible.",
        restr="Cumplimiento Defensa del Consumidor.",
    ),
    _fac(
        "VAR-FAC-D15",
        "operativo",
        ["operativos"],
        "avanza_con_redisenio",
        "train",
        "Agente que reprograma entregas y notifica al cliente sin validacion previa.",
        impacto="Clientes con entregas. Criticidad media; reversible.",
    ),
    _fac(
        "VAR-FAC-D16",
        "negocio",
        ["personales"],
        "avanza_con_redisenio",
        "train",
        "Sistema que actualiza el segmento comercial del cliente y dispara campanias sin revision.",
        impacto="Clientes segmentados. Criticidad media; reversible.",
        restr="Cumplimiento Ley 25.326.",
    ),
    _fac(
        "VAR-FAC-D17",
        "operativo",
        ["personales"],
        "avanza_con_redisenio",
        "val",
        "Agente que actualiza la direccion del cliente en el CRM de forma automatica sin validacion.",
        impacto="Clientes cuyos datos cambian. Criticidad media; reversible.",
    ),
    _fac(
        "VAR-FAC-D18",
        "negocio",
        ["personales"],
        "avanza_con_redisenio",
        "val",
        "Sistema que aprueba devoluciones menores y emite el reembolso sin revision por caso.",
        impacto="Clientes con devoluciones. Criticidad media; reversible.",
    ),
    _fac(
        "VAR-FAC-D19",
        "operativo",
        ["operativos"],
        "avanza_con_redisenio",
        "val",
        "Agente que escala incidentes a proveedores externos de forma automatica sin acotar alcance.",
        impacto="Continuidad operativa. Criticidad media; reversible.",
    ),
    _fac(
        "VAR-FAC-D20",
        "negocio",
        ["personales"],
        "avanza_con_redisenio",
        "val",
        "Sistema que aplica bonificaciones a la factura del cliente sin aprobacion previa.",
        impacto="Clientes con bonificaciones. Criticidad media; reversible.",
    ),
    _fac(
        "TST-FAC-D01",
        "operativo",
        ["personales"],
        "avanza_con_redisenio",
        "test",
        "Agente que reasigna turnos de clientes y los notifica sin revision por caso.",
        impacto="Clientes con turnos. Criticidad media; reversible.",
    ),
    _fac(
        "TST-FAC-D02",
        "negocio",
        ["personales"],
        "avanza_con_redisenio",
        "test",
        "Sistema que ajusta el limite de descuento del vendedor de forma automatica sin aprobacion.",
        impacto="Operacion comercial. Criticidad media; reversible.",
    ),
    _fac(
        "TST-FAC-D03",
        "operativo",
        ["operativos"],
        "avanza_con_redisenio",
        "test",
        "Agente que reinicia servicios productivos ante alertas de forma autonoma sin revision.",
        impacto="Continuidad del servicio. Criticidad media; reversible.",
    ),
    _fac(
        "TST-FAC-D04",
        "negocio",
        ["personales"],
        "avanza_con_redisenio",
        "test",
        "Sistema que envia recordatorios de cobranza personalizados al cliente sin revision.",
        impacto="Clientes contactados. Criticidad media; reversible.",
        restr="Cumplimiento Ley 25.326.",
    ),
    _fac(
        "TST-FAC-D05",
        "operativo",
        ["personales"],
        "avanza_con_redisenio",
        "test",
        "Agente que cierra reclamos y responde al cliente automaticamente sin revision por caso.",
        impacto="Clientes con reclamos. Criticidad media; reversible.",
    ),
    _fac(
        "TST-FAC-D06",
        "operativo",
        ["operativos"],
        "avanza_con_redisenio",
        "test",
        "Agente que modifica reglas de ruteo de red ante desvios de forma autonoma sin revision.",
        impacto="Continuidad operativa. Criticidad media; reversible.",
    ),
    _fac(
        "TST-FAC-D07",
        "negocio",
        ["personales"],
        "avanza_con_redisenio",
        "test",
        "Sistema que actualiza datos de contacto del cliente en sistemas internos sin validacion.",
        impacto="Clientes cuyos datos cambian. Criticidad media; reversible.",
        restr="Cumplimiento Ley 25.326.",
    ),
    _fac(
        "TST-FAC-D08",
        "operativo",
        ["operativos"],
        "avanza_con_redisenio",
        "test",
        "Agente que publica reportes a un tablero externo de forma automatica sin validacion previa.",
        impacto="Audiencia interna amplia. Criticidad media; reversible.",
    ),
    # no_avanza (nuevos: 5 train + 4 val + 8 test) -- (a) inviable tecnico /
    # (b) riesgo no aceptable: autonomo IRREVERSIBLE de alto impacto sobre personas.
    _fac(
        "VAR-FAC-N12",
        "operativo",
        ["personales"],
        "no_avanza",
        "train",
        "Agente que ejecuta la baja laboral del empleado por score de desempenio sin intervencion.",
        impacto="Empleados. Criticidad muy alta; irreversible.",
        riesgo="Autonomia total sobre decision irreversible de alto impacto; el ajuste no alcanza.",
    ),
    _fac(
        "VAR-FAC-N13",
        "operativo",
        ["personales"],
        "no_avanza",
        "train",
        "Agente que corta el servicio esencial al cliente por mora de forma autonoma sin revision.",
        impacto="Clientes; perdida de acceso a servicio esencial. Irreversible.",
        riesgo="Autonomia sobre denegacion de servicio esencial; riesgo no aceptable.",
    ),
    _fac(
        "VAR-FAC-N14",
        "operativo",
        ["confidenciales"],
        "no_avanza",
        "train",
        "Sistema que requiere un modelo on-premise que el unico proveedor no ofrece; la nube esta vetada.",
        riesgo="Sin alternativa tecnica viable en el plazo.",
        restr="Prohibido procesar fuera de la organizacion; sin opcion on-premise.",
    ),
    _fac(
        "VAR-FAC-N15",
        "negocio",
        ["personales"],
        "no_avanza",
        "train",
        "Scoring que depende de un bureau externo sin acuerdo de proteccion de datos vigente ni alternativa.",
        riesgo="Proveedor sin acuerdo; sin alternativa en el plazo.",
        restr="Cumplimiento Ley 25.326.",
    ),
    _fac(
        "VAR-FAC-N16",
        "negocio",
        ["personales"],
        "no_avanza",
        "train",
        "Agente que ejecuta cambios vinculantes en contratos de clientes de forma autonoma sin revision.",
        impacto="Clientes con contratos. Criticidad muy alta; irreversible.",
        riesgo="Autonomia sobre decision contractual vinculante; riesgo no aceptable.",
    ),
    _fac(
        "VAR-FAC-N17",
        "operativo",
        ["confidenciales"],
        "no_avanza",
        "val",
        "Sistema que necesita un volumen de datos curados que no existe ni puede generarse en el plazo.",
        riesgo="Sin datos de calidad suficientes; su generacion excede el plazo.",
        restr="Sin dataset disponible.",
    ),
    _fac(
        "VAR-FAC-N18",
        "negocio",
        ["personales"],
        "no_avanza",
        "val",
        "Sistema que aprueba y desembolsa creditos de forma autonoma sin revision humana.",
        impacto="Solicitantes de credito. Criticidad muy alta; irreversible.",
        riesgo="Autonomia sobre decision financiera vinculante; riesgo no aceptable.",
        restr="Cumplimiento BCRA.",
    ),
    _fac(
        "VAR-FAC-N19",
        "operativo",
        ["operativos"],
        "no_avanza",
        "val",
        "Sistema que requiere infraestructura GPU no disponible ni adquirible en el plazo del proyecto.",
        riesgo="Sin capacidad de computo disponible en el plazo.",
        restr="Presupuesto y plazo fijos.",
    ),
    _fac(
        "VAR-FAC-N20",
        "operativo",
        ["personales"],
        "no_avanza",
        "val",
        "Agente que ejecuta retenciones sobre cuentas de clientes de forma autonoma sin revision.",
        impacto="Clientes; fondos retenidos. Criticidad muy alta; irreversible.",
        riesgo="Autonomia sobre accion financiera irreversible; riesgo no aceptable.",
    ),
    _fac(
        "TST-FAC-N01",
        "operativo",
        ["confidenciales"],
        "no_avanza",
        "test",
        "Sistema que depende de un proveedor cloud sin region local; los datos no pueden salir del pais.",
        riesgo="Sin region local ni alternativa on-premise.",
        restr="Prohibida la transferencia internacional.",
    ),
    _fac(
        "TST-FAC-N02",
        "operativo",
        ["personales"],
        "no_avanza",
        "test",
        "Agente que deniega el alta de un servicio esencial al cliente de forma autonoma sin revision.",
        impacto="Clientes; sin acceso a servicio esencial. Irreversible.",
        riesgo="Autonomia sobre denegacion de servicio esencial; riesgo no aceptable.",
    ),
    _fac(
        "TST-FAC-N03",
        "negocio",
        ["personales"],
        "no_avanza",
        "test",
        "Sistema que requiere una certificacion regulatoria que no estara disponible en el horizonte del proyecto.",
        riesgo="Certificacion pendiente sin fecha; bloquea el despliegue.",
        restr="Cumplimiento obligatorio antes de produccion.",
    ),
    _fac(
        "TST-FAC-N04",
        "operativo",
        ["personales"],
        "no_avanza",
        "test",
        "Agente que ejecuta sanciones disciplinarias a empleados de forma autonoma sin intervencion.",
        impacto="Empleados sancionados. Criticidad alta; irreversible.",
        riesgo="Autonomia sobre decision disciplinaria irreversible; riesgo no aceptable.",
    ),
    _fac(
        "TST-FAC-N05",
        "operativo",
        ["operativos"],
        "no_avanza",
        "test",
        "Sistema que depende de una tecnologia experimental sin version productiva disponible en el plazo.",
        riesgo="Tecnologia inmadura; no hay version productiva.",
        restr="Plazo del proyecto no negociable.",
    ),
    _fac(
        "TST-FAC-N06",
        "negocio",
        ["personales"],
        "no_avanza",
        "test",
        "Sistema que cancela polizas de seguro de clientes de forma autonoma sin revision.",
        impacto="Asegurados; perdida de cobertura. Irreversible.",
        riesgo="Autonomia sobre denegacion de cobertura esencial; riesgo no aceptable.",
        restr="Cumplimiento Superintendencia de Seguros.",
    ),
    _fac(
        "TST-FAC-N07",
        "operativo",
        ["confidenciales"],
        "no_avanza",
        "test",
        "Sistema que exige integrar un core legacy sin API y sin posibilidad de modificacion ahora.",
        riesgo="Integracion inviable con el core actual en el plazo.",
        restr="Sin presupuesto para reemplazar el core.",
    ),
    _fac(
        "TST-FAC-N08",
        "negocio",
        ["personales"],
        "no_avanza",
        "test",
        "Agente que ejecuta el cierre de cuentas bancarias de clientes de forma autonoma sin revision.",
        impacto="Clientes; cuenta cerrada. Criticidad muy alta; irreversible.",
        riesgo="Autonomia sobre decision financiera irreversible; riesgo no aceptable.",
        restr="Cumplimiento BCRA.",
    ),
]


# ===========================================================================
# FAST_GATE: Verde / Amarillo / Rojo / Negro
# ===========================================================================
def _fg(cid, tipo, datos, label, split, decl, **kw):  # noqa: ANN001, ANN003
    return case(cid, tipo, datos, label, split, decl, **kw)


FAST_GATE = [
    # Verde (8 train + 4 val): sin datos sensibles o solo operativos; informativo; revision humana; catalogo interno
    _fg(
        "VAR-FG-V01",
        "capacidad",
        ["ninguno"],
        "Verde",
        "train",
        "Asistente que genera borradores de minutas internas; el autor revisa antes de compartir.",
        impacto="Empleados como usuarios; no decide sobre personas. Criticidad baja.",
    ),
    _fg(
        "VAR-FG-V02",
        "operativo",
        ["operativos"],
        "Verde",
        "train",
        "Sistema que alerta al equipo tecnico ante desvios de metricas de infraestructura; el equipo decide.",
        impacto="Equipo tecnico como destinatario. Criticidad baja para personas.",
        restr="Alertas no automaticas sobre la red.",
    ),
    _fg(
        "VAR-FG-V03",
        "operativo",
        ["ninguno"],
        "Verde",
        "train",
        "Sistema que ordena correos internos por tema; el empleado decide que hacer.",
        impacto="Empleados como usuarios. Criticidad baja.",
    ),
    _fg(
        "VAR-FG-V04",
        "capacidad",
        ["ninguno"],
        "Verde",
        "train",
        "Asistente que sugiere cursos del catalogo interno al empleado; el empleado decide libremente.",
        impacto="Empleados; la decision es del empleado; sin impacto en desempeno. Criticidad baja.",
    ),
    _fg(
        "VAR-FG-V05",
        "operativo",
        ["operativos"],
        "Verde",
        "train",
        "Sistema que resume metricas operativas no sensibles para el equipo; la gerencia valida.",
        impacto="Gerentes como consumidores; no decide sobre personas. Criticidad baja.",
    ),
    _fg(
        "VAR-FG-V06",
        "capacidad",
        ["ninguno"],
        "Verde",
        "train",
        "Asistente que propone respuestas a tickets internos; el agente revisa antes de enviar.",
        impacto="Empleados como usuarios. Criticidad baja.",
    ),
    _fg(
        "VAR-FG-V07",
        "operativo",
        ["ninguno"],
        "Verde",
        "train",
        "Generador de borradores de documentacion interna a partir de notas; el autor aprueba.",
        impacto="Empleados como usuarios. Criticidad baja.",
    ),
    _fg(
        "VAR-FG-V08",
        "tecnico",
        ["operativos"],
        "Verde",
        "train",
        "Pipeline que clasifica logs tecnicos para el equipo de plataforma.",
        impacto="Equipo tecnico. Criticidad baja para personas.",
    ),
    _fg(
        "VAR-FG-V09",
        "capacidad",
        ["ninguno"],
        "Verde",
        "val",
        "Asistente que resume papers para el equipo de investigacion; ellos validan.",
        impacto="Empleados como usuarios. Criticidad baja.",
    ),
    _fg(
        "VAR-FG-V10",
        "operativo",
        ["operativos"],
        "Verde",
        "val",
        "Sistema que sugiere reposicion de stock al comprador; el comprador decide.",
        impacto="Empleados como usuarios. Criticidad baja.",
    ),
    _fg(
        "VAR-FG-V11",
        "operativo",
        ["ninguno"],
        "Verde",
        "val",
        "Asistente que traduce documentacion interna no sensible; el autor revisa.",
        impacto="Empleados como usuarios. Criticidad baja.",
    ),
    _fg(
        "VAR-FG-V12",
        "operativo",
        ["operativos"],
        "Verde",
        "val",
        "Tablero que resume indicadores operativos para gerentes; ninguna decision sobre personas depende del output.",
        impacto="Gerentes como consumidores. Criticidad baja.",
    ),
    # Amarillo (8 train + 4 val): datos personales/confidenciales + un factor mas (externo por homologar o reputacional), con revision humana
    _fg(
        "VAR-FG-A01",
        "capacidad",
        ["confidenciales"],
        "Amarillo",
        "train",
        "Asistente que resume actas internas usando un LLM externo que sera homologado; los participantes validan.",
        impacto="Empleados como usuarios. Criticidad baja.",
        riesgo="El LLM externo sera homologado antes del despliegue.",
        restr="Revision previa; cumplimiento Ley 25.326.",
    ),
    _fg(
        "VAR-FG-A02",
        "operativo",
        ["confidenciales"],
        "Amarillo",
        "train",
        "Sistema que genera contenido para canales publicos; el responsable aprueba antes de publicar.",
        impacto="Canal de salida publico; un error afecta la imagen. Criticidad alta.",
        restr="Normativa de defensa del consumidor sobre publicidad; revision previa.",
    ),
    _fg(
        "VAR-FG-A03",
        "negocio",
        ["personales"],
        "Amarillo",
        "train",
        "Recomendador de upgrade que el representante presenta; el representante decide.",
        impacto="Clientes via representante; el sistema condiciona la oferta. Criticidad media.",
        restr="Cumplimiento Ley 25.326 y Defensa del Consumidor; el representante decide.",
    ),
    _fg(
        "VAR-FG-A04",
        "operativo",
        ["confidenciales"],
        "Amarillo",
        "train",
        "Analizador de clausulas de contratos de clientes; el abogado valida cada hallazgo.",
        impacto="El analisis condiciona acciones legales sobre clientes. Criticidad alta.",
        restr="Confidencialidad contractual; el abogado valida.",
    ),
    _fg(
        "VAR-FG-A05",
        "capacidad",
        ["personales"],
        "Amarillo",
        "train",
        "Resumidor de reuniones con lista de participantes usando un LLM externo por homologar; validan los participantes.",
        impacto="Empleados como usuarios. Criticidad baja.",
        riesgo="El LLM externo sera homologado.",
        restr="Revision previa; cumplimiento Ley 25.326.",
    ),
    _fg(
        "VAR-FG-A06",
        "negocio",
        ["personales"],
        "Amarillo",
        "train",
        "Agente que envia comunicaciones de bienvenida predefinidas al cliente; contenido aprobado.",
        impacto="Clientes que reciben comunicaciones. Criticidad media.",
        restr="Cumplimiento Ley 26.951 No Llame y Ley 25.326; plantillas aprobadas.",
    ),
    _fg(
        "VAR-FG-A07",
        "operativo",
        ["confidenciales"],
        "Amarillo",
        "train",
        "Generador de comunicados para redes sociales corporativas; el responsable aprueba.",
        impacto="Audiencia externa publica; error afecta imagen. Criticidad alta.",
        restr="Normativa de defensa del consumidor; revision previa.",
    ),
    _fg(
        "VAR-FG-A08",
        "negocio",
        ["personales"],
        "Amarillo",
        "train",
        "Chatbot que propone soluciones estandar pre-aprobadas a reclamos; escala casos complejos a humano.",
        impacto="Clientes que interactuan; propone compensaciones. Criticidad alta.",
        restr="Defensa del Consumidor y ENACOM; escalada obligatoria.",
    ),
    _fg(
        "VAR-FG-A09",
        "capacidad",
        ["confidenciales"],
        "Amarillo",
        "val",
        "Asistente que resume documentos internos usando un LLM externo por homologar; el autor valida.",
        riesgo="El LLM externo sera homologado.",
        restr="Revision previa.",
    ),
    _fg(
        "VAR-FG-A10",
        "negocio",
        ["personales"],
        "Amarillo",
        "val",
        "Recomendador de productos que el representante presenta al cliente; el representante decide.",
        impacto="Clientes via representante. Criticidad media.",
        restr="Cumplimiento Ley 25.326; el representante decide.",
    ),
    _fg(
        "VAR-FG-A11",
        "operativo",
        ["confidenciales"],
        "Amarillo",
        "val",
        "Generador de contenido para el blog publico de la empresa; el responsable aprueba.",
        impacto="Audiencia externa. Criticidad alta.",
        restr="Defensa del consumidor; revision previa.",
    ),
    _fg(
        "VAR-FG-A12",
        "negocio",
        ["personales"],
        "Amarillo",
        "val",
        "Analizador de cumplimiento de contratos de clientes; el equipo legal valida.",
        impacto="Condiciona acciones sobre clientes. Criticidad alta.",
        restr="Confidencialidad; el abogado valida.",
    ),
    # Rojo (7 train + 4 val): personal + influye en decision + proveedor externo por homologar + legal, con revision humana
    _fg(
        "VAR-FG-R01",
        "negocio",
        ["personales"],
        "Rojo",
        "train",
        "Chatbot que accede a datos del cliente y responde en tiempo real con un LLM externo por homologar; escala a humano.",
        impacto="Clientes que interactuan; las respuestas influyen en sus decisiones. Criticidad alta.",
        riesgo="El LLM externo sera homologado antes del lanzamiento.",
        restr="Cumplimiento Ley 25.326; evaluacion de seguridad del proveedor pendiente.",
    ),
    _fg(
        "VAR-FG-R02",
        "negocio",
        ["personales"],
        "Rojo",
        "train",
        "Scoring crediticio con API externa por homologar; el analista registra la decision.",
        impacto="Clientes solicitantes; el score determina el acceso. Criticidad muy alta.",
        riesgo="La API externa sera homologada antes de produccion.",
        restr="Cumplimiento BCRA y Ley 25.326; prohibido sesgo discriminatorio.",
    ),
    _fg(
        "VAR-FG-R03",
        "negocio",
        ["personales"],
        "Rojo",
        "train",
        "Asistente de diagnostico que sugiere al medico con un modelo externo por homologar; el medico decide.",
        impacto="Pacientes; el sistema influye en el diagnostico. Criticidad muy alta.",
        riesgo="Modelo externo por homologar.",
        restr="Datos de salud; cumplimiento regulatorio; el medico decide.",
    ),
    _fg(
        "VAR-FG-R04",
        "negocio",
        ["personales"],
        "Rojo",
        "train",
        "Agente de reclamos que aplica automaticamente compensaciones acotadas al catalogo "
        "aprobado por policy; escala a un agente humano solo si el reclamo no encaja en el catalogo.",
        impacto="Clientes con reclamos resueltos dentro del catalogo aprobado. Criticidad alta.",
        riesgo="Accion autonoma acotada a un catalogo de resoluciones predefinido y aprobado.",
        restr="Cumplimiento Defensa del Consumidor; resoluciones limitadas al catalogo.",
    ),
    _fg(
        "VAR-FG-R05",
        "negocio",
        ["personales"],
        "Rojo",
        "train",
        "Motor de recomendacion de inversiones que asesora al cliente via asesor, con LLM externo por homologar.",
        impacto="Clientes; influye en decisiones financieras. Criticidad muy alta.",
        riesgo="LLM externo por homologar.",
        restr="Cumplimiento CNV y Ley 25.326; el asesor decide.",
    ),
    _fg(
        "VAR-FG-R06",
        "negocio",
        ["personales"],
        "Rojo",
        "train",
        "Chatbot legal que orienta al cliente con un modelo externo por homologar; el abogado revisa.",
        impacto="Clientes; influye en decisiones legales. Criticidad alta.",
        riesgo="Modelo externo por homologar.",
        restr="Secreto profesional; el abogado revisa.",
    ),
    _fg(
        "VAR-FG-R07",
        "negocio",
        ["personales"],
        "Rojo",
        "train",
        "Sistema que ajusta automaticamente el limite de credito de clientes dentro de bandas "
        "de politica vigente, sin discrecionalidad fuera de ellas; log mensual revisable por "
        "el equipo de credito dentro de las 48 horas.",
        impacto="Clientes pospago cuyos limites se ajustan dentro de bandas aprobadas. Criticidad alta.",
        riesgo="Ajuste autonomo acotado a bandas predefinidas, con revision sistematica del log dentro de 48hs.",
        restr="Cumplimiento BCRA; ajuste dentro de parametros de politica.",
    ),
    _fg(
        "VAR-FG-R08",
        "negocio",
        ["personales"],
        "Rojo",
        "val",
        "Chatbot de autoatencion con datos del cliente y LLM externo por homologar; escala a humano.",
        impacto="Clientes; influye en decisiones sobre su plan. Criticidad alta.",
        riesgo="LLM externo por homologar.",
        restr="Cumplimiento Ley 25.326; seguridad del proveedor pendiente.",
    ),
    _fg(
        "VAR-FG-R09",
        "negocio",
        ["personales"],
        "Rojo",
        "val",
        "Evaluador de siniestros que recomienda al liquidador con proveedor externo por homologar; el liquidador decide.",
        impacto="Clientes; condiciona la cobertura. Criticidad alta.",
        riesgo="Proveedor externo por homologar.",
        restr="Cumplimiento regulatorio; el liquidador decide.",
    ),
    _fg(
        "VAR-FG-R10",
        "negocio",
        ["personales"],
        "Rojo",
        "val",
        "Asistente de cobranzas que define la estrategia hacia el cliente con LLM externo por homologar; el gestor decide.",
        impacto="Clientes con deuda; influye en la gestion. Criticidad alta.",
        riesgo="LLM externo por homologar.",
        restr="Cumplimiento Defensa del Consumidor; el gestor decide.",
    ),
    _fg(
        "VAR-FG-R11",
        "operativo",
        ["personales"],
        "Rojo",
        "val",
        "Agente que ejecuta automaticamente el alta de un nuevo cliente en el CRM y "
        "facturacion al verificar los criterios de elegibilidad, sin intervencion del "
        "operador; confirma el alta al cliente por email.",
        impacto="Nuevos clientes que solicitan el alta del servicio. Criticidad alta.",
        riesgo="Alta autonoma sin revision previa por caso, pero es una accion favorable "
        "solicitada por el propio cliente.",
        restr="Cumplimiento Ley 25.326; alta dentro de los criterios de elegibilidad estandar.",
    ),
    # Negro (7 train + 4 val): ejecuta acciones de alto impacto sin revision humana previa por caso
    _fg(
        "VAR-FG-N01",
        "negocio",
        ["personales"],
        "Negro",
        "train",
        "Agente que ajusta automaticamente precios y descuentos de planes para mas del 10% "
        "de la base de clientes activos, segun parametros de mercado en tiempo real, sin "
        "bandas ni catalogo acotado.",
        impacto="Mas del 10% de la base de clientes activos. Criticidad muy alta.",
        riesgo="Ajuste autonomo sin bandas ni catalogo predefinido, aplicado a escala sobre la base.",
        restr="Cumplimiento regulatorio de comunicaciones comerciales y proteccion de datos.",
    ),
    _fg(
        "VAR-FG-N02",
        "operativo",
        ["personales"],
        "Negro",
        "train",
        "Agente que ejecuta cortes de servicio a clientes de forma autonoma segun un score "
        "de riesgo, sin aprobacion ni revision sistematica posterior; el corte no es "
        "reversible automaticamente.",
        impacto="Clientes cortados; perdida de acceso al servicio. Criticidad muy alta.",
        riesgo="Corte de servicio (denegacion de acceso) autonomo, sin revision sistematica "
        "ni mecanismo de reversion.",
        restr="Cumplimiento Ley de Defensa del Consumidor y ENACOM.",
    ),
    _fg(
        "VAR-FG-N03",
        "negocio",
        ["personales"],
        "Negro",
        "train",
        "Sistema que aprueba y ejecuta reintegros a clientes automaticamente sin revision por caso.",
        impacto="Clientes con reintegros. Criticidad alta.",
        riesgo="Ejecuta sin aprobacion previa por caso.",
        restr="Cumplimiento Defensa del Consumidor.",
    ),
    _fg(
        "VAR-FG-N04",
        "operativo",
        ["personales"],
        "Negro",
        "train",
        "Agente que bloquea cuentas de clientes de forma autonoma ante senales de riesgo, sin revision previa.",
        impacto="Clientes bloqueados. Criticidad muy alta.",
        riesgo="Bloqueo autonomo sin revision por caso.",
        restr="Cumplimiento BCRA.",
    ),
    _fg(
        "VAR-FG-N05",
        "negocio",
        ["personales"],
        "Negro",
        "train",
        "Sistema que evalua el perfil de riesgo crediticio de cada cliente en tiempo real y "
        "aprueba o rechaza la solicitud de credito de forma automatica, notificando el "
        "resultado sin intervencion humana.",
        impacto="Clientes solicitantes; el sistema decide el acceso al credito en base a su "
        "perfil de riesgo. Criticidad muy alta.",
        riesgo="Decision financiera (otorga o deniega acceso al credito) basada en "
        "perfilamiento automatizado, sin revision humana.",
        restr="Cumplimiento BCRA y Ley 25.326.",
    ),
    _fg(
        "VAR-FG-N06",
        "operativo",
        ["personales"],
        "Negro",
        "train",
        "Agente que detecta incumplimientos contractuales de clientes corporativos y "
        "ejecuta automaticamente la terminacion del contrato al superar el umbral "
        "definido, sin intervencion humana previa; la terminacion es irreversible.",
        impacto="Clientes corporativos con contrato terminado de forma permanente. Criticidad maxima.",
        riesgo="Terminacion de contrato irreversible sin intervencion manual posterior, "
        "ejecutada de forma autonoma.",
        restr="Cumplimiento Ley de Defensa del Consumidor; validacion legal de umbrales.",
    ),
    _fg(
        "VAR-FG-N07",
        "operativo",
        ["personales"],
        "Negro",
        "train",
        "Agente que perfila automaticamente el riesgo de abandono de cada cliente segun su "
        "comportamiento de consumo y ejecuta de forma autonoma ofertas de retencion "
        "vinculantes (descuentos contractuales) basadas en ese perfil, sin aprobacion por caso.",
        impacto="Clientes perfilados y con ofertas vinculantes aplicadas. Criticidad alta.",
        riesgo="Perfilamiento automatizado del comportamiento del cliente que dispara "
        "acciones vinculantes autonomas, sin revision.",
        restr="Cumplimiento Ley de Defensa del Consumidor y Ley 25.326.",
    ),
    _fg(
        "VAR-FG-N08",
        "operativo",
        ["personales"],
        "Negro",
        "val",
        "Agente que da de baja servicios de clientes automaticamente segun reglas de riesgo, sin revision previa.",
        impacto="Clientes dados de baja. Criticidad muy alta.",
        riesgo="Baja autonoma sin revision por caso.",
        restr="Cumplimiento regulatorio.",
    ),
    _fg(
        "VAR-FG-N09",
        "negocio",
        ["personales"],
        "Negro",
        "val",
        "Sistema que aplica penalidades a clientes y las ejecuta automaticamente sin intervencion humana.",
        impacto="Clientes penalizados. Criticidad alta.",
        riesgo="Penalidad autonoma sin revision.",
        restr="Cumplimiento Defensa del Consumidor.",
    ),
    _fg(
        "VAR-FG-N10",
        "operativo",
        ["personales"],
        "Negro",
        "val",
        "Agente que reasigna recursos criticos de produccion de forma autonoma con impacto en clientes, sin revision.",
        impacto="Clientes afectados por el servicio. Criticidad muy alta.",
        riesgo="Reasignacion autonoma de alto impacto sin revision previa.",
        restr="Cumplimiento regulatorio.",
    ),
    _fg(
        "VAR-FG-N11",
        "negocio",
        ["personales"],
        "Negro",
        "val",
        "Sistema que ejecuta ajustes de tarifa al cliente de forma automatica sin aprobacion por caso.",
        impacto="Clientes con cambios de tarifa. Criticidad alta.",
        riesgo="Ajuste autonomo sin revision previa.",
        restr="Cumplimiento Defensa del Consumidor y ENACOM.",
    ),
    # --- Bordes de conteo: cubren los valores de Si ausentes en train/val ---
    # Verde con 1 Si (Si=1): un solo factor activo, sin alto impacto.
    _fg(
        "VAR-FG-V13",
        "negocio",
        ["personales"],
        "Verde",
        "train",
        "Sistema que muestra al representante un resumen del historial de contactos del "
        "cliente antes de la llamada; es informativo y el representante decide como "
        "gestionar. Opera sobre el CRM interno homologado.",
        impacto="Representantes como usuarios; el resumen es informativo y no influye en "
        "decisiones sobre el cliente. Criticidad baja.",
        riesgo="CRM interno homologado; el representante decide cada interaccion.",
        restr="Cumplimiento Ley 25.326; sin proveedores externos; revision humana.",
    ),
    _fg(
        "VAR-FG-V14",
        "capacidad",
        ["ninguno"],
        "Verde",
        "train",
        "Asistente que resume papers tecnicos de acceso publico usando un LLM externo que "
        "sera homologado antes del despliegue; sin datos personales, es informativo y el "
        "investigador valida antes de usar el resumen.",
        impacto="Investigadores como usuarios; sin impacto sobre personas. Criticidad baja.",
        riesgo="El LLM externo sera homologado antes del despliegue; documentos publicos.",
        restr="Sin datos personales; revision humana previa.",
    ),
    _fg(
        "VAR-FG-V15",
        "operativo",
        ["personales"],
        "Verde",
        "val",
        "Sistema que arma para el propio empleado un resumen de su actividad a partir de "
        "sus datos personales, para autoconsulta; no alimenta evaluaciones ni decisiones.",
        impacto="El empleado consulta su propia actividad; no se usa en evaluaciones ni "
        "decisiones sobre personas. Criticidad baja.",
        riesgo="Uso interno informativo; sin proveedores externos.",
        restr="Cumplimiento Ley 25.326; sin impacto en desempeno.",
    ),
    # Amarillo con 2 Si (Si=2): dos factores, sin alto impacto, con revision humana.
    _fg(
        "VAR-FG-A13",
        "capacidad",
        ["personales"],
        "Amarillo",
        "train",
        "Asistente que resume documentos internos con datos personales de empleados usando "
        "un LLM externo aun por homologar; es informativo y el autor valida antes de usar.",
        impacto="Empleados como usuarios; informativo. Criticidad media.",
        riesgo="El LLM externo sera homologado antes del despliegue; revision humana.",
        restr="Cumplimiento Ley 25.326; el autor valida.",
    ),
    _fg(
        "VAR-FG-A14",
        "negocio",
        ["personales"],
        "Amarillo",
        "train",
        "Sistema que sugiere al representante una accion de retencion segun el consumo del "
        "cliente; el representante decide que ofrecer. Plataforma interna homologada.",
        impacto="Clientes via representante; el representante decide. Criticidad media.",
        riesgo="Plataforma interna homologada; el representante decide.",
        restr="Cumplimiento Ley 25.326 y Defensa del Consumidor; el representante decide.",
    ),
    _fg(
        "VAR-FG-A15",
        "operativo",
        ["personales"],
        "Amarillo",
        "val",
        "Sistema que analiza datos personales de clientes para generar un informe interno "
        "de calidad de servicio; un error podria exponer a la empresa a reclamos; el "
        "equipo valida el informe antes de actuar.",
        impacto="Clientes analizados de forma agregada; el equipo valida. Criticidad media.",
        riesgo="Riesgo reputacional si el informe es erroneo; revision humana previa.",
        restr="Cumplimiento Ley 25.326; sin proveedores externos.",
    ),
    # Rojo con 5 Si (Si=5): cumple las 5 preguntas pero acotado+reversible => alto=No
    # (el override Negro NO aplica porque alto_impacto=No).
    _fg(
        "VAR-FG-R12",
        "operativo",
        ["personales", "confidenciales"],
        "Rojo",
        "train",
        "Agente que clasifica reclamos con un LLM externo por homologar y aplica de forma "
        "autonoma compensaciones acotadas a un catalogo aprobado (creditos menores), "
        "cerrando el caso; escala a humano solo fuera del catalogo. El efecto es reversible "
        "por el equipo de atencion.",
        impacto="Clientes con reclamos; las compensaciones estan acotadas y son "
        "reversibles. Criticidad alta.",
        riesgo="El LLM externo sera homologado antes del despliegue; el efecto es "
        "reversible y acotado al catalogo aprobado.",
        restr="Compensaciones acotadas al catalogo aprobado; escalada a humano fuera de el; "
        "cumplimiento Defensa del Consumidor.",
    ),
    _fg(
        "VAR-FG-R13",
        "negocio",
        ["personales", "confidenciales"],
        "Rojo",
        "val",
        "Agente que ajusta automaticamente beneficios del cliente dentro de bandas "
        "aprobadas usando un servicio externo por homologar; influye en la relacion "
        "comercial; los ajustes son reversibles y hay revision sistematica del log.",
        impacto="Clientes con ajustes acotados a bandas y reversibles. Criticidad alta.",
        riesgo="Servicio externo por homologar; ajustes reversibles dentro de bandas con "
        "revision sistematica del log.",
        restr="Ajustes acotados a bandas aprobadas; cumplimiento Defensa del Consumidor.",
    ),
    # --- Romper la colinealidad alto_impacto <=> Negro: alto=Si pero NO Negro (P5=No) ---
    # Rojo con alto=Si y P5=No (Si=4): alto impacto por naturaleza/profiling, pero un
    # humano valida cada caso, por lo que el override Negro no aplica.
    _fg(
        "VAR-FG-R14",
        "negocio",
        ["personales"],
        "Rojo",
        "train",
        "Motor de scoring crediticio que perfila al cliente y condiciona el acceso al "
        "credito; usa una API externa de scoring por homologar; el analista valida y "
        "registra cada decision antes de aplicarla.",
        impacto="Clientes solicitantes; el score condiciona el acceso al credito y hay "
        "perfilamiento. Criticidad muy alta.",
        riesgo="La API externa sera homologada antes de produccion; el analista valida cada "
        "caso antes de ejecutar.",
        restr="Cumplimiento BCRA y Ley 25.326; el analista decide; sin variables discriminatorias.",
    ),
    _fg(
        "VAR-FG-R15",
        "negocio",
        ["personales"],
        "Rojo",
        "val",
        "Sistema que evalua solicitudes de un beneficio financiero perfilando al cliente "
        "con un modelo externo por homologar; un comite humano aprueba cada caso antes de "
        "otorgar el beneficio.",
        impacto="Clientes evaluados; decision financiera con perfilamiento. Criticidad alta.",
        riesgo="Modelo externo por homologar; el comite aprueba cada caso antes de actuar.",
        restr="Cumplimiento BCRA y Ley 25.326; revision humana por caso.",
    ),
    # Amarillo con alto=Si y P5=No (Si=2 y 3): profiling a escala => alto=Si, pero
    # framework interno, sin proveedor externo o riesgo legal y con decision humana.
    _fg(
        "VAR-FG-A16",
        "negocio",
        ["personales"],
        "Amarillo",
        "train",
        "Modelo predictivo de churn que perfila automaticamente a mas de 100.000 clientes y "
        "publica scores en el CRM; el equipo comercial decide autonomamente que accion "
        "tomar. Framework interno certificado; el sistema no actua sobre el cliente.",
        impacto="Mas de 100.000 clientes perfilados; el equipo comercial decide la accion. "
        "Criticidad media.",
        riesgo="Framework interno certificado; el equipo decide cada accion.",
        restr="Cumplimiento Ley 25.326; el sistema no actua sobre el cliente; sin "
        "discriminacion entre cohortes.",
    ),
    _fg(
        "VAR-FG-A17",
        "negocio",
        ["personales"],
        "Amarillo",
        "val",
        "Sistema que segmenta y perfila a mas del 10% de la base de clientes para campanias "
        "usando un LLM externo por homologar; el responsable de marketing decide cada "
        "campania.",
        impacto="Mas del 10% de la base perfilada; el responsable decide. Criticidad media.",
        riesgo="LLM externo por homologar; el responsable decide cada campania.",
        restr="Cumplimiento Ley 25.326; el responsable decide; sin discriminacion.",
    ),
    # --- Negro con conteo distinto de 4: que el override (P5=Si Y alto=Si) domine ---
    # Negro con Si=3 (normalmente Amarillo) que escala por el override.
    _fg(
        "VAR-FG-N12",
        "operativo",
        ["personales"],
        "Negro",
        "train",
        "Agente que cancela automaticamente beneficios a empleados con cuotas vencidas en "
        "un proceso nocturno sin revision por caso; RRHH recibe un reporte al dia "
        "siguiente. La cancelacion restringe el acceso del empleado al beneficio.",
        impacto="Empleados con beneficios cancelados; restriccion de acceso sin revision "
        "por caso. Criticidad alta.",
        riesgo="Ejecucion autonoma sin revision por caso; supervision solo ex-post.",
        restr="Cumplimiento normativa laboral y Ley 25.326; reporte ex-post a RRHH.",
    ),
    # Negro con Si=5 (la cota alta del conteo) + override.
    _fg(
        "VAR-FG-N13",
        "negocio",
        ["personales", "confidenciales"],
        "Negro",
        "val",
        "Pipeline que aprueba y ejecuta microcreditos de forma autonoma usando un LLM "
        "externo por homologar, sin intervencion humana por solicitud; la decision "
        "financiera es irreversible sin accion manual posterior.",
        impacto="Clientes solicitantes; decision financiera autonoma e irreversible. "
        "Criticidad maxima.",
        riesgo="LLM externo por homologar; ejecucion autonoma e irreversible sin revision "
        "por caso.",
        restr="Cumplimiento BCRA y Ley 25.065; el cliente puede pedir revision humana ex-post.",
    ),
    # =======================================================================
    # AMPLIACION VAL (casos borde, D-015): el val en techo no daba gradiente a
    # GEPA (best_idx=baseline 3/3). Se agregan 24 casos val concentrados en el
    # CUELLO (no en Verde facil): Rojo<->Negro por alto_impacto (P5=Si acotado y
    # reversible -> Rojo; P5=Si y alto -> Negro), colinealidad rota (alto=Si con
    # P5=No -> no Negro), transiciones de conteo 1<->2 y 3<->4, y override de
    # Negro con conteo bajo. Todos split=val. El test (30 TC-xx) NO se toca.
    # -- Borde Rojo<->Negro: P5=Si pero accion ACOTADA y REVERSIBLE => alto=No => Rojo.
    _fg(
        "VAR-FG-R16",
        "negocio",
        ["personales"],
        "Rojo",
        "val",
        "Agente que acredita automaticamente bonificaciones de fidelizacion a clientes "
        "acotadas a un catalogo de beneficios aprobado, sin aprobacion por caso; cada "
        "credito es reversible y queda en un log revisable.",
        impacto="Clientes con bonificaciones acotadas y reversibles. Criticidad alta.",
        riesgo="Accion autonoma acotada a un catalogo aprobado y reversible; revision del "
        "log ex-post.",
        restr="Cumplimiento Defensa del Consumidor; beneficios dentro del catalogo.",
    ),
    _fg(
        "VAR-FG-R17",
        "negocio",
        ["personales"],
        "Rojo",
        "val",
        "Asistente que ejecuta ajustes de plan dentro de bandas tarifarias aprobadas "
        "usando un LLM externo por homologar, sin aprobacion por caso; los ajustes son "
        "reversibles y se revisan por log.",
        impacto="Clientes con ajustes acotados a bandas y reversibles. Criticidad alta.",
        riesgo="LLM externo por homologar; ajuste autonomo acotado a bandas y reversible.",
        restr="Cumplimiento Defensa del Consumidor y ENACOM; ajustes dentro de banda.",
    ),
    _fg(
        "VAR-FG-R18",
        "operativo",
        ["personales"],
        "Rojo",
        "val",
        "Sistema que reprograma automaticamente turnos de clientes dentro de la grilla "
        "disponible sin aprobacion por caso; el cliente puede reagendar cuando quiera.",
        impacto="Clientes con turnos reprogramados de forma acotada y reversible. Criticidad alta.",
        riesgo="Reprogramacion autonoma acotada a la grilla y reversible por el cliente.",
        restr="Cumplimiento Defensa del Consumidor; el cliente puede reagendar.",
    ),
    _fg(
        "VAR-FG-R23",
        "negocio",
        ["personales"],
        "Rojo",
        "val",
        "Agente que ejecuta reembolsos a clientes acotados a un catalogo de montos "
        "aprobado usando un LLM externo por homologar, sin aprobacion por caso; cada "
        "reembolso es reversible y queda en un log revisable.",
        impacto="Clientes con reembolsos acotados y reversibles. Criticidad alta.",
        riesgo="LLM externo por homologar; ejecucion autonoma acotada a un catalogo y reversible.",
        restr="Cumplimiento Defensa del Consumidor; montos dentro del catalogo.",
    ),
    # -- Borde Rojo<->Negro: P5=Si y alto=Si => Negro, variando el criterio (a/b/c/d/e).
    _fg(
        "VAR-FG-N14",
        "operativo",
        ["personales"],
        "Negro",
        "val",
        "Agente que ejecuta automaticamente la suspension del servicio a clientes ante "
        "señales de riesgo, sin revision por caso; la suspension corta el acceso hasta "
        "una intervencion manual posterior.",
        impacto="Clientes suspendidos; corte de acceso al servicio. Criticidad muy alta.",
        riesgo="Corte de servicio (denegacion de acceso, criterio b) autonomo sin revision "
        "por caso.",
        restr="Cumplimiento Defensa del Consumidor y ENACOM.",
    ),
    _fg(
        "VAR-FG-N15",
        "operativo",
        ["personales"],
        "Negro",
        "val",
        "Sistema que ejecuta automaticamente la baja definitiva de cuentas inactivas y "
        "borra los datos asociados sin revision por caso; la baja es irreversible.",
        impacto="Clientes dados de baja con borrado irreversible de datos. Criticidad muy alta.",
        riesgo="Baja autonoma e irreversible (criterio c) sin intervencion manual posterior.",
        restr="Cumplimiento Ley 25.326; sin mecanismo de reversion.",
    ),
    _fg(
        "VAR-FG-N16",
        "negocio",
        ["personales"],
        "Negro",
        "val",
        "Agente que perfila automaticamente a mas del 10% de la base de clientes por su "
        "comportamiento y aplica ofertas vinculantes con un LLM externo por homologar, "
        "sin revision por caso.",
        impacto="Mas del 10% de la base perfilada con ofertas vinculantes aplicadas. "
        "Criticidad muy alta.",
        riesgo="LLM externo por homologar; profiling a escala (criterios a y e) con accion "
        "autonoma vinculante.",
        restr="Cumplimiento Ley 25.326 y Defensa del Consumidor.",
    ),
    _fg(
        "VAR-FG-N17",
        "negocio",
        ["personales"],
        "Negro",
        "val",
        "Sistema que aprueba y desembolsa automaticamente adelantos de efectivo a clientes "
        "segun un score, sin revision por caso; el desembolso no esta acotado a un tope "
        "predefinido.",
        impacto="Clientes con desembolsos financieros autonomos sin tope. Criticidad muy alta.",
        riesgo="Decision financiera no acotada (criterio b) ejecutada sin revision por caso.",
        restr="Cumplimiento BCRA y Ley 25.326.",
    ),
    _fg(
        "VAR-FG-N18",
        "negocio",
        ["personales"],
        "Negro",
        "val",
        "Agente que ejecuta automaticamente reportes regulatorios de operaciones "
        "sospechosas a la autoridad usando un proveedor externo por homologar, sin "
        "revision por caso; un reporte erroneo expone a sancion directa.",
        impacto="Clientes reportados a la autoridad de forma autonoma. Criticidad maxima.",
        riesgo="Proveedor externo por homologar; exposicion a sancion regulatoria directa "
        "(criterio d) sin revision por caso.",
        restr="Cumplimiento UIF y Ley 25.326.",
    ),
    # -- Colinealidad rota: alto=Si pero P5=No (humano valida cada caso) => NO Negro.
    _fg(
        "VAR-FG-R19",
        "negocio",
        ["personales"],
        "Rojo",
        "val",
        "Sistema de scoring que condiciona el acceso al credito de clientes perfilando su "
        "riesgo con una API externa por homologar; un analista revisa y aprueba cada "
        "decision antes de notificar al cliente.",
        impacto="Clientes solicitantes; el score condiciona el acceso al credito. "
        "Criticidad muy alta.",
        riesgo="API externa por homologar; decision financiera con profiling, pero el "
        "analista valida cada caso (P5=No).",
        restr="Cumplimiento BCRA y Ley 25.326; el analista decide cada solicitud.",
    ),
    _fg(
        "VAR-FG-R21",
        "operativo",
        ["confidenciales"],
        "Rojo",
        "val",
        "Analizador que condiciona acciones legales sobre clientes con un modelo externo "
        "por homologar y riesgo legal si falla; el abogado valida cada hallazgo antes de "
        "actuar.",
        impacto="El analisis condiciona acciones legales sobre clientes. Criticidad alta.",
        riesgo="Modelo externo por homologar; el abogado valida cada hallazgo (P5=No).",
        restr="Confidencialidad contractual; el abogado decide cada caso.",
    ),
    _fg(
        "VAR-FG-R22",
        "negocio",
        ["personales"],
        "Rojo",
        "val",
        "Asistente de diagnostico que influye en la decision clinica con un modelo externo "
        "por homologar y riesgo legal; el medico revisa y decide cada paciente.",
        impacto="Pacientes; el sistema influye en el diagnostico. Criticidad muy alta.",
        riesgo="Modelo externo por homologar; el medico decide cada caso (P5=No).",
        restr="Datos de salud; cumplimiento regulatorio; el medico decide.",
    ),
    _fg(
        "VAR-FG-A24",
        "negocio",
        ["personales"],
        "Amarillo",
        "val",
        "Recomendador que condiciona ofertas financieras a clientes perfilando su "
        "comportamiento, con framework interno certificado y riesgo legal si falla; el "
        "representante aprueba cada oferta antes de presentarla.",
        impacto="Clientes; perfilamiento que condiciona la oferta (alto_impacto), pero el "
        "representante decide. Criticidad media.",
        riesgo="Framework interno certificado; profiling, pero el representante aprueba cada "
        "oferta (P5=No).",
        restr="Cumplimiento Ley 25.326 y Defensa del Consumidor; el representante decide.",
    ),
    _fg(
        "VAR-FG-A18",
        "negocio",
        ["personales"],
        "Amarillo",
        "val",
        "Sistema que perfila a mas de 100.000 clientes por su comportamiento de consumo "
        "para definir a quienes se ofrecen beneficios, con framework interno certificado; "
        "el equipo de marketing decide cada campania y sin riesgo legal directo.",
        impacto="Mas de 100.000 clientes perfilados (alto_impacto por escala), pero el "
        "equipo decide cada accion. Criticidad media.",
        riesgo="Framework interno certificado; profiling a escala, pero el equipo decide (P5=No).",
        restr="Cumplimiento Ley 25.326; el equipo decide cada campania.",
    ),
    _fg(
        "VAR-FG-A19",
        "negocio",
        ["personales"],
        "Amarillo",
        "val",
        "Sistema que perfila a mas del 10% de la base con un LLM externo por homologar "
        "para priorizar acciones comerciales; el responsable decide cada accion y sin "
        "riesgo legal directo.",
        impacto="Mas del 10% de la base perfilada (alto_impacto por escala), pero el "
        "responsable decide. Criticidad media.",
        riesgo="LLM externo por homologar; profiling a escala, pero el responsable decide (P5=No).",
        restr="Cumplimiento Ley 25.326; el responsable decide cada accion.",
    ),
    # -- Transiciones de conteo Verde<->Amarillo (1<->2 Si).
    _fg(
        "VAR-FG-V16",
        "capacidad",
        ["personales"],
        "Verde",
        "val",
        "Asistente que muestra al empleado un resumen informativo de su propio historial "
        "de desempeño a partir de sus datos; no decide nada ni se comparte con terceros.",
        impacto="Empleado como unico usuario de su propio resumen; no decide sobre personas. "
        "Criticidad baja.",
        riesgo="Uso informativo de datos personales del propio empleado; sin automatizacion.",
        restr="Sin decisiones automaticas; el empleado consume su propio dato.",
    ),
    _fg(
        "VAR-FG-V17",
        "capacidad",
        ["ninguno"],
        "Verde",
        "val",
        "Asistente que traduce documentacion tecnica interna usando un LLM externo por "
        "homologar; sin datos personales, el autor revisa antes de usar.",
        impacto="Empleados como usuarios; sin datos personales ni decision sobre personas. "
        "Criticidad baja.",
        riesgo="LLM externo por homologar, pero sin datos sensibles ni decisiones; el autor "
        "revisa.",
        restr="Sin datos personales; revision humana previa.",
    ),
    _fg(
        "VAR-FG-V18",
        "operativo",
        ["personales"],
        "Verde",
        "val",
        "Tablero que muestra al gerente datos de contacto de clientes de forma informativa; "
        "no influye en decisiones ni automatiza ninguna accion.",
        impacto="Gerente como consumidor de un tablero informativo; no decide sobre personas. "
        "Criticidad baja.",
        riesgo="Uso informativo de datos personales; sin automatizacion ni decision.",
        restr="Solo lectura; sin acciones automaticas.",
    ),
    _fg(
        "VAR-FG-A20",
        "operativo",
        ["personales"],
        "Amarillo",
        "val",
        "Asistente que resume historiales de clientes a partir de sus datos usando un LLM "
        "externo por homologar; es informativo, el representante decide y sin riesgo legal.",
        impacto="Representantes como usuarios de un resumen informativo. Criticidad media.",
        riesgo="LLM externo por homologar sobre datos personales; informativo, el "
        "representante decide.",
        restr="Cumplimiento Ley 25.326; el representante decide.",
    ),
    _fg(
        "VAR-FG-A21",
        "negocio",
        ["personales"],
        "Amarillo",
        "val",
        "Recomendador que sugiere al representante una accion para el cliente segun sus "
        "datos; el representante decide, con plataforma interna homologada y sin riesgo "
        "legal directo.",
        impacto="Clientes via representante; influye en la oferta pero el representante "
        "decide. Criticidad media.",
        riesgo="Plataforma interna homologada; el representante decide cada accion.",
        restr="Cumplimiento Ley 25.326; el representante decide.",
    ),
    # -- Transiciones de conteo Amarillo<->Rojo (3<->4 Si).
    _fg(
        "VAR-FG-A22",
        "negocio",
        ["personales"],
        "Amarillo",
        "val",
        "Generador de comunicaciones a clientes a partir de sus datos que condicionan su "
        "decision, con riesgo reputacional si fallan; el responsable aprueba antes de "
        "enviar, con plataforma interna homologada.",
        impacto="Clientes que reciben comunicaciones que condicionan su decision. "
        "Criticidad media.",
        riesgo="Plataforma interna homologada; el responsable aprueba antes de enviar.",
        restr="Cumplimiento Defensa del Consumidor; revision previa del responsable.",
    ),
    _fg(
        "VAR-FG-A23",
        "negocio",
        ["personales"],
        "Amarillo",
        "val",
        "Asistente que analiza datos de clientes e influye en la oferta que se les presenta, "
        "con un LLM externo por homologar; el representante decide y sin riesgo legal directo.",
        impacto="Clientes via representante; influye en la oferta. Criticidad media.",
        riesgo="LLM externo por homologar; el representante decide cada oferta.",
        restr="Cumplimiento Ley 25.326; el representante decide.",
    ),
    # -- Override de Negro con conteo bajo (P5=Si Y alto=Si, suma de Si < 4).
    _fg(
        "VAR-FG-N19",
        "operativo",
        ["personales"],
        "Negro",
        "val",
        "Agente que restringe automaticamente el acceso de empleados a sistemas criticos "
        "ante señales de riesgo, sin revision por caso; la restriccion limita derechos de "
        "acceso hasta una intervencion posterior.",
        impacto="Empleados con acceso restringido sin revision por caso; restriccion de "
        "derechos (criterio b). Criticidad alta.",
        riesgo="Restriccion de acceso autonoma (criterio b) sin revision por caso; "
        "supervision solo ex-post.",
        restr="Cumplimiento normativa laboral y Ley 25.326.",
    ),
    _fg(
        "VAR-FG-N20",
        "operativo",
        ["personales"],
        "Negro",
        "val",
        "Sistema que ejecuta automaticamente el bloqueo de los pagos de un cliente ante un "
        "score de fraude, sin revision por caso; el bloqueo corta el acceso a sus fondos.",
        impacto="Clientes con pagos bloqueados sin revision por caso; corte de acceso a "
        "fondos (criterio b). Criticidad muy alta.",
        riesgo="Bloqueo autonomo (denegacion de acceso, criterio b) sin revision por caso.",
        restr="Cumplimiento BCRA y Ley 25.326.",
    ),
    # === D-017: VAL representativo del TEST (VAR-FG-T01..T14, todos split=val) ===
    # Casos sembrados con la dificultad REAL del TEST (los TC-xx que el baseline falla
    # 2/2), no casos borde sinteticos limpios. Cada patron reproduce una confusion
    # observada en el diagnostico por-caso (diagnose_rule_baseline). No copian ningun
    # TC: son fichas NUEVAS con la misma estructura de trampa Y la misma textura rica
    # (metricas numericas, multiples restricciones, sponsor nombrado, escala concreta).
    # CLAVE: las fichas son NEUTRALES -- describen el escenario de negocio sin nombrar
    # p1..p5, alto_impacto, criterios ni el color (el modelo debe inferir los juicios,
    # como en los TC reales). Una version previa filtraba la respuesta en el campo
    # supuesto_riesgo y el modelo acertaba sin esfuerzo. El TEST no se toca.
    #
    # Patron 1 -- Amarillo con p2 sutil: el sistema genera un INSUMO (informe/score/
    # analisis) sobre clientes/empleados y un humano decide; el modelo razona "el humano
    # decide -> no influye -> p2=No" y subcuenta. Gold p2=si (influir en la decision = si).
    _fg(
        "VAR-FG-T01",
        "operativo",
        ["personales"],
        "Amarillo",
        "val",
        "Sistema que analiza las transcripciones de las llamadas de cada agente de call "
        "center y calcula un score mensual de calidad de atencion (claridad, resolucion, "
        "tono), publicandolo en un ranking que el supervisor consulta para planificar el "
        "coaching y el feedback de su equipo.",
        nombre="Evaluador de Calidad de Atencion",
        area="Gestion de Contact Center",
        metricas="Cobertura de llamadas evaluadas >= 95%; correlacion del score con la "
        "auditoria manual >= 0;85; tiempo de armado del ranking < 2 horas",
        impacto="Empleados (140 agentes) cuyas llamadas se puntuan mensualmente. El ranking "
        "informa las decisiones de coaching y feedback del supervisor sobre cada agente. El "
        "supervisor decide cada accion. Criticidad media.",
        riesgo="El score se calcula sobre transcripciones completas y el supervisor lo usa "
        "como insumo; framework interno homologado; el agente puede pedir revision de su score.",
        restr="El sistema no toma decisiones sobre el agente; solo publica el score; "
        "cumplimiento Ley 25.326; el supervisor valida; presupuesto maximo USD 35.000",
        sponsor="Lucia Fernandez - Gerente de Contact Center",
    ),
    _fg(
        "VAR-FG-T02",
        "negocio",
        ["personales"],
        "Amarillo",
        "val",
        "Modelo que estima diariamente la probabilidad de mora de cada cliente pospago en "
        "los proximos 30 dias y publica el score en el CRM para consulta del equipo de "
        "cobranzas, que decide a que clientes contactar y con que plan de pago ofrecer. El "
        "sistema no actua sobre el cliente.",
        nombre="Modelo Predictivo de Mora",
        area="Cobranzas",
        metricas="AUC-ROC >= 0;80; reduccion de mora en cohorte contactada >= 12%; "
        "cobertura de la cartera scoreada >= 100%",
        impacto="Clientes (~90.000 pospago) cuyo score se calcula a diario. El equipo de "
        "cobranzas (30 gestores) decide autonomamente la accion. El sistema no contacta ni "
        "actua sobre el cliente. Criticidad media.",
        riesgo="El score es un insumo para el gestor, que decide cada contacto; framework "
        "MLOps interno certificado y vigente.",
        restr="El sistema no actua sobre el cliente; solo publica scores; cumplimiento BCRA "
        "y Ley 25.326; sin variables que generen sesgo; presupuesto maximo USD 80.000",
        sponsor="Martin Rios - Director de Cobranzas",
    ),
    _fg(
        "VAR-FG-T03",
        "operativo",
        ["confidenciales"],
        "Amarillo",
        "val",
        "Sistema que revisa los contratos de clientes corporativos e identifica clausulas "
        "de riesgo (penalidades, renovacion automatica, exclusividad), generando un informe "
        "de hallazgos para el equipo legal. El abogado responsable valida el informe y "
        "decide si negociar, escalar o aceptar.",
        nombre="Analizador de Clausulas Contractuales",
        area="Legal Corporativo",
        metricas="Tiempo de revision contractual reducido >= 60%; cobertura de clausulas de "
        "riesgo detectadas >= 90%; falsos negativos < 5%",
        impacto="El analisis condiciona las posiciones legales sobre los contratos de ~180 "
        "clientes corporativos por mes. Empleados (15 abogados) consumen el informe. El "
        "abogado decide cada accion. Criticidad alta.",
        riesgo="El informe es un insumo; el abogado valida cada hallazgo antes de actuar; "
        "los documentos estan digitalizados; sin proveedores externos.",
        restr="El sistema no propone posiciones de negociacion; solo identifica clausulas; "
        "confidencialidad contractual y secreto profesional; el abogado valida; presupuesto "
        "maximo USD 70.000",
        sponsor="Ignacio Vera - Director Legal",
    ),
    # Patron 5 -- Amarillo con p5 de supervision SOLO posterior: la accion se ejecuta
    # automatica y la unica revision es ex-post (al dia siguiente) -> gold p5=si, pero
    # conteo bajo -> Amarillo. El modelo lee "el equipo revisa" y subcuenta p5=No.
    _fg(
        "VAR-FG-T04",
        "operativo",
        ["confidenciales"],
        "Amarillo",
        "val",
        "Sistema que genera y envia automaticamente, al cierre de cada dia habil, los "
        "reportes de exposicion de riesgo a la gerencia de Riesgo, sin revision previa. El "
        "equipo de riesgo revisa el reporte consolidado a la manana siguiente.",
        nombre="Reportes Automaticos de Exposicion",
        area="Riesgo Financiero",
        metricas="Disponibilidad del reporte antes de las 7:00 AM; precision de las metricas "
        "de exposicion >= 99%; cobertura de la cartera >= 100%",
        impacto="Empleados (10 gerentes y analistas de Riesgo) como destinatarios. Los "
        "reportes informan decisiones de gestion del riesgo; no deciden sobre personas. "
        "Criticidad media.",
        riesgo="Los datos de cierre estan consolidados antes del proceso nocturno; el envio "
        "es automatico y la revision del equipo es a la manana siguiente.",
        restr="Reportes de uso exclusivo de la gerencia de Riesgo; no se distribuyen fuera "
        "del perimetro; cumplimiento BCRA; sin proveedores externos; presupuesto maximo USD 20.000",
        sponsor="Fernando Aguirre - Director de Riesgo",
    ),
    _fg(
        "VAR-FG-T05",
        "operativo",
        ["personales"],
        "Amarillo",
        "val",
        "Herramienta que clasifica automaticamente los emails entrantes de clientes por tipo "
        "y urgencia y los rutea a las colas de atencion correspondientes sin revision previa. "
        "Un supervisor audita una muestra del ruteo al final de cada dia.",
        nombre="Ruteo Automatico de Emails de Clientes",
        area="Atencion al Cliente",
        metricas="Precision de clasificacion >= 88%; reduccion del tiempo de primera "
        "asignacion >= 50%; tasa de re-ruteo manual < 8%",
        impacto="Clientes cuyos emails se clasifican y rutean automaticamente. El ruteo "
        "determina el orden y la cola de atencion, no una decision sobre la persona. "
        "Criticidad baja.",
        riesgo="El ruteo es automatico sin revision previa; el supervisor audita una muestra "
        "a posteriori; framework interno homologado.",
        restr="Cumplimiento Ley 25.326; los emails se conservan segun la politica de "
        "retencion; sin proveedores externos; presupuesto maximo USD 22.000",
        sponsor="Carla Mendez - Gerente de Atencion",
    ),
    # Patron 2 -- Rojo con P5 autonomo ACOTADO + REVERSIBLE: ejecuta sin revision por
    # caso (p5=si) pero limitado a catalogo/bandas y reversible -> alto_impacto=No (filtro
    # del PASO 1) -> Rojo (conteo 4-5), NO Negro. El modelo o subcuenta p5 (cree que
    # "acotado" = revisado) o sobre-escala alto_impacto a Negro.
    _fg(
        "VAR-FG-T06",
        "negocio",
        ["personales"],
        "Rojo",
        "val",
        "Sistema que analiza mensualmente el comportamiento de pago de cada cliente pospago "
        "y ajusta automaticamente su cupo de compra dentro de las bandas definidas por la "
        "politica de credito vigente, sin discrecionalidad fuera de esos limites ni "
        "intervencion por caso. Genera un log mensual revisable por el equipo de credito a "
        "las 48 horas; el cliente puede solicitar revision.",
        nombre="Ajuste Automatico de Cupo de Compra",
        area="Credito y Cobranzas",
        metricas="Reduccion de mora >= 15%; ajustes dentro de banda >= 99;5%; tiempo del "
        "ciclo mensual < 4 horas",
        impacto="Clientes (~80.000 pospago) que reciben ajustes automaticos de cupo sin "
        "intervencion humana por caso. El ajuste afecta directamente su capacidad de "
        "consumo. Criticidad alta.",
        riesgo="Los parametros de politica estan vigentes; el log mensual se revisa a las "
        "48 horas; el cliente puede pedir revision humana de cualquier ajuste.",
        restr="Los ajustes no superan los limites de la politica aprobada; cumplimiento BCRA "
        "y Ley 25.326; el cliente puede solicitar revision; presupuesto maximo USD 100.000",
        sponsor="Fernando Aguirre - Director de Credito",
    ),
    _fg(
        "VAR-FG-T07",
        "negocio",
        ["personales"],
        "Rojo",
        "val",
        "Agente que recibe reclamos de clientes via API, los clasifica con un LLM de un "
        "proveedor externo aun no homologado y aplica automaticamente compensaciones "
        "acotadas al catalogo aprobado por policy (credito de factura, ajuste de plan "
        "menor), cerrando el caso. Escala a un agente humano solo cuando el reclamo no "
        "encaja en ninguna categoria del catalogo. Las resoluciones son reversibles.",
        nombre="Resolucion Automatica de Reclamos",
        area="Operaciones de Atencion",
        metricas="Tasa de resolucion automatizada >= 65%; tiempo de cierre de reclamos "
        "simples < 2 horas; satisfaccion post-resolucion >= 3;9/5",
        impacto="Clientes (~7.000 con reclamos por mes) cuyos casos se resuelven de forma "
        "autonoma dentro del catalogo aprobado. Las resoluciones afectan la relacion "
        "comercial. Criticidad alta.",
        riesgo="El LLM externo clasifica el tipo de reclamo; las resoluciones estan dentro "
        "del catalogo aprobado y son reversibles; el proveedor externo aun no esta homologado.",
        restr="El agente no aplica compensaciones fuera del catalogo; escalada obligatoria "
        "cuando no encaja; cumplimiento Defensa del Consumidor; el LLM externo debe "
        "homologarse; presupuesto maximo USD 130.000",
        sponsor="Tomas Elizondo - Gerente de Operaciones de Reclamos",
    ),
    _fg(
        "VAR-FG-T08",
        "negocio",
        ["personales"],
        "Rojo",
        "val",
        "Modulo del canal digital que ejecuta de forma autonoma los cambios de plan "
        "solicitados por el cliente: verifica la disponibilidad del upgrade en el catalogo "
        "vigente, ejecuta el cambio en el sistema de facturacion y lo confirma, sin "
        "intervencion de un agente humano. El cambio es reversible por el cliente dentro de "
        "las 24 horas.",
        nombre="Ejecucion Autonoma de Cambios de Plan",
        area="Canales Digitales",
        metricas="Cambios completados sin intervencion humana >= 80%; tiempo de "
        "procesamiento < 3 minutos; satisfaccion post-cambio >= 4/5",
        impacto="Clientes (~25.000 por mes) cuyos cambios de plan se ejecutan de forma "
        "autonoma dentro del catalogo. Es una modificacion contractual. Criticidad alta.",
        riesgo="El modulo opera solo sobre upgrades del catalogo vigente; el cambio es "
        "reversible por el cliente dentro de 24 horas; las condiciones no estandar se escalan.",
        restr="Solo upgrades del catalogo aprobado; las condiciones no estandar requieren "
        "agente humano; cumplimiento Defensa del Consumidor y ENACOM; reversible 24hs; "
        "presupuesto maximo USD 65.000",
        sponsor="Gabriela Moreno - Directora de Canales Digitales",
    ),
    _fg(
        "VAR-FG-T09",
        "operativo",
        ["personales"],
        "Rojo",
        "val",
        "Agente que verifica el cumplimiento de los criterios de alta estandar y ejecuta "
        "automaticamente el registro del cliente en el CRM y en facturacion, sin "
        "intervencion del operador por caso, confirmando el alta al cliente por email. Los "
        "casos con documentacion incompleta o fuera de los criterios estandar se derivan a "
        "revision manual.",
        nombre="Alta Automatica de Clientes",
        area="Operaciones Comerciales",
        metricas="Tiempo de alta < 3 minutos; tasa de alta correcta >= 99;5%; satisfaccion "
        "post-alta >= 4/5",
        impacto="Clientes (~5.000 nuevos por mes) cuya alta se ejecuta de forma autonoma, "
        "estableciendo la relacion contractual. Criticidad alta.",
        riesgo="Los criterios de alta estan definidos y vigentes; los casos fuera de "
        "criterio van a revision manual; el alta es una accion favorable solicitada por el "
        "cliente.",
        restr="Los casos fuera de los criterios estandar requieren revision manual; "
        "cumplimiento Ley 25.326; presupuesto maximo USD 40.000",
    ),
    # Patron 3 -- Negro por ESCALA MASIVA pese a bandas: accion autonoma sobre >=10% de la
    # base o >=100.000 personas -> alto_impacto=si por criterio (a), aunque sea acotada a
    # bandas. El modelo aplica el filtro de acotamiento del PASO 1 y subcuenta alto=No.
    _fg(
        "VAR-FG-T10",
        "negocio",
        ["personales"],
        "Negro",
        "val",
        "Agente que ajusta automaticamente precios y descuentos de los planes de unos "
        "300.000 clientes activos, segmentados, en funcion de parametros de mercado y "
        "comportamiento de consumo en tiempo real. Los ajustes se aplican dentro de bandas "
        "predefinidas por el area comercial sin requerir aprobacion individual.",
        nombre="Pricing Dinamico por Segmento",
        area="Gestion Comercial",
        metricas="Incremento de ARPU del segmento >= 5%; reduccion de churn >= 10%; ajustes "
        "dentro de bandas >= 99;9%",
        impacto="Clientes (~300.000 activos en 8 segmentos) cuyos precios y descuentos se "
        "ajustan de forma autonoma. Afecta las condiciones comerciales de cada cliente del "
        "segmento. Criticidad muy alta.",
        riesgo="Las bandas tarifarias estan dentro de los limites regulatorios vigentes; el "
        "area comercial revisa las bandas antes de cada ciclo; los ajustes se aplican sin "
        "aprobacion individual.",
        restr="Los ajustes no superan las bandas aprobadas; cumplimiento ENACOM y Defensa "
        "del Consumidor; los cambios de bandas requieren aprobacion de Gestion Comercial; "
        "presupuesto maximo USD 250.000",
        sponsor="Sebastian Castro - Director Comercial",
    ),
    _fg(
        "VAR-FG-T11",
        "negocio",
        ["personales"],
        "Negro",
        "val",
        "Sistema que recalcula y aplica automaticamente la tarifa de mas del 10% de la base "
        "de clientes segun su patron de consumo mensual, dentro de las bandas aprobadas por "
        "el area comercial, sin revision por caso.",
        nombre="Recalculo Automatico de Tarifas",
        area="Gestion Comercial",
        metricas="Cobertura de la base recalculada >= 10%; ajustes dentro de bandas >= "
        "99;9%; reclamos por cambio de tarifa < 1%",
        impacto="Clientes (mas del 10% de la base activa) cuyas tarifas se recalculan y "
        "aplican de forma autonoma. Afecta directamente lo que paga cada cliente alcanzado. "
        "Criticidad muy alta.",
        riesgo="Las bandas estan dentro de los limites regulatorios; el area revisa las "
        "bandas antes de cada ciclo; el recalculo se aplica sin revision por caso.",
        restr="Los recalculos no superan las bandas aprobadas; cumplimiento ENACOM y "
        "Defensa del Consumidor; presupuesto maximo USD 180.000",
        sponsor="Sebastian Castro - Director Comercial",
    ),
    # Patron 4 -- Negro por DENEGACION/RESTRICCION de acceso, aunque reversible: corte de
    # servicio, bloqueo o restriccion de derechos -> alto_impacto=si por criterio (b),
    # aunque el equipo pueda revertir despues. El modelo lee "reversible" y subcuenta alto=No.
    _fg(
        "VAR-FG-T12",
        "operativo",
        ["personales"],
        "Negro",
        "val",
        "Sistema que analiza cada transaccion en tiempo real y bloquea automaticamente las "
        "que superan el umbral de riesgo definido, sin revision por caso. El equipo de "
        "fraude recibe alertas y puede revertir el bloqueo dentro de las 2 horas siguientes.",
        nombre="Bloqueo Automatico Antifraude",
        area="Prevencion de Fraude",
        metricas="Deteccion de fraude real >= 95%; falsos positivos < 2%; tiempo de decision "
        "< 500ms por transaccion",
        impacto="Clientes (~120.000 transacciones por dia) cuyas operaciones pueden "
        "bloquearse en el momento. El bloqueo impide completar la transaccion. Criticidad "
        "muy alta.",
        riesgo="El bloqueo es a nivel de transaccion individual; el equipo de fraude puede "
        "revertirlo dentro de 2 horas; el modelo de scoring esta en evaluacion.",
        restr="El bloqueo es solo de la transaccion, no de la cuenta; reversible por el "
        "equipo en 2 horas; cumplimiento BCRA; presupuesto maximo USD 200.000",
        sponsor="Diego Carrasco - Gerente de Prevencion de Fraude",
    ),
    _fg(
        "VAR-FG-T13",
        "operativo",
        ["personales"],
        "Negro",
        "val",
        "Agente que suspende automaticamente el acceso de un cliente a la plataforma de "
        "autogestion ante senales de riesgo de seguridad (patrones de acceso anomalos, "
        "indicios de cuenta comprometida), sin revision previa por caso. El area de soporte "
        "puede restituir el acceso a pedido del cliente.",
        nombre="Suspension Automatica de Acceso",
        area="Seguridad de la Informacion",
        metricas="Deteccion de accesos comprometidos >= 90%; falsos positivos < 3%; tiempo "
        "de restitucion < 4 horas",
        impacto="Clientes cuyo acceso a la plataforma se suspende de forma autonoma ante "
        "senales de riesgo. Quedan sin acceso hasta la restitucion. Criticidad alta.",
        riesgo="La suspension es automatica ante senales de riesgo; soporte restituye a "
        "pedido; las senales pueden tener falsos positivos.",
        restr="La suspension se aplica sin revision previa; soporte restituye a pedido del "
        "cliente; cumplimiento Ley 25.326 y Defensa del Consumidor; presupuesto maximo USD 50.000",
    ),
    # Patron 2b -- Rojo con apoyo a decision financiera + proveedor externo (sin ejecucion
    # autonoma): p5=No (el analista decide cada caso) -> conteo 4 -> Rojo. El modelo
    # subcuenta p3/p5 y baja a Amarillo. No es Negro (p5=No).
    _fg(
        "VAR-FG-T14",
        "negocio",
        ["personales"],
        "Rojo",
        "val",
        "Sistema que procesa los datos financieros y de comportamiento del cliente, llama a "
        "una API externa de scoring aun no homologada y devuelve al analista de credito una "
        "recomendacion de aprobacion o rechazo de plan pospago. El analista valida la "
        "recomendacion y registra la decision final en cada caso.",
        nombre="Motor de Scoring Crediticio Asistido",
        area="Credito y Cobranzas",
        metricas="Tasa de mora en aprobados <= 3%; tiempo de evaluacion < 3 minutos; tasa "
        "de aprobacion dentro de banda +/- 5%",
        impacto="Clientes (~5.000 solicitantes por mes). El score condiciona en la practica "
        "el acceso al plan. 30 analistas registran la decision formal. Criticidad muy alta.",
        riesgo="La API externa sera homologada antes de produccion; el analista valida y "
        "registra la decision en cada caso.",
        restr="El sistema no toma la decision; el analista registra la aprobacion o rechazo; "
        "cumplimiento BCRA, Ley 25.326 y Ley 25.065; sin variables discriminatorias; "
        "presupuesto maximo USD 150.000",
        sponsor="Fernando Aguirre - Director de Credito",
    ),
    # === D-017 (few-shot fijos): demos ENSENANTES de las distinciones del cuello ===
    # 2 demos train nuevos con razonamiento explicito para las 2 confusiones que el
    # few-shot sampleado no cubria (ningun demo Amarillo con p2 sutil ni con p5 posterior).
    # Se usan via `few_shot_ids` junto con V03/V13/R01/R04/N01/N02 (set fijo 2/2/2/2).
    _fg(
        "VAR-FG-D01",
        "negocio",
        ["personales"],
        "Amarillo",
        "train",
        "Sistema que calcula un indice de propension de compra de cada cliente y lo "
        "publica en el CRM; el ejecutivo comercial usa ese indice para decidir a quien "
        "ofrecer un upgrade y en que condiciones. El sistema no contacta al cliente.",
        nombre="Indice de Propension de Compra",
        area="Gestion Comercial",
        metricas="Precision del indice >= 0;80; conversion en cohorte priorizada >= 15%; "
        "cobertura de la base scoreada >= 100%",
        impacto="Clientes (~60.000) cuyo indice se calcula. El ejecutivo decide la oferta "
        "a partir del indice. El sistema no actua sobre el cliente. Criticidad media.",
        riesgo="El indice es un insumo; el ejecutivo decide cada oferta; framework interno homologado.",
        restr="El sistema no contacta ni decide; solo publica el indice; cumplimiento Ley 25.326.",
        sponsor="Sebastian Castro - Director Comercial",
    ),
    _fg(
        "VAR-FG-D02",
        "operativo",
        ["personales"],
        "Amarillo",
        "train",
        "Sistema que asigna automaticamente cada caso entrante a un equipo de atencion "
        "segun su contenido, sin revision previa; un coordinador audita el resultado del "
        "dia a la manana siguiente y reasigna lo que haga falta.",
        nombre="Asignacion Automatica de Casos",
        area="Operaciones de Atencion",
        metricas="Precision de asignacion >= 90%; reduccion del tiempo de derivacion >= 55%; "
        "tasa de reasignacion < 7%",
        impacto="Clientes cuyos casos se asignan automaticamente; la asignacion define el "
        "equipo que atiende, sin decidir sobre la persona. Criticidad baja.",
        riesgo="La asignacion se ejecuta automatica sin revision previa; el coordinador "
        "audita el resultado a la manana siguiente.",
        restr="Cumplimiento Ley 25.326; framework interno homologado; sin proveedores externos.",
        sponsor="Carla Mendez - Gerente de Atencion",
    ),
]


# Razonamiento por caso para los demos de fast_gate (few-shot rico). Solo los 30 de
# train: son los unicos que `LabeledFewShot` puede inyectar como demos; val/test no se
# usan como demos y `razonamiento` esta en `ignore_in_metric`. Justifican el color para
# dar senal de cadena-de-razonamiento (cot) a los demos, que sin esto iban vacios.
_FG_RAZONAMIENTO: dict[str, str] = {
    # Verde: uso interno de baja criticidad, sin decision sensible, con revision humana.
    "VAR-FG-V01": "Verde: uso interno de baja criticidad, sin datos sensibles ni decision sobre personas; el autor revisa antes de compartir.",
    "VAR-FG-V02": "Verde: datos operativos no sensibles y alerta no automatica; el equipo tecnico decide la intervencion.",
    "VAR-FG-V03": "Verde: sin datos sensibles, el empleado decide que hacer; sin impacto sobre terceros.",
    "VAR-FG-V04": "Verde: la decision queda en el empleado, sin impacto en su desempeno ni datos sensibles.",
    "VAR-FG-V05": "Verde: datos operativos no sensibles y no decide sobre personas; la gerencia valida.",
    "VAR-FG-V06": "Verde: uso interno y el agente revisa antes de enviar; sin datos sensibles.",
    "VAR-FG-V07": "Verde: documentacion interna y el autor aprueba; sin impacto en personas.",
    "VAR-FG-V08": "Verde: datos tecnicos internos, sin impacto en personas externas.",
    # Amarillo: datos personales/confidenciales + un factor mas, con revision humana.
    "VAR-FG-A01": "Amarillo: datos confidenciales y proveedor externo aun por homologar, mitigado por revision humana previa.",
    "VAR-FG-A02": "Amarillo: salida a un canal publico con riesgo reputacional, acotado por aprobacion previa del responsable.",
    "VAR-FG-A03": "Amarillo: datos personales y condiciona la oferta al cliente, pero el representante decide.",
    "VAR-FG-A04": "Amarillo: datos confidenciales que condicionan acciones legales sobre clientes; el abogado valida cada hallazgo.",
    "VAR-FG-A05": "Amarillo: datos personales y proveedor externo por homologar, con validacion humana de los participantes.",
    "VAR-FG-A06": "Amarillo: contacto con clientes y datos personales, mitigado por plantillas de contenido aprobadas.",
    "VAR-FG-A07": "Amarillo: exposicion publica con riesgo de imagen, acotada por revision previa del responsable.",
    "VAR-FG-A08": "Amarillo: interaccion con clientes en reclamos, limitada a respuestas pre-aprobadas y con escalada a humano.",
    # Rojo: personal + influye en decision + proveedor externo por homologar, con revision.
    "VAR-FG-R01": "Rojo: datos personales, influye en decisiones del cliente y usa un LLM externo aun por homologar; mitigado por escalada a humano.",
    "VAR-FG-R02": "Rojo: condiciona el acceso a credito con una API externa por homologar; el analista registra la decision.",
    "VAR-FG-R03": "Rojo: influye en un diagnostico medico con un modelo externo por homologar; el medico decide.",
    "VAR-FG-R04": "Rojo: resuelve reclamos de forma autonoma sin revision por caso, pero acotado a un catalogo de compensaciones aprobado; fuera del catalogo escala a humano.",
    "VAR-FG-R05": "Rojo: influye en decisiones financieras del cliente con un LLM externo por homologar; el asesor decide.",
    "VAR-FG-R06": "Rojo: influye en decisiones legales del cliente con un modelo externo por homologar; el abogado revisa.",
    "VAR-FG-R07": "Rojo: ajusta limites de credito de forma autonoma sin revision por caso, pero acotado a bandas de politica con revision sistematica del log dentro de 48hs y reversible; el moderador de escalada lo mantiene en Rojo.",
    # Negro: ejecuta acciones de alto impacto sin revision humana previa por caso.
    "VAR-FG-N01": "Negro: ajusta precios y descuentos de forma autonoma sobre mas del 10% de la base de clientes, sin bandas ni catalogo acotado ni revision por caso; alto impacto por escala.",
    "VAR-FG-N02": "Negro: corta el servicio (denegacion de acceso, criterio de naturaleza) de forma autonoma sin revision sistematica ni reversion -- P5=Si y alto impacto por naturaleza (criterio b).",
    "VAR-FG-N03": "Negro: aprueba y ejecuta reintegros de forma autonoma, sin revision humana por caso.",
    "VAR-FG-N04": "Negro: bloquea cuentas de clientes de forma autonoma ante senales de riesgo, sin revision previa.",
    "VAR-FG-N05": "Negro: perfila automaticamente el riesgo crediticio y decide el acceso al credito (naturaleza financiera, criterio b; profiling, criterio e) sin revision -- P5=Si y alto impacto.",
    "VAR-FG-N06": "Negro: termina contratos de forma autonoma e irreversible sin intervencion manual posterior -- P5=Si y alto impacto por irreversibilidad (criterio c).",
    "VAR-FG-N07": "Negro: perfila automaticamente el comportamiento del cliente (profiling, criterio e) y ejecuta ofertas vinculantes basadas en ese perfil sin revision -- P5=Si y alto impacto.",
    # Bordes de conteo.
    "VAR-FG-V13": "Verde: usa datos personales (P1) pero es informativo y el representante decide (P2=No), sin proveedor externo ni riesgo legal y con revision humana; conteo=1.",
    "VAR-FG-V14": "Verde: usa un LLM externo por homologar (P3) pero sin datos personales ni decisiones sobre personas, con revision humana; conteo=1.",
    "VAR-FG-V15": "Verde: usa datos personales del propio empleado (P1) de forma informativa, sin decidir ni automatizar nada; conteo=1.",
    "VAR-FG-A13": "Amarillo: datos personales (P1) y LLM externo por homologar (P3), mitigado por revision humana; sin decision directa ni riesgo legal; conteo=2.",
    "VAR-FG-A14": "Amarillo: datos personales (P1) e influye en la oferta al cliente (P2), pero el representante decide y no hay proveedor externo ni riesgo legal; conteo=2.",
    "VAR-FG-A15": "Amarillo: datos personales (P1) y riesgo reputacional si el informe falla (P4), mitigado por revision humana previa; conteo=2.",
    "VAR-FG-R12": "Rojo: cumple las 5 preguntas (datos personales, decision sobre el cliente, LLM externo por homologar, riesgo legal y ejecucion autonoma), pero la accion esta acotada a un catalogo aprobado y es reversible, por lo que alto_impacto=No y no escala a Negro; conteo=5.",
    "VAR-FG-R13": "Rojo: las 5 preguntas en Si, pero los ajustes estan acotados a bandas aprobadas y son reversibles con revision del log, por lo que alto_impacto=No y no es Negro; conteo=5.",
    # Romper colinealidad alto_impacto <=> Negro (alto=Si pero P5=No -> no Negro).
    "VAR-FG-R14": "Rojo: condiciona el acceso al credito perfilando al cliente (alto_impacto=Si por naturaleza financiera y profiling), con API externa por homologar y riesgo regulatorio, pero el analista valida cada caso (P5=No), por lo que no es Negro; conteo=4.",
    "VAR-FG-R15": "Rojo: decision financiera con perfilamiento (alto_impacto=Si) y modelo externo por homologar, pero el comite aprueba cada caso (P5=No); conteo=4.",
    "VAR-FG-A16": "Amarillo: perfila a mas de 100.000 clientes (alto_impacto=Si por profiling a escala) con datos personales, pero el framework es interno certificado, sin proveedor externo ni riesgo legal y el equipo decide cada accion (P5=No); conteo=2.",
    "VAR-FG-A17": "Amarillo: perfila a mas del 10% de la base (alto_impacto=Si) con LLM externo por homologar, pero el responsable decide cada campania (P5=No) y no hay riesgo legal directo; conteo=3.",
    # Negro por override con conteo distinto de 4.
    "VAR-FG-N12": "Negro: ejecuta de forma autonoma sin revision por caso (P5=Si) una restriccion de acceso del empleado (alto_impacto por naturaleza, criterio b); el override Negro domina aunque el conteo sea 3.",
    "VAR-FG-N13": "Negro: aprueba y ejecuta microcreditos de forma autonoma e irreversible sin revision por caso (P5=Si) con alto impacto financiero; el override Negro aplica; conteo=5.",
    # Ampliacion VAL borde (D-015): Rojo<->Negro por alto_impacto (acotado+reversible).
    "VAR-FG-R16": "Rojo: acredita bonificaciones de forma autonoma sin revision por caso (P5=Si), pero acotadas a un catalogo aprobado y reversibles, por lo que alto_impacto=No y no es Negro; conteo=4.",
    "VAR-FG-R17": "Rojo: ajusta planes de forma autonoma (P5=Si) con LLM externo por homologar, pero dentro de bandas aprobadas y reversible, por lo que alto_impacto=No; conteo=5.",
    "VAR-FG-R18": "Rojo: reprograma turnos de forma autonoma (P5=Si), pero acotado a la grilla y reversible por el cliente, alto_impacto=No; conteo=4 sin proveedor externo.",
    "VAR-FG-R23": "Rojo: ejecuta reembolsos de forma autonoma (P5=Si) con LLM externo por homologar, pero acotados a un catalogo de montos y reversibles, alto_impacto=No; conteo=5.",
    "VAR-FG-N14": "Negro: corta el servicio (denegacion de acceso, criterio b) de forma autonoma sin revision por caso (P5=Si) y alto impacto; conteo=4.",
    "VAR-FG-N15": "Negro: ejecuta una baja irreversible con borrado de datos (criterio c) sin revision por caso (P5=Si) y alto impacto; conteo=4.",
    "VAR-FG-N16": "Negro: perfila a mas del 10% de la base (criterios a y e) y aplica ofertas vinculantes con LLM externo por homologar sin revision (P5=Si); conteo=5.",
    "VAR-FG-N17": "Negro: desembolsa adelantos financieros no acotados (criterio b) sin revision por caso (P5=Si) y alto impacto; conteo=4.",
    "VAR-FG-N18": "Negro: ejecuta reportes regulatorios con exposicion a sancion directa (criterio d) y proveedor externo por homologar sin revision (P5=Si); conteo=5.",
    # Colinealidad rota: alto_impacto=Si con P5=No (humano valida cada caso) -> no Negro.
    "VAR-FG-R19": "Rojo: condiciona el acceso al credito perfilando al cliente (alto_impacto=Si por naturaleza financiera y profiling) con API externa por homologar, pero el analista valida cada caso (P5=No), por lo que no es Negro; conteo=4.",
    "VAR-FG-A24": "Amarillo: perfila al cliente condicionando ofertas financieras (alto_impacto=Si), pero con framework interno certificado (P3=No) y el representante aprueba cada oferta (P5=No); conteo=3.",
    "VAR-FG-A18": "Amarillo: perfila a mas de 100.000 clientes (alto_impacto=Si por escala) con framework interno certificado, pero el equipo decide cada accion (P5=No) y sin proveedor externo ni riesgo legal; conteo=2.",
    "VAR-FG-A19": "Amarillo: perfila a mas del 10% de la base (alto_impacto=Si) con LLM externo por homologar, pero el responsable decide cada accion (P5=No) y sin riesgo legal directo; conteo=3.",
    # Transiciones de conteo Verde<->Amarillo (1<->2) y Amarillo<->Rojo (3<->4).
    "VAR-FG-V16": "Verde: usa datos personales del propio empleado (P1) de forma informativa, sin decidir ni automatizar; conteo=1.",
    "VAR-FG-V17": "Verde: usa un LLM externo por homologar (P3) pero sin datos personales ni decisiones, con revision humana; conteo=1.",
    "VAR-FG-V18": "Verde: muestra datos personales de forma informativa (P1), sin influir en decisiones ni automatizar; conteo=1.",
    "VAR-FG-A20": "Amarillo: datos personales (P1) y LLM externo por homologar (P3), informativo y el representante decide; conteo=2.",
    "VAR-FG-A21": "Amarillo: datos personales (P1) e influye en la oferta (P2), pero el representante decide y plataforma interna homologada; conteo=2.",
    "VAR-FG-A22": "Amarillo: datos personales (P1), influye en la decision del cliente (P2) y riesgo reputacional (P4), mitigado por revision previa y plataforma interna; conteo=3.",
    "VAR-FG-A23": "Amarillo: datos personales (P1), influye en la oferta (P2) y LLM externo por homologar (P3), el representante decide y sin riesgo legal; conteo=3.",
    "VAR-FG-R21": "Rojo: datos confidenciales, condiciona acciones legales, modelo externo por homologar y riesgo legal (4 en Si), pero el abogado valida cada caso (P5=No) y la accion no es de alto impacto autonomo; conteo=4.",
    "VAR-FG-R22": "Rojo: influye en el diagnostico clinico con modelo externo por homologar y riesgo legal (4 en Si), pero el medico decide cada caso (P5=No); conteo=4.",
    # Override de Negro con conteo bajo (P5=Si Y alto=Si, suma de Si < 4).
    "VAR-FG-N19": "Negro: restringe el acceso de empleados (restriccion de derechos, criterio b) de forma autonoma sin revision por caso (P5=Si); el override Negro domina aunque el conteo sea 3.",
    "VAR-FG-N20": "Negro: bloquea los fondos del cliente (denegacion de acceso, criterio b) de forma autonoma sin revision por caso (P5=Si); el override Negro aplica aunque el conteo sea 2.",
    # Demos ensenantes few-shot fijos (D-017): el razonamiento explicita la regla que el
    # modelo sub-aplica (P2 cuando el sistema produce un insumo; P5 con supervision ex-post).
    "VAR-FG-D01": "Amarillo: usa datos personales (P1=Si) y, aunque el ejecutivo toma la decision final, el sistema produce un indice que CONDICIONA esa decision sobre el cliente -> influye (P2=Si). Sin proveedor externo (P3=No), sin riesgo legal directo (P4=No) y sin ejecucion autonoma (P5=No); conteo=2 -> Amarillo.",
    "VAR-FG-D02": "Amarillo: la asignacion se ejecuta de forma automatica y la unica supervision es POSTERIOR (auditoria a la manana siguiente), lo que NO es revision por caso -> P5=Si. Usa datos de clientes (P1=Si) pero no influye en una decision sobre la persona (P2=No), sin proveedor externo ni riesgo legal; conteo=2 -> Amarillo. La revision ex-post no baja P5.",
}

# Anotacion de las 5 preguntas Si/No del Marco + alto_impacto por VAR-FG (D-013,
# arquitectura determinista). Cada tupla es (p1, p2, p3, p4, p5, alto_impacto) y es
# conteo-consistente con el color: derive_color(p1..p5, alto_impacto) == label.
# Columnas extra del fast_gate; el resto de etapas no las usa.
_FG_COLS_EXTRA: tuple[str, ...] = ("p1", "p2", "p3", "p4", "p5", "alto_impacto")
_FG_PREGUNTAS: dict[str, tuple[str, str, str, str, str, str]] = {
    "VAR-FG-A01": ("si", "si", "si", "No", "No", "No"),
    "VAR-FG-A02": ("si", "si", "No", "si", "No", "No"),
    "VAR-FG-A03": ("si", "si", "No", "si", "No", "No"),
    "VAR-FG-A04": ("si", "si", "No", "si", "No", "No"),
    "VAR-FG-A05": ("si", "si", "si", "No", "No", "No"),
    "VAR-FG-A06": ("si", "si", "No", "si", "No", "No"),
    "VAR-FG-A07": ("si", "si", "No", "si", "No", "No"),
    "VAR-FG-A08": ("si", "si", "No", "si", "No", "No"),
    "VAR-FG-A09": ("si", "si", "si", "No", "No", "No"),
    "VAR-FG-A10": ("si", "si", "No", "si", "No", "No"),
    "VAR-FG-A11": ("si", "si", "No", "si", "No", "No"),
    "VAR-FG-A12": ("si", "si", "No", "si", "No", "No"),
    "VAR-FG-N01": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-N02": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-N03": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-N04": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-N05": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-N06": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-N07": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-N08": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-N09": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-N10": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-N11": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-R01": ("si", "si", "si", "si", "No", "No"),
    "VAR-FG-R02": ("si", "si", "si", "si", "No", "No"),
    "VAR-FG-R03": ("si", "si", "si", "si", "No", "No"),
    "VAR-FG-R04": ("si", "si", "No", "si", "si", "No"),
    "VAR-FG-R05": ("si", "si", "si", "si", "No", "No"),
    "VAR-FG-R06": ("si", "si", "si", "si", "No", "No"),
    "VAR-FG-R07": ("si", "si", "No", "si", "si", "No"),
    "VAR-FG-R08": ("si", "si", "si", "si", "No", "No"),
    "VAR-FG-R09": ("si", "si", "si", "si", "No", "No"),
    "VAR-FG-R10": ("si", "si", "si", "si", "No", "No"),
    "VAR-FG-R11": ("si", "si", "No", "si", "si", "No"),
    "VAR-FG-V01": ("No", "No", "No", "No", "No", "No"),
    "VAR-FG-V02": ("No", "No", "No", "No", "No", "No"),
    "VAR-FG-V03": ("No", "No", "No", "No", "No", "No"),
    "VAR-FG-V04": ("No", "No", "No", "No", "No", "No"),
    "VAR-FG-V05": ("No", "No", "No", "No", "No", "No"),
    "VAR-FG-V06": ("No", "No", "No", "No", "No", "No"),
    "VAR-FG-V07": ("No", "No", "No", "No", "No", "No"),
    "VAR-FG-V08": ("No", "No", "No", "No", "No", "No"),
    "VAR-FG-V09": ("No", "No", "No", "No", "No", "No"),
    "VAR-FG-V10": ("No", "No", "No", "No", "No", "No"),
    "VAR-FG-V11": ("No", "No", "No", "No", "No", "No"),
    "VAR-FG-V12": ("No", "No", "No", "No", "No", "No"),
    # Bordes de conteo.
    "VAR-FG-V13": ("si", "No", "No", "No", "No", "No"),
    "VAR-FG-V14": ("No", "No", "si", "No", "No", "No"),
    "VAR-FG-V15": ("si", "No", "No", "No", "No", "No"),
    "VAR-FG-A13": ("si", "No", "si", "No", "No", "No"),
    "VAR-FG-A14": ("si", "si", "No", "No", "No", "No"),
    "VAR-FG-A15": ("si", "No", "No", "si", "No", "No"),
    "VAR-FG-R12": ("si", "si", "si", "si", "si", "No"),
    "VAR-FG-R13": ("si", "si", "si", "si", "si", "No"),
    # Romper colinealidad: alto=Si con P5=No -> Rojo/Amarillo (no Negro).
    "VAR-FG-R14": ("si", "si", "si", "si", "No", "si"),
    "VAR-FG-R15": ("si", "si", "si", "si", "No", "si"),
    "VAR-FG-A16": ("si", "si", "No", "No", "No", "si"),
    "VAR-FG-A17": ("si", "si", "si", "No", "No", "si"),
    # Negro por override con conteo distinto de 4.
    "VAR-FG-N12": ("si", "si", "No", "No", "si", "si"),
    "VAR-FG-N13": ("si", "si", "si", "si", "si", "si"),
    # Ampliacion VAL borde (D-015). Rojo<->Negro: P5=Si acotado+reversible -> alto=No.
    "VAR-FG-R16": ("si", "si", "No", "si", "si", "No"),
    "VAR-FG-R17": ("si", "si", "si", "si", "si", "No"),
    "VAR-FG-R18": ("si", "si", "No", "si", "si", "No"),
    "VAR-FG-R23": ("si", "si", "si", "si", "si", "No"),
    # Rojo<->Negro: P5=Si y alto=Si -> Negro (criterios a/b/c/d/e).
    "VAR-FG-N14": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-N15": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-N16": ("si", "si", "si", "si", "si", "si"),
    "VAR-FG-N17": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-N18": ("si", "si", "si", "si", "si", "si"),
    # Colinealidad rota: alto=Si con P5=No -> Rojo/Amarillo (no Negro).
    "VAR-FG-R19": ("si", "si", "si", "si", "No", "si"),
    "VAR-FG-A24": ("si", "si", "No", "si", "No", "si"),
    "VAR-FG-A18": ("si", "si", "No", "No", "No", "si"),
    "VAR-FG-A19": ("si", "si", "si", "No", "No", "si"),
    # Transiciones de conteo Verde<->Amarillo (1<->2).
    "VAR-FG-V16": ("si", "No", "No", "No", "No", "No"),
    "VAR-FG-V17": ("No", "No", "si", "No", "No", "No"),
    "VAR-FG-V18": ("si", "No", "No", "No", "No", "No"),
    "VAR-FG-A20": ("si", "No", "si", "No", "No", "No"),
    "VAR-FG-A21": ("si", "si", "No", "No", "No", "No"),
    # Transiciones de conteo Amarillo<->Rojo (3<->4).
    "VAR-FG-A22": ("si", "si", "No", "si", "No", "No"),
    "VAR-FG-A23": ("si", "si", "si", "No", "No", "No"),
    "VAR-FG-R21": ("si", "si", "si", "si", "No", "No"),
    "VAR-FG-R22": ("si", "si", "si", "si", "No", "No"),
    # Override de Negro con conteo bajo (P5=Si Y alto=Si).
    "VAR-FG-N19": ("si", "si", "No", "No", "si", "si"),
    "VAR-FG-N20": ("si", "No", "No", "No", "si", "si"),
    # D-017: VAL representativo del TEST (VAR-FG-T01..T14).
    # Patron 1: Amarillo con p2 sutil (insumo que un humano usa para decidir -> p2=si).
    "VAR-FG-T01": ("si", "si", "No", "No", "No", "No"),
    "VAR-FG-T02": ("si", "si", "No", "si", "No", "No"),
    "VAR-FG-T03": ("si", "si", "No", "si", "No", "No"),
    # Patron 5: Amarillo con p5 de supervision solo posterior (p5=si, conteo bajo).
    "VAR-FG-T04": ("si", "No", "No", "No", "si", "No"),
    "VAR-FG-T05": ("si", "No", "No", "No", "si", "No"),
    # Patron 2: Rojo con p5 autonomo acotado+reversible (p5=si, alto=No -> Rojo).
    "VAR-FG-T06": ("si", "si", "No", "si", "si", "No"),
    "VAR-FG-T07": ("si", "si", "si", "si", "si", "No"),
    "VAR-FG-T08": ("si", "si", "No", "si", "si", "No"),
    "VAR-FG-T09": ("si", "si", "No", "si", "si", "No"),
    # Patron 3: Negro por escala masiva pese a bandas (alto=si por criterio a).
    "VAR-FG-T10": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-T11": ("si", "si", "No", "si", "si", "si"),
    # Patron 4: Negro por denegacion/restriccion reversible (alto=si por criterio b).
    "VAR-FG-T12": ("si", "si", "No", "si", "si", "si"),
    "VAR-FG-T13": ("si", "si", "No", "si", "si", "si"),
    # Patron 2b: Rojo con apoyo a decision financiera, p5=No (el analista decide).
    "VAR-FG-T14": ("si", "si", "si", "si", "No", "No"),
    # Demos ensenantes few-shot fijos (D-017): Amarillo p2-sutil y Amarillo p5-posterior.
    "VAR-FG-D01": ("si", "si", "No", "No", "No", "No"),
    "VAR-FG-D02": ("si", "No", "No", "No", "si", "No"),
}

# Sub-hechos objetivos de alto_impacto (D-015a). Cada tupla, en el orden de
# `_FG_SUBHECHO_COLS`: (acotado, reversible, escala_masiva, naturaleza_restrictiva,
# decision_financiera, irreversible_sin_intervencion, exposicion_regulatoria, profiling).
# Invariante: derive_alto_impacto(sub_hechos) == alto_impacto de _FG_PREGUNTAS (test en
# test_flujo_intents). SET CURADO de demos few-shot (Fase 2, D-015a): cubre las
# distinciones que el pilot mostro fallando (acotado+reversible -> No aunque financiera;
# escala/profiling/restrictiva -> Si). El resto de casos queda sin anotar (columnas
# vacias) hasta completar los 100 (la metrica ignora estos campos; el few-shot usa
# few_shot_ids fijos sobre este set). Orden de columnas en `dataset._FG_SUBHECHO_COLS`.
_FG_SUBHECHO_COLS: tuple[str, ...] = (
    "acotado",
    "reversible",
    "escala_masiva",
    "naturaleza_restrictiva",
    "decision_financiera",
    "irreversible_sin_intervencion",
    "exposicion_regulatoria",
    "profiling",
)
_FG_SUBHECHOS: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    # Low / alto=No (acotado=No, sin criterios) -- ensena el piso.
    "VAR-FG-V03": ("No", "No", "No", "No", "No", "No", "No", "No"),
    "VAR-FG-A01": ("No", "si", "No", "No", "No", "No", "No", "No"),
    # GATE acotado+reversible -> alto=No AUNQUE sea financiera (la distincion clave).
    "VAR-FG-R07": ("si", "si", "No", "No", "si", "No", "No", "No"),
    "VAR-FG-R04": ("si", "si", "No", "No", "si", "No", "No", "No"),
    "VAR-FG-D02": ("si", "si", "No", "No", "No", "No", "No", "No"),
    # alto=si por escala (>10% base / >=100k) sin acotamiento.
    "VAR-FG-N01": ("No", "No", "si", "No", "si", "No", "No", "No"),
    # alto=si por naturaleza financiera + irreversibilidad (reintegro ejecutado).
    "VAR-FG-N03": ("No", "No", "No", "No", "si", "si", "No", "No"),
    # alto=si por naturaleza restrictiva (denegacion de credito) + profiling.
    "VAR-FG-N05": ("No", "No", "No", "si", "si", "No", "No", "si"),
    # alto=si por restrictiva + profiling AUNQUE p5=No (rompe colinealidad alto<->Negro).
    "VAR-FG-R14": ("No", "No", "No", "si", "si", "No", "No", "si"),
    # alto=si por escala + profiling aunque el sistema no actue (publica scores), p5=No.
    "VAR-FG-A16": ("No", "si", "si", "No", "No", "No", "No", "si"),
    # alto=si por restrictiva (corte de beneficio al empleado).
    "VAR-FG-N12": ("No", "No", "No", "si", "No", "No", "No", "No"),
}

for _c in FAST_GATE:
    if _c["id"] in _FG_RAZONAMIENTO:
        _c["razonamiento"] = _FG_RAZONAMIENTO[_c["id"]]
    if _c["id"] in _FG_PREGUNTAS:
        for _col, _val in zip(_FG_COLS_EXTRA, _FG_PREGUNTAS[_c["id"]], strict=True):
            _c[_col] = _val
    if _c["id"] in _FG_SUBHECHOS:
        for _col, _val in zip(_FG_SUBHECHO_COLS, _FG_SUBHECHOS[_c["id"]], strict=True):
            _c[_col] = _val


STAGE_CASES: dict[str, list[dict[str, str]]] = {
    "intake": INTAKE,
    "triage_solidez": SOLIDEZ,
    "triage_factibilidad": FACTIBILIDAD,
    "fast_gate": FAST_GATE,
}


def write_variations(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for stage, cases in STAGE_CASES.items():
        # fast_gate agrega las 5 preguntas + alto_impacto (rule_derived, D-013) + los
        # sub-hechos de alto_impacto (rule_derived_alto, D-015a; vacios salvo demos curados).
        extra = list(_FG_COLS_EXTRA) + list(_FG_SUBHECHO_COLS) if stage == "fast_gate" else []
        header = [*_FICHA_COLS, *extra, "label", "razonamiento", "split"]
        path = out_dir / f"flujo_intents_{stage}_var.csv"
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header, delimiter=";")
            writer.writeheader()
            for c in cases:
                writer.writerow({k: c.get(k, "" if k in extra else "false") for k in header})
        written[stage] = path
    return written


def main() -> None:
    pkg_dir = Path(__file__).resolve().parent.parent  # dspy_gepa_poc/
    out_dir = pkg_dir / "datasets" / "variations"
    written = write_variations(out_dir)
    from collections import Counter

    for stage, path in written.items():
        labels = Counter(c["label"] for c in STAGE_CASES[stage])
        splits = Counter(c["split"] for c in STAGE_CASES[stage])
        print(f"[{stage}] {path.name}: labels={dict(labels)} splits={dict(splits)}")


if __name__ == "__main__":
    main()
