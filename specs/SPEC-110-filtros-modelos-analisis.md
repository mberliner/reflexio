# SPEC-110-filtros-modelos-analisis — Filtros combinables por caso, estudiante y profesor en el analisis

Estado: draft
Iteracion: 1 (rev. 2026-11-28)
Relacionada con: [[SPEC-106-roles-intercambiables]] (roles estudiante/profesor/juez en el CSV), [[SPEC-120-costo-real-por-resolucion]] (evaluacion economica por combinacion), docs/ANALISIS_UTILIDADES.md

## User Story (prioridad)

Como persona que analiza el historial de experimentos con `./analyze`, quiero
filtrar las corridas por caso, por modelo estudiante y por modelo profesor
mediante busqueda progresiva (cuanto mas completa la cadena, mas acotado el
resultado, hasta aislar un unico modelo), de forma independiente o combinada
con un `AND` logico en todos los subcomandos
(`leaderboard`, `roi`, `stats`, `budget`), para aislar el rendimiento, las
anomalias, el ROI, la evolucion temporal o el gasto de un modelo o par de
modelos sin ruido del resto del historial.
Prioridad: P2

## Contexto (estado al 2026-11-28)

- `shared/analysis/cli.py::add_common_args` define los filtros comunes `--csv`,
  `--project`, `--case` y `--no-merge` para los 4 subcomandos (`leaderboard`/
  `lb`, `roi`, `stats`, `budget`).
- Cada modulo de analisis (`leaderboard.py`, `roi_calculator.py`,
  `stats_evolution.py`, `budget_breakdown.py`) repite la misma expresion de
  filtrado por caso: `case_filter.lower() in d.get("Caso", "").lower()`.
- El CSV maestro (`metricas_optimizacion.csv`) guarda el modelo estudiante en
  `Modelo Tarea` y el modelo profesor en `Modelo Profesor` (con prefijo de
  proveedor cuando corresponde, p. ej. `azure/gpt-4.1-mini`,
  `anthropic/claude-sonnet-5-5`).
- Con multiples proveedores y combinaciones de roles (SPEC-103, SPEC-106), el
  leaderboard y el resto de reportes crecen en combinaciones por caso; hoy no
  se puede aislar un estudiante o un profesor desde el CLI ni desde las APIs de
  `shared.analysis`.

## Alcance

Incluye: filtros independientes por modelo estudiante (`Modelo Tarea`) y modelo
profesor (`Modelo Profesor`), combinables mediante `AND` logico entre si y con
`--case`, en los 4 subcomandos de `./analyze` (`leaderboard`/`lb`, `roi`,
`stats`, `budget`) y en las funciones `run(...)` de sus modulos; funcion pura
centralizada de filtrado en `shared/analysis/base.py`; correccion de
`--no-merge`, hoy ignorado por los 4 subcomandos (FR-009); tests unitarios y de
CLI; actualizacion de `docs/ANALISIS_UTILIDADES.md`.

Excluye: filtro por `Modelo Juez` (RAG, reservado para una iteracion posterior
si hace falta); operadores `OR`/`NOT`, listas multiples por flag o expresiones
regulares; coincidencia exacta normalizada sin prefijo; cambios en
`seed_protocol.py` o `seed_triage.py`.

## Requisitos funcionales

- FR-001 El CLI (`shared/analysis/cli.py::add_common_args`) MUST incorporar dos
  filtros de modelo opcionales en los 4 subcomandos (`leaderboard`/`lb`, `roi`,
  `stats`, `budget`), junto a `--case`:
  - `--student` con alias `--task` (`dest="student"`): filtra por la columna
    `Modelo Tarea`.
  - `--teacher` con alias `--reflection` (`dest="teacher"`): filtra por la
    columna `Modelo Profesor`.
  Ambos MUST aceptar una cadena opcional (default `None`, sin filtro). Si se
  pasan un flag y su alias en la misma invocacion, prevalece el comportamiento
  estandar de `argparse` para opciones con el mismo `dest` (el ultimo valor).
  El parser MUST conservar `allow_abbrev` por defecto de `argparse`: toda
  abreviatura ambigua se rechaza con error, lo que MUST documentarse en
  `docs/ANALISIS_UTILIDADES.md` con los casos que introduce esta spec: `--t`
  (`--task`/`--teacher`) en los 4 subcomandos y `--s` (`--student`/`--sort`) en
  `budget`; `--c` ya era ambigua (`--case`/`--csv`, y `--cuts` en `stats`).
  Cada `cmd_*` MUST propagar `args.student` y `args.teacher` a `run(...)` como
  `student_filter` y `teacher_filter`.
- FR-002 Los 3 filtros (`case_filter`, `student_filter`, `teacher_filter`) MUST
  actuar de forma independiente y combinarse mediante `AND` logico:
  - Si se informa uno solo, MUST filtrarse unicamente por esa dimension.
  - Si se informan dos o los tres, una fila MUST conservarse solo si cumple
    todos los filtros activos de manera simultanea.
  - Si ninguno esta activo (`None`, vacio o solo espacios en blanco), MUST
    devolverse la lista completa sin modificar el orden ni los registros.
  - Los filtros de fila MUST combinarse ademas en `AND` con `--project` (y con
    el CSV cargado via `--csv`).
  - Todo calculo derivado MUST operar sobre el subconjunto filtrado. En
    `stats`, los limites de lote automaticos (`calculate_batch_boundaries`) se
    calculan sobre las filas filtradas, por lo que el significado de cada lote
    depende de los filtros activos; MUST documentarse en
    `docs/ANALISIS_UTILIDADES.md`. Con `--cuts` los limites son fijos.
- FR-003 El criterio de coincidencia para las 3 dimensiones MUST ser busqueda
  progresiva: subcadena case-insensitive, consistente con `--case` vigente. El
  usuario acota el resultado extendiendo la cadena hasta donde corresponda
  (`gpt` -> `gpt-4` -> `gpt-4.1` -> `gpt-4.1-mini`); la ayuda del CLI y la
  documentacion MUST describir el filtro como busqueda progresiva:
  `needle in (row.get(column) or "").lower()`, donde `needle = filtro.strip().lower()`.
  - El filtro MUST evaluarse sobre el valor crudo de la columna, nunca sobre
    los valores por defecto que algunos modulos usan al agrupar (p. ej.
    `roi_calculator` y `budget_breakdown` agrupan una fila sin `Modelo Profesor`
    como `gpt-4o`; esa fila igual queda excluida por `--teacher gpt-4o`).
  - Una fila donde la columna este ausente o valga `None`/`""` MUST NOT lanzar
    excepcion y MUST quedar excluida si el filtro correspondiente esta activo.
  - Cambio aceptado sobre `--case` vigente: al pasar por `filter_metrics`,
    `--case` adopta `strip()`, trata vacio o solo espacios como "sin filtro" y
    tolera `Caso` ausente o `None`. Hoy `--case " "` filtra por casos que
    contienen un espacio; tras esta spec no filtra.
  - Nota explicita de matching por subcadena: un valor como `"gpt-4o"` coincide
    tanto con `"azure/gpt-4o"` como con `"azure/gpt-4o-mini"`, y `"claude"`
    coincide con toda familia `anthropic/claude-*`.
  - Limite conocido de la busqueda progresiva: cuando el nombre completo de un
    modelo es subcadena del de otro (p. ej. `azure/gpt-5` dentro de
    `azure/gpt-5.4`), ninguna cadena aisla al mas corto; el filtro devuelve
    ambos. MUST documentarse en `docs/ANALISIS_UTILIDADES.md`.
- FR-004 La logica de filtrado MUST centralizarse en una unica funcion pura sin
  I/O en `shared/analysis/base.py`:
  `filter_metrics(data: list[dict[str, Any]], case_filter: str | None = None, student_filter: str | None = None, teacher_filter: str | None = None) -> list[dict[str, Any]]`,
  exportada en `shared/analysis/__init__.py`. Los 4 modulos (`leaderboard.py`,
  `roi_calculator.py`, `stats_evolution.py`, `budget_breakdown.py`) MUST delegar
  el filtrado en esta funcion y MUST NOT duplicar la logica por caso/modelo.
  La funcion MUST NOT mutar `data` ni sus filas y MUST devolver siempre una
  lista nueva, tambien cuando ningun filtro esta activo.
- FR-005 La firma de `run(...)` en los 4 modulos (`leaderboard`,
  `roi_calculator`, `stats_evolution`, `budget_breakdown`) MUST agregar los
  parametros opcionales `student_filter: str | None = None` y
  `teacher_filter: str | None = None`, preservando `case_filter` y todos los
  parametros y defaults existentes para mantener compatibilidad con llamadores
  programaticos, incluido `output_dir: Path | None = None` de
  `leaderboard.run` (D-034).
- FR-006 Cuando los filtros aplicados no dejen ninguna fila coincidente, los 4
  modulos MUST imprimir `"No hay datos para analizar."` y retornar sin lanzar
  excepcion. En `leaderboard`, un resultado vacio MUST NOT crear ni sobrescribir
  `leaderboard.csv`, `leaderboard.md` ni graficos PNG.
  En `roi`, si el filtrado deja filas pero todos los grupos tienen
  `Modelo Tarea == Modelo Profesor` (p. ej. `--student gpt-4o --teacher gpt-4o`),
  MUST conservarse el comportamiento vigente: imprimir la `[NOTA]` de grupos
  omitidos y `"No hay grupos con sustitucion de modelo (Tarea distinto de
  Profesor) para calcular ROI."`, y retornar sin excepcion.
- FR-007 En `leaderboard`, los 3 filtros MUST aplicarse antes de agrupar por
  `(Caso, Modelo Tarea, Modelo Profesor)`, calcular `Estadisticas por Caso`,
  detectar `Anomalias` y escribir CSV/Markdown/graficos, de modo que todas las
  secciones de la salida sean coherentes con el subconjunto filtrado.
  La escritura de salida con `--student`/`--teacher` activos MUST ser identica
  a la de `--case` vigente: `leaderboard.csv`, `leaderboard.md` (salvo que
  `-o/--output` redirija el `.md`) y los PNG de `--graphs` se escriben con la
  vista filtrada en `output_dir` si se informa, o en `get_output_dir(project)`
  en caso contrario (`shared/analysis/output/` sin `--project`,
  `<proyecto>/results/` con `--project`).
  Con al menos un filtro de fila activo, `leaderboard.md` SHOULD incluir bajo
  la linea `Generado:` una linea `Filtros:` con los filtros activos (p. ej.
  `Filtros: caso=CV, estudiante=4.1-mini, profesor=claude`), para que una vista
  parcial sea reconocible; sin filtros activos la linea MUST NOT aparecer, de
  modo que la salida sin filtros no cambia (SC-005). `leaderboard.csv` no
  cambia de formato.
- FR-008 La ayuda del CLI (`shared/analysis/cli.py`) y el SSOT
  `docs/ANALISIS_UTILIDADES.md` MUST documentar `--student`/`--task` y
  `--teacher`/`--reflection`, su combinacion con `--case` en `AND` logico, el
  matching por busqueda progresiva (subcadena case-insensitive, incluyendo el
  aviso sobre subcadenas como `gpt-4o` vs `gpt-4o-mini` y el limite
  `gpt-5` vs `gpt-5.4`) y ejemplos de uso CLI y programatico.
- FR-009 `--no-merge` MUST tener efecto. Hoy los 4 `run(...)` llaman a
  `load_metrics(..., merge=True)` fijo y ningun `cmd_*` propaga
  `args.no_merge`. Los 4 `run(...)` MUST agregar `merge: bool = True` y
  pasarlo a `load_metrics`; cada `cmd_*` MUST pasar `merge=not args.no_merge`.
  Con `--no-merge` y mas de un CSV encontrado, MUST propagarse el `ValueError`
  vigente de `load_metrics`, que `cli.main` ya convierte en `Error: ...` y
  salida 1.

## Criterios de exito (medibles, agnosticos a tecnologia)

- SC-001 Los 4 subcomandos (`leaderboard`, `roi`, `stats`, `budget`) aceptan
  `--student`/`--task`, `--teacher`/`--reflection` y `--case` y filtran con la
  misma semantica `AND`.
- SC-002 Las 8 combinaciones de presencia/ausencia de los 3 filtros (ninguno,
  cada uno aislado, los 3 pares y los 3 simultaneos) quedan cubiertas por tests
  unitarios sobre `filter_metrics` y verificadas en `leaderboard.run(...)`;
  todo test que invoque `leaderboard.run(...)` aisla la salida con
  `output_dir=tmp_path` y no modifica `shared/analysis/output/` (D-034).
- SC-003 En `leaderboard`, con filtros activos, las tablas por modelo, las
  estadisticas por caso, las anomalias y los archivos CSV/Markdown generados
  incluyen solo filas que cumplen todos los filtros activos (las anomalias se
  verifican por `Run ID`, ya que esa seccion no muestra los modelos); cuando no hay
  coincidencias no se escribe ningun archivo y no se lanza error.
- SC-004 Los alias `--task` y `--reflection` producen en el parser del CLI el
  mismo resultado que `--student` y `--teacher` respectivamente.
- SC-005 Sin pasar los filtros nuevos ni `--no-merge`, las llamadas existentes
  (CLI y Python) mantienen comportamiento identico, salvo el cambio aceptado
  sobre `--case` con valores vacios o de solo espacios (FR-003), y
  `./shared/utils/ci_local.sh` pasa con 0 errores y cobertura >= 85%.
- SC-006 `roi`, `stats` y `budget` tienen al menos un test cada uno con un
  filtro de modelo activo y un subconjunto no vacio, que verifica que la salida
  contiene solo las combinaciones filtradas; y cada `cmd_*` tiene un test que
  verifica que propaga `student`, `teacher` y `merge` a `run(...)`.
- SC-007 Con `--no-merge` y dos CSVs encontrados, los 4 subcomandos terminan
  con `Error: ...` y codigo de salida 1; sin `--no-merge` se combinan como hoy.

## Escenarios (Given/When/Then)

- Given un CSV con corridas de `Email Urgency` (`gpt-4o-mini` / `gpt-4o`),
  `CV Extraction` (`gpt-4.1-mini` / `claude-sonnet-5-5`) y `CV Extraction`
  (`gpt-4.1-mini` / `gpt-4o`), con al menos una corrida anomala (p. ej.
  `Optimizado Score < Baseline Score`) en cada grupo, When se ejecuta
  `./analyze leaderboard --case CV --student 4.1-mini --teacher claude`,
  Then solo aparece el grupo `CV Extraction | gpt-4.1-mini | claude-sonnet-5-5`
  en la tabla principal, en estadisticas por caso y en anomalias (solo los
  `Run ID` anomalos de ese grupo), y `leaderboard.md` incluye la linea
  `Filtros:` con los 3 filtros.
- Given el mismo CSV, When se ejecuta `./analyze leaderboard --teacher claude`
  (sin `--case` ni `--student`), Then aparecen todas las corridas de cualquier
  caso y estudiante cuyo `Modelo Profesor` contenga `claude` (case-insensitive).
- Given el mismo CSV, When se ejecuta `./analyze roi --task 4.1-mini --reflection gpt-4o`,
  Then se evalua el ROI unicamente sobre filas donde `Modelo Tarea` contenga
  `4.1-mini` AND `Modelo Profesor` contenga `gpt-4o`.
- Given un CSV donde ninguna fila cumple la combinacion `--case Email --teacher claude`,
  When se ejecuta `./analyze leaderboard --case Email --teacher claude`, Then
  imprime `"No hay datos para analizar."`, no lanza excepcion y no escribe
  archivos de salida.
- Given un CSV de prueba con profesores `azure/gpt-5` y `azure/gpt-5.4` (valores
  presentes en los CSV maestros reales), When se
  ejecuta `./analyze leaderboard --teacher gpt-5`, Then aparecen ambos
  profesores (limite conocido, FR-003); When se ejecuta
  `./analyze leaderboard --teacher gpt-5.4`, Then aparece solo `azure/gpt-5.4`.
- Given filas con `Modelo Tarea == Modelo Profesor == azure/gpt-4o`, When se
  ejecuta `./analyze roi --student gpt-4o --teacher gpt-4o`, Then imprime la
  `[NOTA]` de grupos omitidos y el mensaje de "No hay grupos con sustitucion",
  sin excepcion.
- Given una fila sin la columna `Modelo Profesor` (o vacia), When se filtra con
  `--teacher gpt-4o`, Then la fila se excluye sin error; When no se pasa
  `--teacher`, Then la fila se conserva.

## Coverage mapping (requisito -> derivado)

| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | `shared/analysis/cli.py::add_common_args`, `cmd_*`; tests de parser CLI y de propagacion de `cmd_*` (pendiente) |
| FR-002 | `shared/analysis/base.py::filter_metrics`; tests de las 8 combinaciones `AND` (pendiente) |
| FR-003 | `shared/analysis/base.py::filter_metrics`; tests de case-insensitive, prefijos, espacios, valores faltantes, valor crudo vs default de agrupacion y `--case " "` (pendiente) |
| FR-004 | `shared/analysis/base.py::filter_metrics`, `shared/analysis/__init__.py`, 4 modulos de `shared/analysis/` (pendiente) |
| FR-005 | `run(...)` en `leaderboard.py`, `roi_calculator.py`, `stats_evolution.py`, `budget_breakdown.py` (pendiente) |
| FR-006 | tests de resultado vacio en los 4 modulos, no-escritura en `leaderboard` y grupos todos omitidos en `roi` (pendiente) |
| FR-007 | `shared/analysis/leaderboard.py::run`; tests sobre tabla, estadisticas, anomalias, archivos CSV/MD y linea `Filtros:` (presente con filtros, ausente sin ellos) (pendiente) |
| FR-008 | `shared/analysis/cli.py`, `docs/ANALISIS_UTILIDADES.md` (pendiente) |
| FR-009 | `run(...)` de los 4 modulos, `cmd_*` en `shared/analysis/cli.py`; tests de `--no-merge` (pendiente) |
| SC-001..SC-004, SC-006, SC-007 | `tests/test_shared_analysis.py` (pendiente) |
| SC-005 | `./shared/utils/ci_local.sh` (pendiente) |
