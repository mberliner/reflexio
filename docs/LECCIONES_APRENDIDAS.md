# Lecciones Aprendidas y Hallazgos de Experimentación

Este documento recopila los hallazgos críticos, errores comunes y conocimientos teóricos adquiridos durante las pruebas de optimización con DSPy y GEPA.

## 1. Diseño de Métricas y Evaluación

### El Problema del "Reasoning" (CoT)
**Síntoma:** El modelo obtenía sistemáticamente un puntaje de 50% a pesar de razonar correctamente.
**Causa:** La métrica intentaba hacer una comparación exacta ("string match") del campo `reasoning` generado por el modelo contra el `reasoning` del dataset. Como el modelo genera texto libre, nunca coincidía.
**Lección:**
- **Nunca evalúes campos de texto libre (como "Explicación" o "Razonamiento") con coincidencia exacta.**
- Usa métricas semánticas (usando otro LLM para juzgar) o simplemente excluye el razonamiento de la métrica final, evaluando solo el resultado determinista (ej: la etiqueta de clasificación).
- DSPy genera "Chain of Thought" (CoT) automáticamente; no es necesario forzarlo como un output explícito en la `Signature` si solo se usa para pensar.

### Consistencia de Etiquetas (Multilingüe)
**Síntoma:** El modelo en español obtenía 16% de accuracy a pesar de generar respuestas correctas en español.
**Causa:** El Prompt pedía la salida en español ("positivo"), pero el Dataset tenía las etiquetas en inglés ("positive"). La métrica comparaba `"positivo" == "positive"` -> `False`.
**Lección:**
- **Sincronización:** Asegurar que el idioma de las etiquetas en el Dataset (`Ground Truth`) coincida exactamente con el idioma que el Prompt solicita al modelo.
- Si se trabaja en múltiples idiomas, se deben traducir tanto las instrucciones como las etiquetas de validación.

### Metrica Exacta en Extraction (Falsos Negativos por Formato)
**Sintoma:** Los casos de Order Extraction mostraban alta inestabilidad (Std hasta 27.70) y scores bajos a pesar de que el modelo extraia la informacion correctamente.
**Causa:** `create_dynamic_metric` comparaba strings con igualdad exacta. Diferencias triviales de formato causaban fallos:
- `"$2,999"` vs `"$2999"` = FALLO (coma en moneda)
- `"March 22, 2024"` vs `"March 22 2024"` = FALLO (coma en fecha)
- `"laptops"` vs `"laptop"` = FALLO (plural)

Con 5 ejemplos de test y 5 campos cada uno, un solo campo diferente cambia el score global un 4%.

**Solucion implementada:** Parametro `match_mode` en `create_dynamic_metric` (configurable via YAML):
- `exact`: Comportamiento original (default).
- `normalized`: Elimina puntuacion y normaliza espacios antes de comparar. Resuelve formato de moneda, fechas y puntuacion.
- `fuzzy`: Similitud por `SequenceMatcher` con umbral configurable (`fuzzy_threshold`). Captura near-misses como plurales.

Configuracion en YAML:
```yaml
optimization:
  match_mode: "normalized"    # o "fuzzy"
  fuzzy_threshold: 0.85       # solo aplica en modo fuzzy
```

**Leccion:** Para tareas de extraction con campos de formato variable (moneda, fechas, cantidades), usar `match_mode: "normalized"` como minimo. Reservar `exact` solo para clasificacion o campos con valores cerrados.

## 2. Datos y Complejidad de la Tarea

### El Efecto Techo (Ceiling Effect)
**Síntoma:** El modelo base obtenía 100% de efectividad en la primera prueba ("Zero-Shot").
**Causa:** Los datos eran demasiado simples e inequívocos para un modelo potente como GPT-4o-mini.
**Implicación:** GEPA no puede optimizar lo que ya es perfecto.
**Lección:**
- Para probar la eficacia de un optimizador, el problema debe ser **suficientemente difícil**.
- Se requiere crear datasets "Hard Mode" que incluyan: sarcasmo, ironía, dobles negaciones, tautologías y expectativas fallidas.

## 3. Sesgo de Idioma en LLMs (Inglés vs. Español)

**Hallazgo:** En la misma tarea de "Hard Mode" (Sarcasmo y matices):
- **Inglés:** 100% Accuracy (Test).
- **Español:** 83.33% Accuracy (Test).

**Explicación Técnica:**
1.  **Datos de Entrenamiento:** La gran mayoría del pre-entrenamiento de los LLMs es en inglés. Tienen una "intuición estadística" superior para captar sutilezas en su lengua materna.
2.  **RLHF (Alineamiento):** El ajuste fino para seguir instrucciones complejas se realiza predominantemente en inglés.
3.  **Tokenización:** Los tokenizadores suelen ser más eficientes en inglés, permitiendo al modelo captar mejor las relaciones de larga distancia (contexto) en una oración.
4.  **Matices Culturales:** El sarcasmo y la ironía varían culturalmente. Los modelos suelen aprender un "español promedio" que a veces pierde la agudeza de modismos específicos.

**Estrategias de Mitigación:**
- Usar **Few-Shot Learning** (dar ejemplos resueltos en el prompt) es más crítico en español que en inglés.
- Considerar usar modelos más grandes (ej: GPT-4o en lugar de mini) para tareas de alta sutileza en español.

## 4. Arquitectura de Configuración (Infraestructura vs. Experimento)

**Hallazgo:** Mezclar parámetros de lógica de negocio (como longitudes de texto) en archivos `.env` rompe la reproducibilidad y dificulta la experimentación en paralelo.

**Mejores Prácticas Adoptadas:**
- **.env (Infraestructura):** Reservado exclusivamente para secretos (API Keys), Endpoints de Azure/OpenAI y alias de modelos (Task vs Reflection).
- **YAML (Experimento):** Contiene toda la lógica del caso de uso, incluyendo límites de truncamiento (`max_text_length`), presupuesto de optimización (`max_metric_calls`) y configuración de adapters.

**Beneficio:** Un mismo código puede ejecutar múltiples experimentos simultáneos con parámetros lógicos distintos simplemente pasando diferentes archivos YAML, sin colisiones de variables de entorno globales.

## 5. Cache de DSPy (Baseline = Optimized)

**Problema Detectado:** Las ejecuciones mostraban `baseline_score == optimized_score` consistentemente. DSPy tiene cache activo por defecto en `~/.dspy_cache`. Si el mismo prompt+input se envia al LLM, devuelve resultado cacheado sin llamar al modelo.

**Impacto:** La evaluacion baseline y optimizada usan los mismos ejemplos de validacion. El cache devuelve los mismos resultados, impidiendo ver diferencias reales.

**Solucion Implementada:**

Atributo `cache` en `LLMConfig` (`shared/llm/config.py`) con default `False`. Se inyecta solo en `get_dspy_lm()` (no en `litellm.completion()` que no soporta el parametro como bool).

Configuracion por prioridad (mayor a menor):

| Nivel | Ubicacion | Ejemplo |
|---|---|---|
| YAML (dspy_gepa_poc) | `models.cache` | `cache: true` |
| Variable de entorno | `.env` | `LLM_CACHE=true` |
| Default en codigo | `shared/llm/config.py` | `cache: bool = False` |

Ver `docs/LLM_CONFIG.md` para referencia completa de variables de entorno.

## 6. Comparativa Directa: DSPy+GEPA vs GEPA Standalone (Email Urgency)

### Contexto

Comparacion controlada entre GEPA ejecutado via DSPy (`dspy_gepa_poc`) y GEPA puro (`gepa_standalone`) sobre la misma tarea de clasificacion de urgencia de emails. Se controlaron todas las variables para garantizar justicia en la comparacion.

**Variables controladas:**

| Variable | Standalone | DSPy |
|---|---|---|
| Modelo tarea | azure/gpt-4.1-mini | azure/gpt-4.1-mini |
| Modelo reflexion | azure/gpt-4o | azure/gpt-4o |
| Temperature | 0.1 | 0.1 |
| Budget | 50 llamadas | 50 llamadas |
| Instruccion | Identica | Identica |
| Scoring | Exact match binario | `match_mode: exact` |
| Chain-of-thought | No | No (`predictor_type: predict`) |
| Dataset | email_urgency.csv | Mismo archivo |

### Resultados (Feb 2026)

| Metrica | DSPy Zero-Shot (n=15) | DSPy Few-Shot (n=15) | Standalone (n=86) |
|---|---|---|---|
| **Baseline** | 60.0% | 80.0% | ~60.0% |
| **Optimized (media)** | **88.0%** | **87.3%** | **86.3%** |
| **Optimized (rango)** | 70-100% | 80-100% | 60-100% |
| **Optimized (SD)** | ~7.5 | ~6.8 | ~8.5 |
| **Robustness (media)** | **98.7%** | **100.0%** | **96.3%** |
| **Robustness (rango)** | 80-100% | 100% | 60-100% |
| **Mejora (pp)** | +28.0 | +7.3 | +26.3 |

### Hallazgos

**Equivalencia de rendimiento:** DSPy Zero-Shot y Standalone logran resultados practicamente identicos (88.0% vs 86.3%). La diferencia de ~1.7 pp no es estadisticamente significativa dada la variabilidad (SD ~7-8). GEPA produce los mismos resultados independientemente del framework.

**Temperature como variable critica:** Se descubrio que DSPy usaba temperature=0.7 (default de LLMConfig) mientras standalone usaba 0.1 (desde YAML). Se corrigio agregando override de temperatura en `reflexio_declarativa.py`. Sin este fix, la comparacion habria sido invalida.

**Few-shot infla baseline pero no mejora el techo:** Few-shot arranca en 80% (+20 pp sobre zero-shot) gracias a los 3 ejemplos inyectados por `LabeledFewShot`, pero el score optimizado final es el mismo (~87-88%). GEPA tiene menos margen de mejora (+7 pp vs +28 pp). Few-shot ahorra iteraciones de GEPA pero no sube el techo de rendimiento para esta tarea.

**Robustness superior en DSPy:** DSPy Few-Shot logra 100% en las 15 pruebas. DSPy Zero-Shot logra 98.7%. Standalone logra 96.3% con mas variabilidad. DSPy muestra mejor generalizacion en el test set held-out, posiblemente por la estandarizacion del formato de prompt via Signature + Adapter.

**Menor varianza en DSPy:** SD de DSPy (~7) es menor que Standalone (~8.5). DSPy produce resultados mas predecibles.

### Conclusion

La optimizacion reflexiva (GEPA) es el factor dominante en la mejora, no la infraestructura que la ejecuta. DSPy aporta ventajas operativas (configuracion YAML, modularidad, Signatures tipadas) sin sacrificar rendimiento, con una ligera ventaja en estabilidad y robustness.

### Archivos relacionados

- Configs: `dspy_gepa_poc/configs/dynamic_email_urgency.yaml`, `dynamic_email_urgency_fewshot.yaml`
- Script batch: `dspy_gepa_poc/run_email_urgency_comparison.sh`
- Dataset: `dspy_gepa_poc/datasets/email_urgency.csv`
