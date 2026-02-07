# GEPA Standalone Demos

Este directorio contiene ejemplos de uso directo de GEPA (Generative Evolutionary Prompt Adjustment), permitiendo la optimización de prompts en scripts de Python sin frameworks adicionales.

## Arquitectura Modular

Estructura de `gepa_standalone/` (para estructura completa del proyecto ver `/README.md`):

```text
gepa_standalone/
├── .env                       # Configuracion LLM (API key, modelos)
├── .env.example               # Plantilla de configuracion
├── universal_optimizer.py     # Unico punto de entrada principal
├── config.py                  # Configuracion de adapters y paths
├── config_schema.py           # Validacion de esquemas YAML
├── adapters/                  # Logica de evaluacion y parsing
│   ├── base_adapter.py        # Clase base (usa shared/llm)
│   ├── simple_classifier_adapter.py   # Clasificacion
│   ├── simple_extractor_adapter.py    # Extraccion JSON
│   ├── simple_sql_adapter.py          # Generacion SQL
│   └── simple_rag_adapter.py          # RAG con Juez LLM
├── core/                      # Componentes del sistema
│   └── llm_factory.py         # Factory LLM (usa shared/llm)
├── data/                      # Capa de datos (Loaders)
│   └── data_loader.py         # Cargador universal
├── demos/                     # Scripts de ejemplo ejecutables
├── experiments/               # Espacio de trabajo (Entradas)
│   ├── configs/               # Definiciones YAML de casos de uso
│   ├── datasets/              # Datasets CSV (columna 'split')
│   └── prompts/               # Prompts iniciales en formato JSON
├── results/                   # Salida de experimentos (Autogenerado)
├── utils/                     # Utilidades de analisis y soporte
└── wizard/                    # Wizard interactivo de configuracion
```

## Configuracion

### Configurar API Key

```bash
# Copiar plantilla
cp .env.example .env

# Editar .env con tus credenciales
```

### Variables de Entorno

```bash
# Conexion (una sola API key)
LLM_API_KEY=tu-api-key
LLM_API_BASE=https://tu-recurso.openai.azure.com   # Solo Azure
LLM_API_VERSION=2024-02-15-preview                  # Solo Azure

# Modelos (formato: provider/model)
LLM_MODEL_TASK=azure/gpt-4.1-mini        # Modelo estudiante
LLM_MODEL_REFLECTION=azure/gpt-4o        # Modelo profesor
```

Para documentacion completa de configuracion LLM, ver `/docs/LLM_CONFIG.md`.

## Conceptos Clave: ¿Por qué optimizar RAG?

Para entender qué es GEPA y cómo funciona, ver `/README.md` sección "GEPA en 30 Segundos".

Aunque GEPA siempre optimiza texto, existen diferencias fundamentales según la tarea:

*   **Optimización de Prompt (Demos 1-3):** Busca mejorar la lógica, el formato o la capacidad de clasificación del modelo usando su conocimiento interno. Se mide con comparaciones exactas.
*   **Optimización de RAG (Demo 4):** Busca **eliminar alucinaciones**. GEPA entrena al prompt para que el modelo ignore lo que sabe y responda **únicamente** basándose en el contexto adjunto. Requiere un **Juez LLM** para evaluar la fidelidad semántica.

Para comparación detallada RAG vs Prompt, ver `DEMO4_RAG_GUIDE.md`.

---

## Casos de Uso Soportados

El **Universal Optimizer** permite ejecutar cualquiera de estos casos simplemente apuntando al archivo de configuración correspondiente en `experiments/configs/`:

### 1. Clasificación de Urgencia
Clasifica la urgencia de correos electrónicos (`urgent`, `normal`, `low`).
*   **Comando:** `python universal_optimizer.py --config experiments/configs/email_urgency.yaml`

### 2. Extracción de Datos (CV Parsing)
Extrae campos estructurados (JSON) de currículums.
*   **Comando:** `python universal_optimizer.py --config experiments/configs/cv_extraction.yaml`

### 3. Text-to-SQL
Traduce lenguaje natural a consultas SQL.
*   **Comando:** `python universal_optimizer.py --config experiments/configs/text_to_sql.yaml`

### 4. Optimización RAG (QA Políticas)
Mejora respuestas basadas en contexto usando evaluación "LLM-as-a-Judge".
*   **Comando:** `python universal_optimizer.py --config experiments/configs/rag_optimization.yaml`
*   **Guía específica:** `gepa_standalone/DEMO4_RAG_GUIDE.md`

---

## Universal Optimizer (Recomendado)

Interfaz universal que elimina duplicación de código. **Reduce cada caso de ~130 líneas Python a ~30 líneas YAML.**

### Uso Rápido

```bash
# Primera vez: Wizard interactivo
python gepa_standalone/universal_optimizer.py

# Subsecuentes: Usar config YAML
python gepa_standalone/universal_optimizer.py --config experiments/configs/mi_caso.yaml
```

### Ventajas

*   **Sin código**: Define casos en YAML declarativo
*   **Validación pre-flight**: Detecta errores antes de ejecutar
*   **Logging automático**: Incluye reflexión positiva y notas en metricas_optimizacion.csv
*   **Reutilizable**: Configs versionables y compartibles

Ver guía completa en `UNIVERSAL_OPTIMIZER.md`

---

## Guía de Extensión

Pasos para nuevas optimizaciones:

1.  **Datos:** Añadir CSV en `experiments/datasets/` con columnas `split` y datos input/output.
2.  **Prompt:** Crear JSON en `experiments/prompts/` con la instrucción inicial.
3.  **Adaptador:** Seleccionar un adaptador de `adapters/` o implementar uno nuevo.
4.  **Ejecución:** Crear script en `demos/` importando `gepa.optimize` con los componentes anteriores.
