# Manejo de Errores en GEPA Standalone

> Las secciones "Problema Original" a "Consideraciones" describen el descarte
> directo original (historico). El comportamiento vigente, con clasificacion de
> fallas, atribucion y aborto, esta en "Estado vigente: fallas clasificadas
> (SPEC-104)".

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
        "error_type": type(e).__name__,
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

### Estado vigente: fallas clasificadas (SPEC-104)

El "descarte directo" de arriba es el diseno original. Lo reemplaza
[SPEC-104](../specs/SPEC-104-fallas-tecnicas-justas.md): ya no se atrapa
cualquier `Exception` para descartar el ejemplo. Cada falla se clasifica, se
cuenta una vez por caso y recibe el tratamiento de su clase y su rol. Las
definiciones normativas (reglas de deteccion, umbrales, FR/SC) viven en la spec;
aca solo se resume como operar y leer los resultados.

Roles en codigo, logs, `run.json` y YAML: `task` (tarea), `judge` (juez, solo
RAG) y `reflection` (reflexion). `judge` tiene umbrales propios y no se pliega en
`reflection`.

Capas de deteccion (`shared/llm/failures.py`, `shared/llm/call.py`):

1. Respuesta del LLM: excepcion de LiteLLM, `finish_reason` y `message.refusal`.
2. Parseo de la respuesta (adapter, metrica, juez, envoltorio de reflexion):
   solo la clase `formato`.

| Clase | Causa |
|---|---|
| `configuracion` | 4xx de autenticacion, permisos, modelo inexistente o parametros invalidos; excepcion no clasificada |
| `entrada` | Rechazo antes de generar: filtro de entrada o ventana de contexto excedida |
| `presupuesto` | `finish_reason=length` (`max_tokens` insuficiente), con texto parcial o sin texto |
| `filtro_salida` | `finish_reason=content_filter` o `refusal` presente |
| `sin_texto` | HTTP 200 sin texto, sin otra causa |
| `infraestructura` | Red, timeout, 429 o 5xx que persiste tras los reintentos |
| `formato` | Hay texto pero no cumple el formato (clase no valida, JSON no parseable, `AdapterParseError`, puntaje de juez ilegible) |

En tarea, `entrada` y `presupuesto` se atribuyen contra el baseline (una llamada
extra por caso, cacheada): si el baseline tambien falla es causa externa
(`entrada_dato`, `presupuesto`) y el caso queda NE; si no, es del prompt
(`entrada_candidato`, `presupuesto_candidato`) y puntua 0. Las claves de conteo
son esos nombres.

Tratamiento ("NE" = no evaluado: no suma ni resta al score reportado, se cuenta y
se registra; "Descarta" = la propuesta de reflexion no se adopta):

| Clase | Tarea | Juez | Reflexion |
|---|---|---|---|
| `configuracion` | Aborta | Aborta | Aborta |
| `entrada` | `entrada_candidato`: score 0. `entrada_dato`: NE | NE | Descarta |
| `presupuesto` | `presupuesto_candidato`: score 0. `presupuesto`: NE | NE | Descarta |
| `filtro_salida`, `sin_texto`, `infraestructura` | NE | NE | Descarta |
| `formato` | Score 0 | NE, tras los reintentos del juez | Descarta |

Consecuencias practicas:

- Un caso NE no desaparece: `evaluados + NE == tamano del lote`. Durante la
  optimizacion recibe 0.0 solo como valor tecnico para GEPA y nunca llega al
  Profesor como error del prompt (en `dspy_gepa_poc` el feedback dice que fue una
  falla externa). Las metricas reportadas excluyen los NE y muestran
  `n_evaluados / n_total`; el delta optimizado - baseline es pareado.
- Reintentos: `num_retries=0` en LiteLLM y en el LM de DSPy (engine propio,
  SPEC-105); solo `infraestructura` se
  reintenta (loop propio, backoff exponencial, default 3 reintentos). Los
  intentos intermedios (reintentos de red, fallback de `ChatAdapter` a
  `JSONAdapter`, reintentos del juez) van a DEBUG y no cuentan.
- Cada falla deja un unico WARNING por caso con rol, clave, atribucion, causa,
  `finish_reason` y `case_id`. El conteo de esas lineas coincide con
  `run.json["failures"]["counts"]` (ver `docs/METADATA_REPRODUCIBILIDAD.md`).
- Reflexion: una propuesta con falla de cualquier clase (incluida una salida sin
  bloque de instruccion) se descarta en el envoltorio del `reflection_lm`; GEPA
  saltea la iteracion y el candidato vigente no cambia. El `case_id` es la
  iteracion de GEPA.

#### Aborto de la corrida

La corrida pasa a "abortada" cuando ocurre una falla `configuracion`, o cuando la
tasa de una clase en un rol supera su umbral (con un minimo de intentos). Como
`Evaluate` y GEPA pueden tragarse excepciones, el corte es por estado: los
envoltorios no llaman al LLM si esta abortado y los orquestadores consultan el
estado tras cada paso y antes de `save_results()`. El error nombra clase, rol,
conteo y causa probable; para `presupuesto` agrega que el baseline tambien se
corta, sugiere subir `max_tokens` y, si el modelo lo soporta, bajar el effort.
Una corrida abortada escribe `run.json` con `status: aborted` y ninguna fila de
CSV. Umbrales por defecto y como cambiarlos: seccion `failures` en
`docs/YAML_CONFIG_REFERENCE.md`.

Como leer el conteo del aborto:

- `run.json["abort"]["conteo"]` e `intentos` son los del momento del corte. En
  `dspy_gepa_poc`, tras un aborto por umbral, la metrica puede registrar despues
  la falla del caso que estaba en curso (el `record_attempt` va despues de la
  llamada), por lo que `run.json["failures"]["counts"]` final puede superar
  `abort.conteo`. No es una inconsistencia: `counts` coincide con el log y
  `abort.conteo` es el valor que disparo el aborto.
- En un aborto por `configuracion`, la capa de llamada fija el aborto y el
  envoltorio cuenta la falla despues: el aborto queda pendiente hasta ese
  `record`, asi `abort.conteo` incluye la falla que lo disparo y la linea ERROR
  sale despues de su WARNING.

#### Referencias a modulos anteriores (SPEC-103)

El helper `shared.llm.response_text` (SPEC-103 FR-009) se elimino: la capa de
llamada lanza `LLMCallFailure` y su subclase
`EmptyResponseError` ante una respuesta 200 sin texto. El modulo
`dspy_gepa_poc/empty_response.py` (`EmptyResponsePrediction`,
`zero_on_empty_response`) fue reemplazado por `dspy_gepa_poc/call_failures.py`
(`FailedCallPrediction`, `guard_metric`): el `forward` envuelto devuelve una
prediccion con la falla clasificada y la metrica envuelta decide NE o score 0
segun la tabla; ya no puntua 0.0 toda respuesta sin texto. La inferencia directa
(`run_inference.py` y scripts sin `Evaluate`) no usa el envoltorio y corta ante
una falla (deuda D-020).

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
with patch.object(adapter.client.chat.completions, "create") as mock_create:
    mock_create.side_effect = Exception("API timeout")

    batch = [{"text": "Test email", "urgency": "urgent"}]
    result = adapter.evaluate(batch, {"system_prompt": "Test"})

    # Verificar que el ejemplo fue descartado
    assert len(result.scores) == 0  # No hay scores
    assert len(result.outputs) == 0  # No hay outputs
```

### Ejemplo Real

Ejecutar el caso `email_urgency` (`python -m gepa_standalone.universal_optimizer
--config gepa_standalone/experiments/configs/email_urgency.yaml`) con conexión
inestable mostrará:

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

**Conclusión**: Los errores técnicos no penalizan al prompt candidato: quedan como casos no evaluados, contados y acotados por umbrales (SPEC-104, ver "Estado vigente"). La tabla compara el diseño original con el comportamiento previo a él.