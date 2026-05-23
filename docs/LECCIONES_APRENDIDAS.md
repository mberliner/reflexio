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

### Resumen: Métrica por Tipo de Adapter

La métrica define qué puede aprender GEPA. Cada adapter built-in elige una estrategia acorde a la naturaleza de su salida — esta tabla resume las decisiones tomadas en `gepa_standalone`:

| Adapter      | Métrica de scoring                          | Resuelve                                            | Riesgo si se usara match exacto |
|--------------|---------------------------------------------|-----------------------------------------------------|---------------------------------|
| `classifier` | Match exacto contra `valid_classes`         | Etiquetas de un set cerrado                         | Ninguno (es la opción correcta) |
| `extractor`  | Score parcial por campo correcto            | N campos con formato heterogéneo (monedas, fechas)  | Falsos negativos por puntuación/plurales (ver arriba) |
| `sql`        | Ejecutar SQL y comparar tablas resultado    | Queries equivalentes con sintaxis distinta          | Penalizar SQL semánticamente correcto |
| `rag`        | LLM-as-Judge (precisión + fundamentación)   | Texto libre, alucinación, fidelidad al contexto     | Imposible: ninguna respuesta libre matchea exacto |

**Lección general:** antes de elegir un adapter built-in o crear uno nuevo, identificá qué señal necesita ver el optimizador para mejorar. Si tu score solo da 0/1, GEPA tiene poco gradiente. Si tu score es continuo y refleja la calidad parcial, la optimización converge mucho más rápido.

## 2. Datos y Complejidad de la Tarea

### Calibración de Urgencia en Modelos Reasoning (gpt-5-mini)

**Hallazgo:** gpt-5-mini no mejora con GEPA en la tarea de Email Urgency, a pesar de que gpt-4.1-mini alcanza 96% de robustez en la misma tarea y dataset. La causa no es un bug de código ni de formato de respuesta.

**Diagnóstico:** Se verificó que el flujo técnico funciona correctamente — `apply_reasoning_constraints` eleva `max_tokens` a 16000 y temperatura a 1.0, el modelo devuelve respuestas de una sola palabra en el formato correcto. El problema es una **desalineación sistemática de criterios** entre los labels del dataset y el modelo.

Los 4 ejemplos donde gpt-5-mini difiere consistentemente:

| Label dataset | gpt-5-mini | Texto |
|---|---|---|
| `low` | `normal` | *Aviso: Nueva política efectiva el próximo mes* |
| `normal` | `urgent` | *FYI - Respaldo de datos falló anoche. TI investigando* |
| `low` | `normal` | *Solo revisando si tuviste tiempo de ver mi email anterior* |
| `normal` | `urgent` | *Queja de cliente escalada. Se espera respuesta en 24 horas* |

El patrón es consistente: **gpt-5-mini escala la urgencia un nivel hacia arriba** en casos borderline (`low→normal`, `normal→urgent`). Con solo 10 ejemplos en val y 4 desacuerdos el baseline queda fijo en 0.6, que GEPA no logra superar independientemente del prompt generado. En contraste, el caso Fast Gate (extractor de dominio específico sin priors fuertes del modelo) sí mejora sustancialmente con GEPA y los mismos modelos.

**Lección:**
- Para tareas de clasificación donde el modelo tiene **priors de entrenamiento fuertes** (como urgencia de email), GEPA no puede overridear la calibración interna del modelo via prompt. El optimizador ve un baseline fijo e irreducible.
- Este patrón no aparece en tareas de dominio específico (triage médico, extracción estructurada) donde el modelo no tiene priors propios y depende del prompt para guiar su razonamiento.
- Antes de interpretar un baseline estancado como fallo del optimizador, verificar si el modelo y el dataset comparten los mismos criterios de clasificación para los casos borderline.
- Si hay desalineación, las opciones son: re-etiquetar los casos ambiguos según el criterio del modelo, o documentar la diferencia de calibración como resultado de la experimentación.

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

## 7. Flujos Simples vs. Multietapa (Multi-stage)

**Hallazgo:** Pasar de un prompt único a un flujo de varias capas (ej: Clasificación -> Respuesta) cambia fundamentalmente la dinámica de optimización y el costo operativo.

### Comparativa Conceptual

| Característica | Capa Única (Single) | Multietapa (Multi-stage) | Condicional (Conditional) |
|---|---|---|---|
| **Estructura** | Un solo prompt | Cadena de prompts | Árbol de decisión |
| **Optimización** | Local (Mejora el texto) | Global (Optimiza la cadena) | Eficiente (Optimiza ramas) |
| **Costo Token** | Bajo (1 llamada) | Alto (N llamadas) | Variable (1 a N llamadas) |
| **Precisión** | Media (Riesgo de "olvido") | Alta (Enfoque específico) | Máxima (Especialización) |

### Lecciones sobre Flujos Complejos

1.  **Métrica Unificada:** Para comparar un flujo multietapa contra uno simple en las estadísticas globales, se debe definir una métrica de "éxito final" del flujo completo. Si una etapa intermedia falla, el flujo se considera fallido.
2.  **Propagación de Errores:** En un flujo multietapa, un error en la Capa 1 (ej: mala clasificación) se amplifica en la Capa 2. Por ello, la Capa 1 debe ser la más robusta (usar `ChainOfThought`).
3.  **Análisis de ROI Crítico:** Los flujos multietapa consumen significativamente más tokens. El Leaderboard debe usarse para verificar si el incremento en Accuracy justifica el múltiplo de costo (ej: ¿vale la pena pagar 3x tokens por un +5% de precisión?).
4.  **Lógica Condicional como Optimizador:** Implementar lógica condicional no solo mejora la calidad, sino que es una herramienta de ahorro de costos. Permite derivar casos simples a modelos baratos y reservar los flujos complejos para casos críticos.
5.  **Segmentar para optimizar honestamente:** Optimizar dos funciones con una sola métrica unificada hace que GEPA proponga prompts de compromiso y que el gate estructural contamine el baseline (los casos que no avanzan rellenan campos "gratis"). El caso unificado de intake se discontinuó por esto y se segmentó en `triage_v1` + `fast_gate_v1`. Ver `FAST_GATE_SEGMENTACION.md`.

### Archivos relacionados

- Configs: `dspy_gepa_poc/configs/dynamic_email_urgency.yaml`, `dynamic_email_urgency_fewshot.yaml`
- Script batch: `dspy_gepa_poc/run_email_urgency_comparison.sh`
- Dataset: `dspy_gepa_poc/datasets/email_urgency.csv`

## 8. CV Profile Extraction: historia completa de diagnóstico y techo

Caso de estudio longitudinal sobre `cv_profile` (45 CVs, 10 campos, español). Documentado en tres fases sucesivas; cada fase reveló una capa distinta de problemas.

**Modelo:** `gpt-4.1-mini` (task) + `gpt-4o` (reflection). Budget: 50 llamadas, `auto_budget: heavy`.

### Fase 1 — Métrica ciega: GEPA sin diagnóstico por campo

**Síntoma:** Delta ≈ 0 en 15+ corridas consecutivas con baseline ~80-82%.

**Causa:** `create_dynamic_metric` devolvía solo un float. GEPA recibía un número sin saber qué campos fallaban — las mutaciones de instrucción eran ciegas.

**Fix (commit `48492b3`, 2026-05-17):** Reemplazar por `create_dynamic_metric_with_feedback`, que devuelve `{"score": float, "feedback": "diagnóstico campo a campo"}` cuando GEPA lo solicita. Baseline subió a ~91%, pero el delta siguió siendo marginal — indicando que había un segundo problema.

### Fase 2 — Descripciones de campos ambiguas

**Síntoma:** Con métrica granular, GEPA recibía buen feedback pero las mutaciones de instrucción no mejoraban campos específicos. `per_field_accuracy.py` reveló:

| Campo | Val avg | Tipo de error |
|---|---|---|
| `industria_previa` | 41.7% | Inconsistencia de anotación val vs test (41% vs 87%) |
| `stack_principal` | 82.8% | Modelo filtraba solo tech, ignoraba habilidades funcionales |
| `ubicacion` | 100% val / 75% test | Modelo infería desde dominio de email u origen histórico |
| `nombre` | 100% val / 87% test | Modelo incluía honoríficos ("La Dra. Elena Petrov") |

**Causa raíz:** GEPA optimiza la instrucción general pero **no reescribe las descripciones de los campos individuales**. El modelo interpretaba razonablemente las descripciones vigentes — pero de forma distinta al ground truth.

**Fixes aplicados al YAML (2026-05-18):** Reescritura de las descripciones de `nombre`, `stack_principal` y `ubicacion`; `industria_previa` → `ignore_in_metric` (inconsistencia > 20pp entre splits); `educacion_principal` threshold 0.85 → 0.80.

**Resultado:** Baseline subió de ~90.5% a ~93.5% y el test pasó de 86-90% a **95-97%** (+7pp) solo con las descripciones corregidas.

**Señales de que el problema es la descripción (no el modelo ni el budget):**
- El error del campo es consistente y predecible (siempre el mismo tipo de fallo)
- Aumentar budget no mejora ese campo específico
- El modelo "tiene razón" según una lectura literal de la descripción actual

### Fase 3 — Re-habilitación de campos y techo estructural

**Contexto (2026-05-19):** Se re-habilitaron todos los campos en la métrica y se completaron los valores de `industria_previa` en el dataset. El baseline regresó a ~88% y 3+ corridas con GEPA no mejoraron la robustez (test). Nuevo ciclo de diagnóstico.

**Fuentes de variabilidad identificadas y resueltas:**

| Problema | Fix |
|---|---|
| Bug en `_tokenize_list`: tokens multi-palabra sin `:` truncados (`Vue.js` → `vue`, `Ruby on Rails` → `ruby`) | `metrics.py`: usar `norm` completo en lugar de `norm.split(" ")[0]` |
| 4 filas de train con `industria_previa` vacía vs val/test 100% completos | Completados los 4 valores en train |
| `seniority_declarado`: 48% completo en train vs 25% en val/test | Agregado a `ignore_in_metric` |
| GT incorrecto: `'Biotech'` (CV dice "Bioinformática"), `'Cloud Computing'` (CV dice "Arquitecto Cloud") | Corregidos en CSV |
| GT de `educacion_principal` incluía bootcamp que el modelo correctamente omitía | Eliminado bootcamp del GT |
| Thresholds fuzzy demasiado estrictos (0.85) para variantes semánticas | `industria_previa` → 0.70, `educacion_principal` → 0.75 |

**Impacto acumulado (baseline sin optimización):**

| Estado | Val | Test |
|---|---|---|
| Pre fase 2 | ~81% | ~80% |
| Post fase 2 (descripciones) | ~93.5% | ~95-97% |
| Post re-habilitación (regresión) | ~88% | ~93% |
| Post fase 3 (datos + métrica) | **~91%** | **~93%** |

**Resultado final:** GEPA con baseline ~91% produce delta ≈ 0 en 3+ corridas. Los errores residuales son ambigüedad genuina de ground truth:

| Campo | Esperado | Obtenido | Naturaleza |
|---|---|---|---|
| `industria_previa` | `'Ventas B2B'` | `'Software B2B'` | Interpretación del CV genuinamente ambigua |
| `industria_previa` | `'Gestión de Proyectos'` | `'Project Management'` | CV mixto EN/ES → modelo responde en inglés |
| `ubicacion` | `''` | `'Berlín, Alemania'` | "Originally from Berlin" — inferencia plausible |
| `años_experiencia` | `'7'` | `''` | CV con años por periodos ("4a + 3a") — modelo no suma |

### Contraste: triage de candidatos (cv_triage)

Mismo dataset, tarea distinta: clasificar fit de candidato (`fit_alto` / `fit_medio` / `no_fit`) contra una JD fija de Backend Senior Python LATAM.

| Métrica | Baseline | Optimizado | Δ |
|---|---|---|---|
| Val (12 ejemplos) | 58.33% | **83.33%** | **+25 pp** |
| Test (8 ejemplos) | 87.50% | 87.50% | 0 |

GEPA convirtió una instrucción de ~600 chars en un prompt de ~3000 chars con criterios por categoría, factores de contexto y reglas operativas. Internalizó la JD completa dentro de la instrucción.

**Por qué funcionó aquí y no en extracción:**
- La tarea requiere razonamiento multi-criterio con trade-offs, no extracción literal
- El baseline modesto (58%) dejaba margen real
- La métrica exact sobre clases enumeradas era una señal honesta y sin ruido

**Trade-off:** El prompt optimizado memorizó los detalles de una JD espec��fica. Para multi-JD hay que re-optimizar o parametrizar la JD.

### Cuándo GEPA aporta vs cuándo no

| Tipo de tarea | GEPA aporta | Por qué |
|---|---|---|
| Extracción de campos canónicos con modelos frontera | No | El baseline ya satura; no hay gradiente |
| Extracción con campos ambiguos o modelos más débiles | Sí | Hay margen estructural |
| Clasificación multi-criterio con razonamiento | **Sí** | El prompt debe articular criterios tácitos |
| Pipelines compuestos (extracción → razonamiento) | Solo en la etapa de razonamiento | Cada etapa tiene su propio techo |

**Regla práctica:** Si el baseline en extracción está > 80%, probablemente no haya espacio para GEPA. Si la tarea requiere razonamiento o el baseline está < 70%, vale la pena.

### Cómo subir la robustez cuando GEPA ya no aporta

Las palancas restantes son data-centric o de instrucción específica — no de optimización:

1. **Ontología cerrada para campos de texto libre** (`industria_previa` tiene 27 valores únicos para 45 ejemplos). Definir 10-12 categorías canónicas en la descripción del campo y re-etiquetar. Impacto esperado: +5-8pp en ese campo.
2. **Few-shot fijos** que cubran edge cases conocidos: CV con años divididos en periodos, CVs en inglés con output esperado en español, CVs con "Originally from X" y ubicación vacía.
3. **Ampliar el test set** de 8 a 15-20 ejemplos. Con 8 ejemplos, 1 error = 1.25pp de varianza inevitable.
4. **Descripción de `años_experiencia`** con instrucción explícita de sumar periodos.

### Proceso diagnóstico ante delta plano en extracción multi-campo

```
1. Correr per_field_accuracy.py sobre el run más reciente
2. Para cada campo con avg < 85%: clasificar el tipo de error
   a. Error sistemático y predecible → reescribir la descripción del campo en el YAML
   b. Val y test difieren > 20pp en un campo → ignore_in_metric (inconsistencia de GT)
   c. GT incorrecto vs lo que el modelo extrae correctamente → corregir el GT
   d. Threshold rechaza variantes semánticamente equivalentes → bajar threshold
3. Relanzar con budget moderado (50) para verificar
4. Si el error está distribuido uniformemente y el baseline > 85% → techo estructural;
   GEPA no puede ayudar más; invertir en datos, no en optimización
```

### Archivos relacionados

- Configs: `dspy_gepa_poc/configs/dynamic_cv_profile.yaml`, `dynamic_cv_triage.yaml`
- Datasets: `dspy_gepa_poc/datasets/cv_profile.csv` (45 filas), `cv_triage.csv`
- Scripts: `dspy_gepa_poc/scripts/per_field_accuracy.py`, `baseline_only.py`, `build_cv_profile.py`
