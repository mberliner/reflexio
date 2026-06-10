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
| D-008 | Inconsistencias de criterio entre docs: regla de baseline (>80% en `LECCIONES_APRENDIDAS.md` seccion 8 vs >90% en `CUANDO_APLICAR_Y_CASOS_DE_USO.md`); donde viven los limites de longitud de texto (env-only segun `YAML_CONFIG_REFERENCE.md` vs YAML segun `UNIVERSAL_OPTIMIZER.md` y `LECCIONES_APRENDIDAS.md` seccion 4); campos soportados en codigo sin documentar (`models.max_tokens` GEPA, `skip_perfect_score` DSPy); `YAML_CONFIG_REFERENCE.md` lista module types `sentiment`/`extractor`/`qa` que `reflexio_declarativa.py` rechaza en runtime (solo `dynamic`/`pipeline`) | Auditoria de docs 2026-06-10 | Abierta |
| D-009 | Redundancia documental: `DSPY_DOCUMENTACION.md` y `GEPA_DOCUMENTACION.md` contienen material del framework upstream (instalacion, testing, citacion) que duplica SSOTs propios y una nota de cache contraria al default del proyecto; tabla de precios duplicada (`ANALISIS_UTILIDADES.md` vs `ROI_ANALYSIS.md` vs `DEFAULT_PRICING` en codigo); links relativos rotos en `gepa_standalone/README.md` y referencia `docs/GEPA_DOCUMENTACION.md` con base ambigua en el listado final de `gepa_standalone/docs/demo.sh`; referencia muerta `run_email_urgency_comparison.sh` en `LECCIONES_APRENDIDAS.md` seccion 7; typo en nombre de `docs/plan_implementcion_toma_requerimientos.md`; intro duplicada ES/EN en `README.md` raiz; parrafo obsoleto "cuando crear la primera spec" en `docs/SDD_PROTOCOLO.md` Tramo 2 (SPEC-100/101 ya existen) | Auditoria de docs 2026-06-10 | Abierta |
| D-010 | Datasets espejo entre subproyectos sin convencion registrada: 5 CSV son copias byte-identicas deliberadas (`cv_extraction_v3`, `cv_profile_v3`, `email_urgency`, `fast_gate_v1`, `triage_v1`) pero nada documenta ni protege la sincronizacion (riesgo de divergencia silenciosa); ademas `cv_triage_v3.csv` tiene mismo nombre y esquema distinto en cada engine (intencional pero indistinguible de un drift). Registrar la convencion en el SSOT que corresponda o validar en CI | Auditoria de docs 2026-06-10 | Abierta |
| D-011 | Modo `pipeline` sin tests ni caso activo: `create_pipeline_module` (`dynamic_factory.py`) y `create_pipeline_metric_with_feedback` (`metrics.py`) no tienen tests dedicados y ningun config vigente usa `module.type: pipeline` (el unico, `intake_pipeline.yaml`, se elimino al segmentar; ver `docs/FAST_GATE_SEGMENTACION.md`). Agregar tests unitarios y decidir si se formaliza como spec retrospectiva (rango reservado `SPEC-001..099`) | Cierre de D-003/D-004 (2026-06-10) | Abierta |

## Deuda resuelta

| ID | Descripcion | Resuelta | Cierre |
|---|---|---|---|
| D-002 | Primera spec de capacidad con formato hibrido | 2026-06-03 | `SPEC-100-veredicto-senal-ruido` estrena el formato (registrada en `specs/SPECS_REGISTRY.md`); Tramo 2 pasa a activo |
| D-003 | Soporte para flujos multietapa (multi-stage) en DSPy | 2026-06-10 | Ya estaba implementada en `73bdd1d` (2026-05-21): `DynamicModuleFactory.create_pipeline_module` compone N etapas en serie con signatures YAML (`stages`), validadas por `config_schema.py` y documentadas en `docs/YAML_CONFIG_REFERENCE.md`. La deuda se habia migrado el 2026-06-03 desde un checklist desactualizado. Resto pendiente (tests, caso activo) -> D-011 |
| D-004 | Logica condicional en modulos (etapa segun resultado de la anterior) | 2026-06-10 | Ya estaba implementada en `73bdd1d` (2026-05-21): seccion `routing` con gate (`gate_stage`/`gate_field`/`gate_value`); las etapas no abiertas por el gate no llaman al LLM e inyectan `skip_outputs_when_gated` (ahorro de tokens). Mismo origen del desfase que D-003. Resto pendiente -> D-011 |
| D-007 | Verificar si D-003/D-004 estaban cubiertas por el modo `pipeline` y cerrarlas o re-acotarlas | 2026-06-10 | Verificado contra codigo e historia de git: ambas cubiertas literalmente por `create_pipeline_module` (D-003 y D-004 cerradas); lo no cubierto (tests dedicados, ausencia de caso activo) quedo re-acotado en D-011 |

---

## Log de fases

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
