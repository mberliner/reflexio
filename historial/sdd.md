# Historial SDD — log evolutivo y deuda arrastrada

Registro vivo de la adopcion de SDD en el proyecto. Dos partes:

1. **Deuda arrastrada**: pendientes que se re-explicitan en cada entrada hasta
   resolverse. Es el mecanismo anti "cascada encubierta": un pendiente no
   desaparece por olvido, sigue listado hasta que alguien lo cierra o lo descarta
   con justificacion. SSOT del protocolo: `../docs/SDD_PROTOCOLO.md`.
2. **Log de fases**: entradas datadas (YYYY-MM-DD) con que cambio y por que.

Regla: cuando una entrega produce un bloque `[SDD-Check]` con "Deuda arrastrada"
distinta de "ninguna", ese item MUST aparecer en la tabla de abajo. Al
resolverse, se mueve a "Deuda resuelta" con la fecha y el cierre.

---

## Deuda arrastrada (abierta)

| ID | Descripcion | Origen | Estado |
|---|---|---|---|
| D-001 | Datasets CV `_v2` con `gold_verificado=no` pendientes de revision humana | Protocolo N seeds (`docs/PROTOCOLO_N_SEEDS.md`) | Abierta — bloquea conclusiones definitivas sobre v2 |
| D-005 | Naming definitivo de `dspy_gepa_poc`: el sufijo "POC" ya no refleja el estado. Opciones evaluadas: `dspy_gepa`, `reflexio_dspy`. Impacto: renombrar modulo + imports en todo el repo. Esfuerzo medio | `docs/MEJORAS_PENDIENTES_DSPY_GEPA_POC.md` (T2-2, eliminado) | Abierta |
| D-006 | Reducir duplicacion restante: ~70 lineas de data loading (60% similitud) y ~200 de orquestacion (50%) entre subproyectos. Riesgo bajo. Esfuerzo medio | `docs/MEJORAS_PENDIENTES_DSPY_GEPA_POC.md` (T3-4, eliminado) | Abierta |
| D-012 | Optimizar cada etapa de flujo-intents con GEPA y medir accuracy en el holdout (42 originales); ampliar variaciones a mano si una etapa queda starved (train actual 4-8 casos/etapa) | `SPEC-102-flujo-intents` | Cerrada 2026-06-16 — GEPA corrido por etapa sobre los datasets alineados (gpt-4.1-mini tarea / gpt-4o profesor). Factibilidad generaliza (TEST 79->87,5-91,7); solidez en techo (TEST 95). Fast_gate sigue overfiteando -> frente abierto en D-013 |
| D-008 | Inconsistencias de criterio entre docs: regla de baseline (>80% en `LECCIONES_APRENDIDAS.md` seccion 8 vs >90% en `CUANDO_APLICAR_Y_CASOS_DE_USO.md`); donde viven los limites de longitud de texto (env-only segun `YAML_CONFIG_REFERENCE.md` vs YAML segun `UNIVERSAL_OPTIMIZER.md` y `LECCIONES_APRENDIDAS.md` seccion 4); campos soportados en codigo sin documentar (`models.max_tokens` GEPA, `skip_perfect_score` DSPy); `YAML_CONFIG_REFERENCE.md` lista module types `sentiment`/`extractor`/`qa` que `reflexio_declarativa.py` rechaza en runtime (solo `dynamic`/`pipeline`) | Auditoria de docs 2026-06-10 | Abierta |
| D-009 | Redundancia documental: `DSPY_DOCUMENTACION.md` y `GEPA_DOCUMENTACION.md` contienen material del framework upstream (instalacion, testing, citacion) que duplica SSOTs propios y una nota de cache contraria al default del proyecto; tabla de precios duplicada (`ANALISIS_UTILIDADES.md` vs `ROI_ANALYSIS.md` vs `DEFAULT_PRICING` en codigo); links relativos rotos en `gepa_standalone/README.md` y referencia `docs/GEPA_DOCUMENTACION.md` con base ambigua en el listado final de `gepa_standalone/docs/demo.sh`; referencia muerta `run_email_urgency_comparison.sh` en `LECCIONES_APRENDIDAS.md` seccion 7; typo en nombre de `docs/plan_implementcion_toma_requerimientos.md`; intro duplicada ES/EN en `README.md` raiz; parrafo obsoleto "cuando crear la primera spec" en `docs/SDD_PROTOCOLO.md` Tramo 2 (SPEC-100/101 ya existen) | Auditoria de docs 2026-06-10 | Abierta |
| D-010 | Datasets espejo entre subproyectos sin convencion registrada: 5 CSV son copias byte-identicas deliberadas (`cv_extraction_v3`, `cv_profile_v3`, `email_urgency`, `fast_gate_v1`, `triage_v1`) pero nada documenta ni protege la sincronizacion (riesgo de divergencia silenciosa); ademas `cv_triage_v3.csv` tiene mismo nombre y esquema distinto en cada engine (intencional pero indistinguible de un drift). Registrar la convencion en el SSOT que corresponda o validar en CI | Auditoria de docs 2026-06-10 | Abierta |
| D-013 | Implementar la regla explicita del Marco en fast_gate (Fast Gate de 5 preguntas Si/No; contar sies: 0-1 Verde / 2-3 Amarillo / 4-5 Rojo; Negro = P5=Si + alto impacto), hoy ausente del prompt. Causa raiz del error Rojo->Amarillo (corregida 2026-06-16; el diagnostico inicial "gap de dataset por dominio regulado" queda DESCARTADO): el prompt pide deducir el color en vez de contar, y la P3 ("fuera del catalogo aprobado") tiene el default invertido (sin dato de homologacion el modelo asume P3=No y pierde un si: 4->3 -> Rojo->Amarillo). Rumbo: arquitectura deterministica A (el LLM responde P1..P5 + alto impacto; una funcion pura cuenta y deriva el color). Requiere: default de P3 (intent nuevo=No / sistema ya implementado=Si), definicion de alto impacto (doc del otro proyecto), y anotar P1..P5 como gold en el dataset (hoy 0/76) | Validacion externa + regla canonica del Marco (2026-06-16) | Resuelta 2026-06-16 (rama feat/fast-gate-deterministico) — `module.type: rule_derived`: el LLM responde P1..P5+alto_impacto y `derive_color` deriva el color. Color TEST 80% (supera el end-to-end 76,7%) y AUDITABLE; Rojo->Amarillo cerrado (P3 96,7%, P5 100%). GEPA no aporta (confirmado en 2 tandas): la 1a parecia techo de metrica (7 salidas, VAL 93-96%); corregida a color+alto_impacto, la 2a tanda (N=3) da prompt_changed=no y color 73-83% (media 80 = base+few-shot) -> la varianza del LLM domina, GEPA no separa del baseline. La palanca real fue afilar descripciones + few-shot k=8. Residuales en D-015 |
| D-014 | Etapas nuevas diferidas de flujo-intents (decision del usuario, 2026-06-16): (a) **admisibilidad** que absorba §9.2 (atributos protegidos en decisiones de acceso) y §7.4 (duplicado), hoy sin etapa tras sacarlas de factibilidad — reasignar TC-REJ-09/TC-REJ-10; (b) etapa para **valor real** ("resuelve un dolor de negocio") hoy no cubierta por solidez; (c) reubicar **`devolucion_no_ia`** ("no requiere IA") fuera de solidez a esa etapa nueva. Hasta entonces `no_ia` se deja en solidez para no romper el holdout (TC-REJ-06) | Alineacion al Marco de Gobierno (Solidez/Factibilidad), 2026-06-16 | Abierta |
| D-015 | Residuales del fast_gate determinista (post D-013): (a) **alto_impacto es el cuello** (~80% sobre el test, varianza alta 56-80% entre corridas; sobre-escala a Negro en casos acotados/reversibles) -> medir con N seeds y/o curar demos few-shot de casos limite; (b) **`run_inference.py` usa `create_module` generico**, no `rule_derived` -> en produccion no derivaria el color; (c) el **gold de `alto_impacto` del test es aproximado** (=Negro) para casos P5=No (no afecta el color, si la metrica del campo); (d) GEPA con VAL chico no aporta -> evaluar VAL mayor si se busca exprimir GEPA (**actualizado 2026-06-18**: val ampliado a 22 sigue en techo 86-91%; GEPA+gpt-5 N=3 elige baseline 3/3 con budget completo -> el cuello es senal en val, no budget; pendiente val ~40-50 con casos borde donde el baseline falle) | Cierre de D-013 (2026-06-16) | (a)(b)(c) Abiertas; **(d) cerrada 2026-06-18** — VAL ampliado a 46 casos borde, refutado a N=3 con gpt-5-mini Y gpt-4.1-mini (ambos RUIDO[SOBREAJUSTE]): el VAL sigue en techo 89-93% con los dos modelos y GEPA no generaliza (gap val-test +10/+14). El cuello es la REPRESENTATIVIDAD val-vs-test (los casos borde sinteticos no capturan la dificultad del TEST), no el tamaño/budget/modelo. Dataset ampliado conservado como banco de medicion |
| D-016 | Cuelgue al final de la corrida con reasoning models (gpt-5-mini/gpt-5): `_save_predictions` RE-EJECUTABA el modelo sobre test+val (52 llamadas reasoning extra), lo que ademas era INFIEL (LLM no determinista -> el dump != predicciones que dieron el score) y bloqueaba el registro (corria antes de run.json+CSV) | Cuelgue corrida fast_gate rule_derived + gpt-5 (2026-06-17) | Resuelta 2026-06-18 — causa raiz: el dump re-ejecutaba. Fix: `_eval_repeated` captura `EvaluationResult.results` (dspy 3.x) y `_save_predictions` vuelca las predicciones REALES del eval (sin re-llamar) -> fiel al score y sin llamadas extra. Defensas adicionales: `timeout` configurable (`LLMConfig`, default 600s/`LLM_TIMEOUT`) y dump movido al final de `run()` best-effort. Tests en `test_shared_llm.py`; CI PASO (503). NOTA: los colores por-ficha de corridas previas venian del dump re-ejecutado (no del eval real); desde ahora son fieles |
| D-011 | Modo `pipeline` sin tests ni caso activo: `create_pipeline_module` (`dynamic_factory.py`) y `create_pipeline_metric_with_feedback` (`metrics.py`) no tienen tests dedicados y ningun config vigente usa `module.type: pipeline` (el unico, `intake_pipeline.yaml`, se elimino al segmentar; ver `docs/FAST_GATE_SEGMENTACION.md`). Agregar tests unitarios y decidir si se formaliza como spec retrospectiva (rango reservado `SPEC-001..099`) | Cierre de D-003/D-004 (2026-06-10) | Abierta |
| D-017 | Linea de investigacion (fast_gate): curar un VAL **representativo del TEST** para que GEPA tenga gradiente real. Hipotesis: un VAL sembrado con casos donde el modelo realmente falla (de la dificultad del TEST) daria gradiente | Cierre de D-015d (2026-06-18) | **Refutada 2026-06-19** — se ejecuto el ciclo completo: diagnostico por-caso (`diagnose_rule_baseline.py`), 14 casos `VAR-FG-T01..T14` calibrados a las 5 confusiones del TEST con textura rica y fichas NEUTRALES (se corrigio una fuga de juicio en `supuesto_riesgo`). Gate: el gap de color bajo +22,6 -> +14,1 pp (no cerro <5; residuo = confusion Rojo->Negro). GEPA N=3 con DOS modelos (gpt-5* retirado; nuevos gpt-5.4*): gpt-4.1-mini RUIDO[SOBREAJUSTE][TECHO][ESTABILIZA] (Opt-Base -1,4; Rob TEST 80,0), gpt-5.4-mini SIN REF[SOBREAJUSTE][TECHO] (Opt-Base -2,5; Rob TEST 77,8). Causa raiz nueva: el VAL es representativo en COLOR pero GEPA optimiza la metrica COMBINADA (alto_impacto+color), saturada en techo (87-89%) porque alto_impacto se acierta ~90% y diluye el cuello. El modelo mas nuevo (gpt-5.4-mini) NO mejora -> techo del enfoque, no del modelo. Mejor sistema sigue siendo baseline sin GEPA. Dataset (val 60) y script de diagnostico conservados. Sub-linea abierta: probar metrica solo-color | Cierre de D-015d (2026-06-18) | **Refutada/cerrada 2026-06-19** (la sub-linea "metrica solo-color" queda como nota, no bloqueante) |

## Deuda resuelta

| ID | Descripcion | Resuelta | Cierre |
|---|---|---|---|
| D-002 | Primera spec de capacidad con formato hibrido | 2026-06-03 | `SPEC-100-veredicto-senal-ruido` estrena el formato (registrada en `specs/SPECS_REGISTRY.md`); Tramo 2 pasa a activo |
| D-003 | Soporte para flujos multietapa (multi-stage) en DSPy | 2026-06-10 | Ya estaba implementada en `73bdd1d` (2026-05-21): `DynamicModuleFactory.create_pipeline_module` compone N etapas en serie con signatures YAML (`stages`), validadas por `config_schema.py` y documentadas en `docs/YAML_CONFIG_REFERENCE.md`. La deuda se habia migrado el 2026-06-03 desde un checklist desactualizado. Resto pendiente (tests, caso activo) -> D-011 |
| D-004 | Logica condicional en modulos (etapa segun resultado de la anterior) | 2026-06-10 | Ya estaba implementada en `73bdd1d` (2026-05-21): seccion `routing` con gate (`gate_stage`/`gate_field`/`gate_value`); las etapas no abiertas por el gate no llaman al LLM e inyectan `skip_outputs_when_gated` (ahorro de tokens). Mismo origen del desfase que D-003. Resto pendiente -> D-011 |
| D-007 | Verificar si D-003/D-004 estaban cubiertas por el modo `pipeline` y cerrarlas o re-acotarlas | 2026-06-10 | Verificado contra codigo e historia de git: ambas cubiertas literalmente por `create_pipeline_module` (D-003 y D-004 cerradas); lo no cubierto (tests dedicados, ausencia de caso activo) quedo re-acotado en D-011 |

---

## Log de fases

### 2026-06-19 — fast_gate: VAL calibrado al diagnostico del TEST (D-017) + precios gpt-5.4

**D-017 refutada.** Se ejecuto la hipotesis pendiente: curar un VAL *representativo
del TEST* (no casos borde sinteticos limpios, sino calibrados a donde el modelo falla).

**Ciclo:**
1. **Diagnostico por-caso** (`diagnose_rule_baseline.py`, nuevo): baseline gpt-4.1-mini
   por caso sobre TEST -> gap VAL-TEST **+22,6 pp** (VAL 85,9% color / TEST 63,3%) y la
   causa por juicio: subcuenta **p2** (insumo que un humano usa pero el sistema influye),
   **p5** (supervision solo posterior) y **alto_impacto** (acotado+reversible vs escala/
   denegacion).
2. **VAL representativo:** 14 casos `VAR-FG-T01..T14` (todos val) calibrados a esas 5
   confusiones, con textura rica (metricas, sponsor, restricciones, escala) y **fichas
   neutrales**. Se corrigio una **fuga de juicio**: la 1a version escribia "alto_impacto=Si
   (criterio a)" en `supuesto_riesgo` -> el modelo acertaba leyendo la respuesta. VAL 46 -> 60.
3. **Gate:** gap de color **+22,6 -> +14,1 pp** (VAL 80,8% / TEST 66,7%), densidad de
   error 14% -> 19%, fallando por las MISMAS causas que el TEST. No cerro <5 pp (residuo
   = Rojo->Negro, dificil de fabricar). Se decidio correr GEPA igual (VAL mas representativo
   logrado).
4. **GEPA N=3, DOS modelos** (gpt-5-mini/gpt-5 retirados del endpoint; disponibles los
   nuevos gpt-5.4*):

  | task / reflection      | Baseline VAL | Opt VAL (Opt-Base) | Robustez TEST       | gap  | veredicto |
  |------------------------|--------------|--------------------|---------------------|------|-----------|
  | gpt-4.1-mini / gpt-4o  | 88,6%        | 87,2% (**-1,4**)   | 80,0% [75,0..83,3]  | +7,2 | RUIDO [SOBREAJUSTE] [TECHO] [ESTABILIZA] |
  | gpt-5.4-mini / gpt-5.4 | 87,5%        | 85,0% (**-2,5**)   | 77,8% [73,3..80,0]  | +7,2 | SIN REF [SOBREAJUSTE] [TECHO] |

  Run-ids: gpt-4.1-mini `..._{f14bd3e7,d6a0efd9,b37238b8}`; gpt-5.4 `..._{20552ed9,8c482ea0,59cc8058}`.

- **Causa raiz nueva (la leccion):** el VAL es representativo en COLOR, pero GEPA optimiza
  la metrica COMBINADA `alto_impacto + clasificacion`, que sigue en techo (87-89%) porque
  `alto_impacto` se acierta ~90% y diluye el cuello del color. **El cuello debe estar en la
  metrica que GEPA ve, no en una proyeccion de ella.** Sub-linea abierta: metrica solo-color.
- **El modelo mas nuevo no cambia el techo:** gpt-5.4-mini (mas potente) NO supera a
  gpt-4.1-mini en robustez TEST (77,8 vs 80,0; rangos solapan). Techo del enfoque, no del
  modelo. Unico efecto positivo: `ESTABILIZA` (rango robustez 15,5 -> 8,3 con gpt-4.1-mini).
- **Cierre de la linea (D-015d + D-017):** ni ampliar, ni curar al diagnostico, ni cambiar
  de modelo destraba GEPA en fast_gate. Mejor sistema = baseline sin GEPA.

**Precios gpt-5.4 en el leaderboard.** Ya estaban en `DEFAULT_PRICING` (`roi_calculator.py`,
SSOT): gpt-5.4 $2,50/$15,00, gpt-5.4-mini $0,75/$4,50; el leaderboard ya los usa (lookup
verificado, sin fallback). Se sincronizo la tabla DUPLICADA de `docs/ANALISIS_UTILIDADES.md`
(estaba en 4 modelos) con el codigo y se anoto el SSOT (avance parcial de D-009).

[SDD-Check]
- Spec afectada: `SPEC-102-flujo-intents` (Fast Gate rule_derived; refuta/cierra D-017).
- Includes: `diagnose_rule_baseline.py` (nuevo) + 14 casos `VAR-FG-T01..T14` en
  `make_variations.py` con fichas neutrales + textura rica + regeneracion del dataset
  (val 46 -> 60, TEST intacto); sync de precios gpt-5.4 en `docs/ANALISIS_UTILIDADES.md`.
- Lenguaje normativo: N/A (experimento + doc, no nueva capacidad normativa).
- [NEEDS CLARIFICATION]: ninguno.
- Deuda arrastrada: D-001, D-005, D-006, D-008, D-009 (avanza parcial: precios sync),
  D-010, D-011, D-014, D-015(a)(b)(c). D-017 refutada/cerrada (sub-linea metrica solo-color
  como nota no bloqueante).

### 2026-06-18 — fast_gate: VAL ampliado a 46 casos borde (D-015d) + 2 arreglos de ambiente

Se ejecuto la palanca pendiente de D-015(d): ampliar el VAL con casos borde "donde
el baseline falle" para darle gradiente a GEPA. Refutada con DOS modelos.

**Intervencion (dataset, conservado):** VAL 22 -> 46 con 24 casos nuevos concentrados
en el CUELLO (no en Verde facil), en `make_variations.py` (SSOT): Rojo<->Negro por
`alto_impacto` (P5=Si acotado+reversible -> Rojo; P5=Si y alto -> Negro), colinealidad
rota (alto=Si con P5=No -> no Negro), transiciones de conteo 1<->2 y 3<->4, y override
de Negro con conteo bajo. TEST intacto (30 TC-xx, 8A/7R/7V/8N). `derive_color==gold` en
las 84 filas train/val; 0/30 mismatches dump-vs-regla en las 6 corridas (dump fiel,
D-016).

**Resultado N=3 (color+alto_impacto):**

  | task / reflection      | Baseline val        | Opt val (Opt-Base)     | Robustez TEST       | gap val-test | veredicto |
  |------------------------|---------------------|------------------------|---------------------|--------------|-----------|
  | gpt-5-mini / gpt-5     | 92,76 [90,2..94,6]  | 89,49 (**-3,26**)      | 79,44 [73,3..85,0]  | +10,05       | RUIDO [SOBREAJUSTE] [TECHO] |
  | gpt-4.1-mini / gpt-4o  | 89,49 [88,0..90,2]  | 90,94 (**+1,45**)      | 77,22 [73,3..80,0]  | +13,72       | RUIDO [SOBREAJUSTE] [ESTABILIZA] |

  Color TEST por seed (solo `clasificacion`): gpt-5-mini 80,0/83,3/73,3 (media ~79);
  gpt-4.1-mini 66,7/70,0/73,3 (media 70). vs referencia previa: robustez -2,50 (gpt-5)
  y -2,93 (gpt-4), ambos dentro del ruido (rangos solapados).

- **D-015(d) refutada: el VAL ampliado NO destraba GEPA con ningun modelo.** El VAL
  sigue en techo (89-93%) tambien con el modelo debil: los casos borde son dificiles
  *conceptualmente* pero el LLM los resuelve. Con gpt-4.1-mini GEPA hasta sube en val
  (+1,45, a diferencia de gpt-5-mini que baja), pero NO generaliza: gap val-test +13,72
  y robustez TEST 77,2% (peor que gpt-5-mini). El cuello no es el modelo, ni el budget,
  ni el tamaño del val: es que **los casos borde sinteticos no capturan la dificultad
  del TEST** (gap val-test enorme en ambos). El mejor sistema sigue siendo BASELINE sin
  GEPA. Unico efecto: `ESTABILIZA` con gpt-4 (rango robustez 15,5 -> 6,7).

**Arreglos de ambiente (independientes del experimento, "nada hardcoded de ambientes"):**
1. **Holdout sin originales** (`dataset.py`): `build_stage_csv` omitia fast_gate
   (`return None`) si faltaba `FLUJO_INTENTS_ORIGINALS_DIR`, atando la regeneracion de
   train/val a una ruta externa. Nuevo `_read_existing_test`: sin originales, preserva
   el TEST ya commiteado en el CSV y regenera solo train/val. Reproducible en cualquier
   entorno; verificado byte-identico.
2. **Precedencia de `.env`** (`shared/llm/config.py`): `from_env` hardcodeaba los
   subproyectos `["gepa_standalone", "dspy_gepa_poc"]` y, con `load_dotenv(override=
   False)`, corriendo desde la raiz cargaba el `.env` equivocado (un experimento dspy
   tomaba gpt-4.1-mini de gepa). Se quito el fallback con nombres; precedencia explicita:
   entorno del proceso > `LLM_ENV_FILE` (ruta, sin nombres) > `.env` del cwd > defaults.
   `check_deployments.py` (unico consumidor shared afectado) gana `--env-file`/`LLM_ENV_FILE`
   con default dspy_gepa_poc. El `.env` especifico ya lo carga cada subproyecto via su
   `config.py` (mecanismo correcto preexistente).

[SDD-Check]
- Spec afectada: `SPEC-102-flujo-intents` (Fast Gate rule_derived; cierra D-015d).
- Includes: 24 casos VAL borde en `make_variations.py` + regeneracion de
  `datasets/flujo_intents_fast_gate.csv` (+ `variations/`) preservando el TEST; arreglo
  `dataset.py` (`_read_existing_test`) + test; arreglo precedencia `.env`
  (`shared/llm/config.py` + `check_deployments.py`) + 3 tests; veredicto N=3 con
  gpt-5-mini y gpt-4.1-mini. Excludes: no se cambio el prompt ni la regla; el dataset
  ampliado se CONSERVA (decision del usuario: banco de medicion con mas resolucion).
- Validaciones: `derive_color==gold` en train/val; 0/30 mismatches dump-vs-regla en las
  6 corridas; `./shared/utils/ci_local.sh` PASO (507 tests, cobertura 95,79%); ambos
  deployments validados antes de correr.
- SSOT afectado: `dspy_gepa_poc/flujo_intents/make_variations.py`,
  `dspy_gepa_poc/flujo_intents/dataset.py`,
  `dspy_gepa_poc/datasets/flujo_intents_fast_gate.csv` (+ `variations/`),
  `shared/llm/config.py`, `shared/utils/check_deployments.py`,
  `tests/test_flujo_intents.py`, `tests/test_shared_llm.py`,
  `docs/LECCIONES_APRENDIDAS.md` (seccion 11: VAL ampliado no destraba GEPA).
- Deuda arrastrada: **D-015(d) cerrada** (val mayor refutado a N=3 con dos modelos; el
  cuello es representatividad val-vs-test, no tamaño/budget/modelo). Residuales (a)/(b)/(c)
  de D-015 siguen abiertos. Sin deuda nueva.

### 2026-06-18 — fast_gate: cierre N=3 de GEPA+gpt-5 (predicciones fieles) y veredicto

Confirmacion a N=3 de GEPA con reflection gpt-5 (task gpt-5-mini), pendiente desde
el 2026-06-17, ahora con el dump de predicciones FIEL (D-016 resuelta). Las 3
corridas (`flujo_intents_fast_gate_rule_v1_20260618_{100512,103218,105731}`)
completaron limpias (sin cuelgue) y costaron ~0,67-0,70 USD c/u.

**Resultado (color test, N=3):** 80,0 / 83,3 / 76,7 -> **media 80,0%**
[76,7..83,3]. Contra el baseline gpt-5-mini sin GEPA (82,2%): delta -2,2 pp,
dentro del spread entre corridas (6,6 pp). Veredicto: **RUIDO / regresion leve;
GEPA no aporta**, ahora confirmado a N=3 tambien con modelo fuerte.

**Verificaciones (datos, no re-ejecucion):**
- **Dump fiel:** `pred_clasificacion` deriva exactamente de `pred_p1..p5 +
  pred_alto_impacto` via `derive_color`: **0/30 mismatches en las 3 corridas**. El
  CSV es ahora internamente consistente con el score del eval (cierra el "no es
  real" de D-016).
- **El budget NO es el cuello.** `total_metric_calls` = 90-93 = tope
  `max_metric_calls: 90`: GEPA consume el presupuesto completo. Aun asi genera
  solo **3 candidatos** y elige **best_idx=0 (baseline) en las 3 corridas**: las
  reescrituras empatan o pierden en val (cand0 0,909/0,932/0,977 >= cand1/cand2).
  No le falta presupuesto, le falta gradiente.
- **Causa: techo de val.** val color 86,4 / 86,4 / 90,9% (combinada 0,91-0,98);
  con 22 ejemplos quedan 1-3 fallando -> casi nula senal para el reflection_lm, y
  cada error pesa 4,5 pp (score ruidoso). Mas budget solo aumentaria el riesgo de
  sobreajustar val, no la generalizacion. **Palanca real: val mayor y mas dificil
  (casos borde donde el baseline falle), no mas budget.**

[SDD-Check]
- Spec afectada: `SPEC-102-flujo-intents` (Fast Gate rule_derived; D-015).
- Includes: veredicto N=3 GEPA+gpt-5 con dump fiel; analisis de candidates.json
  (best_idx=baseline 3/3, budget completo). Excludes: ampliacion de val (propuesta,
  no ejecutada); ningun cambio de codigo nuevo en esta entrada.
- Validaciones: color y consistencia regla-vs-dump recomputados desde los
  `predictions_test.csv` de las 3 corridas (0/30 mismatches).
- SSOT afectado: solo `historial/sdd.md` (registro); sin cambios de codigo.
- Deuda arrastrada: **D-015 avanza** (queda como mejora la ampliacion de val para
  exprimir GEPA; conclusion: con val en techo GEPA no separa del baseline, ni con
  gpt-5). **D-016 resuelta** y validada en estas 3 corridas (sin cuelgue, dump fiel).

### 2026-06-17 — fast_gate rule_derived: colinealidad de alto_impacto + interaccion modelo×datos

Tres intervenciones sobre `flujo_intents_fast_gate_rule_v1` para atacar el cuello
`alto_impacto` (D-015) y la persistencia de GEPA sin aporte:

1. **Feedback de metrica rule-aware** (`create_rule_derived_metric_with_feedback` en
   `metrics.py`): antes la metrica daba feedback sobre `clasificacion` (color DERIVADO,
   que el predictor no emite) -> inaccionable para el reflection_lm. Ahora traduce el error
   del color al juicio responsable (traza de la regla + que P1..P5/`alto_impacto` corregir).
   El score no cambia (comparabilidad); con tests (`test_dspy_metric_feedback.py`).
2. **Reescritura de `alto_impacto`** (YAML): de lista (a)-(e) + caveat enterrado a un
   procedimiento de 2 pasos con el filtro acotamiento+reversibilidad como GATE inicial.
3. **Diagnostico de datos (causa raiz, sin tokens):** la distribucion conjunta
   features↔label del train/val estaba DEGENERADA *by-design* en `_FG_PREGUNTAS`: cada
   color en un punto unico del conteo (Verde=0, Amarillo=3, Rojo=4; nunca los bordes que el
   test SI tiene) y **colinealidad espuria `alto_impacto=Si` ⟺ `Negro`** (19/19). El modelo
   aprendia el atajo y `alto_impacto` saturaba el VAL (techo) -> GEPA sin gradiente.
   Fix: 13 casos nuevos (bordes de conteo + Rojo/Amarillo con `alto_impacto=Si` y P5=No para
   romper la colinealidad). Test intacto; train 30->38, val 16->22. `derive_color==gold`
   sin inconsistencias.

**Resultado clave — cuadro 2x2 (baseline SIN GEPA, color test, N=3):**

  |                | datos viejos          | datos nuevos (enriquecido) |
  |----------------|-----------------------|-----------------------------|
  | gpt-4.1-mini   | 80,0 [73,3..86,7]     | 70,0 [63,3..73,3]           |
  | gpt-5-mini     | 77,8 [73,3..83,3]     | **82,2 [80,0..86,7]**       |

- **El gap se INVIERTE segun el modelo.** Con gpt-4.1-mini el dataset enriquecido BAJA 10 pp
  (los few-shot de borde lo hacen subcontar "Si"); con gpt-5-mini SUBE y da el mejor numero
  de toda la serie. Disjunto: gpt-5-mini nuevos [80..86,7] vs gpt-4.1-mini nuevos
  [63,3..73,3] (+12 pp). **El descenso con gpt-4.1-mini era falta de capacidad del modelo,
  NO un defecto de los datos -> NO se revierte el dataset enriquecido.** Esto matiza la
  conclusion previa de la seccion 11 / D-015 ("gpt-5-mini baja el techo"): la bajaba con el
  gold colineal; con el gold limpio lo sube.
- **GEPA sigue sin aportar (n=1 con gpt-5):** color optimizado 66,7% vs baseline 82,2%
  (colapso de Verde por sobre-conteo). Consistente con el patron de VAL chico (seccion 11),
  ahora tambien con reflection gpt-5. Pendiente confirmar a N=3 (corridas del usuario por fuera).
- **Cuelgue operativo:** `dspy.LM` se construye SIN `timeout` (`shared/llm/config.py`); con
  reasoning models (gpt-5-mini) una request puede colgar indefinidamente. La 1a corrida
  completa colgo en `_save_predictions` (val). Fix de robustez pendiente (timeout configurable).

Mejor estado de la sesion: **gpt-5-mini + datos enriquecidos = 82,2% baseline** (sin GEPA).

[SDD-Check]
- Spec afectada: `SPEC-102-flujo-intents` (Fast Gate rule_derived; ataca D-015).
- Includes: `create_rule_derived_metric_with_feedback` (`metrics.py`) + wiring
  (`reflexio_declarativa.py`) + tests (`test_dspy_metric_feedback.py`); reescritura de
  `alto_impacto` en `configs/flujo_intents_fast_gate_rule_v1.yaml`; 13 casos nuevos en
  `make_variations.py` (`FAST_GATE` + `_FG_RAZONAMIENTO` + `_FG_PREGUNTAS`); regeneracion de
  `datasets/flujo_intents_fast_gate.csv` (+ `variations/`) preservando el test; lecciones en
  `docs/LECCIONES_APRENDIDAS.md` (interaccion modelo×datos + feedback de campo derivado).
  Excludes: confirmacion N=3 de GEPA+gpt-5 (corre el usuario por fuera); fix de `timeout` del
  LM (pendiente, ver D-016); decision de commit (todo en working tree).
- Validaciones: `derive_color==gold` en las 60 filas train/val (sin inconsistencias); cuadro
  2x2 medido con LLM real (N=3 por celda); `./shared/utils/ci_local.sh` PASO (498 tests,
  cobertura 92,39%) sobre #1/#2/#3.
- SSOT afectado: `dspy_gepa_poc/metrics.py`, `dspy_gepa_poc/reflexio_declarativa.py`,
  `tests/test_dspy_metric_feedback.py`, `configs/flujo_intents_fast_gate_rule_v1.yaml`,
  `dspy_gepa_poc/flujo_intents/make_variations.py`,
  `dspy_gepa_poc/datasets/flujo_intents_fast_gate.csv` (+ `variations/`),
  `docs/LECCIONES_APRENDIDAS.md`.
- Deuda arrastrada: **D-015 avanza** (alto_impacto atacado por 3 vias; dataset sin colinealidad
  + gpt-5-mini = 82,2% baseline). Nueva **D-016** (timeout configurable del LM para reasoning
  models, evita cuelgues en `_save_predictions`). GEPA+gpt-5 N=3 pendiente de confirmar.

### 2026-06-16 — fast_gate determinista (arquitectura A): cierre de D-013

Se implemento la regla canonica del Marco como arquitectura `module.type: rule_derived`
(rama `feat/fast-gate-deterministico`): el LLM ya no clasifica el color; responde las 5
preguntas Si/No del Fast Gate + un juicio `alto_impacto`, y una funcion pura
(`flujo_intents/fast_gate_rule.derive_color`) deriva el color (contar Si: 0-1 Verde /
2-3 Amarillo / 4-5 Rojo; Negro = P5=Si Y alto impacto, override del conteo). Clave: el
color pasa a ser deterministico, AUDITABLE y fiel al Marco.

Progresion sobre el holdout (30 TC, gpt-4.1-mini; metrica de color):

  | Hito | Color TEST | P3 | alto_impacto |
  |---|---|---|---|
  | end-to-end + few-shot (previo, deduce el color) | 76,7% | -- | -- |
  | rule_derived, nucleo (sin few-shot/GEPA) | 63-70% | 80% | 60% |
  | + descripciones afiladas (P3/P5/alto_impacto) | 76,7% | 96,7% | 63% |
  | + few-shot k=8 (train/val anotados) | 80,0% | 96,7% | 80% |
  | + GEPA (3 runs, prompt_changed=no) | 80,0% | 96,7% | 80% |

Hallazgos:
- **Causa raiz de D-013 confirmada y resuelta**: el Rojo->Amarillo no era gap de dataset
  por "dominio regulado" (descartado), sino el prompt sin conteo + la P3 con default
  invertido. Afilar P3 ("sera homologado mas adelante" => no homologado AHORA => Si) la
  llevo a 96,7% y elimino el Rojo->Amarillo. P5 a 100% (afilar "log revisable != revision
  por caso").
- **La arquitectura A supera al end-to-end** (80% vs 76,7%) y, sobre todo, lo hace
  auditable: el color sale de 6 juicios binarios trazables, no de un salto opaco.
- **GEPA no aporta (veredicto confirmado en 2 tandas).** 1a tanda: la metrica evaluaba las
  7 salidas y como P1/P2/P3/P5 ya estaban en 90-100%, inflaba el baseline VAL a 93-96%
  (techo) y diluia el cuello -> el "no aporta" no era concluyente (artefacto de metrica).
  Fix: metrica = `clasificacion` + `alto_impacto` (se ignoran P1..P5). 2a tanda con la
  metrica destechada (3 runs): **`prompt_changed=no` en las 6 corridas totales**; el color
  del programa GEPA medido N=3 da 83,3 / 73,3 / 83,3 (media 80,0%, rango ±5pp) = IGUAL que
  el base+few-shot. La dispersion es ruido del LLM (temp 0.1 no determinista + sampling de
  few-shot), no efecto de GEPA. Conclusion: con VAL=16 GEPA no mueve el prompt (patron
  seccion 11) y la varianza domina; **la palanca real fue afilar descripciones + few-shot**,
  no la optimizacion. Un run mostro el overfit tipico (VAL 100 / TEST 71,7).
- **Cuello remanente: `alto_impacto`** (~80%, varianza 56-80% entre corridas): el modelo
  sobre-escala a Negro en casos acotados a bandas/catalogo y reversibles. Es el unico
  juicio subjetivo de la regla. Queda en D-015.
- **Auditabilidad materializada**: el harness GEPA solo persiste prompts y scores
  agregados; se agrego un dump por-ficha (`scripts/diagnose_fast_gate_rule.py` ->
  `results/audits/`) con gold vs pred de las 6 respuestas + razonamiento + color.

[SDD-Check]
- Spec afectada: `SPEC-102-flujo-intents` (Fast Gate: regla canonica del Marco + rule_derived).
- Includes: `flujo_intents/fast_gate_rule.py` (`derive_color`); `module.type: rule_derived`
  (`dynamic_factory.py`, `reflexio_declarativa.py`, `config_schema.py`); config
  `flujo_intents_fast_gate_rule_v1.yaml`; anotacion P1..P5+alto_impacto de los 46 VAR-FG
  (`make_variations._FG_PREGUNTAS`) + infra de propagacion en `dataset.py`; scripts
  `enrich_fast_gate_questions.py` y `diagnose_fast_gate_rule.py` (dump auditable);
  correccion de la causa raiz en LECCIONES s11 / sdd / build_witness (commits previos).
- Validaciones: `derive_color` reproduce el color en las 76 filas (test); 3 runs GEPA +
  auditoria del programa optimizado (color 80%); `./shared/utils/ci_local.sh` PASO (492
  tests, cobertura 92,39%).
- SSOT afectado: `dspy_gepa_poc/flujo_intents/fast_gate_rule.py`, `dynamic_factory.py`,
  `reflexio_declarativa.py`, `config_schema.py`, `flujo_intents/make_variations.py`,
  `flujo_intents/dataset.py`, `configs/flujo_intents_fast_gate_rule_v1.yaml`,
  `datasets/flujo_intents_fast_gate.csv` (+ `variations/`), `scripts/*`,
  `tests/test_flujo_intents.py`.
- Deuda arrastrada: **D-013 resuelta**; nueva **D-015** (residuales: alto_impacto, N seeds,
  run_inference rule_derived, gold aproximado de alto_impacto en test).

### 2026-06-16 — factibilidad y solidez: alineacion al Marco + datasets balanceados + des-hardcode de ruta

Contraste contra el Marco de Gobierno (tabla oficial Solidez/Factibilidad que aporto el
usuario): **factibilidad estaba desalineada**. El Marco define 3 salidas (Avanza a Fast
Gate / Avanza con rediseno / No avanza por ahora); la implementacion tenia 4 (la extra,
`rechazo_formal`, mezclaba admisibilidad §9.2 -atributos protegidos- y dedup §7.4 dentro de
"factibilidad tecnica"). Ademas la frontera D/N no usaba el criterio del Marco
(aceptabilidad del riesgo): casos autonomos de alto impacto sin supervision estaban como
`avanza_con_redisenio` cuando el Marco los manda a `no_avanza`. Esto explica parte del
colapso de la etapa (Rob ~13-47% bajo el trivial 86,7%): criterios heterogeneos en una sola
decision + frontera cruzada = tarea no aprendible.

Decisiones del usuario y alcance:
- **Factibilidad -> 3 clases.** Se elimino `rechazo_formal`. Frontera D/N recalibrada al
  Marco: `avanza_con_redisenio` = autonomo REVERSIBLE de impacto medio (un ajuste acotado
  basta); `no_avanza` = (a) inviable tecnico o (b) riesgo no aceptable (autonomo
  IRREVERSIBLE de alto impacto sobre personas, donde el ajuste no alcanza).
- **Dataset balanceado y medible** (para macro-F1, no accuracy enganada por el holdout
  26/1/1/2): factibilidad pasa a train 12/12/12, val 8/8/8, test 8/8/8 (3 clases). El test
  es un holdout balanceado a mano (prefijo `TST-FAC-*`, escenarios distintos a train/val,
  0 fugas verificadas) porque los originales solo tienen ~4 rechazos de factibilidad reales
  y no se pueden balancear. El val sube de 15 a 24 (palanca contra el overfit de GEPA,
  seccion 11).
- **Admisibilidad / valor real / no_ia -> etapas futuras (diferido, D-014).** No se crean
  ahora.
- **Des-hardcode**: la ruta externa de los originales (`/datum1/...`) sale del codigo; se
  resuelve por `FLUJO_INTENTS_ORIGINALS_DIR`. Si no esta, las etapas que dependen de
  originales para el test (intake/solidez/fast_gate) NO se regeneran (se dejan intactas, no
  se pisan con test vacio); factibilidad (test propio en variaciones) si se regenera.

**Solidez (mismo criterio del Marco).** El Marco define solidez por 4 criterios con salida
binaria (Si/No): resultado claro (no tecnologia), valor real, sponsor accountable, ficha
completa. La implementacion tenia 3 clases; `devolucion_no_ia` ("no requiere IA") NO es
criterio de solidez del Marco -> se RETIRO (va a etapa nueva con "valor real", D-014).
`ficha completa` ya la cubre Intake. Resultado: solidez pasa a **2 clases**
(`solido` / `devolucion_reformulacion`), alineada al Si/No. `devolucion_reformulacion`
conserva los 3 disparadores que SI son del Marco (tecnologia-en-vez-de-resultado, sponsor
colectivo, metricas no medibles). Mismo rebalanceo medible que factibilidad: train 14/14,
val 10/10, test 10/10 (holdout balanceado a mano `TST-SOL-*`, 0 fugas). Val sube de 15 a
20. Como ahora usa test propio, el holdout de originales deja de hacer falta: TC-REJ-06 sale
del mapeo (diferido a la etapa de no_ia), por eso ya no es necesario "dejar no_ia para no
romper el holdout" como se penso al abrir D-014.

[SDD-Check]
- Spec afectada: `SPEC-102-flujo-intents` (alineacion de factibilidad y solidez al Marco; iter en curso).
- Includes: factibilidad a 3 clases (49 casos nuevos, frontera D/N por impacto/
  irreversibilidad) y solidez a 2 clases (38 casos nuevos, retiro de `devolucion_no_ia`) en
  `make_variations.py`; soporte de `split=test` desde variaciones y des-hardcode de la ruta
  de originales en `dataset.py`; instrucciones de ambos configs alineadas; ajuste de 2 tests
  (`REJ_STAGE_MAP`=7 sin TC-REJ-06/09/10, fuga por ficha en vez de prefijo). Excludes:
  etapas de admisibilidad/valor real/no_ia (D-014); corrida GEPA real con los datasets
  nuevos (D-012); reasignacion de TC-REJ-06/09/10.
- Validaciones: datasets regenerados (factibilidad 36/24/24 en 3 clases; solidez 28/20/20 en
  2 clases; 0 fugas verificadas en ambos); `tests/test_flujo_intents.py` 28/28; ambos
  configs cargan con AppConfig; `./shared/utils/ci_local.sh` PASO.
- Baseline SIN GEPA medido (`baseline_only.py`, `gpt-4.1-mini`, n=1, test balanceado ->
  accuracy ~= balanced accuracy ~= proxy de macro-F1):

  | Etapa | VAL | TEST | trivial (clase mayoritaria) |
  |---|---|---|---|
  | Factibilidad (3 clases, test 8/8/8) | 87,5% | 79,17% | 33,3% |
  | Solidez (2 clases, test 10/10) | 95,0% | 95,0% | 50,0% |

  Lectura: el "colapso" previo de factibilidad (Rob ~47% 4.1-mini / ~13% 5-mini "bajo el
  trivial 86,7%") era ARTEFACTO del test roto 26/1/1/2 + taxonomia cruzada (`rechazo_formal`
  mezclaba admisibilidad con factibilidad tecnica), NO debilidad del modelo ni de GEPA: con
  el Marco (3 clases) y test balanceado, el baseline sin GEPA ya da 79,17% sobre trivial
  33,3% -> la etapa SI discrimina. Solidez queda en 95% sobre trivial 50%. Caveat: numeros
  in-distribution (test de autoria propia, como train/val); el chequeo riguroso seria un set
  testigo de marco independiente (hoy solo existe para fast_gate; encaja con D-014). Estos
  baselines son la referencia contra la que comparar la corrida GEPA + `gpt-4o` (en curso por
  fuera): si GEPA no supera 79,17 / 95,0 en TEST, se repite el patron seccion 11 aun con VAL
  mayor (24 y 20).
- SSOT afectado: `dspy_gepa_poc/flujo_intents/make_variations.py`,
  `dspy_gepa_poc/flujo_intents/dataset.py`,
  `dspy_gepa_poc/configs/flujo_intents_triage_factibilidad.yaml`,
  `dspy_gepa_poc/configs/flujo_intents_triage_solidez.yaml`,
  `dspy_gepa_poc/datasets/flujo_intents_triage_{factibilidad,solidez}.csv` (+ `variations/`),
  `tests/test_flujo_intents.py`.
- Deuda arrastrada: D-014 (nueva, etapas diferidas: admisibilidad §9.2/§7.4 -> TC-REJ-09/10;
  valor real + no_ia -> TC-REJ-06). D-012 sigue (falta corrida GEPA por etapa, ahora sobre
  los datasets alineados).

### 2026-06-16 — GEPA por etapa sobre datasets alineados: cierre D-012

Corrida GEPA por fuera (9 runs, 13:11-13:39) sobre los datasets alineados al Marco.
Tarea `azure/gpt-4.1-mini`, profesor `azure/gpt-4o`, estrategia medium, n=1.
Columnas: VAL base/opt = pre/post GEPA; TEST = `Robustez` (holdout balanceado, metrica
no circular). Baseline = `baseline_only.py` (sin GEPA) de la entrada anterior.

| Etapa | VAL base | VAL opt | TEST (rob) | baseline TEST | trivial |
|---|---|---|---|---|---|
| Factibilidad (3 cl., 24/24) | 79,17 | 79,17 | **91,67** | 79,17 | 33,3% |
| Factibilidad (3 cl., 24/24) | 79,17 | 87,50 | **87,50** | 79,17 | 33,3% |
| Solidez (2 cl., 20/20) | 90,0 | 95,0 | **95,0** | 95,0 | 50,0% |
| Solidez (2 cl., 20/20) | 90,0 | 85,0 | 95,0 | 95,0 | 50,0% |
| Fast Gate (few-shot rico v1) | 87,5 | 100,0 | 73,33 | n/d | -- |
| Fast Gate (few-shot rico v1) | 93,75 | 93,75 | 76,67 | n/d | -- |
| Fast Gate (few-shot rico v1) | 87,5 | 93,75 | 73,33 | n/d | -- |
| Fast Gate (few-shot rico v1) | 93,75 | 93,75 | 70,0 | n/d | -- |
| Fast Gate (few-shot rico v1) | 87,5 | 87,5 | 66,67 | n/d | -- |

Lectura por etapa:
- **Factibilidad: GEPA rescatado.** Por primera vez transfiere al holdout: TEST 87,5-91,7
  vs baseline 79,17 y trivial 33,3%. Rompe el patron de la seccion 11 (de LECCIONES) en esta
  etapa. Confirma que el "colapso" previo era artefacto del test roto + taxonomia cruzada, no
  debilidad del modelo ni de GEPA: con 3 clases del Marco y test balanceado, GEPA suma valor.
- **Solidez: en techo.** TEST clavado en 95 (= baseline) sobre trivial 50%. GEPA no aporta
  margen pero tampoco rompe; una corrida bajo VAL a 85 manteniendo TEST 95 (ruido de VAL=20).
- **Fast Gate: sigue overfiteando.** VAL hasta 100 con TEST 67-77. Patron seccion 11 intacto;
  no se resuelve con budget sino con la rubrica de dominio regulado -> D-013.

- Validaciones: n/a (solo `.md`; el CI ignora `**.md`). Datos: 9 filas en
  `dspy_gepa_poc/results/experiments/metricas_optimizacion.csv` (run ids 6255d5dc, c3b702a8,
  48f8c682, 74ceb1f4, 2563e6a5, d0374562, 4e5133ae, d391500a, 501b4221).
- Deuda arrastrada: **D-012 cerrada** (GEPA corrido por etapa, factibilidad generaliza,
  solidez en techo). Queda **D-013** como frente abierto de fast_gate (rubrica dominio
  regulado) y D-014 (etapas diferidas).

### 2026-06-16 — fast_gate: auditoria de datasets y validacion externa con casos testigo

Dos trabajos de calidad de datos sobre fast_gate (y las 4 etapas), motivados por la
preocupacion de que train/val sean poco representativos.

Auditoria de clones/diversidad (las 4 etapas). Deteccion lexica (Jaccard de tokens +
union-find). Hallazgo metodologico: el Jaccard SIN remover el andamiaje de plantilla
**sobre-detecta clones de forma severa** (las fichas comparten ~la mitad de tokens en
campos de formulario). Con boilerplate removido (tokens en >=80% de las fichas), la
diversidad real es alta (solidez 45/45 escenarios distintos, fast_gate 41, factibilidad
33). Unico foco real: intake tenia un cluster de 16 fichas `incompleta` declaracion-vacia
que colapsaban porque `case()` rellena 7 campos con defaults compartidos y la declaracion
-el unico distintivo- estaba vacia. Fix: diversificar el contexto de 4 casos
(`VAR-INT-I01`/`I09`/`I15`/`I18`) manteniendo `decl=""`; el cluster bajo de 16 a 5. NO
hay fuga train/val->test en ninguna etapa (Jaccard cross-split max ~0.44) -> las
conclusiones previas no son artefacto de leakage.

Validacion externa con casos testigo. Para romper la circularidad train/val<->criterios
(ambos de autoria propia), se creo un set de 14 casos testigo etiquetados con marco
INDEPENDIENTE: EU AI Act (Art. 5 prohibido; Anexo III alto riesgo) anclado a reguladores
AR (BCRA, ENACOM, AAIP/Ley 25.326, SSN). Regla de mapeo graduada por impacto para la
frontera Rojo/Amarillo (decision del usuario: "depende del dato/impacto"). Resultado del
programa base (sin GEPA) fuera de distribucion: gpt-4.1-mini 71,4% (10/14), gpt-5-mini
92,9% (13/14). Hallazgos nuevos invisibles en el holdout interno: (a) **reversal
in/out-of-distribution** -el mejor modelo interno es el peor externo; el holdout
sobreestimaba a gpt-4.1-mini-; (b) error externo dominante **Rojo->Amarillo** (causa
real corregida 2026-06-16, ver D-013: el prompt no cuenta los 5 sies del Marco y la P3
tiene el default invertido; NO es gap de dataset por dominio regulado); (c) los 5 Negro
(incl. prohibidos) perfectos en ambos modelos. Detalle en
`docs/LECCIONES_APRENDIDAS.md` seccion 11 (con VEREDICTO de correccion al cierre).

[SDD-Check]
- Spec afectada: `SPEC-102-flujo-intents` (calidad de datos + validacion externa fast_gate).
- Includes: des-clonado de 4 casos intake en `make_variations.py`; nuevo set testigo
  (`scripts/build_witness.py` -> `datasets/flujo_intents_fast_gate_witness.csv`) y su
  evaluador (`scripts/witness_eval.py`); ampliacion de `LECCIONES_APRENDIDAS.md` seccion
  11; este registro. Excludes: no se cambia el prompt ni la rubrica de fast_gate.
- Validaciones: auditoria lexica reproducible; eval testigo con LLM real (2 modelos);
  `./shared/utils/ci_local.sh` (ver abajo).
- SSOT afectado: `dspy_gepa_poc/flujo_intents/make_variations.py`,
  `dspy_gepa_poc/datasets/flujo_intents_fast_gate.csv` (intake regenerado),
  `dspy_gepa_poc/datasets/flujo_intents_fast_gate_witness.csv`,
  `dspy_gepa_poc/scripts/build_witness.py`, `dspy_gepa_poc/scripts/witness_eval.py`,
  `docs/LECCIONES_APRENDIDAS.md`.
- Deuda arrastrada nueva: D-013 (la rubrica fast_gate no tiene regla explicita,
  graduada por impacto, para "dominio de alto riesgo + revision humana"; el dataset no
  ensena ese patron -> Rojo->Amarillo sistematico fuera de distribucion).
- Pendiente (no bloqueante): ampliar clases minoritarias del TEST en intake/solidez/
  factibilidad (1-3 ejemplos, no medibles); medir testigo con N seeds.

### 2026-06-15 — SPEC-102: optimizacion preliminar, ablacion de framing y pilot de realismo

Primeras corridas GEPA de las 4 etapas LLM y tres experimentos de diagnostico. Todo
sobre el split real (medido, no asumido): cada etapa es 30/15/30 con train/val
balanceados por clase a mano (`VAR`) y test = originales (`TC`). Correccion: la deuda
D-012 declaraba "train 4-8 casos/etapa"; es FALSO, son 30. La causa de los resultados
malos no es volumen de train.

Hallazgo 1 (desbalance del holdout). El `test` (originales `TC`) esta dominado por la
clase "pasa": intake 28/2, solidez 26/3/1, factibilidad 26/1/1/2; solo fast_gate tiene
test balanceado (8/7/7/8). El `Rob%` del leaderboard MUST leerse contra el baseline de
clase mayoritaria (trivial), no contra `Base%`/`Delta%`. Medido asi, factibilidad
(47,8% vs trivial 86,7%) y solidez marco (83,9% vs 86,7%) quedan POR DEBAJO del trivial.
Registrado tambien como deuda en `SPEC-102`.

Hallazgo 2 (ablacion de framing). Se crearon `flujo_intents_<etapa>_neutral_v1.yaml`:
mismo dataset/optimization, instruccion SIN alusion al "Marco de Gobierno de IA", sin
`§`, sin priming de riesgo/autoridad (provenance movida a `description`). Con n=3:
intake y fast_gate empatan (framing irrelevante); factibilidad neutral (50,0%, sd 12,5)
EMPATA con marco (47,8%) y ambos colapsan bajo el trivial; solidez neutral (95,0%)
supera a marco (83,9%). El "neutral peor en factibilidad" de la primera lectura era
ruido de n=1 (un unico run de 33,3%). Conclusion: el framing NO es la palanca de
factibilidad ni fast_gate; el colapso es estructural (split/realismo), no de prompt.

Hallazgo 3 (pilot de realismo, hipotesis (3); CERRADO - REFUTADA). Se midio la brecha
`VAR` (~650 chars, sinteticos, nombre=id) vs `TC` (~1450 chars, reales), sistemica en las
4 etapas (artefacto de `make_variations.py`). Pilot acotado a solidez: se reescribieron
los 45 `VAR` con nombres reales, fichas mas ricas y sin nombre=id (VAR 671->843 chars,
0/45 nombre=id, balance y no-fuga intactos). Matriz 2x2 (prompt x datos), Rob% holdout
(trivial 86,7):

  |         | datos finos | datos realistas |
  | marco   | 83,9 (bajo) | 86,7 sd0 colapso |
  | neutral | 95,0 (OK)   | 86,7 colapso     |

El cuadrante decisivo neutral+realistas CAYO de 95,0 a 86,7: el mejor discriminador
perdio su ventaja solo por cambiar los datos. Confusion confirmada en ambos realistas:
predicen solido 29/30. Causa raiz (confirmada con longitud por clase de los TC: solido
1529, reformulacion 1039, no_ia 1162 chars): las clases de rechazo son naturalmente mas
finas y con el defecto prominente; al enriquecer las minorias se ENTERRO el defecto
decisivo (metrica vaga / sponsor colectivo / sin-IA) en contexto plausible, haciendolas
parecer solido. Veredicto: la hipotesis (3) [realismo cierra el gap] queda REFUTADA para
solidez (los datos finos generalizaban mejor, 95,0). Leccion normativa: lo que importa es
la SALIENCIA del defecto, no igualar longitud; el enriquecimiento de datos MUST mantener
las clases de rechazo finas/defecto-prominentes. Decision: NO escalar el enriquecimiento
realista a las otras 3 etapas. Mejor config de solidez = neutral+datos finos. Acciones de
cierre (este mismo dia): se revirtio el `SOLIDEZ` de `make_variations.py` a los VAR finos
y se promovio el prompt NEUTRAL a las 4 configs canonicas como base del orquestador (ver
Hallazgo 2). Eventual hipotesis nueva de "realismo asimetrico" (enriquecer solo solido,
minorias finas) queda fuera de alcance.

Hallazgo 4 (few-shot en fast_gate; mejora CONFIRMADA). Se agrego demos del trainset
(LabeledFewShot, k=8 -> cubre las 4 clases determinísticamente con seed 0) sobre el prompt
neutral, en el banco ideal: fast_gate tiene test BALANCEADO (8/7/7/8), asi que la mejora es
real y no la enmascara un colapso a clase mayoritaria. Resultado: Rob 66,7% (neutral, n=3)
-> 72,0% (few-shot, n=5: 73/77/67/77/67), +5,3pp. Y eso CON demos flacos: en el train de
fast_gate `razonamiento` y p1..p5 estan vacios (0/30), asi que los demos son ficha->color
sin razonamiento (debil para `cot`). Queda como siguiente paso "few-shot rico" (poblar el
razonamiento de los demos). Brazo en Caso aparte `flujo_intents_fast_gate_fewshot_v1.yaml`.

Bug del optimizer (hallado al perseguir candidates.json). `GEPAOptimizer` construia
`dspy.GEPA` con un try/except todo-o-nada; como esta version de dspy no acepta
`max_text_length`, el `except` caia al fallback basico y DESCARTABA todos los opcionales
(`track_stats`, `skip_perfect_score` -del fix 8a8aee4-, `use_merge`,
`candidate_selection_strategy`, `reflection_minibatch_size`, `max_merge_invocations`), que
quedaban INERTES. Fix: filtrar los opcionales por la firma real de `dspy.GEPA` y pasar solo
los soportados (los demas se omiten con warning). Con `track_stats` activo, `candidates.json`
y el bloque de evolucion en consola pasan a funcionar en runs futuros. Los runs hasta hoy
(incluido el A/B few-shot) corrieron sin esos params; el +5,3pp sigue valido porque ambos
brazos compartian el mismo defecto.

Reconocimiento de tandas: el registro por-run (`metricas_optimizacion.csv`) no guarda
hash de dataset; el leaderboard agrupa por `title`. Por eso cada cambio de contenido de
dataset SHOULD ir con tag de version en el title (`datos realistas vN`) para no mezclar
versiones bajo el mismo Caso.

Cambios:
- `dspy_gepa_poc/configs/flujo_intents_{intake,triage_solidez,triage_factibilidad,fast_gate}_neutral_v1.yaml`
  (variantes neutrales, `eval_repeats: 1`).
- `flujo_intents_triage_factibilidad.yaml`: `title` "...factibilidad y riesgo" -> "...factibilidad"
  (riesgo lo clasifica el Fast Gate; provenance al `description`). Relabel de 2 filas
  historicas en `metricas_optimizacion.csv` para no partir el Caso.
- `flujo_intents_triage_solidez_datos_v1.yaml` (marco+realistas) y
  `flujo_intents_triage_solidez_neutral_datos_v1.yaml` (neutral+realistas): brazos del pilot.
- `flujo_intents/make_variations.py`: bloque `SOLIDEZ` reescrito (45 casos realistas);
  datasets regenerados (`make_variations` + `dataset`).
- `specs/SPEC-102`: correccion de la deuda falsa (split real 30/15/30) + hallazgos.
- `reflexio_declarativa.py`: persistencia de candidatos GEPA (`build_candidates_payload`,
  `_save_candidates` -> `candidates.json` por run) para auditar las propuestas que la
  metrica NO adopto (antes solo en consola). `tests/test_candidates_payload.py` (5 tests).
  Aplica solo a runs futuros.
- Few-shot rico (siguiente paso de Hallazgo 4): plomeria para que `razonamiento` viaje de
  `make_variations` al CSV (`case()` + `_FG_RAZONAMIENTO` con 30 justificaciones del train
  de fast_gate; `dataset.py::_read_variations`/`_row`). Brazo A/B
  `flujo_intents_fast_gate_fewshot_rico_v1.yaml` (demos con razonamiento) contra el flaco
  (72,0%). Se retiro el config flaco `*_fewshot_v1` (lee el mismo CSV ya enriquecido, asi
  que re-correrlo mentiria); sus 5 runs quedan como referencia en el leaderboard.
- `dspy_gepa_poc/optimizer.py`: fix del armado de `dspy.GEPA` (filtrar opcionales por firma
  en vez de try/except todo-o-nada); reactiva `track_stats` y demas params que estaban
  inertes. Habilita `candidates.json` y la evolucion GEPA en runs futuros.
- Decision adoptada: prompt NEUTRAL como base. Las 4 configs canonicas
  `flujo_intents_{intake,triage_solidez,triage_factibilidad,fast_gate}.yaml` pasan a la
  instruccion neutral (provenance §/marco movida al `description`); el orquestador lo toma
  como `baseline`. Se retiraron las 6 variantes (`*_neutral_v1`, `*_datos_v1`,
  `*_neutral_datos_v1`) y se revirtio el dataset de solidez a VAR finos. Caveat: las
  canonicas conservan su `title`, asi que corridas futuras se mezclan con los runs marco
  historicos bajo el mismo Caso (decision explicita: marco queda como referencia).

[SDD-Check]
- Spec afectada: `SPEC-102-flujo-intents` (sigue draft, iter 1); deuda corregida y ampliada.
- Includes: 4 configs neutrales, 2 configs de pilot de datos, rename de etapa 3,
  reescritura de `SOLIDEZ` realista, 3 analisis (desbalance, ablacion de framing,
  colapso por realismo). Excludes: enriquecimiento realista de las otras 3 etapas
  (DESCARTADO: hipotesis (3) refutada en el pilot de solidez), reporte de accuracy por
  clase en el leaderboard (hoy se calcula con script ad-hoc).
- Validaciones: `./shared/utils/ci_local.sh` PASO (480 tests, cobertura 92,39%);
  configs nuevas cargan con AppConfig; matriz de confusion de solidez verificada en vivo.
- SSOT afectado: `dspy_gepa_poc/configs/`, `dspy_gepa_poc/flujo_intents/make_variations.py`,
  `dspy_gepa_poc/datasets/`, `specs/SPEC-102`.
- Decision de diseno: pilot de realismo acotado a una etapa antes de escalar a las 4
  (evita reescribir 240 casos sobre una hipotesis sin validar); brazos como Caso aparte
  para A/B limpio.
- Deuda arrastrada: D-012 reformulada (el holdout esta desbalanceado y la metrica global
  enmascara colapso a clase mayoritaria; reportar accuracy POR CLASE y/o rebalancear el
  test). Pilot de realismo CERRADO (refutado); revert de datos a VAR finos y promocion del
  prompt neutral a las 4 canonicas (base del orquestador) HECHOS. Sin pendiente operativo.

### 2026-06-15 (cont.) — Few-shot rico: resultado + fix real de `candidates.json`

3 corridas de `flujo_intents_fast_gate_fewshot_rico_v1` (demos con `razonamiento`).
Resultado: Rob 73,3 / 70,0 / 76,7 -> promedio 73,33 (Delta -18,33 vs trivial 91,67).

Comparativa de los 3 niveles de few-shot en fast_gate (mismo prompt neutral, test
balanceado 4 colores):
- Sin few-shot (neutral v1): Rob 66,67
- Few-shot flaco (demos sin razonamiento, k=8): Rob 72,00
- Few-shot rico (demos con razonamiento, k=8): Rob 73,33

Lectura: rico repite la ganancia de "tener demos" (+6,7pp vs sin few-shot) pero el
razonamiento en los demos NO aporta sobre el few-shot flaco mas alla del ruido
(+1,3pp, dentro del std~3-5pp de ambos brazos). Hallazgo 4 cierra: el salto fuerte es
"agregar demos"; enriquecerlos con cadena-de-razonamiento es marginal en este caso.

Bug real de `candidates.json` (el fix de optimizer.py de esta fase NO era suficiente):
`dspy.GEPA.compile()` setea `detailed_results` (y `best_outputs`) en el PROGRAMA
DEVUELTO (`new_prog.detailed_results = ...`), no en `self` (la instancia de
`dspy.GEPA`). `GEPAOptimizer.get_detailed_results()`/`_print_stats()` leian
`self.optimizer.detailed_results`, que nunca existe -> `detailed` siempre `None` ->
nunca se imprimio "EVOLUCION GEPA" ni se escribio `candidates.json` en NINGUN run del
proyecto (verificado: 0 `candidates.json` en `dspy_gepa_poc/results/runs/`, incl. los
3 runs rico recien corridos con el fix de parametros ya aplicado).

Fix definitivo en `dspy_gepa_poc/optimizer.py`: `compile()` guarda
`self._compiled_program = optimized_program`; `get_detailed_results()`,
`get_best_outputs()` y `_print_stats()` leen de `self._compiled_program` en vez de
`self.optimizer`. Aplica a runs futuros (no retroactivo a los runs ya corridos).

Matriz de confusion en TEST (`per_field_accuracy.py --show-all`, nuevo flag, sobre los
3 runs rico = 90 predicciones, 27 errores = 70% prom., consistente con el leaderboard):

| Confusion           | Conteo | % errores |
|----------------------|-------:|----------:|
| Negro -> Rojo         |     13 |       48% |
| Amarillo -> Rojo      |      6 |       22% |
| Rojo -> Negro         |      4 |       15% |
| Verde -> Amarillo     |      4 |       15% |

Hallazgo 5: la confusion Negro<->Rojo bidireccional es el 63% de TODOS los errores
(17/27) -- el modelo no distingue confiablemente "Negro" (sin remedio) de "Rojo"
(alto riesgo gestionable), en ambas direcciones (no es solo sobre-escalada). El
patron Amarillo->Rojo (sobre-escalada, hipotesis previa) es real pero secundario
(22%). Hipotesis: el criterio Negro vs Rojo en el prompt no es operacional. Proximo
paso propuesto (no ejecutado): afinar esa descripcion en el prompt neutral + few-shot
rico, pilot manual sin GEPA, antes de gastar budget de optimizacion.

[SDD-Check]
- Spec afectada: `SPEC-102-flujo-intents` (Hallazgo 4 cerrado: demos > demos+razonamiento;
  Hallazgo 5 abierto: confusion Negro<->Rojo).
- Includes: analisis de las 3 corridas rico (leaderboard + comparativa de 3 niveles de
  few-shot); fix de `optimizer.py` (lectura de `detailed_results`/`best_outputs` desde
  el programa compilado, no desde la instancia de `dspy.GEPA`); flag `--show-all` en
  `per_field_accuracy.py` + matriz de confusion completa de fast_gate (Hallazgo 5).
  Excludes: re-correr los 72 runs historicos para generar sus `candidates.json` (no
  retroactivo); el pilot de prompt Negro/Rojo (propuesto, no ejecutado).
- Validaciones: `./shared/utils/ci_local.sh` PASO (475 tests, cobertura 92,39%).
- SSOT afectado: `dspy_gepa_poc/optimizer.py`, `dspy_gepa_poc/scripts/per_field_accuracy.py`.
- Pendiente: (a) confirmar end-to-end en la PROXIMA corrida de cualquier config que
  ahora aparezca el bloque "EVOLUCION GEPA" y se escriba `candidates.json`; (b) decidir
  si se ataca Hallazgo 5 (Negro vs Rojo) con un pilot de prompt.

### 2026-06-15 (cont.) — Hallazgo 5: revision de dataset fast_gate (enfoque por casos)

Para atacar Hallazgo 5 (confusion Negro<->Rojo, 63% de errores), se descarta de
entrada la opcion de afinar la definicion Negro/Rojo en el prompt: el objetivo del
experimento es que el sistema aprenda la distincion a partir de casos, no de una
definicion hardcoded (si el enfoque por casos falla en pruebas, el pilot de prompt
queda como fallback, no descartado).

Se diagnostico un GAP de diseno en `dspy_gepa_poc/flujo_intents/make_variations.py`
(`FAST_GATE`): todos los casos Rojo de train/val tenian P5=No (revision humana por
caso), mientras todos los Negro tenian P5=Si + naturaleza financiera/restrictiva. El
dataset nunca mostro el patron "P5=Si pero moderador/excepcion -> sigue en Rojo" que
si aparece en ~4/11 casos Rojo del test holdout (`flujo_intents_fast_gate.csv`:
TC-R-02 ajuste de limites dentro de bandas + revision 48hs; TC-R-03 resoluciones
acotadas a catalogo con escalada fuera de catalogo; TC-EXT-05 y TC-RECLA-01 accion
favorable solicitada por el cliente, excepcion al criterio (b)). El modelo aprendio
la regla espuria "autonomia -> Negro". Ademas, `VAR-FG-N01` (train, Negro: "ajusta
limites de credito... log ex-post") colisionaba semanticamente con TC-R-02 (test,
Rojo, escenario casi identico pero con bandas + revision documentada).

Fuente de los criterios de "alto impacto" usados para redactar los casos nuevos
(no se copian al prompt, solo informan el dataset): `Criterios Fast Gate V3.txt` y
`RECOMENDACION_ALTO_IMPACTO_FAST_GATE.md` en
`/datum1/Descargas/Claudio/analisis/Transformacion AI-Native Org/normativa/analisis_temporal/analisis_fast_gate/`
(moderador de escalada ex-post acotada; excepcion criterio (b) para acciones
favorables solicitadas por el cliente; criterio de escala >=10% base/>=100k clientes).

Cambio minimo, sin crecer el dataset (se preserva 30 train / 16 val / 30 test,
balance 8V/8A/7R/7N train, 4/4/4/4 val):
- `VAR-FG-R07` (train, Rojo): reescrito a "ajuste automatico de limite de credito
  dentro de bandas de politica, sin discrecionalidad fuera de ellas, con revision
  sistematica del log dentro de 48hs" -- moderador completo, espejo de TC-R-02.
- `VAR-FG-R04` (train, Rojo): reescrito a "agente de reclamos que aplica
  compensaciones acotadas a un catalogo aprobado por policy; fuera de catalogo
  escala a humano" -- moderador acotado a catalogo, espejo de TC-R-03.
- `VAR-FG-R11` (val, Rojo): reescrito a "alta automatica de cliente en CRM/
  facturacion, accion favorable solicitada por el propio cliente" -- excepcion
  criterio (b), espejo de TC-EXT-05/TC-RECLA-01.
- `VAR-FG-N01` (train, Negro): reescrito a "ajuste automatico de precios/descuentos
  sobre mas del 10% de la base de clientes activos, sin bandas ni catalogo acotado"
  -- alto impacto por escala (criterio a), sin colision con el nuevo R07.

`_FG_RAZONAMIENTO` actualizado para R04/R07/N01 (few-shot rico). Datasets
regenerados con `python -m dspy_gepa_poc.flujo_intents.make_variations` +
`python -m dspy_gepa_poc.flujo_intents.dataset`.

[SDD-Check]
- Spec afectada: `SPEC-102-flujo-intents` (Hallazgo 5: prueba de enfoque por casos
  antes de pilot de prompt).
- Includes: reescritura de 4 casos fast_gate (`VAR-FG-R04`, `VAR-FG-R07`,
  `VAR-FG-R11`, `VAR-FG-N01`) + `_FG_RAZONAMIENTO` correspondiente; regeneracion de
  `dspy_gepa_poc/datasets/flujo_intents_fast_gate.csv` y `variations/*.csv` (las 4
  etapas, por el flujo compartido). Excludes: cambios al prompt/instruction de
  `flujo_intents_fast_gate*.yaml`; el pilot de prompt (sigue como fallback).
- Validaciones: `./shared/utils/ci_local.sh` PASO (475 tests, cobertura 92,39%).
- SSOT afectado: `dspy_gepa_poc/flujo_intents/make_variations.py`,
  `dspy_gepa_poc/datasets/flujo_intents_fast_gate.csv`.
- Pendiente: correr GEPA sobre fast_gate con el dataset revisado y comparar la
  matriz de confusion Negro<->Rojo contra el baseline de Hallazgo 5 (13 Negro->Rojo,
  4 Rojo->Negro de 27 errores). Si la confusion no mejora, ejecutar el pilot de
  prompt como fallback (condicion explicita del usuario).

### 2026-06-15 (cont.) — Hallazgo 5: cierre. GEPA overfittea VAL chico; gana el prompt pilot SIN GEPA

Cierre de Hallazgo 5 (confusion Negro<->Rojo). Se completaron las dos pruebas que
quedaban pendientes del bloque anterior y el resultado invierte la hipotesis de
trabajo: el problema no era el dataset ni la falta de un buen prompt, sino la
**propia optimizacion GEPA**.

Modelos de toda la serie (relevante porque el siguiente paso es repetir con otros):
- Task LM: `azure/gpt-4.1-mini`, temperature 0.1, max_tokens 4000, cache off.
- Reflection LM (GEPA): `azure/gpt-4o`, temperature 0.1, max_tokens 4000.

Experimento 3 (dataset round-2). Se reescribieron 4 casos Negro de train
(`VAR-FG-N02`/`N05`/`N06`/`N07`) para codificar explicitamente un criterio de alto
impacto cada uno (b naturaleza / b+e financiero+profiling / c irreversibilidad / e
profiling), en estilo y longitud similares a los casos Negro del holdout, mas
`_FG_RAZONAMIENTO` correspondiente. Sobre `fewshot_rico_prompt_v1`, n=3 (TEST 90):
accuracy 71,1% (64/90), Negro->Rojo 11/26 errores. Frente al experimento previo
(75,6%, Negro->Rojo 12) la accuracy global RETROCEDIO y Negro->Rojo bajo solo 1
caso (ruido). El enfoque por casos no resolvio Hallazgo 5.

Hallazgo clave (la corrida "sospechosa"). De las 3 corridas de
`fewshot_rico_prompt_v1`, la mejor en TEST (76,7%) fue la unica en la que GEPA
**dejo el prompt identico al base** (`optimized_program.json` byte-identico a la
instruction del YAML; verificado por hash). Las dos en que GEPA si expandio el
prompt (a 6,5k y 6,9k chars) fueron las peores (66,7% y 70,0%). Las tres llevaron
VAL a 100%/93,8%: GEPA sobreajusta los 16 ejemplos de val a costa de TEST.

Experimento 4 (confirmacion N seeds del prompt base SIN GEPA). Via
`python -m dspy_gepa_poc.scripts.baseline_only --config
flujo_intents_fast_gate_fewshot_rico_prompt_v1.yaml` (evalua prompt base +
few-shot rico fijo, sin compilar GEPA), N=5: TEST media 75,3%, mediana/moda 76,7%
(23/30 en 4 de 5), rango 70,0-76,7 (6,7 pp). El 76,7% no fue suerte: es el punto
de operacion estable. GEPA, en esta tarea, solo puede igualarlo (cuando no toca el
prompt) o degradarlo (cuando lo toca).

Conclusion (acotada al perfil del caso, no generalizable a cualquier clasificacion):
para clasificacion ORDINAL de severidad en 4 niveles, con frontera tacita Rojo/Negro
(criterios de alto impacto deliberadamente fuera del prompt) y VAL chico (16 ej.),
GEPA overfittea y el prompt pilot manual + few-shot rico SIN optimizacion es la
config mas fuerte y estable. Negro->Rojo (~3/corrida en el punto estable) queda como techo estructural
de `gpt-4.1-mini` en esta distincion, no atacable por dataset ni por GEPA. Detalle
metodologico en `docs/LECCIONES_APRENDIDAS.md` seccion 11.

[SDD-Check]
- Spec afectada: `SPEC-102-flujo-intents` (Hallazgo 5: cierre).
- Includes: reescritura de `VAR-FG-N02`/`N05`/`N06`/`N07` + `_FG_RAZONAMIENTO` en
  `make_variations.py`; regeneracion de datasets; nueva seccion 11 en
  `docs/LECCIONES_APRENDIDAS.md`; este registro. Excludes: no se adopta el dataset
  round-2 como mejora (no rindio); no se cambia el prompt canonico de fast_gate.
- Validaciones: experimentos 3 y 4 medidos con `per_field_accuracy.py` y
  `baseline_only.py` (LLM real). `./shared/utils/ci_local.sh` PASO (476 tests,
  cobertura 93,12%) sobre el cambio de `make_variations.py`.
- SSOT afectado: `dspy_gepa_poc/flujo_intents/make_variations.py`,
  `dspy_gepa_poc/datasets/flujo_intents_fast_gate.csv`,
  `docs/LECCIONES_APRENDIDAS.md`.
- Recomendacion registrada: config de referencia de fast_gate = prompt pilot con
  few-shot rico, SIN GEPA-prompt-optimization, con `gpt-4.1-mini`.
- Prueba multi-modelo (cerrada): se repitio la serie con Task LM `azure/gpt-5-mini`
  / Reflection `azure/gpt-5`. gpt-5-mini queda ~12-13 pp por debajo en ambas
  condiciones (sin GEPA N=5: 62,7% vs 75,3%; con GEPA n=3: 58,9% vs 71,1%) y cambia
  el modo de fallo a sobre-escalacion sistematica (Verde->Amarillo 3->12,
  Amarillo->Rojo 6->10), manteniendo Negro->Rojo en 12. El reasoning model no sube
  el techo: lo baja y descalibra. La degradacion por GEPA se sostiene con modelo
  distinto -> es del regimen (VAL=16), no del modelo. Detalle en
  `docs/LECCIONES_APRENDIDAS.md` seccion 11.
- Deuda arrastrada: ninguna nueva (corrida GEPA por etapa sigue en D-012).

### 2026-06-14 — SPEC-102: flujo-intents (atencion multipaso de intents)

Nueva capacidad `SPEC-102-flujo-intents` (draft): pipeline de 5 etapas DSPy
agnosticas (intake, triage_solidez, triage_factibilidad, fast_gate, aprobacion)
que atiende un intent del Marco de Gobierno IA hasta recomendacion + auto-Verde.
Cada etapa LLM es un `module.type: dynamic` optimizable por GEPA con la interfaz
actual (`reflexio_declarativa --config flujo_intents_<etapa>.yaml`); el Fast Gate
clasifica `ficha -> color` directo (sin matriz en codigo, `p1..p5` diagnosticos).
La etapa `aprobacion` es un mapeo por config (no se entrena). El orquestador lee
SOLO `flujo_intents/flujo_intents.yaml` y encadena con gates/skip.

Hygiene de datos: ratio por etapa ~40/20/40 (train 30 / val 15 / test 30). El test
son los originales del proyecto de gobierno (`intake_clasificacion.csv` +
`triage_rechazos.csv`) recortados a 30 estratificado; train/val son 45 variaciones a
mano por etapa (`make_variations.py`, 180 casos en total). Sin fuga: ningun original
en train/val ni variacion en test. El mapeo rechazo->etapa es explicito por id (la
columna `marcadores` del CSV original esta desalineada por `;` sin comillas).

Cambios:
- `dspy_gepa_poc/flujo_intents/` (nuevo): `ficha.py` (serializacion + normalize_color),
  `dataset.py` (builder por etapa, holdout), `make_variations.py` (casos a mano),
  `aprobacion.py` (mapeo §9.1), `orchestrator.py` (run_flow + CLI), `flujo_intents.yaml`.
- `dspy_gepa_poc/configs/flujo_intents_{intake,triage_solidez,triage_factibilidad,fast_gate}.yaml`.
- `tests/test_flujo_intents.py` (20 tests, sin LLM).
- `specs/SPEC-102-flujo-intents.md` + registro. `pyproject.toml` (per-file-ignore E501
  para el modulo de datos `make_variations.py`).

[SDD-Check]
- Spec creada: `SPEC-102-flujo-intents` (draft, iter 1).
- Includes: 5 etapas (4 LLM + aprobacion mapeo), dataset builder con holdout,
  variaciones a mano, orquestador, 20 tests, spec. Excludes: optimizacion GEPA real
  de cada etapa (pendiente), simulacion de aprobacion humana, registro en Inventario.
- Validaciones: `./shared/utils/ci_local.sh` PASO (lint + format + bandit +
  pip-audit + 469 tests, cobertura 93.12%). Configs cargan con AppConfig y datasets
  con CSVDataLoader; `run_flow` verificado en vivo (Verde/Rojo/cortes); sin fuga
  train/test verificada por test.
- SSOT afectado: `specs/` (SPEC-102 + registro), `dspy_gepa_poc/` (subpaquete y
  configs nuevos), `pyproject.toml`.
- Decision de diseno: etapas agnosticas (la logica de negocio vive en prompts y
  casos, no en codigo) para re-optimizar sin reescribir ante cambios del Marco.
- Deuda arrastrada: D-012 (nueva) — optimizar cada etapa con GEPA y medir accuracy
  en el holdout; ampliar variaciones a mano si una etapa queda starved (train actual
  4-8 casos/etapa).

### 2026-06-10 — Auditoria de docs: correccion de contradicciones P1

Auditoria de redundancia/contradicciones sobre toda la documentacion. Se
corrigieron las 4 contradicciones de mayor prioridad:

- Estado SDD unificado al SSOT (`docs/SDD_PROTOCOLO.md`, T0-T2 activos):
  `CLAUDE.md` (+ copias `AGENTS.md`/`GEMINI.md`) decia "tramos 0-1" y
  `docs/CONTRIBUTING.md` decia "Tramo 2 con esqueleto listo".
- `gepa_standalone/docs/UNIVERSAL_OPTIMIZER.md`: variables legacy `AZURE_OPENAI_*`
  reemplazadas por `LLM_*`; eliminada la seccion de override `models.task`/
  `models.reflection` (el codigo solo soporta `temperature`/`max_tokens`);
  corregida la semantica de `skip_perfect_score`; referencia muerta
  `utils/leaderboard.py` -> `./analyze leaderboard` (`shared/analysis/`);
  agregado `rag` a los tipos de adapter validos.
- `docs/GEPA_STANDALONE_EN_DSPY_ANALISIS.md`: eliminado el "Modo V1" con
  `modules.py`/`adapters/` (inexistentes); modos reales `dynamic`/`pipeline`;
  estructura de `dspy_gepa_poc/` actualizada a los archivos vigentes.
- `docs/DEVELOPMENT.md`: "Flujo de trabajo tipico" reescrito al flujo declarativo
  real (CSV + YAML + dryrun + baseline + entry point), sin `modules.py`/`data.py`/
  `examples/`.

Hallazgos restantes de la auditoria registrados como deuda D-007/D-008/D-009/D-010.

Seguimiento (mismo dia): se resolvio D-007 verificando D-003/D-004 contra codigo
e historia de git. El modo `pipeline` (`73bdd1d`, 2026-05-21) cubre literalmente
ambas: multietapa via `stages` (D-003) y gate condicional via `routing` con
ahorro de tokens (D-004). El desfase se origino el 2026-06-03 al migrar la deuda
desde el checklist sin tildar de `MEJORAS_PENDIENTES_DSPY_GEPA_POC.md`, 13 dias
despues de que el codigo ya existiera. D-003/D-004/D-007 pasan a resueltas; lo
genuinamente pendiente (tests dedicados del pipeline y ausencia de caso activo)
queda re-acotado en D-011.

### 2026-06-03 — SPEC-101: triaje de casos para N seeds (+ fix matching DSPy)

Nueva capacidad `SPEC-101-triaje-casos-nseeds`: un runner que, antes de gastar
tokens, mira los resultados previos y los prerequisitos de TODOS los casos (ambos
engines) y propone solo los que vale la pena re-correr. A diferencia de
`run_demos_gepa.sh` (lista YAML a ciegas), clasifica cada caso en
RESUELTO/DUDOSO/SIN DATOS usando solo la referencia comparable por modelo
(criterio de SPEC-100 FR-008), verifica dataset/gold y delega la corrida en
`seed_protocol`.

En el camino se encontro y corrigio un bug preexistente de `seed_protocol`: para
DSPy `ConfigInfo` filtraba el CSV solo por `case.name`, pero la columna Caso
guarda el `title` (campo case unificado). Resultado: TODOS los casos DSPy daban
"Sin filas" en el protocolo y en el triaje. Fix: `case_names = {title, name}`
para ambos engines (antes solo GEPA). El protocolo N seeds ahora tambien
encuentra el historial DSPy.

Cambios:
- `shared/utils/seed_triage.py` (nuevo): `diagnose` (pura), `_matches`,
  `target_models`, `gold_is_unverified`, `collect_diagnoses`, `print_board`,
  `main` interactivo. Constantes `TRIAGE_VARIANCE_RANGE_PTS=5`,
  `TRIAGE_MIN_REFERENCE_ROWS=3`.
- `shared/utils/run_nseeds_triage.sh` (nuevo): wrapper fino estilo run_demos.
- `shared/utils/seed_protocol.py`: `case_names` unificado a {title, name} (fix).
- `tests/test_seed_triage.py` (nuevo): 16 tests (status, matches, prerequisitos,
  deteccion de gold).
- `specs/SPEC-101-*` + registro; `docs/PROTOCOLO_N_SEEDS.md` seccion "Triaje de
  casos".

Verificado en vivo (`--list`): triage v2/v3 -> RESUELTO (techo), email_urgency ->
DUDOSO (rango Rob 40), cv_profile -> DUDOSO (mejora sin confirmar); casos DSPy ya
aparecen con su historial tras el fix.

[SDD-Check]
- Spec creada: `SPEC-101-triaje-casos-nseeds` (depende de SPEC-100).
- Includes: triaje + wrapper + fix matching + tests + spec + doc. Excludes: no
  cambia el veredicto ni la ejecucion de corridas.
- Validaciones: `./shared/utils/ci_local.sh` PASO (lint + format + bandit +
  pip-audit + 437 tests, cobertura 93.12%). Tablero verificado en vivo.
- SSOT afectado: `docs/PROTOCOLO_N_SEEDS.md`, `specs/` (SPEC-101 + registro),
  `shared/utils/seed_protocol.py` (fix).
- Retrocompatible: el fix de matching solo AMPLIA lo que matchea (antes DSPy no
  encontraba nada); no afecta GEPA. El triaje es lectura pura (no gasta API).
- Deuda arrastrada: ninguna nueva. (El fix de matching DSPy reactiva el historial
  DSPy en el protocolo; conviene re-mirar conclusiones DSPy previas que se
  hubieran sacado creyendo "sin filas".)

### 2026-06-03 — SPEC-100 iter 2: comparabilidad de modelos en el veredicto

Una prueba real de N seeds (cv_extraction_v2, GEPA) destapo un confound: la
"referencia previa" agrupaba por Caso pero NO por modelo. Las 7 filas historicas
eran `task=gpt-5-mini` y la corrida nueva salio con `task=gpt-4.1-mini` (el modelo
lo fija el `.env`, que habia cambiado). El veredicto comparaba robustez entre
modelos distintos -> medía el cambio de modelo, no la intervencion (baseline
confound, leccion 10).

Fix (FR-008 en `SPEC-100`): `filter_reference_by_models` conserva de la referencia
previa solo las filas con el mismo par (`Modelo Tarea`, `Modelo Profesor`) que el
lote nuevo, y `report()` avisa con `[WARN]` cuantas excluyo. Si no queda ninguna
comparable -> `SIN REFERENCIA`. Verificado ademas en vivo: al re-correr con
`LLM_MODEL_TASK=azure/gpt-5-mini` (override de env, gana sobre `.env`), las 2 filas
gpt-4.1-mini de la corrida previa se auto-excluyen y la comparacion queda entre
gpt-5-mini homogeneo.

Cambios:
- `shared/utils/seed_protocol.py`: columnas `Modelo Tarea`/`Modelo Profesor`,
  helper `_models`, funcion pura `filter_reference_by_models`, filtrado + `[WARN]`
  en `report()` (incluye aviso de mezcla en `--report-only`).
- `tests/test_seed_protocol.py`: clase `TestComparabilidadModelos` (3 tests).
- `specs/SPEC-100-veredicto-senal-ruido.md`: FR-008, SC-005, escenario y coverage
  mapping; iteracion 1 -> 2. `specs/SPECS_REGISTRY.md`: Iter 2.
- `docs/PROTOCOLO_N_SEEDS.md`: paso de comparabilidad en el flujo y subseccion
  "Comparabilidad de modelos (prerequisito)".

[SDD-Check]
- Spec leida/editada: `SPEC-100-veredicto-senal-ruido` (iter 2; FR-008/SC-005).
- Includes: filtrado por modelo + WARN + tests + spec + doc. Excludes: no se toca
  `verdict` (sigue siendo pura sobre agregados ya filtrados) ni la ejecucion.
- Validaciones: `./shared/utils/ci_local.sh` PASO (lint + format + bandit +
  pip-audit + tests). Verificacion en vivo con corrida real gpt-5-mini.
- SSOT afectado: `shared/utils/seed_protocol.py`, `docs/PROTOCOLO_N_SEEDS.md`,
  `specs/SPEC-100-*` y `specs/SPECS_REGISTRY.md`.
- Retrocompatible: si el CSV no trae columnas de modelo, `_models` devuelve
  ('', '') y el filtro es no-op (no excluye nada). Salida adicional solamente.
- Deuda arrastrada: ninguna nueva.

### 2026-06-03 — Veredicto senal-vs-ruido automatico en seed_protocol

El protocolo de N seeds reportaba media/rango/desvio y gap val-test, pero la
lectura "mejoro o es ruido?" la hacia la persona a mano (criterio en prosa en
`docs/PROTOCOLO_N_SEEDS.md`). Se codifica ese criterio en una funcion pura
`verdict()` que emite un veredicto primario (MEJORA/REGRESION/RUIDO/SIN
REFERENCIA, por solapamiento de rangos de Robustez contra la referencia previa)
mas flags independientes (SOBREAJUSTE si gap>3, TECHO si baseline>=85 y delta
plano, ESTABILIZA si cae la varianza). Umbrales como constantes nombradas
(`GAP_OVERFIT_PTS=3`, `CEILING_BASELINE_PTS=85`, `NOISE_EPS_PTS=0.5`).

Ademas se renombra el concepto "vara" -> "referencia previa" en todo el codigo y
docs (decision del usuario): mas explicito y menos jerga.

Cambios:
- `shared/utils/seed_protocol.py`: constantes de umbral, `Verdict` (dataclass),
  `verdict()` (pura) y `_scaled()`; render del veredicto en `report()`; el `3`
  hardcodeado pasa a `GAP_OVERFIT_PTS`; rename "vara" -> "referencia previa".
- `tests/test_seed_protocol.py` (nuevo): 11 tests de `verdict()` cubriendo cada
  primario, cada flag, coexistencia, escala 0-1->0-100 y render.
- `docs/PROTOCOLO_N_SEEDS.md`: seccion "Veredicto automatico" con tabla de
  etiquetas y umbrales; rename; matiz en "Que NO hace" (es heuristico por
  rangos, no test de significancia formal).

La capacidad se formaliza ademas como `SPEC-100-veredicto-senal-ruido` (estado
active), que estrena el formato hibrido de spec y cierra D-002.

[SDD-Check]
- Spec leida/creada: `SPEC-100-veredicto-senal-ruido` (nueva; primera spec de
  capacidad del proyecto, registrada en `specs/SPECS_REGISTRY.md`).
- Includes: funcion `verdict` + flags + tests + doc + SPEC-100. Excludes: no se
  toca la ejecucion de corridas (`run_seeds`), el scoring ni el formato del CSV.
- Validaciones: `./shared/utils/ci_local.sh` PASO (lint + format + bandit +
  pip-audit + 419 tests, cobertura 93.12%). +11 tests nuevos. Coverage mapping
  de SPEC-100 verificado contra `tests/test_seed_protocol.py`.
- SSOT afectado: `docs/PROTOCOLO_N_SEEDS.md`, `shared/utils/seed_protocol.py`,
  `specs/SPECS_REGISTRY.md` y `docs/SDD_PROTOCOLO.md` (Tramo 2 -> activo).
- Retrocompatible: solo agrega salida (la seccion "Veredicto"); no cambia los
  numeros ni la ejecucion. `--report-only` y el flujo de corridas intactos.
- Limite registrado: el veredicto es heuristico (solapamiento de rangos +
  umbrales fijos), NO un test de significancia formal; es el criterio
  conservador del proyecto para N chico. El umbral TECHO=85 es una eleccion (la
  leccion 8 dice ">80"); se mitiga exigiendo baseline alto Y delta plano juntos.
- Deuda arrastrada: ninguna nueva; cierra D-002.

### 2026-06-03 — Poda del doc efimero de mejoras pendientes

Se elimina `docs/MEJORAS_PENDIENTES_DSPY_GEPA_POC.md`. Era un documento efimero
(fechado 2026-02-08) cuyo diagnostico ya estaba caduco: reportaba 45 tests / 19%
de cobertura cuando el CI actual corre 408 tests / 93%, y sus Tier 1-3 sobre CI,
tests de adapters, tests de `shared/analysis/` y creacion de SSOTs
(`ARCHITECTURE.md`/`CONTRIBUTING.md`/`DEVELOPMENT.md`) ya estaban cumplidos. Un
doc con la mayoria de su contenido contradiciendo el estado real es un
anti-patron SSOT.

Lo vivo se migro a deuda arrastrada antes de borrar: T4-1 -> D-003 (multietapa),
T4-2 -> D-004 (logica condicional), T2-2 -> D-005 (naming `dspy_gepa_poc`),
T3-4 -> D-006 (duplicacion restante). El resto del doc (resumen ejecutivo,
estado actual, tiers cumplidos) se descarta por caduco. Las "Fortalezas
(Mantener)" ya son invariantes en `docs/ARCHITECTURE.md`; no se duplican aqui.

[SDD-Check]
- Spec leida: n/a (mantenimiento de documentacion; sin spec de capacidad asociada).
- Includes: 4 deudas nuevas (D-003..D-006), baja del doc efimero, limpieza de su
  referencia en `00-INDEX.md`. Excludes: sin cambios de codigo ni de specs.
- Validaciones: n/a (solo `.md`; el CI ignora `**.md`).
- SSOT afectado: `historial/sdd.md` (este archivo) y `00-INDEX.md`.
- Deuda arrastrada: 4 nuevas (D-003..D-006), trasladadas desde el doc eliminado
  para que no se pierdan por olvido. D-003 sigue siendo la candidata a estrenar
  el formato de spec (ligada a D-002).
- Riesgos: ninguno; el contenido eliminado era diagnostico caduco o ya cubierto
  en otros SSOTs.

### 2026-06-02 — Fix: salida garabateada de los entry points en Git Bash/mintty

Sintoma: al correr los runners (`run_dspy_total.sh`, `run_demos_gepa.sh`) en
mintty (Git Bash, `MSYSTEM=MINGW64`) las lineas se pisaban entre si (cabeceras
sobreescritas por colas de otras lineas). El mismo entry point con stdout
redirigido a archivo sale perfecto (`cat -A` sin un solo `^M`).

Causa raiz: `python.exe` es un binario nativo de Windows y mintty usa un pty
estilo Unix; Git Bash los conecta con un puente pipe que reordena/retiene la
salida de Python y la mezcla con los `echo` del shell. No es `\r` en los datos
ni buffering de Python: por eso `PYTHONUNBUFFERED`, `stdbuf` y `newline` no lo
arreglan (ninguno toca el puente).

Cambios:
- `dspy_gepa_poc/run_dspy_total.sh` y `gepa_standalone/run_demos_gepa.sh`: helper
  `run_py()` que envuelve la llamada a `python` con `winpty` (incluido en Git
  Bash) cuando stdout es terminal (`[ -t 1 ]`) y winpty existe; si esta
  redirigido ejecuta directo. Ademas re-exec bajo `stdbuf -oL -eL` y
  `PYTHONUNBUFFERED=1` para ordenar el modo redirigido a archivo.
- `shared/display/formatting.py`: helper SSOT `configure_stdio()` (exportado por
  `shared/display`) que hace `reconfigure(encoding="utf-8", newline="\n",
  line_buffering=True)` sobre stdout/stderr. Invocado al inicio de `main()` en
  ambos entry points. El `encoding="utf-8"` evita el crash cp1252 al redirigir.

[SDD-Check]
- Spec leida: n/a (correccion de entorno/observabilidad; sin spec asociada).
- Includes: `run_py`/winpty en ambos `.sh`, `configure_stdio` y su cableado.
  Excludes: no se toca logica de optimizacion ni metricas.
- Validaciones: `./shared/utils/ci_local.sh` PASO (lint + security + 408 tests,
  cobertura 93%); `bash -n` OK en ambos `.sh`. El render bajo winpty se valida
  manualmente en mintty (no automatizable en CI Linux).
- Retrocompatible: en Linux/CI `winpty` no existe -> `run_py` ejecuta directo;
  `newline="\n"` es no-op (default) y `stdbuf` es nativo de coreutils.
- Deuda arrastrada: ninguna nueva.
- Riesgos: depende de `winpty` presente en Git Bash; alternativa documentada es
  usar Windows Terminal/conhost donde `python.exe` nativo funciona sin puente.

### 2026-06-02 — Logs unificados: prompts, evolucion GEPA y caracteres ASCII

Se nivela la salida de los dos motores hacia una vision unica y se eliminan los
caracteres no estandar que rompian en consolas Windows (cp1252).

Cambios:
- `shared/display/formatting.py`: nuevos helpers SSOT `print_prompt`,
  `format_candidate`, `print_gepa_evolution` (mejor de cada etapa, prompt
  completo) y `print_gepa_search_stats` (candidatos, metric calls, mejor idx).
- `dspy_gepa_poc`: el entry point ahora muestra PROMPT INICIAL/ORIGINAL/OPTIMIZADO,
  la evolucion de GEPA y las stats de busqueda, leidas de `detailed_results`
  (`GEPAOptimizer.get_detailed_results`). Antes DSPy no exponia nada de esto.
- `gepa_standalone`: migra sus `print` ad-hoc de prompts a `print_prompt` y suma
  los mismos bloques de evolucion y stats (misma fuente `GEPAResult`).
- Limpieza de caracteres no estandar en codigo que emite logs: `shared/llm/config.py`
  (`->` en describe) y `shared/utils/check_deployments.py` (`[OK]`/`[X]`/`-`/`->`).

[SDD-Check]
- Spec leida: n/a (mejora de observabilidad; sin spec de capacidad asociada).
- Includes: helpers de display, cableado en ambos entry points, limpieza ASCII.
  Excludes: no se toca la logica de optimizacion ni las metricas; el `•` en CVs
  sinteticos (`build_cv_profile.py`) y los `→` en docstrings de tests quedan
  (son datos/documentacion, no salida de logs).
- Validaciones: `./shared/utils/ci_local.sh` PASO (lint + security + 408 tests,
  cobertura 93%).
- SSOT afectado: `shared/display/formatting.py` (SSOT de formato de terminal).
- Derivados: ninguno; las descripciones de prompts intermedios son post-hoc desde
  `detailed_results`, no se agrega flag `--verbose` a DSPy (decision: prompts
  completos siempre, mejor de cada etapa).
- Deuda arrastrada: ninguna nueva.
- Riesgos: si una version futura de `gepa`/`dspy` renombra `candidates` o
  `val_aggregate_scores`, los bloques se degradan a un `[WARN]` (DSPy) o no se
  imprimen; el resto del run no se ve afectado.

### 2026-06-01 — Adelgazamiento de entry files: extraccion a SSOTs

Se aplica el principio SSOT del propio repo a los entry files, siguiendo el modelo
del testigo `agent-test-suite` (entry files finos + detalle en `docs/`). Motivado
por dos sintomas: (a) el pipeline local `shared/utils/ci_local.sh` no se aplicaba
porque no estaba documentado como paso canonico; (b) triplicacion CLAUDE/AGENTS/
GEMINI con drift real (GEMINI tenia `split=dev` contra `val` correcto en
`csv_validator.py`).

Cambios:
- Nuevos SSOTs: `docs/DEVELOPMENT.md` (setup, comandos, pipeline local, entry
  points), `docs/ARCHITECTURE.md` (patrones e invariantes), `docs/CONTRIBUTING.md`
  (convenciones y workflow).
- Entry files reducidos a reglas-gatillo + protocolo de navegacion hacia los
  SSOTs. CLAUDE/AGENTS/GEMINI quedan identicos (regenerados por copia).
- `00-INDEX.md`: registra los 3 SSOTs nuevos y corrige la descripcion del entry.
- Se corrige la invariante `split`: `train`/`val`/`test` (fuente:
  `shared/validation/csv_validator.py` `VALID_SPLITS`).

[SDD-Check]
- Spec leida: n/a (cambio de documentacion; no hay spec de capacidad asociada).
- Includes: extraccion de Desarrollo/Patrones/Invariantes/Convenciones a docs/,
  entry files finos, 00-INDEX actualizado. Excludes: sin cambios de codigo.
- Validaciones: pendiente correr `./shared/utils/ci_local.sh` (CI ignora `**.md`,
  pero se corre para confirmar entorno sano).
- SSOT afectado: 3 docs nuevos + 00-INDEX.md + 3 entry files.
- Derivados: memoria de feedback `local_ci_pipeline` repunteada a DEVELOPMENT.md.
- Deuda arrastrada: ninguna nueva.
- Riesgos: los 3 entry files MUST mantenerse identicos a mano (decision explicita
  de no usar stubs); riesgo de drift futuro si se edita uno solo.

### 2026-06-01 — Tramo 2 esqueleto: registro de specs de capacidad

Se crea `specs/SPECS_REGISTRY.md` (vacio, solo capacidades) y la plantilla de
spec hibrida en `docs/SDD_PROTOCOLO.md`, siguiendo el modelo del testigo
`agent-test-suite`: specs de capacidad en `specs/`, docs en `docs/`, ambos unidos
por el Mapa de SSOTs de `00-INDEX.md` sin duplicarse. No se migra ningun doc ni
codigo existente. La primera spec real queda pendiente (D-002) hasta que aparezca
una capacidad nueva donde estrenar el formato.

### 2026-06-01 — Tramo 1 activo: circuito de aprendizaje

Se crea este archivo (`historial/sdd.md`) con la seccion *Deuda arrastrada*,
adoptando el mecanismo anti-cascada del proyecto testigo `agent-test-suite`
(ver `../../analisis/SDD/software/COMPARATIVA-SPECKIT-VS-TESTIGO.md`). Diferencia
clave frente a Spec Kit: el feedback bidireccional no queda como principio a
disciplina, sino instrumentado en un artefacto obligatorio.

Se inicializa la tabla con dos deudas reales preexistentes (D-001 datasets v2,
D-002 Tramo 2 SDD).

### 2026-06-01 — Tramo 0 activo: convenciones de salida

Alta del SSOT `docs/SDD_PROTOCOLO.md` y de la seccion "Protocolo SDD" en los tres
entry files (CLAUDE.md / AGENTS.md / GEMINI.md). Convenciones: bloque
`[SDD-Check]` por entrega, marcador `[NEEDS CLARIFICATION]`, lenguaje normativo
MUST/SHOULD/MAY. No invasivo: sin cambios en codigo ni estructura.
