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

| Argumento | Descripcion |
|-----------|-------------|
| `--csv PATH` | Usar un archivo CSV especifico |
| `--project NAME` | Filtrar por nombre de proyecto (match parcial) |
| `--case NAME` | Filtrar por nombre de caso (match parcial) |
| `--no-merge` | No combinar multiples CSVs (error si hay mas de uno) |

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
```

**Salidas generadas:**
- `shared/analysis/output/leaderboard.csv`
- `shared/analysis/output/leaderboard.md`
- `shared/analysis/output/performance_improvement.png` (con --graphs)
- `shared/analysis/output/roi_analysis.png` (con --graphs)

#### roi

```bash
# ROI para 1000 llamadas (default)
./analyze roi

# ROI para volumen especifico
./analyze roi --volume 5000

# Solo un proyecto
./analyze roi --project standalone --volume 10000
```

**Metricas calculadas:**
- Costo de optimizacion (task + reflection calls)
- Costo en produccion sin/con GEPA
- Ahorro neto y porcentaje ROI
- Punto de equilibrio (break-even calls)

#### stats

```bash
# Evolucion en 3 lotes (default)
./analyze stats

# Dividir en 4 lotes temporales
./analyze stats --batches 4

# Cortes de fecha manuales
./analyze stats --cuts "2026-01-15,2026-02-01"
```

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
```

## Uso Programatico

### Cargar Datos

```python
from shared.analysis import load_metrics, find_all_metrics_csv

# Auto-descubrir y combinar todos los CSVs
data = load_metrics()

# Solo un proyecto especifico
data = load_metrics(project="dspy")

# CSV explicito
data = load_metrics(csv_path=Path("/ruta/al/archivo.csv"))

# Listar CSVs disponibles
csvs = find_all_metrics_csv()
for csv_path in csvs:
    print(csv_path)
```

### Ejecutar Analisis

```python
from shared.analysis import leaderboard, roi_calculator

# Leaderboard
leaderboard.run(project="dspy", graphs=True)

# ROI
roi_calculator.run(volume=5000, case_filter="Email")
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
| Notas | Informacion adicional (texto libre) |

**Delimitador:** `;` (semicolon)
**Decimal:** `,` (coma europea)

## Precios de Modelos (ROI)

Configurados en `roi_calculator.py`:

| Modelo | Input (1M tokens) | Output (1M tokens) |
|--------|-------------------|-------------------|
| gpt-4o | $2.50 | $10.00 |
| gpt-4o-mini | $0.15 | $0.60 |
| gpt-4.1-mini | $0.15 | $0.60 |

Para actualizar precios, editar `DEFAULT_PRICING` en `shared/analysis/roi_calculator.py`.

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
