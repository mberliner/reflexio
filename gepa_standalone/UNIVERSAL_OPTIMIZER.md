# Universal GEPA Optimizer - Guía de Configuración

## Propósito

Interfaz universal para optimizar prompts con GEPA en cualquier caso de uso (classifier, extractor, SQL). Elimina duplicación de código: **387 líneas → 30 líneas YAML por caso**.

---

## Uso Rápido

### Primera Vez (Wizard Interactivo)
```bash
cd gepa_standalone
python universal_optimizer.py
```

El wizard te guía paso a paso y genera un YAML en `experiments/configs/{caso}.yaml`

### Ejecuciones Subsecuentes
```bash
python universal_optimizer.py --config experiments/configs/mi_caso.yaml
```

---

## Jerarquía de Configuración

El optimizer combina 3 fuentes de configuración con esta prioridad (mayor a menor):

### 1. YAML Explícito (Mayor Prioridad)
Parámetros especificados directamente en el archivo YAML.

```yaml
adapter:
  type: "extractor"
  max_positive_examples: 3  # Override explícito
```

### 2. Variables de Entorno (.env)
Valores definidos en `.env` (o variables de sistema).

```bash
# .env
AZURE_OPENAI_API_KEY=tu-key-aqui
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini
EXTRACTOR_MAX_POSITIVE_EXAMPLES=1
```

### 3. Defaults de Config.py (Menor Prioridad)
Valores por defecto si no se especifica nada.

```python
# config.py línea 47
EXTRACTOR_MAX_POSITIVE_EXAMPLES = int(os.getenv("...", "0"))  # default: 0
```

---

## Configuración de Variables de Entorno

Para lista completa de variables de entorno (requeridas y opcionales), ver `/README.md` sección "Configurar API Key".

---

## Anatomía de un Config YAML

### Ejemplo: Classifier (email_urgency.yaml)

```yaml
# 1. METADATA
case:
  name: "email_urgency"              # ID interno (snake_case)
  title: "Email Urgency"             # Título para reportes
  description: "Clasificación..."    # Opcional

# 2. ADAPTADOR
adapter:
  type: "classifier"                 # classifier | extractor | sql
  valid_classes:                     # Específico para classifier
    - "urgent"
    - "normal"
    - "low"

# 3. DATOS
data:
  csv_filename: "email_urgency.csv"  # En experiments/datasets/
  input_column: "text"               # Columna entrada (default: "text")
  output_columns:                    # Columnas salida
    - "urgency"

# 4. PROMPT INICIAL
prompt:
  filename: "email_urgency_v1.json"  # En experiments/prompts/

# 5. PARÁMETROS GEPA
optimization:
  max_metric_calls: 50               # Presupuesto (rango válido: 10-500, recomendado: 40-150)
  skip_perfect_score: true           # Detener si alcanza 1.0
  display_progress_bar: true         # Mostrar barra
```

### Ejemplo: Extractor (cv_extraction.yaml)

```yaml
case:
  name: "cv_extraction"
  title: "CV Extraction"

adapter:
  type: "extractor"
  required_fields:                   # Específico para extractor
    - "nombre"
    - "email"
    - "años_experiencia"
  max_positive_examples: 0           # Override: usar 0 en vez de Config

data:
  csv_filename: "cv_extraction.csv"
  input_column: "text"
  output_columns:
    - "nombre"
    - "email"
    - "años_experiencia"

prompt:
  filename: "cv_extraction_v1.json"

optimization:
  max_metric_calls: 40
  skip_perfect_score: true
  display_progress_bar: true
```

### Ejemplo: SQL (text_to_sql.yaml)

```yaml
case:
  name: "text_to_sql"
  title: "Text-to-SQL"

adapter:
  type: "sql"                        # SQL no requiere params adicionales

data:
  csv_filename: "text_to_sql.csv"
  input_column: "question"           # Diferente de "text"
  output_columns:
    - "schema"
    - "expected_sql"

prompt:
  filename: "text_to_sql_v1.json"

optimization:
  max_metric_calls: 150              # SQL necesita más presupuesto
  skip_perfect_score: true           # Detener si alcanza score perfecto
  display_progress_bar: true
```

---

## Parámetros por Tipo de Adaptador

| Parámetro | Classifier | Extractor | SQL | Descripción |
|-----------|------------|-----------|-----|-------------|
| `type` | ✓ | ✓ | ✓ | Tipo de adaptador (REQUERIDO) |
| `valid_classes` | ✓ | - | - | Lista de clases válidas (REQUERIDO) |
| `required_fields` | - | ✓ | - | Campos a extraer (REQUERIDO) |
| `max_positive_examples` | - | ✓ | - | Ejemplos exitosos en reflexión (0-3) |

---

## Estructura de Archivos

### Inputs (Usuario Coloca)

```text
experiments/
├── configs/                    # Archivos YAML que orquestan cada caso
│   ├── email_urgency.yaml      # Define adaptador, columnas y presupuesto
│   └── ...
├── datasets/                   # Datos de entrenamiento y prueba
│   ├── email_urgency.csv       # Requerido: columna 'split' (train, val, test)
│   └── ...
└── prompts/                    # Punto de partida para la optimización
    ├── email_urgency_v1.json   # JSON con la clave "system_prompt"
    └── ...
```

### Outputs (Generados Automáticamente)

El sistema organiza los resultados en `results/` para facilitar el análisis:

*   **`results/experiments/metricas_optimizacion.csv`**: El registro histórico maestro. Cada fila es un experimento. Usa formato europeo (`;` y `,`) para compatibilidad directa con Excel.
*   **`results/runs/{case}/{timestamp}_{id}/`**: La "caja negra" de cada ejecución. Contiene:
    *   `config.json`: Copia de los parámetros usados.
    *   `initial_prompt.txt` / `final_prompt.txt`: Los prompts antes y después.
    *   `results.json`: Métricas detalladas y scores de cada ejemplo.
*   **`results/estadistica_casos_agrupados.csv`**: Generado por `utils/leaderboard.py`. Consolida los mejores promedios por modelo/caso.

---

## Validaciones Implementadas

El sistema valida **antes** de ejecutar GEPA:

### 1. Estructura del Config
- Campos requeridos: `case.name`, `adapter.type`, `data.csv_filename`, `optimization.max_metric_calls`
- Tipo de adaptador válido: `classifier`, `extractor`, o `sql`
- Parámetros específicos del adaptador presentes

### 2. Existencia de Archivos
- CSV en `experiments/datasets/{csv_filename}`
- Prompt JSON en `experiments/prompts/{prompt_filename}`

### 3. Estructura del CSV
- Columna `split` obligatoria (valores: train, val, test)
- `input_column` existe
- Todas las `output_columns` existen

### 4. Parámetros de Optimización
- `max_metric_calls` es entero entre 10 y 500 (valores típicos: 40-150 para la mayoría de casos)

**Si hay errores, se muestran claramente ANTES de ejecutar.**

---

## Ejemplos de Override

### Cambiar Modelos en Runtime (sin modificar .env)

Agregar al YAML:
```yaml
models:
  task: "gpt-4o-mini"              # Override AZURE_OPENAI_DEPLOYMENT
  reflection: "gpt-4o"             # Override AZURE_OPENAI_REFLECTION_DEPLOYMENT
  temperature: 0.0
```

### Forzar Ejemplos Positivos

En el YAML:
```yaml
adapter:
  type: "extractor"
  required_fields: [...]
  max_positive_examples: 2         # Ignora Config y .env
```

---

## Comparación con Demos Originales

| Aspecto | Demos Originales | Universal Optimizer |
|---------|------------------|---------------------|
| **Líneas por caso** | ~130 líneas Python | ~30 líneas YAML |
| **Configuración** | Hardcoded en código | Archivo YAML reutilizable |
| **Nuevos casos** | Copiar/modificar demo | Ejecutar wizard 2 min |
| **Validación** | Runtime (puede fallar tarde) | Pre-flight (falla temprano) |
| **Logging** | Idéntico | Idéntico (mismo metricas_optimizacion.csv) |
| **Compatibilidad** | N/A | 100% backward compatible |

---

## Troubleshooting

### Error: "Config file not found"
**Solución:** Verifica la ruta relativa o usa ruta absoluta.
```bash
python universal_optimizer.py --config gepa_standalone/experiments/configs/email_urgency.yaml
```

### Error: "CSV file not found"
**Solución:** Coloca el CSV en `experiments/datasets/` o actualiza `csv_filename` en el YAML.

### Error: "Output column 'X' not found in CSV"
**Solución:** Verifica encoding UTF-8 del CSV o ajusta `output_columns` en el YAML.

### Error: "Missing required section: 'case'"
**Solución:** El YAML está malformado. Compara con ejemplos en `experiments/configs/`.

---

## Notas Importantes

- **Logging europeo**: metricas_optimizacion.csv usa `;` separador y `,` decimal
- **Paths relativos**: run_directory en metricas_optimizacion.csv es relativo a results/
- **Config versionable**: YAMLs son git-friendly y compartibles entre equipo
