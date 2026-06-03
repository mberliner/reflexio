# SPEC-100-veredicto-senal-ruido — Veredicto senal-vs-ruido del protocolo de N seeds

Estado: active
Iteracion: 2 (rev. 2026-06-03)
Relacionada con: docs/PROTOCOLO_N_SEEDS.md (SSOT del protocolo y sus umbrales)

## User Story (prioridad)

Como persona que evalua una intervencion de optimizacion, quiero que el protocolo
de N seeds dictamine automaticamente si el lote nuevo es una mejora real, ruido o
techo, para decidir "funciono o no" sin interpretar los numeros a mano cada vez.
Prioridad: P1

## Requisitos funcionales

- FR-001 El protocolo MUST emitir, por cada caso con lote nuevo, un veredicto
  primario unico en `{MEJORA, REGRESION, RUIDO, SIN REFERENCIA}`.
- FR-002 El primario MUST derivarse del solapamiento del rango de Robustez del
  lote nuevo contra la referencia previa: rangos disjuntos con el nuevo por
  encima -> `MEJORA`; disjuntos con el nuevo por debajo -> `REGRESION`; rangos
  solapados -> `RUIDO`; sin filas previas del caso -> `SIN REFERENCIA`.
- FR-003 El protocolo MUST emitir flags independientes, que MAY coexistir con
  cualquier primario:
  - `SOBREAJUSTE` cuando el gap val-test `(media Opt - media Rob) > GAP_OVERFIT_PTS`.
  - `TECHO` cuando `media Baseline >= CEILING_BASELINE_PTS` Y
    `(media Opt - media Baseline) <= NOISE_EPS_PTS` (condicion conjunta).
  - `ESTABILIZA` cuando el rango de Robustez del lote nuevo es menor que el de la
    referencia previa.
- FR-004 Cada veredicto y flag emitido MUST citar los numeros que lo dispararon
  (rangos, delta, gap), no solo la etiqueta.
- FR-005 La logica del veredicto MUST vivir en una funcion pura sin I/O,
  verificable de forma aislada (sin LLM ni subprocess).
- FR-006 Los umbrales MUST ser constantes nombradas (no literales en linea) y su
  semantica MUST documentarse en `docs/PROTOCOLO_N_SEEDS.md`.
- FR-007 El veredicto MUST ser salida adicional; MUST NOT alterar la ejecucion de
  corridas, el scoring ni el formato del CSV (retrocompatibilidad).
- FR-008 La referencia previa MUST igualar los modelos (`Modelo Tarea` y
  `Modelo Profesor`) del lote nuevo: las filas previas con un par de modelos
  distinto MUST excluirse antes de computar el veredicto (comparar robustez entre
  modelos invalida la conclusion: baseline confound, leccion 10). Cuando se
  excluyan filas, el protocolo MUST advertirlo (`[WARN]`) indicando cuantas. Si
  no queda ninguna fila comparable, el primario MUST ser `SIN REFERENCIA`.

## Criterios de exito (medibles, agnosticos a tecnologia)

- SC-001 El 100% de los casos con lote nuevo produce exactamente un primario.
- SC-002 Un caso con `media Baseline >= 85` pero `media Opt - media Baseline > 0.5`
  NO recibe flag `TECHO` (la condicion conjunta evita falsos techos cuando hay
  gradiente).
- SC-003 El veredicto produce el mismo dictamen sobre datos GEPA (escala 0-1) y
  DSPy (escala 0-100), normalizando ambos a 0-100 antes de decidir.
- SC-004 Existe al menos un test unitario por cada primario y por cada flag.
- SC-005 Dada una referencia previa con N filas de un modelo y M de otro, al
  correr seeds con el primer modelo la referencia efectiva tiene exactamente N
  filas y se reportan M exclusiones.

## Escenarios (Given/When/Then)

- Given un lote con rango de Robustez disjunto y por encima de la referencia
  previa, When se ejecuta el protocolo, Then el primario es `MEJORA`.
- Given un lote con rango de Robustez que se solapa con la referencia previa,
  When se ejecuta el protocolo, Then el primario es `RUIDO`.
- Given `media Baseline = 91` y `media Opt - media Baseline = +0.1`, When se
  evalua el lote, Then se agrega el flag `TECHO`.
- Given `media Opt - media Rob = 15`, When se evalua el lote, Then se agrega el
  flag `SOBREAJUSTE`.
- Given no hay filas previas del caso en el CSV, When se ejecuta el protocolo,
  Then el primario es `SIN REFERENCIA` y solo aplican flags internos.
- Given una referencia previa con filas de `gpt-5-mini` y de `gpt-4.1-mini`, When
  se corren seeds con `gpt-5-mini`, Then las filas de `gpt-4.1-mini` se excluyen,
  se emite `[WARN]` con la cuenta y el veredicto solo usa las filas de `gpt-5-mini`.

## Coverage mapping (requisito -> derivado)

| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | `shared/utils/seed_protocol.py::verdict` (primario unico); `tests/test_seed_protocol.py::TestPrimario` |
| FR-002 | `verdict` (logica de solapamiento); `TestPrimario::test_mejora_*`, `test_regresion_*`, `test_ruido_*`, `test_sin_referencia_*` |
| FR-003 | `verdict` (flags); `tests/test_seed_protocol.py::TestFlags` |
| FR-004 | `Verdict.reasons` + `Verdict.tag`; `TestEscalaYRender::test_reasons_no_vacio` |
| FR-005 | `verdict` es funcion pura; toda `TestPrimario`/`TestFlags` corre sin LLM ni subprocess |
| FR-006 | `GAP_OVERFIT_PTS`/`CEILING_BASELINE_PTS`/`NOISE_EPS_PTS` en `seed_protocol.py`; tabla en `docs/PROTOCOLO_N_SEEDS.md` (seccion "Veredicto automatico") |
| FR-007 | `report()` solo agrega salida; `run_seeds`/CSV intactos (entrada de fase 2026-06-03 en `historial/sdd.md`) |
| FR-008 | `filter_reference_by_models` + WARN en `report()`; `tests/test_seed_protocol.py::TestComparabilidadModelos` |
| SC-001 | `report()` llama a `verdict` una vez por caso con lote nuevo |
| SC-002 | `TestFlags::test_no_techo_si_hay_gradiente` |
| SC-003 | `TestEscalaYRender::test_scale_lleva_gepa_0_1_a_0_100` |
| SC-004 | `TestPrimario` (4) + `TestFlags` (4) cubren cada etiqueta |
| SC-005 | `TestComparabilidadModelos::test_conserva_solo_filas_con_mismos_modelos` |
