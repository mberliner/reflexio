# Protocolo de N Seeds (senal vs ruido)

SSOT del protocolo para distinguir mejoras reales de ruido en los casos de
optimizacion. Cubre el script `shared/utils/seed_protocol.py`, los configs y
datasets `_v2`, la convencion `gold_verificado` y la interpretacion de resultados.

## Proposito

Una corrida unica no distingue una mejora real de la suerte: las llamadas LLM
(temperatura > 0) y la busqueda estocastica de GEPA hacen que el mismo config
de un resultado distinto cada vez. El protocolo ejecuta cada caso N veces (seed
distinto por corrida) y reporta media, rango y desvio del lote, mas el gap
val-test, para que la decision "funciono o no" se tome sobre una distribucion y
no sobre un punto.

## Invocacion

Siempre como modulo desde la raiz del repo (ver convencion en `CLAUDE.md`):

```bash
python -m shared.utils.seed_protocol \
    --config dspy_gepa_poc/configs/dynamic_cv_profile_v2.yaml \
    --config dspy_gepa_poc/configs/dynamic_cv_triage_v2.yaml \
    --config gepa_standalone/experiments/configs/cv_extraction_v2.yaml \
    --seeds 5
```

Argumentos:

| Flag | Default | Descripcion |
|------|---------|-------------|
| `--config` | (requerido, repetible) | Ruta a config YAML. Una por caso. |
| `-n`, `--seeds` | 5 | Corridas por config. |
| `-j`, `--jobs` | 1 | Corridas en paralelo (1 = secuencial). |
| `--report-only` | off | No ejecuta; solo agrega filas ya presentes en el CSV. |

El framework (DSPy vs GEPA) y el CSV de metricas se infieren de la ruta del config.

## Que hace (flujo)

```
COMANDO: python -m shared.utils.seed_protocol --config ... --seeds 5
   |
   |  por CADA --config:
   v
1. ConfigInfo(yaml)
   - ruta "dspy_gepa_poc" -> entry dspy_gepa_poc.reflexio_declarativa
     ruta "gepa_standalone" -> entry gepa_standalone.universal_optimizer
   - case.name / title -> filtro del CSV
   - summary_csv del proyecto, dataset_path, eval_repeats
   v
2. FOTO PREVIA (read_rows): filas existentes del caso -> "referencia previa"
   v
   existe dataset?  --NO-->  [SKIP] (no gasta tokens)
   |  SI
   v
3. run_seeds(N): N subprocess (secuencial o -j en paralelo)
   seed 1 .. seed N:
      python -m <entry_point> --config <yaml>   (= corrida normal)
        self.seed = generate_seed()  (aleatorio, distinto cada vez)
        - eval baseline en val
        - GEPA optimiza (eval_repeats=k: cada medicion promedia k veces)
        - mide Optimizado en val
        - mide Robustez en test
      cada corrida ESCRIBE artefactos estandar:
        results/runs/<Caso>_<timestamp>/  (run.json, config_snapshot.yaml,
                                           optimized_program.json/final_prompt.txt)
        results/experiments/metricas_optimizacion.csv  (+1 fila)
        results/.metadata/  (environment.json, experiment.meta.json)
   v
4. FOTO POSTERIOR + report():
   nuevas = after - before  (por Run ID)
   COMPARABILIDAD: la referencia previa se filtra para conservar solo las filas
     con los mismos (Modelo Tarea, Modelo Profesor) que el lote nuevo; las demas
     se excluyen con [WARN] (comparar robustez entre modelos invalida la
     conclusion -> baseline confound, leccion 10).
   agrega Base/Opt/Robustez: media, min, max, rango, desvio
   escala GEPA 0-1 -> 0-100
   gap val-test = media(Opt) - media(Rob)   (>3 pts -> marca posible sobreajuste)
   delta robustez vs referencia previa
   veredicto: primario (MEJORA/REGRESION/RUIDO/SIN REFERENCIA) + flags
              (SOBREAJUSTE/TECHO/ESTABILIZA), citando los numeros
   v
SALIDA por stdout (el protocolo NO escribe a disco).
```

### Que NO hace

- No calcula scores propios: solo dispara las corridas estandar y lee el CSV.
- No hace test de significancia formal (t-test, intervalos de confianza): el
  veredicto es heuristico, basado en solapamiento de rangos y umbrales fijos
  (ver "Criterio de exito"). Es el criterio conservador del proyecto para N
  chico, no una prueba estadistica.
- No calcula macro-F1: el CSV guarda accuracy agregada (ver Limitaciones).
- No modifica leaderboard ni `analyze`; es complementario.

## Artefactos y trazabilidad

Cada corrida deja la metadata de reproducibilidad de 3 niveles (SSOT en
`docs/METADATA_REPRODUCIBILIDAD.md`). La cadena para auditar un resultado:

```
fila CSV (Run ID + Run Directory) --> results/runs/.../run.json --> seed + models
```

Trazabilidad (auditar de que corrida vino un numero): SI, completa.

Reproducibilidad (re-correr un seed y obtener lo mismo): NO. El seed se
genera con `generate_seed()` y solo se registra en `run.json`; no siembra
`random`/`numpy` ni se pasa a GEPA/DSPy, y no es inyectable desde config/env.
Es una etiqueta de auditoria, no una palanca de determinismo. Para el protocolo
esto es lo deseado: se busca variacion aleatoria distinta en cada seed para
medir varianza.

## Configs y datasets v2

Cada config `_v2` = baseline congelado + `eval_repeats: 3` + UNA intervencion
(una sola variable por experimento):

| Config | Intervencion | Dataset |
|--------|--------------|---------|
| `dspy_gepa_poc/configs/dynamic_cv_profile_v2.yaml` | umbrales fuzzy `industria_previa` y `educacion_principal` 0.70/0.75 -> 0.85 | `cv_profile.csv` (sin cambios) |
| `dspy_gepa_poc/configs/dynamic_cv_triage_v2.yaml` | `metric_feedback: true` + dataset balanceado | `cv_triage_v2.csv` |
| `gepa_standalone/experiments/configs/cv_extraction_v2.yaml` | dataset ampliado | `cv_extraction_v2.csv` |

Los datasets `_v2` se regeneran con `python -m shared.utils.build_cv_v2_datasets`.
Contenido redactado por un modelo distinto a los que estan bajo prueba (evita
circularidad), con ruido de la vida real inyectado en los inputs (acentos
faltantes, typos, emails con formato roto, fechas en formatos mixtos, mezcla
ES/EN, abreviaturas, campos ausentes). Balance:

- `cv_triage_v2.csv`: train 10, val 12 (4/4/4), test 21 (7/7/7).
- `cv_extraction_v2.csv`: train 6, val 10, test 20.

### Convencion `gold_verificado`

Ambos CSV `_v2` llevan la columna `gold_verificado` con valor `no`. Indica que
el gold es un BORRADOR generado automaticamente y debe ser revisado por una
persona (poner `si`) antes de confiar en los datos como test. La columna NO la
usa el pipeline: no es output de signature ni `required_field`, por lo que queda
fuera de `eval_fields` y no afecta el score. Es una desviacion deliberada del
esquema estandar de dataset (`split` + inputs + outputs).

## Criterio de exito (como reconocer una mejora)

Comparar el lote `_v2` contra su referencia previa, no una corrida suelta:

1. El rango del lote nuevo NO se solapa con el de la referencia previa.
2. El gap val-test (Opt - Rob) es <= 3 pts (gaps mayores indican sobreajuste:
   el optimizado sube en val pero no generaliza a test).
3. Caer la varianza entre seeds (rango/desvio mas chico) tambien cuenta como
   exito: significa que la intervencion estabilizo la seleccion del prompt.

**Comparabilidad de modelos (prerequisito).** La referencia previa solo es valida
si usa los MISMOS modelos (`Modelo Tarea` y `Modelo Profesor`) que el lote nuevo.
El protocolo lo garantiza automaticamente: filtra las filas previas con un par de
modelos distinto y avisa con `[WARN]` cuantas excluyo. Comparar robustez entre
modelos distintos mide el cambio de modelo, no la intervencion (baseline confound,
ver `LECCIONES_APRENDIDAS.md` seccion 10). El modelo lo fija el `.env`
(`LLM_MODEL_TASK`/`LLM_MODEL_REFLECTION`); para reproducir una referencia hay que
correr con su mismo par de modelos (se puede forzar por variable de entorno, que
gana sobre el `.env`).

### Veredicto automatico

Desde 2026-06-03 el protocolo emite un veredicto que codifica las tres reglas de
arriba (funcion pura `verdict` en `shared/utils/seed_protocol.py`, testeada en
`tests/test_seed_protocol.py`). Se compone de un **primario** (relacion de la
Robustez del lote nuevo con la referencia previa) y **flags** independientes que
pueden coexistir con cualquier primario:

| Etiqueta | Tipo | Condicion | Significado |
|---|---|---|---|
| `MEJORA` | primario | rangos de Rob disjuntos y el nuevo por encima | la intervencion supera el ruido entre seeds |
| `REGRESION` | primario | rangos disjuntos y el nuevo por debajo | empeoro de forma distinguible |
| `RUIDO` | primario | los rangos de Rob se solapan | delta indistinguible de la variacion entre seeds |
| `SIN REFERENCIA` | primario | no hay filas previas del caso en el CSV | no hay con que comparar el delta; solo aplican flags |
| `SOBREAJUSTE` | flag | gap val-test (Opt - Rob) > 3 pts | sube en val, no generaliza a test |
| `TECHO` | flag | baseline >= 85 Y (Opt - Base) <= 0.5 | baseline saturado y la optimizacion no mueve la aguja |
| `ESTABILIZA` | flag | rango de Rob del nuevo < rango de la referencia | la intervencion estabilizo la seleccion del prompt |

Umbrales (constantes nombradas en `seed_protocol.py`): `GAP_OVERFIT_PTS=3.0`,
`CEILING_BASELINE_PTS=85.0`, `NOISE_EPS_PTS=0.5`. El `TECHO` exige baseline alto
**y** delta plano de forma conjunta: un baseline de 86 con una mejora real de
+5 pp NO se marca como techo. El veredicto es una ayuda; el numero y su contexto
siguen mandando.

Por caso:

- Triage: reportar macro-F1 (no accuracy global, dominada por la clase
  mayoritaria) y verificar que baje el rango entre seeds.
- Profile: cerrar el gap val-test y que no haya corridas con Opt < Baseline.
- Extraction: que el rango del test se colapse (medicion fiable).

## Triaje de casos: que vale la pena re-correr

Antes de gastar tokens, el triaje (`shared.utils.seed_triage`, wrapper
`shared/utils/run_nseeds_triage.sh`) mira los resultados previos y los
prerequisitos de TODOS los casos (ambos engines) y propone solo los que conviene
re-correr. No gasta API: solo lee el CSV (capacidad `SPEC-101-triaje-casos-nseeds`).

```bash
./shared/utils/run_nseeds_triage.sh            # tablero + seleccion + corrida
./shared/utils/run_nseeds_triage.sh --list      # solo tablero
python -m shared.utils.seed_triage --list        # equivalente sin wrapper
```

Clasifica cada caso usando solo la referencia COMPARABLE (mismo modelo que usaria
una corrida nueva; el modelo objetivo sale del `.env`, y una env var lo fuerza):

| Estado | Cuando | Accion |
|---|---|---|
| `DUDOSO` | mejora sin confirmar (Rob < techo y Opt-Base > 0.5), alta varianza (rango Rob > 5), poca evidencia (n < 3) o sin referencia comparable | candidato a re-correr |
| `RESUELTO` | en techo (Rob >= 85) y estable | no re-correr |
| `SIN DATOS` | nunca corrido | curar/decidir antes |

Prerequisitos por caso: dataset ausente BLOQUEA la seleccion; `gold_verificado=no`
ADVIERTE (D-001) y exige confirmacion antes de lanzar. La seleccion ofrece solo
los `DUDOSO` seleccionables y delega la corrida en `seed_protocol` (que aplica el
veredicto de `SPEC-100`). Umbrales: `TRIAGE_VARIANCE_RANGE_PTS=5`,
`TRIAGE_MIN_REFERENCE_ROWS=3` (constantes en `seed_triage.py`).

## Limitaciones conocidas

- El seed es trazable pero no reproducible (ver arriba).
- El val sigue chico (triage 12, extraction 10): la senal de optimizacion de
  GEPA es coarse aunque el test ya sea fiable. `eval_repeats: 3` lo mitiga
  parcialmente.
- macro-F1 requiere predicciones por ejemplo, que el CSV no guarda; el protocolo
  solo agrega los scores agregados existentes.

## Referencias

- `docs/METADATA_REPRODUCIBILIDAD.md`: metadata de 3 niveles (seed, modelos, hash).
- `docs/ANALISIS_UTILIDADES.md`: leaderboard, ROI y estadisticas complementarias.
- `docs/LECCIONES_APRENDIDAS.md`: efecto techo, metrica exacta, hallazgos previos.
- `docs/GEPA_MANEJO_ERRORES.md`: descarte vs score 0 en GEPA.
