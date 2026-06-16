"""Tests de flujo-intents: serializacion, mapeo por etapa, aprobacion y orquestacion.

Deterministas y sin LLM: la logica de encadenamiento se prueba con un stage_runner
falso, y el mapeo rechazo->etapa con las funciones puras del dataset builder.
"""

from __future__ import annotations

import csv

import pytest

from dspy_gepa_poc.flujo_intents import normalize_color, serialize_ficha
from dspy_gepa_poc.flujo_intents.aprobacion import resolve_aprobacion
from dspy_gepa_poc.flujo_intents.dataset import (
    PASS_LABEL,
    REJ_STAGE_MAP,
    STAGE_LABEL_FIELD,
    STAGE_ORDER,
    _stage_rows_for_rejection,
)
from dspy_gepa_poc.flujo_intents.fast_gate_rule import derive_color
from dspy_gepa_poc.flujo_intents.orchestrator import load_master_config, run_flow
from shared.paths import get_dspy_paths

MASTER_CONFIG = "dspy_gepa_poc/flujo_intents/flujo_intents.yaml"


# --- ficha -------------------------------------------------------------------


def test_serialize_ficha_incluye_campos_clave():
    row = {
        "nombre_iniciativa": "Asistente X",
        "tipo_intent_operativo": "true",
        "declaracion_intent": "Sistema que resume reportes.",
        "metricas_de_exito": "Tiempo -50%",
        "datos_requeridos_datos_personales": "true",
    }
    text = serialize_ficha(row)
    assert "Asistente X" in text
    assert "Operativo" in text
    assert "Sistema que resume reportes." in text
    assert "personales" in text


def test_serialize_ficha_marca_campos_vacios_y_sin_datos():
    text = serialize_ficha({"nombre_iniciativa": "N"})
    assert "(vacio)" in text  # campos de texto ausentes
    assert "(ninguno declarado)" in text  # sin flags de datos
    assert "(no declarado)" in text  # sin tipo de intent


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Verde", "Verde"),
        ("Negro (escalada §7.3 desde Rojo)", "Negro"),
        ("Amarillo (track simplificado §7.7)", "Amarillo"),
        ("Verde (caso pre-clasificado §7.4)", "Verde"),
    ],
)
def test_normalize_color_variantes(raw, expected):
    assert normalize_color(raw) == expected


def test_normalize_color_invalido_levanta():
    with pytest.raises(ValueError):
        normalize_color("mrios@trix.com")


# --- dataset: mapeo rechazo -> etapa -----------------------------------------


def test_rej_stage_map_cubre_los_rechazos_originales():
    # 7 rechazos con etapa terminal. Salieron del mapeo (esperan etapas nuevas
    # diferidas, ver historial/sdd.md D-014 y SPEC-102): TC-REJ-06 (no requiere IA,
    # no es criterio de solidez del Marco) y TC-REJ-09/10 (§9.2 uso prohibido / §7.4
    # duplicado, admisibilidad, no es factibilidad tecnica).
    assert len(REJ_STAGE_MAP) == 7
    assert all(rid.startswith("TC-REJ-") for rid in REJ_STAGE_MAP)
    assert {"TC-REJ-06", "TC-REJ-09", "TC-REJ-10"}.isdisjoint(REJ_STAGE_MAP)


def test_rechazo_propaga_pasa_en_etapas_previas_y_corta_en_terminal():
    # TC-REJ-07 termina en factibilidad (no_avanza): intake/solidez = 'pasa',
    # factibilidad = label terminal, fast_gate ausente.
    labels = _stage_rows_for_rejection("TC-REJ-07")
    assert labels["intake"] == PASS_LABEL["intake"]
    assert labels["triage_solidez"] == PASS_LABEL["triage_solidez"]
    assert labels["triage_factibilidad"] == "no_avanza"
    assert "fast_gate" not in labels


def test_rechazo_intake_no_aparece_en_etapas_posteriores():
    # TC-REJ-01 termina en intake: solo intake presente.
    labels = _stage_rows_for_rejection("TC-REJ-01")
    assert labels == {"intake": "incompleta"}


def test_todo_rechazo_termina_en_etapa_valida():
    for rid, (stage, _label) in REJ_STAGE_MAP.items():
        assert stage in STAGE_ORDER, rid


# --- aprobacion --------------------------------------------------------------


@pytest.fixture
def aprobacion_mapping():
    return load_master_config(MASTER_CONFIG)["aprobacion"]["mapping"]


def test_aprobacion_verde_es_automatica(aprobacion_mapping):
    res = resolve_aprobacion("Verde", aprobacion_mapping)
    assert res["decision"] == "aprobado"
    assert res["nivel_requerido"] == "automatico"


@pytest.mark.parametrize("color", ["Amarillo", "Rojo", "Negro"])
def test_aprobacion_no_verde_es_recomendacion(color, aprobacion_mapping):
    res = resolve_aprobacion(color, aprobacion_mapping)
    assert res["decision"] == "recomendacion"
    assert res["nivel_requerido"]
    assert res["dictamen"]


def test_aprobacion_color_invalido_levanta(aprobacion_mapping):
    with pytest.raises(ValueError):
        resolve_aprobacion("Azul", aprobacion_mapping)


# --- orquestador: encadenamiento ---------------------------------------------


@pytest.fixture
def flujo_cfg():
    return load_master_config(MASTER_CONFIG)


def _runner(values: dict[str, str]):
    return lambda name, ficha: values.get(name, "")


def _run(flujo_cfg, values):
    return run_flow(
        ficha="f",
        stages=flujo_cfg["stages"],
        skip_value=flujo_cfg["skip_value"],
        aprobacion_mapping=flujo_cfg["aprobacion"]["mapping"],
        stage_runner=_runner(values),
    )


def test_flujo_completo_verde_aprueba(flujo_cfg):
    res = _run(
        flujo_cfg,
        {
            "intake": "admitida",
            "triage_solidez": "solido",
            "triage_factibilidad": "avanza_fast_gate",
            "fast_gate": "Verde",
        },
    )
    assert res["aprobacion"]["decision"] == "aprobado"


def test_flujo_corta_en_solidez_inyecta_skip(flujo_cfg):
    res = _run(flujo_cfg, {"intake": "admitida", "triage_solidez": "devolucion_reformulacion"})
    skip = flujo_cfg["skip_value"]
    assert res["triage_solidez"] == "devolucion_reformulacion"
    assert res["triage_factibilidad"] == skip
    assert res["fast_gate"] == skip
    assert res["aprobacion"]["decision"] == "detenido"


def test_flujo_corta_en_intake_todo_skip(flujo_cfg):
    res = _run(flujo_cfg, {"intake": "incompleta"})
    skip = flujo_cfg["skip_value"]
    assert res["intake"] == "incompleta"
    assert res["triage_solidez"] == skip
    assert res["triage_factibilidad"] == skip
    assert res["fast_gate"] == skip
    assert res["aprobacion"]["decision"] == "detenido"
    assert "intake" in res["aprobacion"]["dictamen"]


# --- integridad de los datasets generados (sin fuga) -------------------------

_DATASET_STAGES = ["intake", "triage_solidez", "triage_factibilidad", "fast_gate"]


def _load_stage_csv(stage: str) -> list[dict[str, str]]:
    path = get_dspy_paths().datasets / f"flujo_intents_{stage}.csv"
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("stage", _DATASET_STAGES)
def test_dataset_sin_fuga_train_val_vs_test(stage):
    rows = _load_stage_csv(stage)
    # Invariante real (no por prefijo): ninguna ficha de train/val aparece en test.
    # Vale tanto para el holdout de originales (intake/solidez/fast_gate) como para el
    # holdout balanceado a mano de factibilidad (split=test en las variaciones).
    trainval = {r["ficha"] for r in rows if r["split"] in {"train", "val"}}
    test = {r["ficha"] for r in rows if r["split"] == "test"}
    assert not (trainval & test), f"{stage}: fichas compartidas train/val<->test (fuga)"


@pytest.mark.parametrize("stage", _DATASET_STAGES)
def test_dataset_tiene_los_tres_splits(stage):
    rows = _load_stage_csv(stage)
    splits = {r["split"] for r in rows}
    assert {"train", "val", "test"} <= splits, f"{stage}: faltan splits {splits}"
    # La etiqueta de la etapa nunca esta vacia.
    label_field = STAGE_LABEL_FIELD[stage]
    assert all(r[label_field].strip() for r in rows), f"{stage}: hay label vacio"


# --- fast_gate: regla determinista (color derivado de P1..P5 + alto impacto) -------


@pytest.mark.parametrize(
    "p,ai,expected",
    [
        ((0, 0, 0, 0, 0), False, "Verde"),  # 0 sies
        ((1, 0, 0, 0, 0), False, "Verde"),  # 1 si
        ((1, 1, 0, 0, 0), False, "Amarillo"),  # 2 sies
        ((1, 1, 1, 0, 0), False, "Amarillo"),  # 3 sies
        ((1, 1, 1, 1, 0), False, "Rojo"),  # 4 sies
        ((1, 1, 1, 1, 1), False, "Rojo"),  # 5 sies, P5 pero sin alto impacto
        ((1, 1, 1, 1, 1), True, "Negro"),  # 5 sies, P5 + alto impacto
        ((1, 1, 0, 0, 1), True, "Negro"),  # suma 3 pero P5 + alto impacto (override, TC-N-06)
        ((0, 0, 0, 0, 1), True, "Negro"),  # P5 + alto impacto solos
        ((1, 1, 1, 1, 0), True, "Rojo"),  # alto impacto sin P5 no escala a Negro
    ],
)
def test_derive_color_tabla_de_verdad(p, ai, expected):
    assert derive_color(*p, ai) == expected


def test_derive_color_acepta_si_no_strings():
    assert derive_color("si", "si", "No", "No", "No", "No") == "Amarillo"
    assert derive_color("Si", "si", "si", "si", "si", "si") == "Negro"


def test_derive_color_reproduce_el_lote_anotado():
    # fast_gate_v1.csv tiene P1..P5 anotadas (fuente de las etiquetas del test).
    # La regla debe reproducir el color de los 32 casos usando alto_impacto=(color==Negro):
    # todos los Negro tienen P5=Si, y V/A/R salen del conteo.
    path = get_dspy_paths().datasets / "fast_gate_v1.csv"
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows, "fast_gate_v1.csv vacio"
    for r in rows:
        gold = r["clasificacion"].strip()
        alto_impacto = "si" if gold == "Negro" else "No"
        ps = [r[c] for c in ("p1", "p2", "p3", "p4", "p5")]
        got = derive_color(*ps, alto_impacto)
        assert got == gold, f"{r['case_id']}: derive={got} != gold={gold} (p={ps})"


def test_flujo_rojo_recomendacion_con_nivel(flujo_cfg):
    res = _run(
        flujo_cfg,
        {
            "intake": "admitida",
            "triage_solidez": "solido",
            "triage_factibilidad": "avanza_fast_gate",
            "fast_gate": "Rojo",
        },
    )
    assert res["aprobacion"]["decision"] == "recomendacion"
    assert "Legal" in res["aprobacion"]["nivel_requerido"]
