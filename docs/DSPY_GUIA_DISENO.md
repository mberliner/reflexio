# Guía de Diseño de Sistemas DSPy

## Propósito
Esta guía proporciona un marco estratégico para diseñar, construir y optimizar sistemas de IA utilizando DSPy. Se enfoca en la selección de componentes y patrones arquitecturales basados en requisitos funcionales, desacoplando la "Ingeniería de Sistemas" de la implementación de bajo nivel.

---

## 1. Catálogo de Componentes (Bloques de Construcción)

En DSPy, un sistema se compone de **Módulos** (capas de procesamiento) y se compila con **Optimizadores** (algoritmos de mejora).

### A. Módulos de Procesamiento (Layers)
Componentes que procesan datos en tiempo de inferencia.

| Categoría | Módulo | Función Principal | Cuándo Usar |
| :--- | :--- | :--- | :--- |
| **Core** | `dspy.Predict` | Input → LLM → Output | Tareas simples, clasificación directa, extracción sin lógica compleja. |
| | `dspy.ChainOfThought` | Input → Razonamiento → Output | Tareas que requieren lógica, deducción o matices sutiles. Mejora precisión general. |
| | `dspy.ChainOfThoughtWithHint` | Input + Pista → CoT → Output | Cuando el usuario puede dar sugerencias en tiempo real para guiar al modelo. |
| **Agentes** | `dspy.ReAct` | Bucle: Pensar → Usar Herramienta → Observar | Cuando el modelo necesita datos externos (APIs, Búsquedas) o calculadoras. |
| | `dspy.ProgramOfThought` | Input → Generar Código → Ejecutar → Output | Problemas matemáticos, lógica algorítmica robusta o análisis de datos. |
| **Control** | `dspy.Assert` | `assert condition, "error msg"` | Validaciones suaves. Si falla, el modelo reintenta corrigiendo el error (Backtracking). |
| | `dspy.Suggest` | `suggest condition, "error msg"` | Validaciones críticas. Si falla, descarta la traza actual y prueba otro camino. |
| **Ensamble** | `dspy.Majority` | Votación entre múltiples predicciones | Cuando la consistencia es crítica y se puede sacrificar latencia/costo. |
| **RAG** | `dspy.Retrieve` | Consulta → Top-K Pasajes | Recuperación de contexto desde bases vectoriales (Chroma, Weaviate, etc.). |

### B. Optimizadores (Teleprompters)
Algoritmos que "compilan" el programa, ajustando prompts y ejemplos antes del despliegue.

| Tipo | Optimizador | Estrategia | Escenario Ideal |
| :--- | :--- | :--- | :--- |
| **Few-Shot** | `LabeledFewShot` | Inyecta ejemplos aleatorios del trainset. | Línea base rápida. Pocos datos disponibles. |
| | `BootstrapFewShot` | Teacher-Student. Genera ejemplos para sí mismo. | Tareas estándar. Requiere dataset pequeño (>10 ejemplos). |
| | `BootstrapFewShotWithRandomSearch` | Genera y combina candidatos de ejemplos. | **Estándar de Oro**. Mejor balance costo-beneficio para la mayoría de tareas. |
| | `KNNFewShot` | Selecciona ejemplos similares al input actual. | Datasets de entrenamiento muy grandes y diversos. |
| **Instruction** | `COPRO` | Reescribe las instrucciones del sistema. | Cuando el prompt inicial es vago o mejorable. |
| | `MIPRO / MIPROv2` | Optimiza instrucciones + ejemplos (Bayesiano). | Tareas complejas y multi-paso. State-of-the-Art (pero costoso de entrenar). |

---

## 2. Patrones Arquitecturales

Formas probadas de conectar los bloques para resolver problemas comunes.

### A. RAG Clásico (Retrieval-Augmented Generation)
**Flujo:** `Retrieve(k=N)` → `ChainOfThought(Context+Query -> Answer)`
**Uso:** Preguntas y respuestas sobre documentos privados.
**Mejora:** Usar `dspy.Assert` para verificar que la respuesta contenga citas del contexto.

### B. RAG Multi-Hop (Patrón Baleen)
**Flujo:** Bucle de `[Generar Query → Retrieve → Leer]` hasta tener suficiente info → `Answer`.
**Uso:** Preguntas complejas que requieren combinar datos de múltiples fuentes ("¿Nació Obama en el mismo estado que Lincoln?").

### C. Pipeline de Extracción y Validación
**Flujo:** `Predict(Extraction)` → `Assert(SchemaValidation)`
**Uso:** Convertir texto no estructurado a JSON estricto (Pydantic). Si el JSON falla, el `Assert` retroalimenta el error al LLM para que se corrija.

### D. Cascada de Modelos (Cascade)
**Flujo:** `Predict(Modelo Pequeño)` → `Assert(HighConfidence)` → *Fallback* → `Predict(Modelo Grande)`
**Uso:** Optimización de costos. Se intenta resolver con un modelo barato (GPT-4o-mini) y solo se escala al costoso (GPT-4o) si la confianza es baja.

### E. Self-Refine (Refinamiento Iterativo)
**Flujo:** `Predict(Draft)` → `Predict(Critique)` → `Predict(Refine based on Critique)`
**Uso:** Generación de contenido creativo o código de alta calidad donde el primer borrador suele ser imperfecto.

---

## 3. Matriz de Selección de Estrategia

Guía rápida para elegir componentes según las características del problema.

| Característica del Problema | Módulo Recomendado | Optimizador Sugerido | Patrón Clave |
| :--- | :--- | :--- | :--- |
| **Clasificación Simple** (Sentimiento, Spam) | `Predict` | `BootstrapFewShot` | Directo |
| **Clasificación Matizada** (Tono, Intención) | `ChainOfThought` | `BootstrapFewShotWithRandomSearch` | - |
| **Extracción Estructurada** (CV, Facturas) | `Predict` (con Pydantic) | `BootstrapFewShot` | Validación (`Assert`) |
| **QA sobre Documentos** (Soporte Técnico) | `ChainOfThought` | `MIPROv2` | RAG con Citas |
| **Razonamiento Lógico/Math** | `ProgramOfThought` | `BootstrapFewShot` | CoT |
| **Agentes Autónomos** (Web Scraper) | `ReAct` | `BootstrapFewShot` | Tool Use |
| **Generación de Código (SQL)** | `ChainOfThought` | `BootstrapFewShot` | Self-Correction (`Assert`) |

---

## 4. Metodología de Diseño de Pasos

Cómo descomponer un problema complejo en un pipeline de DSPy.

1.  **Definir la Firma (Signature):** Escribir inputs y outputs claros. Tipar los datos.
2.  **Identificar Bloqueos Cognitivos:** ¿Dónde se "trabaría" un humano?
    *   *Falta de Info:* Agregar paso de `Retrieve`.
    *   *Ambigüedad:* Agregar paso de `Clarification` o `Reasoning`.
    *   *Error de Formato:* Agregar paso de `Assert`.
3.  **Seleccionar Optimizador:**
    *   Empieza con `BootstrapFewShot` (rápido y barato).
    *   Si necesitas más calidad, pasa a `RandomSearch`.
    *   Si el prompt es el problema, usa `MIPRO`.
4.  **Definir Métrica:** Crear una función Python que devuelva `True/False` o un puntaje `0.0-1.0`. Sin una buena métrica, la optimización es imposible.

---

## 5. Referencia Rápida de Métricas

| Tipo de Tarea | Métrica Sugerida | Descripción |
| :--- | :--- | :--- |
| **Clasificación** | `dspy.evaluate.answer_exact_match` | Coincidencia exacta de string o categoría. |
| **QA Corto** | `dspy.evaluate.answer_match` | Coincidencia parcial (el target está en la respuesta). |
| **QA Largo / RAG** | `dspy.evaluate.SemanticF1` | Similitud semántica usando embeddings o n-grams. |
| **Código / SQL** | `ExecutionMatch` | Ejecutar el código generado y comparar el resultado de ejecución. |
| **Compleja / Subjetiva** | `LLM-as-a-Judge` | Usar un LLM para evaluar la calidad (con `dspy.Predict`). |

### Modos de Matching para `create_dynamic_metric`

La metrica dinamica (`dspy_gepa_poc/metrics.py`) soporta 3 modos de comparacion configurables via YAML:

| Modo | Comportamiento | Caso de Uso |
| :--- | :--- | :--- |
| `exact` (default) | Igualdad exacta tras `strip().lower()` | Clasificacion, campos con valores cerrados |
| `normalized` | Elimina puntuacion, normaliza espacios, luego compara | Extraction con formatos variables (moneda, fechas) |
| `fuzzy` | `SequenceMatcher.ratio() >= threshold` sobre texto normalizado | Near-misses (plurales, variaciones menores) |

Configuracion en YAML (`optimization`):
```yaml
optimization:
  match_mode: "normalized"
  fuzzy_threshold: 0.85       # solo aplica en modo fuzzy
```

Ver `docs/LECCIONES_APRENDIDAS.md` (Seccion 1) para el diagnostico detallado del problema que motivo esta implementacion.
