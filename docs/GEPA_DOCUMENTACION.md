# GEPA - Framework de Optimización Reflexiva para Sistemas con LLMs

## Descripción General

**GEPA** (Genetic-Pareto) es un framework open-source para **optimizar sistemas arbitrarios compuestos de componentes de texto** usando reflexión basada en LLMs y búsqueda evolutiva.

- **Licencia**: MIT
- **Autor**: Lakshya A Agrawal (UC Berkeley)
- **Repositorio**: https://github.com/gepa-ai/gepa
- **Paper**: "GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning" (arXiv:2507.19457)
- **Versiones**: Ver `requirements.txt` (SSOT)

### Filosofía Central

| Enfoque Tradicional | Enfoque GEPA |
|---------------------|--------------|
| Mutaciones aleatorias | Mutaciones reflexivas con LLM |
| Prueba y error manual | Evolución automática |
| Optimización de un solo componente | Co-evolución de múltiples componentes |
| Feedback numérico solamente | Feedback textual rico (errores, trazas) |

### Propósito

- Evolucionar componentes de texto (prompts, código, especificaciones, instrucciones) mediante mutación y reflexión iterativa
- Aprovechar feedback de ejecución, evaluación y trazas para mejorar de forma dirigida
- Usar búsqueda evolutiva Pareto-eficiente para encontrar variantes robustas con evaluaciones mínimas
- Habilitar co-evolución de múltiples componentes en sistemas modulares

### Innovación Clave

**GEPA usa LLMs para reflexionar** sobre comportamiento del sistema y fallos, usando feedback textual (errores de compilador, reportes de profiler, documentación, trazas de ejecución) para proponer mutaciones inteligentes en lugar de cambios aleatorios.

### Resultados Reales

- Mejora GPT-4.1 Mini en AIME de 46.6% a 56.6% (+10%)
- Evoluciona DSPy ChainOfThought básico (67% en MATH) a programa multi-paso sofisticado (93% precisión)
- Funciona en dominios diversos: problemas matemáticos, QA multi-hop, sistemas RAG, agentes terminal, OCR
- **Databricks**: Agentes empresariales 90x más económicos
- **Intrinsic Labs**: 38% reducción de error en OCR

---

## Arquitectura del Proyecto

### Estructura de Directorios

```
gepa/
├── README.md                  # Documentación principal
├── pyproject.toml             # Configuración del paquete (v0.0.23)
├── CONTRIBUTING.md            # Guía de desarrollo
├── LICENSE                    # Licencia MIT
├── uv.lock                    # Dependencias congeladas
│
├── src/gepa/                  # Código fuente principal (56 archivos Python)
│   ├── api.py                 # Función optimize() principal (19KB)
│   ├── gepa_utils.py          # Utilidades (lógica Pareto)
│   │
│   ├── core/                  # Motor de optimización core
│   │   ├── adapter.py         # Protocolo GEPAAdapter (9.2KB)
│   │   ├── engine.py          # Orquestación GEPAEngine (14.3KB)
│   │   ├── state.py           # GEPAState para tracking (11.7KB)
│   │   ├── result.py          # GEPAResult para salida (8.5KB)
│   │   └── data_loader.py     # Utilidades de datos
│   │
│   ├── adapters/              # Adaptadores de sistemas
│   │   ├── default_adapter/           # Prompts LLM simples
│   │   ├── dspy_adapter/              # Signatures DSPy
│   │   ├── dspy_full_program_adapter/ # Programas DSPy completos
│   │   ├── generic_rag_adapter/       # Sistemas RAG
│   │   ├── terminal_bench_adapter/    # Agentes terminal
│   │   └── anymaths_adapter/          # Problemas matemáticos
│   │
│   ├── proposer/              # Mutación de candidatos
│   │   ├── reflective_mutation/
│   │   │   └── reflective_mutation.py  # Lógica de mutación (7.3KB)
│   │   └── merge.py           # Combinar mejoras (15KB)
│   │
│   ├── strategies/            # Selección y muestreo
│   │   ├── batch_sampler.py           # Muestreo de batches
│   │   ├── candidate_selector.py      # Selección de candidatos
│   │   ├── component_selector.py      # Selección de componentes
│   │   └── eval_policy.py             # Políticas de evaluación
│   │
│   ├── logging/               # Experiment tracking
│   │   ├── logger.py          # Logger protocol
│   │   └── experiment_tracker.py      # WandB, MLflow
│   │
│   ├── examples/              # Ejemplos de uso
│   └── utils/                 # Utilidades generales
│       └── stop_condition.py  # Condiciones de parada
│
└── tests/                     # Suite de tests (10+ archivos)
```

### Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────────┐
│                      API PÚBLICA                                 │
│              gepa.optimize()                                     │
│  seed_candidate, trainset, valset                                │
│  task_lm, reflection_lm, max_metric_calls                        │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MOTOR CORE                                  │
│  GEPAEngine  │  GEPAState   │  GEPAResult                        │
│ (orquestador)│  (tracking)  │   (salida)                         │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   CAPA DE ADAPTADORES                            │
│  Default   │    DSPy    │    RAG     │  Terminal                 │
│  Adapter   │  Adapter   │  Adapter   │   Bench                   │
│                                                                  │
│  Protocolo: GEPAAdapter                                          │
│  - evaluate()                                                    │
│  - make_reflective_dataset()                                    │
│  - propose_new_texts() [opcional]                               │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  CAPA DE PROPOSER                                │
│  ReflectiveMutationProposer + MergeProposer (opcional)           │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  ESTRATEGIAS                                     │
│  Candidate Selection │ Component Selection │ Batch Sampler       │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                LOGGING (WandB, MLflow, Custom)                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Instalación

### Instalación Básica

```bash
# Desde PyPI
pip install gepa

# Última versión desde GitHub
pip install git+https://github.com/gepa-ai/gepa.git

# Con todas las funcionalidades
pip install "gepa[full]"
```

### Configuración de Desarrollo

```bash
# Con uv (recomendado)
git clone https://github.com/gepa-ai/gepa
cd gepa
uv sync --extra dev --python 3.11
uv run pytest tests/

# Con conda + pip
conda create -n gepa-dev python=3.11
conda activate gepa-dev
pip install -e ".[dev]"
pytest tests/
```

### Dependencias

Consulte `requirements.txt` para la lista completa de bibliotecas y sus versiones.

---

## Conceptos Fundamentales

### 1. GEPAAdapter - Interfaz de Sistema

El **GEPAAdapter** conecta tu sistema con GEPA mediante 2-3 métodos:

**Método 1: evaluate()** - Ejecuta el candidato

**Método 2: make_reflective_dataset()** - Extrae feedback textual

**Método 3: propose_new_texts()** - [Opcional] Lógica custom

### 2. Loop de Optimización GEPA

```
1. INICIALIZACIÓN
   └─> Evaluar seed_candidate en trainset/valset

2. LOOP PRINCIPAL (hasta stop_condition)
   └─> SELECT: Elegir candidato a mutar (ParetoCandidateSelector)
   └─> SAMPLE: Minibatch de trainset (BatchSampler)
   └─> EVALUATE: Ejecutar candidato (adapter.evaluate)
   └─> REFLECT: Extraer feedback (adapter.make_reflective_dataset)
   └─> SELECT COMPONENT: Qué componente optimizar
   └─> PROPOSE: Generar textos mejorados (ReflectiveMutationProposer)
   └─> ACCEPT/REJECT: Test en minibatch
   └─> FULL VALIDATION: Evaluar en valset completo
   └─> [OPCIONAL] MERGE: Combinar mejoras
   └─> LOG: Trackear métricas

3. RETURN: GEPAResult con candidatos, scores, lineage
```

### 3. Selección de Pareto

GEPA mantiene un **Pareto front por instancia de validación**:
- Trackea qué candidatos son mejores (Pareto-óptimos)
- Un candidato está en el Pareto front si ningún otro lo supera
- Selección ponderada: candidatos en más fronts se eligen más frecuentemente

### 4. Frontera de Pareto

Basado en conceptos de optimización, una **frontera de Pareto** representa un conjunto de soluciones óptimas en un problema con múltiples objetivos, donde no se puede mejorar un objetivo sin empeorar otro.

En el contexto de la optimización de LLMs, visualiza el compromiso entre **calidad** y **costo/velocidad**:

1.  **Múltiples Objetivos:** Se busca maximizar tanto la calidad de los resultados como la velocidad del cómputo (o minimizar el costo).
2.  **Compromiso (Trade-off):** Generalmente, las configuraciones que producen resultados de mayor calidad tardan más en ejecutarse (menor velocidad) o son más costosas, y las configuraciones más rápidas pueden producir resultados de menor calidad.
3.  **Soluciones Óptimas:** La frontera de Pareto está formada por todas las configuraciones para las que no existe otra configuración que sea *a la vez* más rápida *y* de mayor calidad.

Al elegir un punto en esta frontera "Pareto-óima", se sabe que no hay otra opción que sea mejor en ambos ejes. Para obtener una mayor calidad, se debe aceptar una menor velocidad (o mayor costo), y viceversa. GEPA utiliza este principio para mantener un conjunto de diversas soluciones de alto rendimiento.

---

## Estrategia de Configuración

Para garantizar la reproducibilidad y permitir la experimentación en paralelo, el proyecto sigue una separación estricta de responsabilidades:

### 1. Variables de Entorno (.env) - Infraestructura y Seguridad
Reservado exclusivamente para parámetros que dependen del entorno de ejecución local:
- `LLM_API_KEY`: Credenciales de acceso.
- `LLM_API_BASE`: Endpoints de proveedores (Azure/OpenAI).
- `LLM_MODEL_TASK` / `LLM_MODEL_REFLECTION`: Alias de modelos para facilitar el cambio de proveedor sin tocar el código.

### 2. Archivos YAML - Lógica del Experimento
Contiene todos los parámetros que definen el comportamiento y los resultados de la optimización:
- **Límites de Adaptador**: `max_text_length`, `truncation_strategy`.
- **Hiperparámetros GEPA**: `max_metric_calls`, `minibatch_size`, `max_positive_examples`.
- **Definición de Tarea**: Nombres de columnas, rutas de datasets, clases válidas.

**Nota de Diseño:** Los parámetros lógicos en YAML tienen prioridad sobre cualquier valor por defecto en el código o variables de entorno, permitiendo que cada archivo YAML sea una "receta" completa y reproducible del experimento.

---

## Algoritmo de Optimización Detallado

A continuación se describe el algoritmo exacto implementado en el proyecto, utilizando la terminología de roles y los parámetros de configuración reales.

### 1. Inicialización
- **Datos**: El dataset se divide en tres conjuntos estrictos: `Train` (Entrenamiento), `Val` (Validación) y `Test` (Prueba).
- **Asignación de Modelos**:
    - **Estudiante (Task Model)**: Se usa un modelo rápido y económico (ej. `gpt-4.1-mini`) para la ejecución repetitiva.
    - **Profesor (Reflection Model)**: Se usa un modelo de alta capacidad (ej. `gpt-4o`) exclusivamente para el razonamiento de optimización.

### 2. Fase de Baseline (Línea Base)
Antes de iniciar la optimización, se evalúa el **Prompt Inicial (Semilla)** contra el conjunto de **Validación (`Val`)** completo.
- **Objetivo**: Establecer una métrica justa de comparación contra el resultado final, usando datos que el optimizador no verá durante el entrenamiento.

### 3. Bucle de Optimización (Evolución Reflexiva)
El proceso itera hasta agotar el presupuesto de llamadas a métrica (ej. 50 calls).

#### Paso A: Muestreo por Lotes (Batch Sampling)
- **Datos**: Selección aleatoria de un subconjunto de **`Train` (Entrenamiento)**.
- **Tamaño del Lote**: **3 ejemplos** (valor por default).
- **Objetivo**: Crear "mini-pruebas" rápidas que evitan el sobreajuste y reducen drásticamente el consumo de tokens.

#### Paso B: Evaluación del Estudiante
- **Acción**: El modelo **Estudiante** resuelve los 3 casos con el prompt candidato actual.
- **Optimización**: Si el score es perfecto (3/3), se activa `skip_perfect_score` y se salta la fase de mutación para ahorrar recursos.

#### Paso C: Reflexión y Mutación
- **Actor**: El modelo **Profesor**.
- **Input**: Prompt actual + Trazas de error del Estudiante (sobre datos de `Train`) + Respuesta esperada.
- **Proceso**: El Profesor diagnostica la causa raíz del fallo ("Reflexión") y reescribe las instrucciones del sistema ("Mutación") para corregirlo.

#### Paso D: Selección de Pareto
- **En la Teoría**: GEPA busca un equilibrio entre la **Calidad** del prompt y su **Eficiencia** (longitud/costo en tokens).
- **En la Práctica (Implementación Actual)**: El algoritmo prioriza la **Especialización por Datos**.
    - **Qué guarda**: GEPA mantiene una "población" de prompts donde cada uno ha demostrado ser el mejor (o empatar) resolviendo al menos un ejemplo específico del set de validación.
    - **Resultado**: En lugar de quedarse con un solo prompt "promedio", GEPA conserva un grupo de "especialistas" que cubren diferentes rincones de tus datos. Esto evita que el sistema pierda la capacidad de resolver casos difíciles mientras evoluciona.

### 4. Selección del Campeón
- **Contexto**: Una vez agotado el presupuesto.
- **Acción**: Los sobrevivientes de la Frontera de Pareto se evalúan contra el **conjunto de Validación (`Val`) completo**.
- **Criterio**: El candidato con mejor métrica promedio en validación es seleccionado como el "Campeón".

### 5. Test de Robustez
- **Acción Final**: El Campeón se evalúa una única vez contra el conjunto de **Test (`Test`)** (datos nunca vistos) para certificar su capacidad de generalización real antes del despliegue.

---

## Forma de Operar

### Uso Básico

```bash
# 1. Preparar datos
trainset = [...]  # Lista de ejemplos
valset = [...]    # Lista de validación

# 2. Definir candidato semilla
seed_candidate = {
    "system_prompt": "You are a helpful assistant."
}

# 3. Optimizar
result = gepa.optimize(
    seed_candidate=seed_candidate,
    trainset=trainset,
    valset=valset,
    adapter=MiAdapter(),
    task_lm="openai/gpt-4o-mini",
    reflection_lm="openai/gpt-4o",
    max_metric_calls=150
)

# 4. Obtener resultado
best_prompt = result.best_candidate["system_prompt"]
score = result.best_score
```

### Parámetros Principales

| Parámetro | Descripción | Típico |
|-----------|-------------|--------|
| `seed_candidate` | Diccionario con componentes iniciales | `{"prompt": "..."}` |
| `trainset` | Datos de entrenamiento | 50-500 ejemplos |
| `valset` | Datos de validación | 20-150 ejemplos |
| `adapter` | Instancia de GEPAAdapter | MiAdapter() |
| `task_lm` | Modelo a optimizar | "openai/gpt-4o-mini" |
| `reflection_lm` | Modelo para reflexión | "openai/gpt-4o" |
| `max_metric_calls` | Presupuesto de evaluaciones | 50-2000 |

---

## Casos de Uso

### 1. Optimización de Prompts (AIME)

**Caso**: Mejorar prompts para problemas matemáticos

**Mejora típica**: 46.6% → 56.6% (+10%)

### 2. Programas DSPy Completos

**Caso**: Evolucionar código DSPy completo

**Mejora típica**: 67% → 93% (+26% en MATH)

### 3. Sistemas RAG

**Casos de uso**:
- Optimización de answer generation (demo educativo en gepa_standalone)
- Query reformulation, context synthesis, reranking (librería GEPA completa)

**Implementaciones**:
- **Demo educativo**: `gepa_standalone/DEMO4_RAG_GUIDE.md` - Optimización con evaluación LLM-as-a-Judge
- **Producción**: Librería GEPA con soporte para ChromaDB, Weaviate, Qdrant, Milvus, LanceDB

**Para comenzar**: `python gepa_standalone/demos/demo4_rag_optimization.py`

### 4. Agentes con Herramientas

**Caso**: Optimizar system prompts de agentes que interactúan con ambientes externos

---

## Estrategias Avanzadas

### Selección de Candidatos

- **ParetoCandidateSelector**: Pareto-óptimo (por defecto, robusto)
- **CurrentBestCandidateSelector**: Siempre el mejor (greedy)
- **EpsilonGreedyCandidateSelector**: Epsilon-greedy (exploración)

### Selección de Componentes

- **RoundRobinReflectionComponentSelector**: Un componente por iteración (por defecto)
- **AllReflectionComponentSelector**: Todos a la vez

### Condiciones de Parada

- **MaxMetricCallsStopper**: Límite de presupuesto
- **NoImprovementStopper**: Early stopping en plateau
- **ScoreThresholdStopper**: Para al alcanzar objetivo
- **CompositeStopper**: Combinar múltiples (AND/OR)

---

## Experiment Tracking

### WandB

Integración automática con WandB para tracking en tiempo real.

### MLflow

Integración con MLflow para artifact storage y model registry.

### Custom Logger

Protocolo `LoggerProtocol` para implementaciones personalizadas.

---

## Integración con DSPy

### Opción 1: API DSPy (Recomendado)

Usar `dspy.GEPA` directamente - versión más actualizada en repo DSPy.

### Opción 2: GEPA con DSPy Adapter

Usar `gepa.adapters.dspy_adapter` para optimizar signatures DSPy.

### Opción 3: Full Program Adapter

Usar `dspy_full_program_adapter` para evolucionar programas completos.

**Tutorial**: https://dspy.ai/tutorials/gepa_ai_program/

---

## GEPAResult - Artefacto de Salida

### Propiedades Principales

| Propiedad | Descripción |
|-----------|-------------|
| `best_candidate` | Mejor candidato (dict) |
| `best_score` | Score del mejor |
| `best_idx` | Índice del mejor |
| `candidates` | Lista de todos los candidatos |
| `validation_scores` | Scores de validación |
| `total_metric_calls` | Total de llamadas al LM |

### Métodos Útiles

| Método | Descripción |
|--------|-------------|
| `non_dominated_indices()` | Candidatos Pareto-óptimos |
| `lineage(idx)` | Árbol genealógico desde seed |
| `best_k(k)` | Top-k candidatos |
| `save_json(path)` | Guardar a JSON |
| `to_dict()` | Convertir a diccionario |

---

## Testing

### Ejecutar Tests

```bash
# Con uv
uv run pytest tests/

# Con pytest
pytest tests/ -v

# Test específico
pytest tests/test_candidate_selector.py

# Con coverage
pytest tests/ --cov=gepa --cov-report=html
```

### Fixtures Reproducibles

GEPA usa **mocked LLMs** para tests reproducibles:
- Modo REPLAY (por defecto): usa respuestas cacheadas
- Modo RECORD: hace llamadas reales y cachea

### Type Checking

```bash
uv run pyright src/gepa/
```

---

## Mejores Prácticas

### Diseño de Feedback

Implementar feedback específico y accionable en `make_reflective_dataset()`.

### Selección de Modelos

- **Económico**: task_lm=gpt-4o-mini, reflection_lm=gpt-4o
- **Máximo rendimiento**: task_lm=gpt-4o, reflection_lm=o1
- **Local**: task_lm=ollama/llama3

### Presupuesto

- **Exploración inicial**: 50 calls
- **Optimización estándar**: 150 calls
- **Optimización intensiva**: 500 calls
- **Sistemas complejos**: 2000 calls

### Tamaño de Datasets

- **Desarrollo**: train=20, val=10
- **Estándar**: train=100, val=50
- **Producción**: train=500, val=150

---

## Integraciones en Producción

| Organización | Uso |
|--------------|-----|
| **DSPy** | API `dspy.GEPA` con tutoriales |
| **MLflow** | `mlflow.genai.optimize_prompts()` |
| **Databricks** | Optimización de agentes (90x reducción costo) |
| **Weaviate** | Video tutorial sobre rerankers |
| **HuggingFace** | Cookbook oficial DSPy+GEPA |
| **OpenAI** | Cookbook sobre agentes auto-evolutivos |
| **Arc.computer** | Agentes de diagnóstico en producción |
| **Intrinsic Labs** | 38% reducción error OCR |

---

## Recursos

### Documentación

- **GitHub**: https://github.com/gepa-ai/gepa
- **Paper**: https://arxiv.org/abs/2507.19457
- **DSPy Tutorials**: https://dspy.ai/tutorials/gepa_ai_program/
- **HuggingFace Cookbook**: DSPy+GEPA integration
- **OpenAI Cookbook**: Self-evolving agents

### Comunidad

- GitHub Issues: Reportar bugs
- GitHub Discussions: Preguntas
- DSPy Discord: Canal #gepa

### Citación

```bibtex
@misc{agrawal2025gepareflectivepromptevolution,
    title={GEPA: Reflective Prompt Evolution Can Outperform
           Reinforcement Learning},
    author={Lakshya A Agrawal and Shangyin Tan and Dilara Soylu
            and Noah Ziems and others},
    year={2025},
    eprint={2507.19457},
    archivePrefix={arXiv},
    primaryClass={cs.CL},
    url={https://arxiv.org/abs/2507.19457}
}
```

---

## Resumen Ejecutivo

GEPA es un framework de optimización que usa:

**Características Clave:**
- Mutaciones reflexivas con LLMs (no aleatorias)
- Búsqueda Pareto-eficiente
- Feedback textual rico
- Co-evolución de múltiples componentes
- Integración con DSPy, MLflow, WandB

**Resultados Comprobados:**
- +10% en AIME
- +26% en MATH
- 90x reducción de costo (Databricks)
- 38% reducción error OCR

**Ideal Para:**
- Optimización de prompts LLM
- Evolución de programas DSPy
- Mejora de sistemas RAG
- Optimización de agentes
- Cualquier sistema con componentes de texto

---

