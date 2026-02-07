# Manejo de Errores en GEPA Standalone

## Problema Original

Cuando hay un **error técnico** durante la evaluación de un ejemplo (excepción de API, timeout, problema de conexión), NO es lo mismo que cuando el modelo da una **respuesta incorrecta**.

### Diferencia Conceptual

| Tipo de Fallo | Descripción | ¿Refleja calidad del prompt? |
|---------------|-------------|------------------------------|
| **Respuesta Incorrecta** | El modelo respondió, pero clasificó/extrajo incorrectamente | SÍ - El prompt es deficiente |
| **Error Técnico** | El modelo NO pudo responder (API error, timeout, excepción) | NO - Problema técnico, no del prompt |

### Impacto en Estadísticas (Comportamiento Anterior)

**Antes de la corrección**, ambos casos recibían `score = 0.0`:

```python
# Comportamiento INCORRECTO (anterior)
except Exception as e:
    outputs.append({"error": str(e), "text": user_text})
    scores.append(0.0)  # Penaliza el prompt por error técnico
```

**Problema**: Los errores técnicos sesgaban las estadísticas y podían hacer que GEPA descartara buenos prompts por razones no relacionadas con su calidad.

#### Ejemplo del Problema

Si tienes 5 ejemplos con estos resultados:
- Ejemplo 1: Correcto -> score = 1.0
- Ejemplo 2: Correcto -> score = 1.0
- Ejemplo 3: **Error técnico (timeout)** -> score = 0.0
- Ejemplo 4: Incorrecto -> score = 0.0
- Ejemplo 5: Correcto -> score = 1.0

**Score promedio (INCORRECTO)** = (1.0 + 1.0 + 0.0 + 0.0 + 1.0) / 5 = **0.6 (60%)**

El prompt parece tener 60% de precisión cuando en realidad tiene 75% (3/4 ejemplos válidos).

---

## Solución Implementada

### Estrategia: Descarte Directo

Los ejemplos con **errores técnicos** NO se incluyen en las estadísticas. Solo se registran para debugging.

### Implementación

```python
# Comportamiento CORRECTO (nuevo)
try:
    response = self.client.chat.completions.create(...)
    # ... evaluar respuesta ...
    outputs.append(output)
    scores.append(score)

except Exception as e:
    # ESTRATEGIA: Descarte directo
    # No agregar a outputs/scores/trajectories
    # Solo registrar para debugging
    error_info = {
        "batch_idx": idx,
        "text_preview": user_text[:100],
        "error": str(e),
        "error_type": type(e).__name__
    }
    errors_log.append(error_info)
    print(f"[WARNING] Error técnico en ejemplo {idx}, descartando de estadísticas: {e}")
```

### Beneficios

1. **Estadísticas precisas**: Solo reflejan la calidad del prompt, no problemas técnicos
2. **GEPA más efectivo**: No descarta buenos candidatos por errores transitorios
3. **Transparencia**: Los errores se registran para debugging
4. **Información clara**: Se muestra cuántos ejemplos fueron descartados

### Ejemplo Corregido

Mismos 5 ejemplos que antes:
- Ejemplo 1: Correcto -> score = 1.0
- Ejemplo 2: Correcto -> score = 1.0
- Ejemplo 3: **Error técnico (timeout)** -> **DESCARTADO**
- Ejemplo 4: Incorrecto -> score = 0.0
- Ejemplo 5: Correcto -> score = 1.0

**Score promedio (CORRECTO)** = (1.0 + 1.0 + 0.0 + 1.0) / 4 = **0.75 (75%)**

Ahora refleja correctamente la calidad del prompt.

---

## Logging de Errores

### Durante la Evaluación

Cuando ocurre un error, se muestra:

```
[WARNING] Error técnico en ejemplo 3, descartando de estadísticas: Connection timeout
```

### Resumen Final

Al finalizar el batch, si hubo errores:

```
[INFO] 2 ejemplos descartados por errores técnicos de 20 totales
[INFO] Estadísticas calculadas sobre 18 ejemplos válidos
```

### Información Registrada

Para cada error se guarda:
- `batch_idx`: Posición en el batch
- `text_preview`: Primeros 100 caracteres del texto
- `error`: Mensaje de error
- `error_type`: Tipo de excepción (TimeoutError, ConnectionError, etc.)

---

## Archivos Modificados

### 1. `gepa_standalone/adapters/simple_classifier_adapter.py`

**Método `evaluate()`** (líneas 44-138):
- Agregado `errors_log` para tracking
- Agregado `idx` al loop para identificar ejemplos
- Bloque `except` modificado para descarte directo
- Logging de resumen de errores
- Documentación actualizada

### 2. `gepa_standalone/adapters/simple_extractor_adapter.py`

**Método `evaluate()`** (líneas 45-171):
- Agregado `errors_log` para tracking
- Agregado `idx` al loop para identificar ejemplos
- Bloque `except` modificado para descarte directo
- Logging de resumen de errores
- Documentación actualizada

---

## Consideraciones

### ¿Cuándo NO usar descarte directo?

Si tu caso de uso requiere que **todos los ejemplos** sean evaluados (por ejemplo, en un benchmark estricto), considera:

1. **Implementar reintentos**: Agregar lógica de retry con backoff exponencial
2. **Fallback a modelo alternativo**: Si falla el modelo principal, usar uno de respaldo
3. **Pausar y alertar**: Detener la optimización si hay muchos errores técnicos

### ¿Qué tipos de errores se descartan?

Cualquier `Exception` capturada durante la llamada al LLM:
- `ConnectionError`
- `TimeoutError`
- `APIError`
- `RateLimitError`
- `ServiceUnavailableError`
- Etc.

### ¿Y los errores de parsing JSON?

En el extractor, los errores de **parsing JSON** NO causan descarte. El adaptador intenta:
1. `json.loads()` directo
2. Si falla, `_extract_json_from_text()` para extraer JSON del texto
3. Si sigue fallando, retorna `{}` (dict vacío) -> score = 0.0

Esto es correcto porque un JSON mal formado **SÍ refleja** un problema con el prompt (no dio instrucciones claras de formato).

---

## Testing

### Probar el Nuevo Comportamiento

Para verificar que funciona correctamente:

```python
# Simular error técnico
from unittest.mock import patch

adapter = SimpleClassifierAdapter(["urgent", "normal", "low"])

# Mock para lanzar excepción
with patch.object(adapter.client.chat.completions, 'create') as mock_create:
    mock_create.side_effect = Exception("API timeout")

    batch = [{"text": "Test email", "urgency": "urgent"}]
    result = adapter.evaluate(batch, {"system_prompt": "Test"})

    # Verificar que el ejemplo fue descartado
    assert len(result.scores) == 0  # No hay scores
    assert len(result.outputs) == 0  # No hay outputs
```

### Ejemplo Real

Ejecutar `demo1_email_urgency.py` con conexión inestable mostrará:

```
[WARNING] Error técnico en ejemplo 3, descartando de estadísticas: Connection timeout
[WARNING] Error técnico en ejemplo 7, descartando de estadísticas: Connection timeout

[INFO] 2 ejemplos descartados por errores técnicos de 15 totales
[INFO] Estadísticas calculadas sobre 13 ejemplos válidos

[OK] Correctos: 10/13 (76.9%)
```

---

## Resumen

| Aspecto | Antes | Ahora |
|---------|-------|-------|
| Error técnico -> Score | 0.0 | **Descartado** |
| Afecta promedio | SÍ (sesgo) | NO |
| Visibilidad de errores | Limitada | Logging completo |
| Estadísticas precisas | NO | SÍ |
| GEPA optimiza mejor | Sesgado | Preciso |

**Conclusión**: Los errores técnicos ahora se manejan correctamente, descartándolos de las estadísticas en lugar de penalizar injustamente los prompts candidatos.