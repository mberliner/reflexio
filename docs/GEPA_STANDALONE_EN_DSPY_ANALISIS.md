# Arquitectura de Integración DSPy + GEPA (Implementada)

## Propósito del Documento
Este documento es la Fuente Única de Verdad (SSOT) para la arquitectura de integración entre el framework DSPy y el optimizador GEPA en el proyecto Reflexio Dicta. Describe la implementación final que combina la modularidad de DSPy con la metodología de producción de GEPA Standalone.

---

## 1. Visión General de la Arquitectura

El sistema implementa una arquitectura declarativa donde el entry point
`reflexio_declarativa.py` orquesta todo el flujo a partir de un config YAML, sin
código Python por caso.

### Diagrama de Alto Nivel

```mermaid
graph TD
    User[Usuario] -->|YAML Config| ReflexioDeclarativa[reflexio_declarativa.py]
    User -->|CSV Data| CSVDataLoader[data_loader.py]

    subgraph Core Engine
        ReflexioDeclarativa --> AppConfig[config.py / config_schema.py]
        ReflexioDeclarativa -->|dynamic / pipeline| DynamicFactory[dynamic_factory.py]

        CSVDataLoader -->|Train/Val/Test| ReflexioDeclarativa
    end

    subgraph Optimization Loop
        ReflexioDeclarativa --> GEPAOptimizer[optimizer.py]
        GEPAOptimizer -->|Reflective Mutation| ReflectionLLM[Teacher Model]
        GEPAOptimizer -->|Evaluation| TaskLLM[Student Model]
    end

    subgraph Output Artifacts
        ReflexioDeclarativa -->|Log| MasterLog[metricas_optimizacion.csv]
        ReflexioDeclarativa -->|Artifacts| RunFolder[results/runs/...]
    end
```

---

## 2. Modos de Operación

El entry point soporta dos tipos de módulo (`module.type`; campos completos en
`docs/YAML_CONFIG_REFERENCE.md`):

### Modo `dynamic` (Zero-Code / YAML-Defined)
Ideal para tareas de una sola etapa (clasificación, extracción, QA).
- **Definición:** La `Signature` (instrucción, inputs, outputs) se define enteramente en el archivo YAML.
- **Implementación:** `DynamicModuleFactory.create_module` genera la clase DSPy al vuelo.
- **Ventaja:** No requiere escribir ni una línea de código Python.

### Modo `pipeline` (Multi-etapa con routing condicional)
Ideal para flujos de N etapas en serie donde una etapa-gate decide si las posteriores se ejecutan.
- **Definición:** Lista de `stages` (cada una con su `signature`) más una sección `routing` (`gate_stage`, `gate_field`, `gate_value`), todo en YAML.
- **Implementación:** `DynamicModuleFactory.create_pipeline_module`.
- **Ventaja:** Composición de etapas sin código; los casos que el gate no abre no ejecutan las etapas posteriores.

---

## 3. Estructura del Proyecto

```
dspy_gepa_poc/
├── configs/            # Configuración Declarativa (YAML), ej: dynamic_email_urgency.yaml
├── datasets/           # Fuente de Verdad de Datos (CSV, columna split)
├── scripts/            # Utilidades: dryrun_config, baseline_only, per_field_accuracy, ...
├── results/            # Salidas Estructuradas (gitignored)
│   ├── experiments/    # Log Maestro (metricas_optimizacion.csv)
│   └── runs/           # Artefactos por ejecución
├── config.py           # Sistema de Configuración (AppConfig)
├── config_schema.py    # Validación Estricta de YAML
├── data_loader.py      # Carga de CSVs a DSPy Examples (Train/Val/Test)
├── dynamic_factory.py  # Generador de Signatures/Modules al vuelo (dynamic y pipeline)
├── metrics.py          # Métricas de Evaluación (match modes, feedback por campo)
├── optimizer.py        # Wrapper de GEPA
├── results_logger.py   # Gestión del Log Maestro
├── run_inference.py    # Motor de inferencia sobre runs optimizados (ver sección 8)
└── reflexio_declarativa.py # Punto de Entrada Principal
```

---

## 4. Metodología de Datos (3 Conjuntos)

El sistema impone estrictamente la metodología de 3 conjuntos para garantizar validez científica, idéntica a `gepa_standalone`.

| Split | Rol | Descripción |
| :--- | :--- | :--- |
| **train** | Optimización | Usado por GEPA para proponer candidatos y reflexionar sobre errores. |
| **val** | Selección | Usado para puntuar candidatos y seleccionar el mejor de la frontera de Pareto. |
| **test** | Robustez | Usado **una sola vez** al final para evaluar el rendimiento real del modelo optimizado. |

**Formato CSV Requerido:**
```csv
split,text,sentiment,...
train,"Ejemplo 1","positive",...
val,"Ejemplo 2","negative",...
test,"Ejemplo 3","neutral",...
```

---

## 5. Configuracion (YAML)

El sistema utiliza configuracion declarativa validada por esquema. Los archivos YAML se ubican en `dspy_gepa_poc/configs/`.

Para la referencia completa de todos los campos disponibles, ver **`docs/YAML_CONFIG_REFERENCE.md`** (seccion 1: DSPy + GEPA).

Los ejemplos funcionales se encuentran en `dspy_gepa_poc/configs/`.

---

## 6. Salidas y Resultados

### Log Maestro
Ubicación: `dspy_gepa_poc/results/experiments/metricas_optimizacion.csv`
Formato: CSV Europeo (separador `;`, decimal `,`).
Compatible con: Herramientas de `ROI Calculator` y `Leaderboard` de GEPA Standalone.

**Columnas:**
- Run ID (UUID)
- Fecha
- Caso
- Modelo Tarea / Profesor
- Scores (Baseline, Optimizado, Robustez)
- Directorio del Run

### Artefactos por Ejecución
Ubicación: `dspy_gepa_poc/results/runs/<Case_Name>_<Timestamp>/`
Contenido:
- `optimized_program.json`: El módulo DSPy compilado y listo para producción.
- `config_snapshot.yaml`: Copia exacta de la configuración usada.

---

## 7. Flujo de Trabajo Típico

1.  **Preparar Datos:** Subir archivo `.csv` a `dspy_gepa_poc/datasets/`.
2.  **Configurar:** Crear un archivo `.yaml` en `dspy_gepa_poc/configs/`.
3.  **Ejecutar** (desde la raíz del repo; `-m` evita errores de `import shared`):
    ```bash
    python -m dspy_gepa_poc.reflexio_declarativa \
        --config dspy_gepa_poc/configs/mi_experimento.yaml
    ```
4.  **Analizar:** Revisar `metricas_optimizacion.csv` o los logs de consola.
5.  **Desplegar:** Tomar `optimized_program.json` para uso en producción.

---

## 8. Inferencia y Uso en Producción

El sistema incluye un motor de inferencia genérico que permite consumir los resultados de la optimización sin necesidad de re-ejecutar GEPA ni utilizar el modelo de reflexión (Teacher).

### Ejecución de Inferencia
Ubicación: `dspy_gepa_poc/run_inference.py`

Este script es **completamente agnóstico a la tarea** y reconstruye el entorno de ejecución basándose en los artefactos de la carpeta de ejecución (`run`).

```bash
# Desde la raíz del repo
python -m dspy_gepa_poc.run_inference dspy_gepa_poc/results/runs/<NOMBRE_DEL_RUN>/
```

### Características del Motor de Inferencia
- **Carga Dinámica:** Lee el `config_snapshot.yaml` para reconstruir la `Signature` y la arquitectura del módulo DSPy automáticamente.
- **Inyección de Pesos:** Carga el `optimized_program.json` (que contiene los prompts refinados y los mejores ejemplos few-shot encontrados) sobre el modelo estudiante.
- **Eficiencia de Costos:** Solo requiere configurar el `LLM_MODEL_TASK`. No utiliza el modelo de reflexión, lo que reduce drásticamente el consumo de tokens y la latencia.
- **Interfaz Adaptable:** Detecta automáticamente los campos de entrada y salida definidos en el YAML original para presentarlos en un loop interactivo de consola.

### Flujo de Integración Externa
Para integrar un modelo optimizado en una aplicación propia, solo se requiere:
1. Inicializar DSPy con el modelo estudiante.
2. Recrear la `Signature` (o usar `DynamicModuleFactory`).
3. Ejecutar `module.load("path/to/optimized_program.json")`.