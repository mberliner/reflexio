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


def test_build_stage_csv_preserva_holdout_sin_originales(tmp_path):
    # Sin fuente externa de originales, regenerar fast_gate debe preservar el test ya
    # commiteado (no omitir la etapa) para que train/val se regeneren sin depender de
    # FLUJO_INTENTS_ORIGINALS_DIR (no atar la regeneracion al entorno).
    import shutil

    from dspy_gepa_poc.flujo_intents.dataset import build_stage_csv

    src = get_dspy_paths().datasets
    (tmp_path / "variations").mkdir()
    shutil.copy(
        src / "variations" / "flujo_intents_fast_gate_var.csv",
        tmp_path / "variations" / "flujo_intents_fast_gate_var.csv",
    )
    shutil.copy(src / "flujo_intents_fast_gate.csv", tmp_path / "flujo_intents_fast_gate.csv")
    test_before = [
        r for r in _read_csv_comma(tmp_path / "flujo_intents_fast_gate.csv") if r["split"] == "test"
    ]

    # originals vacio simula la fuente externa ausente.
    out = build_stage_csv("fast_gate", tmp_path / "variations", tmp_path, {"fast_gate": []})
    assert out is not None, "fast_gate omitida: no preservo el holdout"
    test_after = [r for r in _read_csv_comma(out) if r["split"] == "test"]
    assert test_after == test_before, "el holdout cambio al regenerar sin originales"


def _read_csv_comma(path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


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


# --- alto_impacto: descomposicion en sub-hechos objetivos (D-015a) ----------------


@pytest.mark.parametrize(
    "kw,expected",
    [
        # Gate: acotado + reversible -> No, SALVO override por restrictiva/irreversible.
        ({"acotado": True, "reversible": True}, False),
        # financiera acotada+reversible NO es alto impacto (no override-ea):
        ({"acotado": True, "reversible": True, "decision_financiera": True}, False),
        # escala/profiling NO override-ean el gate:
        ({"acotado": True, "reversible": True, "escala_masiva": True, "profiling": True}, False),
        # override (b): corte/denegacion/restriccion aun acotado+reversible:
        ({"acotado": True, "reversible": True, "naturaleza_restrictiva": True}, True),
        # override (c): irreversibilidad:
        ({"acotado": True, "reversible": True, "irreversible_sin_intervencion": True}, True),
        # Sin gate (no acotado o no reversible): cualquier criterio (a)-(e) -> Si.
        ({"escala_masiva": True}, True),  # (a) escala
        ({"naturaleza_restrictiva": True}, True),  # (b) naturaleza restrictiva
        ({"decision_financiera": True}, True),  # (b) financiera no acotada
        ({"irreversible_sin_intervencion": True}, True),  # (c) irreversibilidad
        ({"exposicion_regulatoria": True}, True),  # (d) regulatorio
        ({"profiling": True}, True),  # (e) profiling
        ({}, False),  # ningun criterio
        ({"acotado": True}, False),  # acotado pero NO reversible y sin criterios
    ],
)
def test_derive_alto_impacto_tabla_de_verdad(kw, expected):
    from dspy_gepa_poc.flujo_intents.fast_gate_rule import derive_alto_impacto

    assert derive_alto_impacto(**kw) is expected


def test_derive_alto_impacto_acepta_si_no_strings():
    from dspy_gepa_poc.flujo_intents.fast_gate_rule import derive_alto_impacto

    # Reusa _is_true: 'si'/'No'/'true'/'1'/bool.
    assert derive_alto_impacto(escala_masiva="si") is True
    assert derive_alto_impacto(acotado="Si", reversible="si") is False
    assert derive_alto_impacto(acotado="si", reversible="si", naturaleza_restrictiva="si") is True


def test_derive_alto_impacto_from_row():
    from dspy_gepa_poc.flujo_intents.fast_gate_rule import derive_alto_impacto_from_row

    row = {"acotado": "si", "reversible": "si", "irreversible_sin_intervencion": "si"}
    assert derive_alto_impacto_from_row(row) is True
    assert derive_alto_impacto_from_row({"profiling": "No"}) is False


def test_rule_derived_module_exige_preguntas_en_outputs():
    from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory

    sig = {
        "instruction": "x",
        "inputs": [{"name": "ficha"}],
        "outputs": [{"name": "clasificacion"}],  # faltan p1..p5 + alto_impacto
    }
    with pytest.raises(ValueError, match="rule_derived requiere"):
        DynamicModuleFactory.create_rule_derived_module(sig)


def test_rule_derived_module_construye_con_outputs_completos():
    from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory

    outs = ["p1", "p2", "p3", "p4", "p5", "alto_impacto", "razonamiento", "clasificacion"]
    sig = {
        "instruction": "x",
        "inputs": [{"name": "ficha"}],
        "outputs": [{"name": n} for n in outs],
    }
    module = DynamicModuleFactory.create_rule_derived_module(sig)
    assert module is not None
    # 'clasificacion' NO es output del predictor (se deriva); el resto si.
    assert "clasificacion" not in module._predicted
    assert {"p1", "p5", "alto_impacto"} <= set(module._predicted)


class _FakeSubhechoPredictor:
    """Predictor falso para el modulo rule_derived_alto: devuelve respuestas fijas."""

    def __init__(self, **answers):
        self._answers = answers

    def __call__(self, **_kwargs):
        import dspy

        return dspy.Prediction(**self._answers)


def test_rule_derived_alto_module_exige_subhechos_en_outputs():
    from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory

    sig = {
        "instruction": "x",
        "inputs": [{"name": "ficha"}],
        # faltan los sub-hechos (solo p1..p5 + derivados):
        "outputs": [{"name": n} for n in ("p1", "p2", "p3", "p4", "p5", "clasificacion")],
    }
    with pytest.raises(ValueError, match="rule_derived_alto requiere"):
        DynamicModuleFactory.create_rule_derived_alto_impacto_module(sig)


def _alto_sig():
    from dspy_gepa_poc.flujo_intents.fast_gate_rule import ALTO_IMPACTO_SUBHECHO_FIELDS

    outs = [
        "p1",
        "p2",
        "p3",
        "p4",
        "p5",
        *ALTO_IMPACTO_SUBHECHO_FIELDS,
        "razonamiento",
        "alto_impacto",
        "clasificacion",
    ]
    return {
        "instruction": "x",
        "inputs": [{"name": "ficha"}],
        "outputs": [{"name": n} for n in outs],
    }


def test_rule_derived_alto_module_no_predice_los_derivados():
    from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory

    module = DynamicModuleFactory.create_rule_derived_alto_impacto_module(_alto_sig())
    assert "alto_impacto" not in module._predicted
    assert "clasificacion" not in module._predicted
    assert {"acotado", "reversible", "p5"} <= set(module._predicted)


def test_rule_derived_alto_module_deriva_ambos_campos():
    from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory

    module = DynamicModuleFactory.create_rule_derived_alto_impacto_module(_alto_sig())
    # P5=Si + escala_masiva (sin gate acotado+reversible) -> alto_impacto=si.
    # 5 sies (p1..p5) + alto -> Negro.
    module.predictor = _FakeSubhechoPredictor(
        p1="si",
        p2="si",
        p3="si",
        p4="si",
        p5="si",
        acotado="No",
        reversible="No",
        escala_masiva="si",
        naturaleza_restrictiva="No",
        decision_financiera="No",
        irreversible_sin_intervencion="No",
        exposicion_regulatoria="No",
        profiling="No",
        razonamiento="x",
    )
    pred = module(ficha="cualquiera")
    assert pred.alto_impacto == "si"
    assert pred.clasificacion == "Negro"


def test_rule_derived_alto_module_gate_acotado_reversible():
    from dspy_gepa_poc.dynamic_factory import DynamicModuleFactory

    module = DynamicModuleFactory.create_rule_derived_alto_impacto_module(_alto_sig())
    # acotado+reversible sin override -> alto_impacto=No; P5=Si, 5 sies pero sin alto -> Rojo.
    module.predictor = _FakeSubhechoPredictor(
        p1="si",
        p2="si",
        p3="si",
        p4="si",
        p5="si",
        acotado="si",
        reversible="si",
        escala_masiva="si",
        naturaleza_restrictiva="No",
        decision_financiera="si",
        irreversible_sin_intervencion="No",
        exposicion_regulatoria="No",
        profiling="No",
        razonamiento="x",
    )
    pred = module(ficha="cualquiera")
    assert pred.alto_impacto == "No"
    assert pred.clasificacion == "Rojo"


def test_dataset_fast_gate_color_consistente_con_preguntas():
    # Invariante de la arquitectura rule_derived: en todo el dataset de fast_gate, el
    # color gold se reproduce contando las P1..P5 + alto_impacto anotadas.
    from dspy_gepa_poc.flujo_intents.fast_gate_rule import derive_color_from_row

    rows = _load_stage_csv("fast_gate")
    annotated = [r for r in rows if r["p1"].strip()]
    assert len(annotated) == len(rows), "hay filas de fast_gate sin P1..P5 anotadas"
    for r in rows:
        assert derive_color_from_row(r) == r["clasificacion"].strip(), r["case_id"]


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


def test_fixfs_config_few_shot_ids_existen_en_train():
    # El config de few-shot FIJOS (D-017) pina demos por case_id. Invariante: todos los
    # few_shot_ids deben existir en el dataset y pertenecer al split train (LabeledFewShot
    # y la inyeccion fija solo pueden usar el trainset como demos).
    import yaml

    cfg_path = get_dspy_paths().configs / "flujo_intents_fast_gate_rule_fixfs_v1.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    ids = cfg["optimization"]["few_shot_ids"]
    assert len(ids) == len(set(ids)), "few_shot_ids con duplicados"

    rows = _load_stage_csv("fast_gate")
    train_ids = {r["case_id"] for r in rows if r["split"] == "train"}
    faltan = [cid for cid in ids if cid not in train_ids]
    assert not faltan, f"few_shot_ids ausentes del split train: {faltan}"
