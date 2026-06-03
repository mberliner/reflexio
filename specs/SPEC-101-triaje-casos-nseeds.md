# SPEC-101-triaje-casos-nseeds — Triaje de casos para el protocolo de N seeds

Estado: active
Iteracion: 1 (rev. 2026-06-03)
Depende de: [[SPEC-100-veredicto-senal-ruido]]
Relacionada con: docs/PROTOCOLO_N_SEEDS.md

## User Story (prioridad)

Como persona que decide en que invertir corridas (que cuestan tokens), quiero un
runner que mire los resultados previos y los prerequisitos de cada caso y me
proponga solo los que vale la pena re-correr, para no elegir a ciegas ni gastar
en casos ya resueltos o sin datos curados.
Prioridad: P2

## Requisitos funcionales

- FR-001 El triaje MUST descubrir los configs de ambos engines
  (`dspy_gepa_poc/configs/*.yaml` y `gepa_standalone/experiments/configs/*.yaml`)
  y diagnosticar cada caso sin gastar API (solo lee el CSV).
- FR-002 Por cada caso MUST emitir un estado en `{RESUELTO, DUDOSO, SIN DATOS}`
  a partir de las filas previas COMPARABLES (mismo par de modelos que usaria una
  corrida nueva, criterio de [[SPEC-100-veredicto-senal-ruido]] FR-008).
- FR-003 Un caso MUST clasificarse `DUDOSO` cuando se cumpla alguno de:
  - mejora sin confirmar: `media Rob < CEILING_BASELINE_PTS` y `Opt - Base > NOISE_EPS_PTS`;
  - alta varianza: `rango Rob > TRIAGE_VARIANCE_RANGE_PTS`, o poca evidencia
    (`n_comparable < TRIAGE_MIN_REFERENCE_ROWS`);
  - sin referencia comparable: hay filas previas pero ninguna con el modelo objetivo.
  MUST clasificarse `RESUELTO` si esta en techo y estable; `SIN DATOS` si no hay
  filas del caso.
- FR-004 MUST verificar prerequisitos por caso y reflejarlos: dataset ausente es
  BLOQUEANTE (el caso no es seleccionable); `gold_verificado=no` es ADVERTENCIA
  (no bloquea, pero exige confirmacion explicita antes de correr).
- FR-005 La clasificacion MUST vivir en una funcion pura sin I/O, testeable de
  forma aislada.
- FR-006 La seleccion MUST ofrecer solo casos `DUDOSO` seleccionables, y el
  lanzamiento MUST delegar en `shared.utils.seed_protocol` (no reimplementar la
  corrida ni el veredicto).
- FR-007 El tablero MUST ordenarse con los `DUDOSO` primero y citar, por caso, la
  razon de su estado y los prerequisitos que fallan.

## Criterios de exito (medibles, agnosticos a tecnologia)

- SC-001 Casos historicamente en techo (`cv_triage_v2`, `cv_triage_v3`) se
  clasifican `RESUELTO`; casos con varianza alta conocida (`email_urgency`) se
  clasifican `DUDOSO`.
- SC-002 Un caso cuyo dataset no existe NO es seleccionable.
- SC-003 Un caso con `gold_verificado=no` aparece seleccionable pero con
  advertencia; al elegirlo, el runner pide confirmacion antes de lanzar.
- SC-004 Existe al menos un test por estado (`RESUELTO`/`DUDOSO`/`SIN DATOS`) y
  por prerequisito (dataset/gold).

## Escenarios (Given/When/Then)

- Given un caso con referencia comparable en techo y estable, When se ejecuta el
  triaje, Then su estado es `RESUELTO` y no se ofrece para correr.
- Given un caso con filas previas solo de otro modelo, When se ejecuta el triaje,
  Then su estado es `DUDOSO` con razon "sin referencia comparable".
- Given un caso sin dataset, When se ejecuta el triaje, Then se marca BLOQUEADO y
  no es seleccionable.
- Given el operador elige un caso con `gold_verificado=no`, When confirma la
  seleccion, Then el runner pide confirmacion extra antes de lanzar seeds.

## Coverage mapping (requisito -> derivado)

| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | `shared/utils/seed_triage.py::collect_diagnoses` (+ `CONFIG_DIRS`) |
| FR-002 | `diagnose` + `_matches` + `target_models`; `tests/test_seed_triage.py::TestStatus`, `TestMatches` |
| FR-003 | `diagnose` (umbrales `TRIAGE_*`); `TestStatus::test_dudoso_*`, `test_resuelto_*`, `test_sin_datos_*` |
| FR-004 | `diagnose` (blockers/warnings) + `gold_is_unverified`; `TestPrerequisitos`, `TestGoldDetection` |
| FR-005 | `diagnose` es funcion pura; toda `TestStatus`/`TestPrerequisitos` corre sin LLM ni subprocess |
| FR-006 | `main()` filtra `DUDOSO` seleccionables y hace `subprocess` a `seed_protocol` |
| FR-007 | `print_board` (orden `_STATUS_ORDER`, razones/warnings/blockers por fila) |
| SC-001 | verificado en vivo (tablero 2026-06-03): triage v2/v3 RESUELTO, email_urgency DUDOSO |
| SC-002 | `TestPrerequisitos::test_dataset_ausente_bloquea_seleccion` |
| SC-003 | `TestPrerequisitos::test_gold_no_verificado_advierte_pero_no_bloquea` + confirmacion en `main()` |
| SC-004 | `TestStatus` (6) + `TestPrerequisitos` (2) + `TestGoldDetection` (4) |
