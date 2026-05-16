# Guía: Optimizar Prompts con Base de Conocimiento (Archivo de Reglas)

## Problema

Cuando el sistema usa un archivo de reglas (reglamento, política, especificación técnica) como contexto
y debe aplicarlas correctamente para responder, clasificar o tomar decisiones — esto es un caso de
**grounded generation** o RAG simplificado sin recuperación vectorial.

---

## Selección de Framework

| Criterio | GEPA standalone | DSPy + GEPA |
|---|---|---|
| El archivo de reglas cabe en el contexto del prompt | **Ideal** | También funciona |
| Reglas son estáticas (mismo archivo para todos los casos) | **Ideal** | Viable |
| Quieres optimizar solo el `system_prompt` | **Ideal** | Más complejo |
| La tarea requiere razonamiento multi-paso sobre las reglas | Aceptable | **Mejor** |
| Presupuesto de evaluaciones reducido (< 60 llamadas LLM) | **Ideal** | Más costoso |

**Punto de partida recomendado: GEPA standalone con adapter `rag`.**

---

## Implementación con GEPA standalone

### Adapter a usar: `rag`

El `SimpleRAGAdapter` cubre exactamente este patrón:
- `context` = tu archivo de reglas (o la sección relevante)
- `question` = el caso de entrada a evaluar
- `answer` = la respuesta esperada (ground truth)
- GEPA optimiza el `system_prompt` de forma reflexiva iterativa

### 1. Dataset CSV

Archivo: `gepa_standalone/experiments/datasets/<nombre>.csv`

```csv
question,context,answer,split
"¿Puede un cliente con 2 incidencias abrir un ticket prioritario?","REGLA 1: Los clientes premium tienen acceso prioritario...\nREGLA 2: Clientes con más de 3 incidencias activas...","No, porque la Regla 2 bloquea el acceso hasta resolver las incidencias activas.",train
```

Columnas requeridas:
- `question`: el caso de entrada
- `context`: el contenido del archivo de reglas (repetir en cada fila si las reglas son siempre las mismas)
- `answer`: respuesta esperada
- `split`: `train` / `val` / `test`

Datos mínimos recomendados: 15-20 ejemplos en `train` para que la reflexión de GEPA sea útil.

### 2. Prompt inicial

Archivo: `gepa_standalone/experiments/prompts/<nombre>.json`

```json
{
  "system_prompt": "Eres un asistente que aplica las reglas del sistema para responder consultas. Usa únicamente la información provista en el contexto."
}
```

GEPA evoluciona este prompt de forma reflexiva — no necesita ser perfecto al inicio.

### 3. Config YAML

Archivo: `gepa_standalone/experiments/configs/<nombre>.yaml`

```yaml
case:
  name: "mis_reglas"
  title: "Aplicación de Reglas de Negocio"
  description: "Optimiza el sistema para aplicar un reglamento con precisión"

adapter:
  type: "rag"
  rag_context_max_length: 3000   # ajustar al tamaño del archivo de reglas
  rag_max_positive_examples: 2

data:
  csv_filename: "<nombre>.csv"
  input_column: "question"
  output_columns:
    - "context"
    - "answer"

prompt:
  filename: "<nombre>.json"

optimization:
  max_metric_calls: 60
  skip_perfect_score: true
  display_progress_bar: true
```

### 4. Ejecución

```bash
python -m gepa_standalone.universal_optimizer --config <nombre>.yaml
```

---

## Cuándo escalar a DSPy + GEPA

Si la tarea requiere razonamiento encadenado (ej: "evalúa la Regla A, y si cumple, aplica la Regla B"),
usar DSPy con `ChainOfThought` y config dinámico. La referencia de estructura es
`dspy_gepa_poc/configs/dynamic_email_urgency.yaml`, adaptando la `signature` para incluir
`rules_context` como campo de entrada adicional.

Optimizadores DSPy recomendados para este patrón:

| Optimizador | Cuándo usarlo |
|---|---|
| `BootstrapFewShot` | Línea base rápida, pocas iteraciones |
| `BootstrapFewShotWithRandomSearch` | Estándar de oro, mejor balance costo-calidad |
| `MIPROv2` | Cuando el prompt inicial es el problema principal |

---

## Decisiones de Diseño Críticas

### Archivo de reglas grande (> 4k tokens)

No usar `context` fijo en cada fila del CSV. Las opciones son:
1. Pre-filtrar las secciones relevantes por caso antes de armar el CSV.
2. Usar retrieval vectorial real con DSPy (`dspy.Retrieve`) — implica más infraestructura.

### Métrica de evaluación

El `SimpleRAGAdapter` usa LLM-as-Judge por defecto, que es costoso pero flexible.

Si las respuestas esperadas son categóricas (sí/no, aprobar/rechazar), usar en su lugar el
adapter `classifier` con coincidencia exacta: más barato, determinista y sin dependencia del
modelo juez.

### Volumen de datos

| Ejemplos en `train` | Recomendación |
|---|---|
| < 15 | DSPy `BootstrapFewShot` puede ser más efectivo que GEPA |
| 15-50 | GEPA standalone es ideal |
| > 50 | GEPA o DSPy con `KNNFewShot` |

---

## Referencias

- `gepa_standalone/experiments/configs/rag_optimization.yaml` — config de referencia
- `gepa_standalone/adapters/simple_rag_adapter.py` — implementación del adapter
- `gepa_standalone/adapters/simple_classifier_adapter.py` — alternativa para respuestas categóricas
- `docs/DSPY_GUIA_DISENO.md` — patrones arquitecturales DSPy (sección RAG Clásico)
- `docs/GEPA_DOCUMENTACION.md` — filosofía y arquitectura de GEPA
