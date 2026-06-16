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

**Hallazgo:** gpt-5-mini no mejora con GEPA en la tarea de Email Urgency, a pesar de que gpt-4.1-mini alcanza 96-99% de robustez en la misma tarea y dataset. En el leaderboard GEPA standalone (14 runs, task `gpt-5-mini` / prof `gpt-5`) el caso da `Base 59,29 / Opt 59,29 / Rob 50,00 / Std 13,01 / delta -9,29` ("Atención"): la optimización **no aporta nada (Opt=Base) e incluso degrada la robustez**. La causa no es un bug de código ni de formato de respuesta.

**Diagnóstico:** Se verificó que el flujo técnico funciona correctamente — `apply_reasoning_constraints` eleva `max_tokens` a 16000 y temperatura a 1.0 (gpt-5 ignora la temperatura de todos modos), y el modelo devuelve respuestas de una sola palabra en el formato correcto. El problema es una **desalineación sistemática de criterios** entre los labels del dataset y el modelo: el gold etiqueta por pistas léxicas ("FYI", "recordatorio amable", "compartiendo ideas" -> `low`), mientras gpt-5-mini razona la **intención** del email (si te piden una acción, escala la urgencia).

El patrón es consistente en ambos splits: **gpt-5-mini escala la urgencia un nivel hacia arriba** en casos borderline (`low→normal`, `normal→urgent`).

Desacuerdos en `val` (análisis inicial):

| Label dataset | gpt-5-mini | Texto |
|---|---|---|
| `low` | `normal` | *Aviso: Nueva política efectiva el próximo mes* |
| `normal` | `urgent` | *FYI - Respaldo de datos falló anoche. TI investigando* |
| `low` | `normal` | *Solo revisando si tuviste tiempo de ver mi email anterior* |
| `normal` | `urgent` | *Queja de cliente escalada. Se espera respuesta en 24 horas* |

**Confirmación por dump de predicciones sobre `test` (2026-06-03).** Se corrió `gpt-5-mini` sobre los 5 emails de `test` con el prompt baseline y dos prompts ya optimizados (runs `120020` Opt=90 y `134143` Opt=60), 4 veces cada uno. Resultados:

1. **Los 3 emails con señal clara son 100% estables** (2 urgentes inequívocos + 1 normal con plazo): aciertan siempre, en todo prompt y toda corrida. El "techo" no está ahí.
2. **Todo el desacuerdo se concentra en 2 emails ambiguos, ambos con gold `low`:**

   | Email (test) | gold | gpt-5-mini razona |
   |---|---|---|
   | "Compartiendo ideas... **Avísame qué piensas**" | low | pide feedback -> acción -> `normal` |
   | "Recordatorio amable... **Confirma si asistes**" | low | pide confirmación con plazo -> `normal` |

3. **Inestabilidad de muestreo:** el mismo prompt, sobre el mismo email, **flipea entre corridas idénticas** (gpt-5 muestrea distinto aunque no exponga temperatura). La accuracy del baseline osciló 60/80/80/60 y la de cada prompt optimizado saltó entre 60 y 100 según la corrida. Esto explica directamente el `Std 13` y la `Rob 50` del leaderboard.
4. **La optimización es de suma cero:** ningún prompt acierta los 2 ambiguos a la vez de forma estable (arreglar uno tiende a romper el otro), por eso GEPA no halla mejora neta que generalice (`Opt = Base`) y el prompt sobre-especificado con reglas léxicas baja la robustez. Dato revelador: el prompt del run "Opt=60" rindió igual o mejor que el de "Opt=90" en el dump, evidenciando que esos scores históricos eran **ruido de muestreo, no calidad de prompt**.

**Contraste que cierra el diagnóstico:** el mismo `gpt-5-mini` mejora **+28 a +62 pp con Std bajo** en `CV Extraction` y `Text-to-SQL` (leaderboard GEPA), donde hay **verdad objetiva verificable** y su razonamiento se alinea. También el caso Fast Gate (extractor de dominio específico sin priors fuertes) mejora con GEPA y los mismos modelos. La diferencia no es el modelo: es la naturaleza de la tarea. `email_urgency` es la única que combina criterio subjetivo + gold definido por keywords, las dos condiciones que perjudican a un reasoning model.

**Lección:**
- Para tareas de clasificación con criterio **subjetivo/convencional** donde el modelo tiene priors fuertes (urgencia de email), GEPA no puede overridear la calibración interna del modelo vía prompt: el optimizador ve un baseline fijo e irreducible, y si los 2 casos ambiguos exigen criterios contradictorios, la optimización es de suma cero (Opt=Base, robustez a la baja).
- Este patrón no aparece en tareas con verdad objetiva (extracción estructurada, SQL, triage de dominio) donde el modelo depende del prompt y su razonamiento se alinea con un gold verificable.
- Ante delta bajo/negativo con un reasoning model, **hacer dump por ejemplo y separar casos con-señal vs ambiguos antes de culpar al modelo o al optimizador.** Si los fallos se concentran en items de gold heurístico-léxico y flipean entre corridas, es desacuerdo de criterio + inestabilidad de muestreo (no optimizable vía prompt), no incapacidad del modelo.
- Si hay desalineación, las opciones son: re-etiquetar los casos ambiguos según un criterio cerrado, preferir tareas con verdad verificable para reasoning models, o documentar la diferencia de calibración como resultado de la experimentación.

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

### Campo `case` unificado entre subproyectos

**Hallazgo:** La columna `Caso` del CSV maestro y del leaderboard salía de campos distintos en cada engine: GEPA usaba `case.title` y DSPy usaba `case.name` (que además contenía el texto largo y ensuciaba los nombres de los run dirs). Esto rompía el SSOT y dificultaba comparar.

**Criterio adoptado (SSOT en `docs/YAML_CONFIG_REFERENCE.md`):** en ambos subproyectos `case.name` es un slug corto (run dir / `experiment_name`) y `case.title` es el título semántico (columna `Caso`). Los títulos se mantienen distintos por engine para que el leaderboard combinado no mezcle ambos motores.

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

## 9. Protocolo de N seeds sobre los casos CV v2 (señal vs ruido)

Validación del protocolo de N seeds (ver `PROTOCOLO_N_SEEDS.md`) sobre los tres
casos CV con configs `_v2`: baseline congelado + `eval_repeats: 3` + una sola
intervención por caso. Cada caso se corrió con **5 seeds**. Objetivo: medir
varianza real y separar mejora de suerte, no maximizar el score de una corrida.

**Modelos:** task `gpt-5-mini`, reflection `gpt-5` (los tres casos).

### Resultados (2026-05-30, N=5 por caso)

| Caso | Baseline | Optimizado (val) | Robustez (test) | Gap val-test |
|---|---|---|---|---|
| `cv_extraction_v2` (GEPA, test=20) | 52.7 ±1.3 (σ0.42) | 79.5 ±6.0 (σ2.0) | **81.5 ±2.0 (σ0.86)** | −2.0 |
| `cv_profile_v2` (DSPy, test=8) | ~91.2 | 93.3 ±1.7 (σ0.57) | **91.2 ±4.5 (σ1.58)** | +2.0 |
| `cv_triage_v2` (DSPy, test=21) | 100 | 100 ±0 (σ0) | **97.8 ±4.8 (σ1.62)** | +2.2 |

(media ± rango, σ = desvío poblacional. Gap = media Opt − media Rob.)

### Hallazgos

**Extraction: el test ampliado vuelve fiable la medición.** Sobre test=20 la
robustez tiene rango 2 pts (σ0.86), contra los ~40 pts de rango que daba el
histórico sobre test=3. Recorrido real (52.7 → 81.5) y sin sobreajuste (gap −2,
el test rinde mejor que val). Confirma la lección del techo invertida: cuando hay
margen y la métrica es fiable, GEPA aporta de forma reproducible.

**Profile: el sobreajuste se domó, el techo persiste.** El gap val-test bajó a
+2 pts (en el histórico v1 llegaba a ~9) y las 5 corridas tienen Opt > Baseline
(en v1 varias tenían Opt < Baseline). Pero la robustez (91.2) ≈ baseline (91.2):
la ganancia de ~2 pts en val no se traslada a test. Subir umbrales fuzzy
(`industria_previa`/`educacion_principal` → 0.85) + `eval_repeats` mejoró la
**consistencia**, no el techo. El caso sigue resuelto al ~91% (ver sección 8).

**Triage: el modelo más potente sube la tarea al techo en el baseline.** Con
`gpt-5-mini` el baseline da 100% en val y GEPA no tiene nada que optimizar
(delta cero, WARN "no modificó las instructions"). La robustez 97.8% equivale a
fallar ~1 de 21 en test. Contraste directo con el histórico v1 (task
`gpt-4.1-mini`): allí el baseline era 50-75% y el optimizado oscilaba 66-100%.
El dataset v2, aunque tiene ruido de la vida real, no es lo bastante difícil para
`gpt-5-mini`: separa `fit_alto`/`fit_medio`/`no_fit` trivialmente.

### Lecciones

- **El techo se mueve con el modelo, no solo con los datos.** La misma tarea de
  triage que con `gpt-4.1-mini` tenía margen (+25 pp via GEPA, sección 8) pasa a
  saturar el baseline con `gpt-5-mini`. Antes de diseñar un experimento de
  optimización, fijar el par tarea/modelo: un dataset "difícil" para un modelo
  puede ser trivial para otro.
- **Para que triage sea un caso de optimización útil con `gpt-5-mini`** hace falta
  o casos frontera más ambiguos (alto/medio), o bajar el task model a
  `gpt-4.1-mini` para recrear headroom comparable al v1.
- **El protocolo cumple su función:** con N=5 distingue "GEPA aporta y generaliza"
  (extraction) de "no hay nada que optimizar" (triage, profile), algo que una
  corrida única no podía mostrar.

### Caveat de datos

Los datasets `cv_triage_v2.csv` (test 7/7/7) y `cv_extraction_v2.csv` (test=20)
fueron redactados por un modelo distinto a los bajo prueba (Claude) con ruido de
la vida real, y llevan la columna `gold_verificado="no"`: el gold es BORRADOR
pendiente de revisión humana. El hallazgo "triage está en techo" es robusto, pero
con baseline 100 un gold mal etiquetado podría enmascarar errores; revisar el gold
antes de cerrar conclusiones cuantitativas finas.

### Seguimiento (2026-05-31): intervenciones v2.1 sobre triage y profile

Tras la corrida N=5, se atacaron los dos casos en techo. **Cambios de setup, pendientes de re-correr el protocolo N=5 para medir efecto.**

**Triage (opcion B: recrear headroom sin bajar el modelo).** Se añadieron 15
casos FRONTERA `fit_alto`<->`fit_medio` al generador (`build_cv_v2_datasets.py`),
con ambiguedad deliberada en un solo eje: ingles B1 vs B2, 5 años exactos vs
casi-5, huso GMT-5/-6 compartido vs residencia fuera de LATAM (Miami/Houston),
Flask/Tornado/aiohttp vs Django/FastAPI, PostgreSQL ausente en perfil por lo
demas perfecto. `test` 21 -> 27 (10/10/7). El gold es defendible pero discutible
(es justo donde un humano podria diferir): su revision es PRIORITARIA antes de
confiar en la medicion. Hipotesis: bajan baseline < 100 y devuelven a GEPA algo
que optimizar. Si aun satura, queda la opcion A (task=`gpt-4.1-mini`).

**Profile (per_field + ampliar test).** `per_field_accuracy.py` sobre el run
`20260530_161740` localizo el techo: `industria_previa` 75% en val Y test
(consistente), seguido de `stack_principal` (85.5% val) y `educacion_principal`
(~88-92%). Los fallos son de DEFINICION de gold, no de modelo: `'Diseño'` vs
`'Diseño UX'` (granularidad), `'Backend'` vs `''` (disciplina mal etiquetada como
industria), `'Lic. CS'` vs `'Licenciatura CS'` (abreviatura). Confirma que el
~9% residual no es optimizable por GEPA. Ademas se amplio `test` 8 -> 18
(rebalance en `build_cv_profile.py`, `PROMOTE_TO_TEST`, sin fabricar filas) para
volver fiable la robustez, replicando la leccion de extraction (test 3->20 bajo
el rango de 40 a 2 pts). `train` 25 -> 15, `val` 12 sin cambios.

### Archivos relacionados

- Protocolo: `shared/utils/seed_protocol.py`, `docs/PROTOCOLO_N_SEEDS.md`
- Configs: `dynamic_cv_profile_v2.yaml`, `dynamic_cv_triage_v2.yaml`, `cv_extraction_v2.yaml`
- Datasets: `cv_triage_v2.csv`, `cv_extraction_v2.csv` (generados por `shared/utils/build_cv_v2_datasets.py`); `cv_profile.csv` (generado por `dspy_gepa_poc/scripts/build_cv_profile.py`)

## 10. Comparar DSPy vs GEPA de forma justa (baseline confound y scoring SSOT)

### El confound: baselines absolutos no son comparables entre frameworks

El caso DSPy `cv_profile_v3` mostraba un baseline mucho mas alto que el caso GEPA
`cv_extraction_v3`. Eso NO era senal de que un framework extraiga mejor: era un
artefacto de medicion. El profile DSPy parte con tres ventajas que GEPA no tenia:

1. **Descripcion por campo** en la signature (formato, valores permitidos, reglas
   anti-error como "sin honorificos", "no inferir ubicacion del email"). El seed
   GEPA (`cv_extraction_v1.json`) solo listaba nombres de campo.
2. **Metrica tolerante por campo** (`field_configs`): `set` para skills/idiomas
   (orden y duplicados no penalizan), `fuzzy` para educacion/ubicacion/industria.
   GEPA puntuaba todo con igualdad exacta (`strip().lower()` + `==`).
3. **`ignore_in_metric`** (no cuenta `seniority_declarado`) y **few-shot**.

Leccion: **comparar baselines crudos entre frameworks es invalido salvo que
prompt + metrica + datos esten igualados.** O se igualan las condiciones, o se
compara el **delta** (baseline -> optimizado), no el valor absoluto.

### Dos formas de igualar, ambas materializadas (2026-05-31)

- **Bajar DSPy a las condiciones de GEPA** (austero): `dynamic_cv_extraction_v3.yaml`
  — 5 campos, prompt pobre sin desc, `match_mode: exact`, sin `ignore_in_metric`,
  sin few-shot, 40 metric_calls. Mismo CSV que GEPA (`cv_extraction_v3.csv`, copiado).
- **Subir GEPA a las condiciones de DSPy** (enriquecido): `cv_profile_v3.yaml` del
  lado GEPA — 10 campos, seed con descripcion por campo (`cv_profile_v3.json`),
  `field_configs` set/fuzzy/normalized, `ignore_in_metric: [seniority]`, few-shot=2.
  Mismo CSV que DSPy (`cv_profile_v3.csv`, copiado).

### El scoring pasó a ser SSOT en shared/ (requisito de la igualación)

Igualar GEPA hacia arriba exigia que el extractor puntuara como DSPy. La logica
vivia solo en `dspy_gepa_poc/metrics.py`, y GEPA **no puede importar de
`dspy_gepa_poc`** (invariante de paquetes hermanos). Solucion: extraer los
primitivos (`score_field`, `score_set`, `compare_*`, `normalize_text`,
`tokenize_list`) a `shared/scoring/field_match.py`. Ahora DSPy y el
`SimpleExtractorAdapter` puntuan con el **mismo objeto**, sin duplicacion ni
riesgo de divergencia. El refactor fue comportamiento-identico (tests previos sin
tocar) y se hizo en dos fases con verificacion verde intermedia.

### Cambio de comportamiento deliberado en el extractor GEPA

Se quito el guard `field_name in extracted_fields` del extractor: GEPA antes
penalizaba un campo ausente aunque el gold fuera vacio; DSPy nunca lo hace
(`getattr(pred, field, "")`). Alinearlos **desplaza levemente los numeros del
`cv_extraction_v3` GEPA ya corrido** (mas leniente solo cuando gold vacio + campo
ausente). Es el precio de la equivalencia y queda registrado para no confundirlo
con un cambio de modelo.

### Archivos relacionados

- Scoring SSOT: `shared/scoring/field_match.py`, `tests/test_scoring_shared.py`
- DSPy austero: `dspy_gepa_poc/configs/dynamic_cv_extraction_v3.yaml`, `dspy_gepa_poc/datasets/cv_extraction_v3.csv`
- GEPA enriquecido: `gepa_standalone/experiments/configs/cv_profile_v3.yaml`, `gepa_standalone/experiments/prompts/cv_profile_v3.json`, `gepa_standalone/experiments/datasets/cv_profile_v3.csv`
- Extractor con `field_configs`: `gepa_standalone/adapters/simple_extractor_adapter.py`, `tests/test_gepa_adapters.py` (clase `TestExtractorFieldConfigs`)

## 11. Fast Gate (flujo-intents): GEPA overfittea VAL chico en clasificación 4-clases

**Tipo y características del caso (importante para no sobre-generalizar).** Esto NO
es un benchmark de clasificación cualquiera; las conclusiones de abajo aplican a
tareas con este perfil concreto:
- **Tarea:** clasificación **ordinal de severidad de riesgo en 4 niveles**
  (Verde < Amarillo < Rojo < Negro) — etapa Fast Gate de `flujo-intents`, gobierno
  de IA. No es multiclase plana: las clases tienen orden y los errores "de un nivel"
  no son equivalentes (sub-escalar el tope Negro es el error caro).
- **Frontera y criterios (matizado 2026-06-16):** la regla del Marco es en realidad
  **objetiva** — contar 5 preguntas Sí/No (0-1 Verde / 2-3 Amarillo / 4-5 Rojo) y
  Negro = P5=Sí + alto impacto. Por decisión de diseño NO se puso en el prompt: se
  **optó** por que el sistema infiera el color de los casos (few-shot), sin enunciar
  el conteo. El único criterio subjetivo es "alto impacto" (escala, irreversibilidad,
  naturaleza financiera/restrictiva, perfilado) para el tope Negro — el límite difuso
  donde el modelo "razona de más". Veredicto al cierre de la sección: inferir la
  regla de los casos no se verifica en la práctica → se adopta la regla explícita.
- **Datos chicos y balanceados a mano:** 30 train / 16 val / 30 test, few-shot rico
  (`LabeledFewShot k=8`, demos con razonamiento). VAL = 16 ejemplos: clave, porque
  es lo que GEPA puede sobreajustar.
- **Holdout fijo** (30 originales `TC`, nunca tocados) → las comparaciones son sobre
  el mismo set, no sobre folds variables.

Bajo otro perfil (muchos datos de VAL, clases planas, frontera explícita) estas
conclusiones podrían NO valer; ver la tabla de la sección 8.

**Error dominante de partida.** Confusión Negro<->Rojo (~63% de todos los errores de
`clasificacion` en TEST; "Hallazgo 5"). Modelos de la serie base: Task LM
`azure/gpt-4.1-mini`, Reflection LM (GEPA) `azure/gpt-4o`, ambos temp 0.1, cache off.

**Qué se probó (4 experimentos, todos sobre el mismo holdout fijo de 30).**

| Intervención | TEST acc | Negro->Rojo |
|---|---|---|
| Baseline rico_v1 (sin revisión) | 70,0% | 13 |
| Dataset round-1 (4 casos "moderador" Rojo + 1 Negro por escala) | 73,3% | 12 |
| Round-1 + prompt pilot (distinción Negro/Rojo manual) | 75,6% | 12 |
| Round-2 (4 casos Negro con criterios a-e explícitos) + prompt pilot | 71,1% | 11 |

Ni el enfoque por casos (reescribir train para enseñar la distinción) ni el prompt
manual movieron Negro->Rojo más allá del ruido (13 -> 11 en 4 iteraciones).

**El hallazgo real: GEPA estaba degradando la tarea.** En las 3 corridas GEPA del
prompt pilot, la mejor en TEST (76,7%) fue la única en la que **GEPA dejó el prompt
idéntico al base** (`optimized_program.json` byte-idéntico al YAML; verificado por
hash). Las dos en que GEPA expandió el prompt (a 6,5k y 6,9k chars) fueron las peores
(66,7% y 70,0%). Las tres llevaron VAL a 100%/93,8%. Confirmado con N=5 del prompt
base **sin GEPA** (`baseline_only.py`): TEST media 75,3%, mediana/moda 76,7% (23/30 en
4 de 5), rango 70,0-76,7. El 76,7% es el punto de operación estable; GEPA solo lo
iguala (cuando no toca el prompt) o lo degrada (cuando lo toca).

**Lección.**
- **Con VAL chico (~16 ejemplos) en clasificación de pocas clases, GEPA sobreajusta
  el val set y puede degradar el holdout.** El reflection_lm encuentra reglas que
  suben VAL a 100% y no generalizan. Verificar SIEMPRE si el `optimized_program` real
  cambió el prompt (hash contra el YAML base): si la mejor corrida es la que NO lo
  cambió, GEPA no está aportando — está restando.
- **Antes de iterar dataset/prompt, medir el prompt base + few-shot SIN GEPA con N
  seeds** (`baseline_only.py`). Si iguala o supera a las corridas GEPA, la config de
  producción es esa, sin optimización.
- **No todo error de clasificación se cierra con datos.** Negro->Rojo persistió en
  ~3/corrida en el punto estable: es un techo del modelo (`gpt-4.1-mini`) en una
  distinción que depende de matices de "alto impacto", no de volumen ni de framing.
  El siguiente paso correcto (CORRECCIÓN 2026-06-16) no es "probar modelos más
  capaces" sino **implementar la regla explícita del Marco** (conteo de 5 preguntas
  + default de P3 + Negro), que es lo que el prompt nunca tuvo. Ver veredicto.
- Complementa la tabla de la sección 8 ("Cuándo GEPA aporta vs cuándo no"): aun en
  clasificación con razonamiento, si el VAL es chico GEPA puede no aportar.

**Prueba multi-modelo: el modelo "más capaz" empeora.** Se repitió toda la serie
cambiando solo el Task LM a `azure/gpt-5-mini` (reasoning) / Reflection LM
`azure/gpt-5`. Mismo holdout, mismo prompt pilot:

| Config | TEST |
|---|---|
| gpt-4.1-mini, sin GEPA (N=5) | **75,3%** (mediana 76,7%) |
| gpt-4.1-mini + GEPA (n=3) | 71,1% |
| gpt-5-mini, sin GEPA (N=5) | 62,7% (mediana 63,3%) |
| gpt-5-mini + GEPA (n=3) | 58,9% |

`gpt-5-mini` queda ~12-13 pp por debajo en ambas condiciones, sin solapamiento de
rangos (no es ruido). Y **cambia el modo de fallo**: con gpt-4.1-mini el error era
casi monotemático Negro->Rojo (sub-escalar el tope); con gpt-5-mini aparece
**sobre-escalación sistemática de abajo** (Verde->Amarillo salta de 3 a 12,
Amarillo->Rojo de 6 a 10 sobre 90 TEST), contando 24 errores de sobre-escalar vs 13
de sub-escalar. El reasoning model razona de más sobre los criterios de impacto y se
vuelve risk-averse, pero sigue sub-escalando el tope (Negro->Rojo se mantiene en 12).

Lecciones adicionales:
- **Un modelo más grande/razonador no es estrictamente mejor en clasificación
  calibrada.** Acá empeora la accuracy Y degrada la calibración (sobre-escalación).
  Evaluar siempre en el holdout antes de "subir de modelo".
- **El que GEPA degrade se sostiene con modelo distinto** (4.1-mini 75,3->71,1;
  5-mini 62,7->58,9): la degradación es del régimen (VAL=16 ejemplos), no del modelo.
- Config recomendada de producción para fast_gate: **gpt-4.1-mini + prompt pilot +
  few-shot rico, SIN GEPA** (76,7% mediana, la mejor de toda la investigación)
  — pero ver la validación externa de abajo, que matiza este "mejor".

**Validación externa con casos testigo (rompe la circularidad train/val<->criterios).**
El holdout interno (los 30 `TC`) es de autoría propia y comparte procedencia con la
rúbrica de criterios → validar solo con él es circular. Se construyó un set de 14
**casos testigo** etiquetados con un marco INDEPENDIENTE: EU AI Act (Art. 5
prohibido; Anexo III alto riesgo) anclado a reguladores AR (BCRA, ENACOM, AAIP/Ley
25.326, SSN). Regla de mapeo graduada por impacto para la frontera Rojo/Amarillo de
"alto riesgo de dominio + revisión humana" (Rojo si financiero/sensible/esencial/
masivo; Amarillo si acotado y reversible). Resultado del programa base (sin GEPA):

| Modelo | Holdout interno | **Testigo externo** |
|---|---|---|
| gpt-4.1-mini | 76,7% (el mejor) | **71,4%** (10/14) |
| gpt-5-mini | 62,7% | **92,9%** (13/14) |

Hallazgos que NO aparecían internamente:
1. **Reversal in/out-of-distribution.** gpt-4.1-mini, el mejor en el holdout, es el
   **peor** en casos externos; gpt-5-mini se da vuelta. El holdout interno
   **sobreestimaba** al modelo chico. En producción las entradas son novedosas → la
   métrica relevante es la externa, donde el reasoning model generaliza mejor.
2. **Error externo dominante: Rojo->Amarillo** (gpt-4.1-mini sub-escala crédito,
   seguros con datos de salud y beneficios esenciales). **Causa real (corregida
   2026-06-16, ver veredicto):** NO es un gap de dataset por "dominio regulado". Es
   que el prompt no implementa el conteo del Marco y, sobre todo, la **P3 tiene el
   default invertido**: cuando la ficha no menciona proveedor, el modelo responde
   P3=No (homologado), pierde un "sí" y el caso baja de 4 a 3 síes -> Rojo se vuelve
   Amarillo. Reproducido a mano sobre W-06/W-08 (4 síes con P3 default Sí = Rojo).
3. **Los 5 Negro (incl. prohibidos Art. 5) perfectos en ambos** → el Negro->Rojo del
   holdout interno es sobre casos internos sutiles, no una ceguera general al tope.
4. **Gap de SPEC (reformulado 2026-06-16):** era cierto que la regla del Marco no
   estaba en el prompt (se optó por inferirla). Como inferirla no funciona, la deuda
   D-013 pasa a ser **implementar la regla explícita del Marco** (conteo de las 5
   preguntas + default de P3 + regla de Negro) vía la arquitectura determinística.

Lección transversal: **el holdout in-distribution puede mentir.** Un set testigo
etiquetado con un marco externo es barato (14 casos, una llamada LLM c/u) y expone
gaps de generalización y de spec invisibles internamente — y puede invertir el
ranking de modelos.

**VEREDICTO (2026-06-16): la causa raíz no era la del diagnóstico inicial.** Al
contrastar con la regla canónica del Marco (Fast Gate de 5 preguntas Sí/No; contar
los síes: 0-1 Verde / 2-3 Amarillo / 4-5 Rojo; Negro = P5=Sí + alto impacto):
- El diagnóstico "gap de dataset por dominio regulado" (Hallazgo 2) era **erróneo**.
  El witness está bien etiquetado y es consistente con el conteo.
- La causa real es el **prompt**: (i) pide *deducir* el color en vez de **contar**
  P1..P5 y aplicar umbrales, y (ii) la **P3** ("¿usa herramientas/proveedores fuera
  del catálogo aprobado?") tiene el **default invertido** — sin dato de homologación
  el modelo asume P3=No y pierde un "sí", bajando Rojo (4) a Amarillo (3). Default
  correcto: intent nuevo -> se propondrá homologado (P3=No); sistema ya implementado
  -> probablemente no (P3=Sí).
- El camino "que el sistema infiera la regla de los casos" (decisión de diseño
  registrada arriba) **no se verifica en la práctica**.
- **Rumbo adoptado: arquitectura determinística (A).** El LLM responde solo P1..P5
  (Sí/No) + un juicio de "alto impacto"; una función pura cuenta y deriva el color.
  Convierte la tarea en 5 binarios + cálculo fijo (auditable, fiel al Marco). Plan en
  `historial/sdd.md` (D-013) y `specs/SPEC-102-flujo-intents.md`.

### Archivos relacionados

- Config (prompt pilot, sin GEPA en producción): `dspy_gepa_poc/configs/flujo_intents_fast_gate_fewshot_rico_prompt_v1.yaml`
- Dataset y generador: `dspy_gepa_poc/datasets/flujo_intents_fast_gate.csv`, `dspy_gepa_poc/flujo_intents/make_variations.py`
- Set testigo externo (AI Act + AR) y su builder: `dspy_gepa_poc/datasets/flujo_intents_fast_gate_witness.csv`, `dspy_gepa_poc/scripts/build_witness.py`
- Scripts: `dspy_gepa_poc/scripts/baseline_only.py` (eval sin GEPA, N seeds), `dspy_gepa_poc/scripts/per_field_accuracy.py` (matriz de confusión), `dspy_gepa_poc/scripts/witness_eval.py` (eval testigo fuera de distribución)
- Registro de fases: `historial/sdd.md` (2026-06-15/16, Hallazgo 5 y validación externa)
