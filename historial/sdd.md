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
| D-002 | Primera spec de capacidad con formato hibrido (esqueleto listo, registro vacio) | `docs/SDD_PROTOCOLO.md`, `specs/SPECS_REGISTRY.md` | Abierta — esperando primera capacidad nueva donde estrenar el formato |
| D-003 | Soporte para flujos multietapa (multi-stage) en DSPy: encadenar varios predictores/signatures en un modulo. Requiere extender `DynamicModuleFactory` y el esquema YAML. Esfuerzo alto. Candidata natural a estrenar el formato de spec (cierra D-002) | `docs/MEJORAS_PENDIENTES_DSPY_GEPA_POC.md` (T4-1, eliminado) | Abierta |
| D-004 | Logica condicional en modulos: ejecutar una etapa segun el resultado de la anterior (ahorro de tokens, derivar casos simples). Esfuerzo medio | `docs/MEJORAS_PENDIENTES_DSPY_GEPA_POC.md` (T4-2, eliminado) | Abierta |
| D-005 | Naming definitivo de `dspy_gepa_poc`: el sufijo "POC" ya no refleja el estado. Opciones evaluadas: `dspy_gepa`, `reflexio_dspy`. Impacto: renombrar modulo + imports en todo el repo. Esfuerzo medio | `docs/MEJORAS_PENDIENTES_DSPY_GEPA_POC.md` (T2-2, eliminado) | Abierta |
| D-006 | Reducir duplicacion restante: ~70 lineas de data loading (60% similitud) y ~200 de orquestacion (50%) entre subproyectos. Riesgo bajo. Esfuerzo medio | `docs/MEJORAS_PENDIENTES_DSPY_GEPA_POC.md` (T3-4, eliminado) | Abierta |

## Deuda resuelta

| ID | Descripcion | Resuelta | Cierre |
|---|---|---|---|
| — | — | — | — |

---

## Log de fases

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
