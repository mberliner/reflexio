# Utilidades de Analisis Compartidas

SSOT para las utilidades de analisis ubicadas en `shared/analysis/`.

## Descripcion General

Las utilidades de analisis permiten evaluar resultados de experimentos GEPA de forma unificada, independientemente del proyecto de origen (dspy_gepa_poc, gepa_standalone, o cualquier otro).

**Caracteristicas principales:**
- Auto-descubrimiento de CSVs de metricas
- Merge automatico de datos de multiples proyectos
- Agnostico a nombres de directorios
- CLI unificado con comandos especializados

## Estructura

```
reflexio/
├── analyze                      # CLI ejecutable principal
└── shared/analysis/
    ├── __init__.py              # Exports publicos
    ├── base.py                  # Carga de datos y utilidades comunes
    ├── cli.py                   # Dispatcher de comandos
    ├── leaderboard.py           # Ranking + anomalias + ROI
    ├── roi_calculator.py        # Calculo retorno de inversion
    ├── stats_evolution.py       # Evolucion temporal por lotes
    ├── budget_breakdown.py      # Desglose presupuesto por caso
    └── output/                  # Archivos generados (auto-creado)
```

## Uso via CLI

### Comando Principal

```bash
cd reflexio/
./analyze <comando> [opciones]
```

### Comandos Disponibles

| Comando | Alias | Descripcion |
|---------|-------|-------------|
| `leaderboard` | `lb` | Ranking completo con estadisticas, anomalias y ROI |
| `roi` | - | Calculo detallado de retorno de inversion |
| `stats` | - | Evolucion temporal dividida en lotes |
| `budget` | - | Desglose de presupuesto gastado por caso |

### Argumentos Comunes

Disponibles en todos los comandos:

| Argumento | Alias | Descripcion |
|-----------|-------|-------------|
| `--csv PATH` | - | Usar un archivo CSV especifico |
| `--project NAME` | - | Filtrar por nombre de proyecto (match por prefijo: `dspy`, `gepa`) |
| `--case TEXT` | - | Filtrar por columna `Caso` (busqueda progresiva) |
| `--student TEXT` | `--task` | Filtrar por modelo estudiante / columna `Modelo Tarea` (busqueda progresiva) |
| `--teacher TEXT` | `--reflection` | Filtrar por modelo profesor / columna `Modelo Profesor` (busqueda progresiva) |
| `--no-merge` | - | No combinar multiples CSVs (error y salida 1 si hay mas de uno) |

#### Filtrado combinable y busqueda progresiva

- **Combinacion con `AND` logico:** `--case`, `--student`/`--task` y `--teacher`/`--reflection` actuan de forma independiente y se combinan en `AND` entre si, ademas de combinarse en `AND` con `--project` (y con el archivo cargado via `--csv`). Una fila se conserva solo si cumple todos los filtros activos simultaneamente.
- **Busqueda progresiva (subcadena case-insensitive):** para las tres dimensiones de fila se recorta el espacio alrededor del filtro (`strip()`) y se busca como subcadena sin distincion de mayusculas sobre el valor crudo de la columna. El resultado se acota extendiendo la cadena (`gpt` -> `gpt-4` -> `gpt-4.1` -> `gpt-4.1-mini`). Un filtro vacio o de solo espacios se trata como "sin filtro".
- **Valor crudo vs defaults de agrupacion:** el filtro se evalua sobre el valor crudo del CSV antes de agrupar; una fila sin `Modelo Profesor` (ausente o vacio) queda excluida al pasar `--teacher gpt-4o`, aunque `roi` y `budget` usen `gpt-4o` como fallback al agrupar.
- **Matching por subcadena:** un valor como `gpt-4o` coincide tanto con `azure/gpt-4o` como con `azure/gpt-4o-mini`, y `claude` coincide con toda la familia `anthropic/claude-*`.
- **Limite conocido:** cuando el nombre completo de un modelo es subcadena del de otro (p. ej. `azure/gpt-5` dentro de `azure/gpt-5.4`), ninguna cadena de busqueda progresiva aisla al mas corto: `--teacher gpt-5` devuelve ambos, mientras que `--teacher gpt-5.4` aisla solo `azure/gpt-5.4`.
- **Abreviaturas ambiguas (`argparse`):** el parser conserva `allow_abbrev` por defecto, por lo que toda abreviatura ambigua se rechaza con error. En particular:
  - `--t` es ambigua en los 4 subcomandos (`--task` / `--teacher`).
  - `--s` es ambigua en `budget` (`--student` / `--sort`).
  - `--c` es ambigua en los 4 subcomandos (`--case` / `--csv`, y tambien `--cuts` en `stats`).
- **Sin coincidencias:** si los filtros no dejan ninguna fila, los 4 subcomandos imprimen `No hay datos para analizar.` y terminan sin error (y `leaderboard` no crea ni sobrescribe archivos).

### Ejemplos por Comando

#### leaderboard

```bash
# Analisis completo de todos los proyectos
./analyze leaderboard

# Solo proyecto dspy_gepa_poc
./analyze leaderboard --project dspy

# Generar graficos PNG (requiere matplotlib)
./analyze leaderboard --graphs

# Guardar markdown en ubicacion especifica
./analyze leaderboard -o /ruta/reporte.md

# Filtrar por caso
./analyze leaderboard --case "Email"

# Filtrar combinando caso, estudiante y profesor (AND)
./analyze leaderboard --case CV --student 4.1-mini --teacher claude

# Aislar un profesor en todos los casos y estudiantes
./analyze leaderboard --teacher claude
```

**Salidas generadas:**
- `shared/analysis/output/leaderboard.csv` (o `<proyecto>/results/` con `--project`)
- `shared/analysis/output/leaderboard.md` (o ruta indicada con `-o/--output`)
- `shared/analysis/output/performance_improvement.png` (con `--graphs`)
- `shared/analysis/output/roi_analysis.png` (con `--graphs`)

Con filtros de fila activos (`--case`, `--student`/`--task` o `--teacher`/`--reflection`), las tablas, estadisticas por caso, anomalias, CSV, Markdown y graficos reflejan solo el subconjunto filtrado, y `leaderboard.md` agrega una linea `Filtros: ...` bajo `Generado:` (`leaderboard.csv` mantiene el mismo formato). Sin filtros de fila activos, la linea `Filtros:` no aparece.

#### roi

```bash
# ROI para 1000 llamadas (default)
./analyze roi

# ROI para volumen especifico
./analyze roi --volume 5000

# Solo un proyecto
./analyze roi --project standalone --volume 10000

# Filtrar por estudiante y profesor (usando alias --task y --reflection)
./analyze roi --task 4.1-mini --reflection gpt-4o --volume 5000
```

**Metricas calculadas:**
- Costo de optimizacion (task + reflection calls)
- Costo en produccion sin/con GEPA
- Ahorro neto y porcentaje ROI
- Punto de equilibrio (break-even calls)

**Supuestos del calculo (que es real y que es estimado):**
- El ROI modela un ahorro por **sustitucion de modelo**: sin GEPA se usaria el
  modelo Profesor (caro) en produccion; con GEPA, el modelo Tarea (barato). Si
  Tarea == Profesor no hay sustitucion y el ROI no aplica (se muestra `N/A`,
  mismo criterio en `roi` y en `leaderboard`).
- **Costo de optimizacion (la inversion):** usa el costo real medido por corrida
  (columna `Costo Real USD`) cuando esta disponible; cae a estimacion
  (`budget x val_size x tokens_estimados`) para corridas sin ese dato.
- **Tokens de produccion (input/output por inferencia):** estimacion fija por
  familia (`DEFAULT_TOKEN_ESTIMATES`); las columnas `Tokens Task`/`Tokens
  Reflection` son agregados de toda la optimizacion, no sirven por-inferencia.
- **Overhead del prompt optimizado:** `DEFAULT_PROMPT_OVERHEAD`, medido por
  familia sobre pares `initial_prompt`/`final_prompt` reales (~1100 en CV, ~720
  Text-to-SQL, ~380 Email). Se aplica tanto al ahorro como al break-even.

#### stats

```bash
# Evolucion en 3 lotes (default)
./analyze stats

# Dividir en 4 lotes temporales
./analyze stats --batches 4

# Cortes de fecha manuales
./analyze stats --cuts "2026-01-15,2026-02-01"

# Evolucion filtrada por modelo estudiante y profesor
./analyze stats --student 4.1-mini --teacher claude --batches 3
```

**Nota sobre limites de lote con filtros:** con `--batches` (limites automaticos via `calculate_batch_boundaries`), las fechas de corte se calculan sobre las filas filtradas, por lo que el rango temporal de cada lote depende de los filtros activos. Para mantener cortes temporales fijos entre vistas filtradas, usar `--cuts`.

**Indicadores de tendencia:**
- `^` Mejoro respecto al lote anterior
- `v` Empeoro respecto al lote anterior
- `=` Sin cambio significativo
- `-` Sin datos en ese lote

#### budget

```bash
# Desglose ordenado por costo (default)
./analyze budget

# Ordenar por cantidad de experimentos
./analyze budget --sort count

# Ordenar alfabeticamente
./analyze budget --sort name

# Desglose filtrado por caso y profesor
./analyze budget --case CV --teacher gpt-5.4
```

## Uso Programatico

### Cargar y Filtrar Datos

```python
from pathlib import Path
from shared.analysis import filter_metrics, find_all_metrics_csv, load_metrics

# Auto-descubrir y combinar todos los CSVs
data = load_metrics()

# Solo un proyecto especifico
data = load_metrics(project="dspy")

# CSV explicito
data = load_metrics(csv_path=Path("/ruta/al/archivo.csv"))

# Filtrar filas por caso, estudiante y/o profesor (AND logico, funcion pura)
subset = filter_metrics(
    data,
    case_filter="CV",
    student_filter="4.1-mini",
    teacher_filter="claude",
)

# Listar CSVs disponibles
csvs = find_all_metrics_csv()
for csv_path in csvs:
    print(csv_path)
```

### Ejecutar Analisis

```python
from shared.analysis import budget_breakdown, leaderboard, roi_calculator, stats_evolution

# Leaderboard con filtros combinables (y opcionalmente output_dir para aislar salida)
leaderboard.run(
    project="dspy",
    case_filter="CV",
    student_filter="4.1-mini",
    teacher_filter="claude",
    graphs=True,
)

# ROI filtrado
roi_calculator.run(
    volume=5000,
    case_filter="Email",
    student_filter="4.1-mini",
    teacher_filter="gpt-4o",
)

# Evolucion temporal y desglose de presupuesto (merge=False exige un unico CSV)
stats_evolution.run(student_filter="4.1-mini", cuts="2026-02-01,2026-03-01")
budget_breakdown.run(teacher_filter="claude", merge=False)
```

### Utilidades de Formateo

```python
from shared.analysis import parse_float, format_float, format_currency

# Parsear formato europeo (coma decimal)
valor = parse_float("0,8500")  # -> 0.85

# Formatear a europeo
texto = format_float(0.85)  # -> "0,8500"

# Formatear moneda
precio = format_currency(2.50)  # -> "$2.50"
```

## Auto-Descubrimiento de CSVs

El sistema busca archivos de metricas automaticamente:

1. Parte desde `shared/analysis/`
2. Sube al directorio raiz (`reflexio/`)
3. Busca en cada subdirectorio: `{proyecto}/results/experiments/metricas_optimizacion.csv`
4. Ignora: `shared/`, `docs/`, `.git/`, `__pycache__/`

**Ventaja:** Renombrar proyectos no requiere cambios en las utilidades.

## Formato CSV Esperado

Las utilidades esperan el formato estandar de `shared/logging`:

| Campo | Descripcion |
|-------|-------------|
| Run ID | Identificador unico del run |
| Fecha | Timestamp (YYYY-MM-DD HH:MM:SS) |
| Caso | Nombre del caso de uso |
| Modelo Tarea | Modelo usado para la tarea |
| Modelo Profesor | Modelo usado para reflexion |
| Baseline Score | Score inicial |
| Optimizado Score | Score tras optimizacion |
| Robustez Score | Score en conjunto de test |
| Run Directory | Directorio del run |
| Reflexion Positiva | Si el caso usa reflexion positiva |
| Budget | Max metric calls durante la optimizacion |
| Tokens Task / Tokens Reflection / Costo Real USD | Uso real de tokens y costo del run |
| Versiones Librerias | `dspy`/`gepa`/`litellm`/`openai` del run (SPEC-100 FR-009) |
| Notas | Informacion adicional (texto libre) |

**Delimitador:** `;` (semicolon)
**Decimal:** `,` (coma europea)

## Precios de Modelos (ROI)

SSOT: `DEFAULT_PRICING` en `shared/analysis/roi_calculator.py` (precios por 1M
de tokens, con la fuente y la fecha de consulta en comentarios). Para verlos,
`./analyze roi` imprime la tabla vigente al inicio. Un modelo sin precio emite un
warning y se calcula con el de `gpt-4o-mini` (costo subestimado): agregarlo al
diccionario.

## Escala de Estabilidad

Usada en leaderboard para clasificar variabilidad:

| Std Dev | Clasificacion | Descripcion |
|---------|---------------|-------------|
| < 0.05 | Alta | Comportamiento predecible |
| 0.05 - 0.10 | Buena | Estandar industrial |
| 0.10 - 0.15 | Atencion | Requiere supervision |
| > 0.15 | Inestable | Alta variabilidad |

## Dependencias Opcionales

- **matplotlib**: Requerido para `--graphs` en leaderboard
- **numpy**: Requerido para graficos

Instalar con:
```bash
pip install matplotlib numpy
```

## Troubleshooting

### "No se encontro metricas_optimizacion.csv"

Verificar que existe al menos un archivo:
```bash
find . -name "metricas_optimizacion.csv"
```

### "Multiples CSVs encontrados"

Usar `--project` para filtrar:
```bash
./analyze leaderboard --project dspy
```

O `--csv` para especificar exactamente:
```bash
./analyze leaderboard --csv dspy_gepa_poc/results/experiments/metricas_optimizacion.csv
```

### Graficos no se generan

Instalar matplotlib:
```bash
pip install matplotlib
```
