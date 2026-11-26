# SPEC-107-costo-real-por-resolucion — Costo real de cada combinacion de roles

Estado: draft
Iteracion: 1 (rev. 2026-11-26)
Depende de: [[SPEC-106-roles-intercambiables]] (combinacion de roles registrada y bucket `judge`), [[SPEC-104-fallas-tecnicas-justas]] (casos evaluados y probes de atribucion)
Relacionada con: [[SPEC-100-veredicto-senal-ruido]] (formato del CSV, comparabilidad), docs/ANALISIS_UTILIDADES.md, docs/METADATA_REPRODUCIBILIDAD.md

Origen: FR-007 y FR-008 de la iteracion 1 de SPEC-106, separados en su
iteracion 2 (2026-11-26) tras una revision que encontro huecos de definicion en
la formula, el uso por fase y el ROI.

## User Story (prioridad)

Como persona que compara combinaciones de estudiante, profesor y juez, quiero
saber cuanto cuesta de verdad optimizar con cada una y cuanto cuesta despues
cada caso resuelto por el estudiante, medido con tokens reales sobre los casos
de prueba, para elegir por costo real y no por precio por token.
Prioridad: P2

## Contexto (estado al 2026-11-26)

- `shared/llm/usage.py::UsageTracker` acumula tokens reales por bucket durante
  toda la corrida, sin distinguir fases. Con SPEC-106 FR-004 hay buckets `task`,
  `reflection` y `judge`.
- `Costo Real USD` del CSV es el costo total de la corrida (todas las fases),
  tarifado por `roi_calculator.cost_from_usage`.
- Ambos subproyectos evaluan con `eval_repeats` (k) repeticiones; los configs
  `_v2`/`_v3` usan k=3. `MetricSummary.n_evaluados` cuenta casos unicos.
- Las metricas por caso son continuas en [0, 1] en varios adapters (extractor
  por campo, RAG con juez, DSPy multi-campo).
- En RAG el juez corre tambien en la evaluacion de test: es costo de medicion,
  no de produccion.
- Los probes de atribucion contra el baseline (SPEC-104 FR-004,
  `shared/llm/attribution.py`) usan el rol `task` con el prompt baseline y pueden
  dispararse durante la evaluacion de test.
- En DSPy un caso puede costar mas de una llamada HTTP (fallback de adapter,
  modulos de varias etapas).
- `calculate_production_roi` compara el profesor en produccion (estimado por
  `DEFAULT_TOKEN_ESTIMATES`) contra el estudiante con el prompt optimizado.
  `leaderboard.py` no usa `Costo Real USD`. Ninguno lee `run.json`.

## Alcance

Incluye: uso medido por fase; tres costos por corrida; formula de costo por
resolucion con metricas continuas y k repeticiones; persistencia; presentacion
en ROI y leaderboard sin mezclar medido con estimado. Ambos subproyectos.

Excluye: medir al profesor resolviendo el test (corrida adicional);
recomendacion automatica de combinacion; cambiar la semantica de
`Costo Real USD`; tablas de precios nuevas (se usa la vigente).

## Requisitos funcionales

- FR-001 El uso real MUST medirse por fase y bucket. Fases:
  - `optimizacion`: desde el arranque hasta el fin de la seleccion del mejor
    candidato, incluidas las evaluaciones del baseline y del mejor candidato en
    val;
  - `test`: evaluacion del prompt optimizado sobre test, con sus k repeticiones;
  - `atribucion`: probes de SPEC-104 FR-004, en cualquier fase. MUST NOT sumarse
    al uso de `test`.
  - toda evaluacion del baseline sobre test, si existe, MUST ir a una fase
    `referencia`, no a `test`.
  La separacion MUST ser correcta con evaluacion multihilo (la fase no puede
  depender de estado local del hilo que no se propaga a los workers).
- FR-002 Por corrida completada MUST reportarse, con tokens reales y el precio
  del modelo de cada bucket:
  - `costo_optimizacion`: todos los buckets de la fase `optimizacion`;
  - `costo_por_caso_test`: costo del bucket `task` en `test` / (k x casos de
    test). Se mide por caso inferido, no por llamada HTTP, asi que incluye
    fallbacks, etapas y tokens de razonamiento;
  - `costo_por_resolucion`: costo del bucket `task` en `test` / S, donde S es la
    suma de los scores de los casos evaluados (SPEC-104 FR-003) en las k
    repeticiones. Con metrica binaria equivale a costo por caso resuelto. Con
    metrica continua cuenta casos equivalentes. k se cancela. El numerador
    incluye las llamadas de los casos no evaluados, porque se pagaron.
- FR-003 El costo del juez en `test` y el de las fases `atribucion` y
  `referencia` MUST reportarse aparte como costo de medicion, y MUST NOT entrar
  en `costo_por_caso_test` ni en `costo_por_resolucion` (en produccion no hay
  juez ni probes).
- FR-004 Casos limite: con S = 0, sin casos evaluados, con testset vacio o con
  un modelo sin precio en la tabla, el costo afectado MUST reportarse como `N/A`
  con el motivo, nunca como 0 ni infinito. Una corrida abortada MAY reportar los
  costos de las fases que completo, marcada como abortada.
- FR-005 `Costo Real USD` MUST conservar su semantica (total de la corrida, todas
  las fases) y debe coincidir con la suma de los costos por fase.
- FR-006 Persistencia: los tres costos y el uso por fase y bucket MUST quedar en
  `run.json`.
  [NEEDS CLARIFICATION: ademas, columnas nuevas en el CSV maestro (tercera
  excepcion a SPEC-100 FR-007, con migracion que deja vacias las filas
  antiguas), o que `roi_calculator` y `leaderboard` lean `run.json`
  (rutas con `\` de Windows, filas sin `run.json` anteriores a 2026-01-12)?
  Recomendacion: columnas en el CSV, porque todo el analisis ya lee el CSV y
  `run.json` queda como detalle.]
- FR-007 ROI y leaderboard:
  - MUST mostrar los costos medidos de FR-002 cuando existan, en columnas
    propias, y "sin medicion" en corridas antiguas.
  - El ROI de produccion MUST seguir marcado como estimado mientras
    `cost_without_gepa` sea una estimacion. MUST NOT combinar un
    `cost_with_gepa` medido con un `cost_without_gepa` estimado en el mismo
    calculo.
  - Los grupos que mezclan corridas medidas y antiguas MUST indicarlo.
  [NEEDS CLARIFICATION: se quiere un ROI de produccion medido? Exige medir al
  profesor (o al modelo de referencia) resolviendo el test, que es una corrida
  extra y sale del alcance actual.]
- FR-008 Los costos MUST compararse solo entre corridas de la misma combinacion
  (terna de [[SPEC-106-roles-intercambiables]] FR-006).
- FR-009 MUST documentarse en `docs/ANALISIS_UTILIDADES.md` (formulas y
  columnas) y `docs/METADATA_REPRODUCIBILIDAD.md` (bloque de costos de
  `run.json`).

## Criterios de exito (medibles, agnosticos a tecnologia)

- SC-001 El 100% de las corridas completadas nuevas reportan los tres costos de
  FR-002 (o `N/A` con motivo segun FR-004).
- SC-002 `costo_por_resolucion` coincide con el calculado a mano desde el uso por
  fase y bucket, los scores por caso de test y la tabla de precios, con k=1 y
  con k=3.
- SC-003 Con datos sinteticos, una corrida con k=3 y otra con k=1 de igual
  comportamiento por repeticion dan el mismo `costo_por_resolucion`.
- SC-004 Un probe de atribucion durante test no cambia `costo_por_caso_test`
  ni `costo_por_resolucion`.
- SC-005 La suma de los costos por fase coincide con `Costo Real USD`.
- SC-006 `./shared/utils/ci_local.sh` verde y sin cambio de `Costo Real USD` en
  corridas comparables.

## Escenarios (Given/When/Then)

- Given dos combinaciones con el mismo caso, When una tiene precio por token mas
  bajo pero resuelve menos o consume mas tokens por caso, Then su
  `costo_por_resolucion` lo refleja y puede ser mayor.
- Given una corrida RAG, When termina, Then el costo del juez en test aparece
  como costo de medicion y no en el costo por caso del estudiante.
- Given una corrida sin ningun caso evaluado en test, When se reporta, Then
  `costo_por_resolucion` es `N/A` con motivo "sin casos evaluados".
- Given una corrida anterior a esta spec, When se arma el leaderboard, Then sus
  costos medidos figuran como "sin medicion" y el ROI como estimado.

## Coverage mapping (requisito -> derivado)

| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | `shared/llm/usage.py` (fase), `shared/llm/attribution.py`, orquestadores de ambos subproyectos (pendiente) |
| FR-002 | `shared/analysis/roi_calculator.py`, registro de corrida en ambos subproyectos (pendiente) |
| FR-003 | idem FR-002 (pendiente) |
| FR-004 | idem FR-002; tests de casos limite (pendiente) |
| FR-005 | `shared/analysis/roi_calculator.py::cost_from_usage` (pendiente) |
| FR-006 | `shared/logging/metadata.py`, segun la clarificacion `shared/logging/csv_writer.py` y `shared/utils/migrate_metrics_csv.py` (pendiente) |
| FR-007 | `shared/analysis/roi_calculator.py`, `shared/analysis/leaderboard.py` (pendiente) |
| FR-008 | idem FR-007 (pendiente) |
| FR-009 | `docs/ANALISIS_UTILIDADES.md`, `docs/METADATA_REPRODUCIBILIDAD.md` |
| SC-001..SC-005 | tests con uso y scores sinteticos + verificacion sobre una corrida real (pendiente) |
| SC-006 | `./shared/utils/ci_local.sh` |
