# SPEC-102-flujo-intents — Atencion multipaso de intents (Marco de Gobierno IA)

Estado: draft
Iteracion: 1 (rev. 2026-06-14)
Relacionada con: ../analisis/Transformacion AI-Native Org/normativa/MARCO_GOBIERNO_IA.md (§5, §7, §9)

## User Story (prioridad)

Como laboratorio que necesita probar y calibrar un agente que atienda intents de
punta a punta antes de productivizarlo, quiero un pipeline de 5 etapas DSPy agnosticas
(intake, triage_solidez, triage_factibilidad, fast_gate, aprobacion), cada una
optimizable por GEPA por separado y encadenable por una config maestra, para poder
cambiar la logica de negocio reetiquetando casos y re-optimizando prompts en vez de
reescribir codigo.
Prioridad: P2

## Requisitos funcionales

- FR-001 Cada etapa LLM MUST ser optimizable con la interfaz actual
  (`python -m dspy_gepa_poc.reflexio_declarativa --config <etapa>.yaml`). Intake,
  triage_solidez y triage_factibilidad son `module.type: dynamic` (`ficha -> decision`
  + `razonamiento`). El **Fast Gate** MUST implementar la regla canonica del Marco como
  `module.type: rule_derived` (decision 2026-06-16, D-013): el LLM responde las 5
  preguntas Si/No del Fast Gate + `alto_impacto`, y la funcion pura
  `flujo_intents/fast_gate_rule.derive_color` deriva el color por conteo. Las preguntas
  (`p1..p5`, `alto_impacto`) son gold del dataset, conteo-consistentes con el color, NO
  diagnosticos ignorados. [Revierte la decision previa "clasificar color directo sin
  conteo en codigo", que daba Rojo->Amarillo opaco; ver `historial/sdd.md` D-013.]
- FR-001b Regla canonica del Fast Gate (Marco de Gobierno de IA). Contar los "Si" de:
  P1 (datos personales o de clientes), P2 (influye en decision sobre cliente/empleado),
  P3 (herramientas/proveedores fuera del catalogo aprobado; default: intent nuevo sin
  dato => homologado => No; "ya implementado" o externo/no homologado => Si), P4 (riesgo
  legal o reputacional si falla), P5 (ejecuta sin revision humana por caso). Mapeo: 0-1
  Verde / 2-3 Amarillo / 4-5 Rojo; **Negro = P5=Si Y alto impacto** (override del conteo).
  Alto impacto = al menos uno de: escala (>=10% de la base o >=100.000 clientes),
  naturaleza (decision financiera / corte de servicio / denegacion de acceso /
  restriccion de derechos), irreversibilidad sin intervencion manual, exposicion a
  sancion regulatoria directa, o profiling automatizado de personas.
- FR-002 Ratio por etapa ~40/20/40 (objetivo train 30 / val 15 / test 30). El `test`
  MUST derivarse de los originales (`intake_clasificacion.csv` + `triage_rechazos.csv`)
  recortados a 30 de forma estratificada (preservando clases minoritarias). El
  `train`/`val` MUST provenir de variaciones a mano. Sin fuga: ningun original en
  train/val ni variacion en test.
- FR-003 El mapeo rechazo->etapa terminal MUST ser explicito por id (autoritativo) y un
  rechazo MUST etiquetar 'pasa' en las etapas previas a su terminal y NO aparecer en las
  posteriores.
- FR-004 La etapa `aprobacion` MUST ser un mapeo determinista color->(decision,
  nivel_requerido, dictamen) leido de la config maestra (no se entrena). Verde MUST
  auto-aprobar; Amarillo/Rojo/Negro MUST emitir recomendacion no vinculante con nivel.
- FR-005 El orquestador MUST leer SOLO la config maestra (`flujo_intents/flujo_intents.yaml`),
  encadenar las etapas con gates y, al cortar una etapa, inyectar `skip_value` en las
  posteriores sin ejecutarlas.
- FR-006 La logica de encadenamiento (`run_flow`) MUST ser pura respecto del LLM (via un
  `stage_runner` inyectable), testeable sin llamadas reales.

## Criterios de exito (medibles, agnosticos a tecnologia)

- SC-001 Las 4 configs de etapa cargan con `AppConfig` y sus datasets cargan con
  `CSVDataLoader` (train/val/test no vacios donde corresponde).
- SC-002 Cada etapa parte en ~40/20/40 (train 30 / val 15 / test 30): test son
  originales (`TC-*`) recortados a 30 estratificado; train/val son variaciones a mano
  (`VAR-*`). Sin fuga: ningun `VAR-*` en test ni `TC-*` en train/val.
- SC-003 `run_flow` produce: Verde->aprobado/automatico; Rojo->recomendacion con nivel
  que incluye Legal; corte en una etapa->`detenido` con `skip_value` aguas abajo.
- SC-004 Existe al menos un test por: serializacion, normalize_color, mapeo
  rechazo->etapa, aprobacion (4 colores + invalido) y cada escenario de corte.

## Escenarios (Given/When/Then)

- Given una ficha completa y de bajo riesgo, When corre el flujo, Then todas las etapas
  pasan y `aprobacion` es aprobado/automatico (Verde).
- Given una ficha con la declaracion del intent vacia, When corre intake, Then corta con
  `incompleta` y las etapas posteriores quedan en `skip_value`.
- Given una ficha que describe tecnologia en vez de resultado, When corre el triage de
  solidez, Then corta con `devolucion_reformulacion`.
- Given un color Rojo del Fast Gate, When corre aprobacion, Then emite recomendacion no
  vinculante con nivel N2+Legal+Regulacion+Seguridad+N1.

## Coverage mapping (requisito -> derivado)

| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | `dspy_gepa_poc/configs/flujo_intents_{intake,triage_solidez,triage_factibilidad}.yaml` (dynamic) |
| FR-001 / FR-001b | Fast Gate rule_derived: `configs/flujo_intents_fast_gate_rule_v1.yaml`, `flujo_intents/fast_gate_rule.py::derive_color`, `DynamicModuleFactory.create_rule_derived_module`; `make_variations._FG_PREGUNTAS` (gold P1..P5+alto_impacto); `test_derive_color_*`, `test_rule_derived_module_*`, `test_dataset_fast_gate_color_consistente_con_preguntas` |
| FR-002 | `flujo_intents/dataset.py` (split test=originales) + `flujo_intents/make_variations.py`; `test_flujo_intents.py` |
| FR-003 | `dataset.py::REJ_STAGE_MAP`, `_stage_rows_for_rejection`; `test_rechazo_propaga_*`, `test_rechazo_intake_no_aparece_*` |
| FR-004 | `flujo_intents/aprobacion.py` + `flujo_intents/flujo_intents.yaml`; `test_aprobacion_*` |
| FR-005 | `flujo_intents/orchestrator.py::run_flow` (gates/skip); `test_flujo_corta_*` |
| FR-006 | `run_flow` recibe `stage_runner`; toda `test_flujo_*` corre sin LLM |
| SC-001 | validacion en vivo (AppConfig + CSVDataLoader) |
| SC-002 | `build_test_rows` (distribuciones); ids `VAR-*` vs `TC-*` |
| SC-003 | `test_flujo_completo_verde_aprueba`, `test_flujo_rojo_recomendacion_con_nivel`, `test_flujo_corta_*` |
| SC-004 | `tests/test_flujo_intents.py` (43 tests, incl. derive_color y rule_derived) |

## Pendientes (deuda para proximas iteraciones)

- Desbalance del holdout (hallazgo 2026-06-15): el split real por etapa es 30/15/30 con
  train/val balanceados por clase, pero el `test` (originales `TC-*`) esta dominado por la
  clase "pasa": intake 28/2 (admitida), solidez 26/3/1 (solido), factibilidad 26/1/1/2
  (avanza_fast_gate); solo fast_gate tiene test balanceado (8/7/7/8). Consecuencia: Rob%
  debe leerse contra el baseline de clase mayoritaria, no contra Base%. Medido asi, la
  optimizacion de factibilidad (Rob 46,67% vs trivial 86,7%) y solidez (76,67% vs 86,7%)
  queda POR DEBAJO del trivial; fast_gate (67,5% vs azar 26,7%) e intake (100% vs 93,3%,
  fragil por solo 2 negativos) si superan. MUST no promover factibilidad ni solidez
  optimizados a produccion (dejar `baseline` en la config maestra) hasta rebalancear el
  holdout o reportar accuracy por clase.
- Optimizar cada etapa con GEPA y reportar accuracy en el holdout por clase (no solo
  global), corriendo N seeds (`docs/PROTOCOLO_N_SEEDS.md`): fast_gate y factibilidad solo
  tienen 1-2 runs y Std alto.
- Simulacion de aprobacion humana (N2/Legal/N1) y registro en Inventario (§6.2): fuera de
  alcance de esta iteracion.
