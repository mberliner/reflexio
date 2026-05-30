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
2. FOTO PREVIA (read_rows): filas existentes del caso -> "vara"
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
   agrega Base/Opt/Robustez: media, min, max, rango, desvio
   escala GEPA 0-1 -> 0-100
   gap val-test = media(Opt) - media(Rob)   (>3 pts -> marca posible sobreajuste)
   delta robustez vs vara previa
   v
SALIDA por stdout (el protocolo NO escribe a disco).
```

### Que NO hace

- No calcula scores propios: solo dispara las corridas estandar y lee el CSV.
- No hace test de significancia: entrega media, rango y desvio; la lectura de
  "se solapan los rangos?" la hace la persona.
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

Comparar el lote `_v2` contra su vara, no una corrida suelta:

1. El rango del lote nuevo NO se solapa con el de la vara previa.
2. El gap val-test (Opt - Rob) es <= 3 pts (gaps mayores indican sobreajuste:
   el optimizado sube en val pero no generaliza a test).
3. Caer la varianza entre seeds (rango/desvio mas chico) tambien cuenta como
   exito: significa que la intervencion estabilizo la seleccion del prompt.

Por caso:

- Triage: reportar macro-F1 (no accuracy global, dominada por la clase
  mayoritaria) y verificar que baje el rango entre seeds.
- Profile: cerrar el gap val-test y que no haya corridas con Opt < Baseline.
- Extraction: que el rango del test se colapse (medicion fiable).

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
