# Universal GEPA Optimizer - Guía de Configuración

## Propósito

Interfaz universal para optimizar prompts con GEPA en cualquier caso de uso (classifier, extractor, SQL, RAG). Elimina duplicación de código: cada caso se define en ~30 líneas de YAML, sin escribir Python.

---

## Uso Rápido

> Todas las invocaciones se hacen **desde la raíz del repo** con `python -m`. Esto es necesario para que `import shared` resuelva: si se ejecuta el script directo, Python pone el dir del script (no la raíz) en `sys.path` y los imports fallan.

### Primera Vez (Wizard Interactivo)
```bash
python -m gepa_standalone.universal_optimizer
```

El wizard te guía paso a paso y genera un YAML en `gepa_standalone/experiments/configs/{caso}.yaml`

### Ejecuciones Subsecuentes
```bash
python -m gepa_standalone.universal_optimizer \
    --config gepa_standalone/experiments/configs/mi_caso.yaml
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
LLM_API_KEY=tu-key-aqui
LLM_MODEL_TASK=azure/gpt-4.1-mini
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
  skip_perfect_score: true           # Omitir ejemplos con score perfecto en la reflexión
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
  skip_perfect_score: true           # Omitir ejemplos con score perfecto en la reflexión
  display_progress_bar: true
```

---

## Parámetros por Tipo de Adaptador

| Parámetro | Classifier | Extractor | SQL | RAG | Descripción |
|-----------|------------|-----------|-----|-----|-------------|
| `type` | ✓ | ✓ | ✓ | ✓ | Tipo de adaptador (REQUERIDO) |
| `valid_classes` | ✓ | - | - | - | Lista de clases válidas (REQUERIDO en classifier) |
| `required_fields` | - | ✓ | - | - | Campos a extraer (REQUERIDO en extractor) |
| `max_positive_examples` | - | ✓ | - | - | Ejemplos exitosos en reflexión (0-3) |
| `rag_context_max_length` | - | - | - | ✓ | Límite de tokens del contexto |
| `rag_max_positive_examples` | - | - | - | ✓ | Ejemplos exitosos en reflexión |

---

## Anatomía del adapter

El adapter es el **único punto de extensión** que conecta tu dominio con el motor evolutivo de GEPA. Hay dos caminos según el caso de uso.

### Camino 1: Usar un adapter built-in (95% de los casos)

Solo configurás la sección `adapter:` del YAML — no escribís código. Los 4 tipos cubren los patrones más comunes:

| `adapter.type` | Patrón de tarea         | Estrategia de scoring                        |
|----------------|-------------------------|----------------------------------------------|
| `classifier`   | Clase de un set cerrado | Match exacto contra `valid_classes`          |
| `extractor`    | N campos estructurados  | Score parcial por campo correcto             |
| `sql`          | Generación de query     | Ejecutar SQL y comparar resultados (no strings) |
| `rag`          | Respuesta libre + contexto | LLM-as-Judge (semántico + fundamentación)  |

> Cada adapter elige una métrica acorde a la naturaleza de la salida. La métrica define qué puede aprender GEPA — ver `docs/LECCIONES_APRENDIDAS.md` sección 1.

### Camino 2: Crear un adapter nuevo

Heredás de `BaseAdapter` (`adapters/base_adapter.py`) e implementás dos métodos:

```python
class MiAdapter(BaseAdapter):
    def evaluate(self, batch, candidate, capture_traces=False) -> EvaluationBatch:
        # Llama al LLM con el prompt candidato, scorea cada ejemplo (0..1)
        ...

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        # Construye el material que ve el LLM Profesor para proponer mutaciones
        ...
```

Tamaños reales como referencia:
- `simple_classifier_adapter.py` — 123 líneas
- `simple_sql_adapter.py` — 109 líneas
- `simple_extractor_adapter.py` — 234 líneas
- `simple_rag_adapter.py` — 360 líneas (el más complejo, por LLM-as-Judge)

Todo lo demás —loop evolutivo, selección Pareto, logging, reproducibilidad, snapshots de config— se hereda gratis del framework.

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
*   **Leaderboard consolidado**: se genera con el CLI de análisis desde la raíz del repo (`./analyze leaderboard`, implementado en `shared/analysis/leaderboard.py`); produce `leaderboard.csv` y `leaderboard.md`. Ver `/docs/ANALISIS_UTILIDADES.md`.

---

## Validaciones Implementadas

El sistema valida **antes** de ejecutar GEPA:

### 1. Estructura del Config
- Campos requeridos: `case.name`, `adapter.type`, `data.csv_filename`, `optimization.max_metric_calls`
- Tipo de adaptador válido: `classifier`, `extractor`, `sql` o `rag`
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

### Ajustar Parámetros del Modelo (sin modificar .env)

Los modelos task/reflection se definen únicamente por `.env` (`LLM_MODEL_TASK` /
`LLM_MODEL_REFLECTION`, ver `/docs/LLM_CONFIG.md`); el YAML no los sobreescribe.
Lo que sí admite override en la sección `models:` del YAML:

```yaml
models:
  temperature: 0.0                 # Override de temperatura
  max_tokens: 16000                # Override de max tokens (necesario para reasoning models)
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
**Solución:** Verifica la ruta relativa (debe ser desde la raíz del repo) o usa ruta absoluta.
```bash
python -m gepa_standalone.universal_optimizer \
    --config gepa_standalone/experiments/configs/email_urgency.yaml
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
