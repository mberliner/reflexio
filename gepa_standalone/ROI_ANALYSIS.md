# Análisis de ROI - Optimización GEPA

## Resumen Ejecutivo

Este análisis demuestra el retorno de inversión económico de usar GEPA para optimizar prompts con la estrategia **Profesor-estudiante** (modelo caro para optimizar, modelo barato para producción).

## Presupuesto Gastado en Experimentación

### Total Invertido: $82.91 en 245 experimentos

| Caso | Experimentos | Costo Total | Costo/Exp | % del Total |
|------|-------------|-------------|-----------|-------------|
| **Text-to-SQL** | 75 | $47.98 | $0.64 | 57.9% |
| **CV Extraction** | 82 | $22.52 | $0.27 | 27.2% |
| **Email Urgency** | 77 | $8.58 | $0.11 | 10.3% |
| **RAG Optimization** | 11 | $3.82 | $0.35 | 4.6% |

### Desglose por Combinación de Modelos

**Text-to-SQL (max_metric_calls: 150):**
- GPT-4o + GPT-4o: 22 exp × $1.20 = $26.40 (55%)
- GPT-4.1-mini + GPT-4o: 32 exp × $0.49 = $15.84 (33%)
- GPT-4o-mini + GPT-4o: 10 exp × $0.49 = $4.95 (10%)
- GPT-4.1-mini + GPT-4.1-mini: 11 exp × $0.07 = $0.79 (2%)

**CV Extraction (max_metric_calls: 40):**
- GPT-4o + GPT-4o: 22 exp × $0.52 = $11.44 (51%)
- GPT-4.1-mini + GPT-4o: 39 exp × $0.22 = $8.55 (38%)
- GPT-4o-mini + GPT-4o: 10 exp × $0.22 = $2.19 (10%)
- GPT-4.1-mini + GPT-4.1-mini: 11 exp × $0.03 = $0.34 (2%)

**Email Urgency (max_metric_calls: 50):**
- GPT-4o + GPT-4o: 22 exp × $0.21 = $4.54 (53%)
- GPT-4.1-mini + GPT-4o: 33 exp × $0.09 = $2.93 (34%)
- GPT-4o-mini + GPT-4o: 11 exp × $0.09 = $0.98 (11%)
- GPT-4.1-mini + GPT-4.1-mini: 11 exp × $0.01 = $0.14 (2%)

**RAG Optimization (max_metric_calls: 60):**
- GPT-4.1-mini + GPT-4o: 11 exp × $0.35 = $3.82 (100%)

### Insight Clave

**La combinación GPT-4o + GPT-4o representa ~50-55% del costo total**, pero NO genera ROI en producción (mismo modelo optimizado y ejecutor = solo mejora calidad, no reduce costo).

**Los experimentos eficientes (Profesor GPT-4o + estudiante mini) representan ~34-38% del costo**, pero son los que generan ROI masivo en producción.

---

## ROI en Producción

### Estrategia Óptima: Profesor GPT-4o + estudiante GPT-4o-mini

| Caso | Costo Optimización | Punto Equilibrio | ROI @ 10k llamadas | ROI @ 100k llamadas |
|------|-------------------|------------------|-------------------|---------------------|
| **Email Urgency** | $0.09 | 75 llamadas | 13,139% | 132,294% |
| **CV Extraction** | $0.22 | 58 llamadas | 17,053% | 171,432% |
| **Text-to-SQL** | $0.49 | 210 llamadas | 4,647% | 47,374% |
| **RAG Optimization** | $0.35 | 82 llamadas | 12,076% | 121,661% |

### Interpretación

**Punto de Equilibrio Promedio: 106 llamadas**

Después de aproximadamente **100 llamadas en producción**, GEPA ya recuperó su inversión. Cada llamada adicional es ahorro puro.

**Ejemplo Concreto (CV Extraction @ 10,000 llamadas/mes):**

```
Sin GEPA (solo GPT-4o):
  10,000 llamadas × $0.004 = $40.00/mes

Con GEPA (GPT-4o-mini + optimización):
  Costo inicial: $0.22 (una sola vez)
  10,000 llamadas × $0.00024 = $2.40/mes
  Total primer mes: $2.62

Ahorro mensual (después del 1er mes): $37.60
Ahorro anual: $451.20
ROI primer mes: 1,424%
```

---

## Casos de Uso por Volumen

### Startups / Prototipos (< 1,000 llamadas/mes)
- **Recomendación:** GEPA sigue siendo rentable
- **ROI esperado:** 374% - 1,615%
- **Ahorro mensual:** $1 - $4
- **Beneficio adicional:** Mejora de calidad en las respuestas

### Empresas Medianas (1,000 - 10,000 llamadas/mes)
- **Recomendación:** GEPA es altamente rentable
- **ROI esperado:** 4,647% - 17,053%
- **Ahorro mensual:** $11 - $37
- **Recuperación:** En la primera semana

### Empresas Grandes (> 10,000 llamadas/mes)
- **Recomendación:** GEPA es crítico para control de costos
- **ROI esperado:** 47,374% - 171,432%
- **Ahorro mensual:** $117 - $375 (por cada 100k llamadas)
- **Recuperación:** En las primeras horas

---

## Por Qué Funciona: Diferencial de Precios

### Azure OpenAI Pricing (USD por 1M tokens)

| Modelo | Input | Output | Costo por llamada promedio* |
|--------|-------|--------|---------------------------|
| **GPT-4o** | $2.50 | $10.00 | $0.0025 - $0.0040 |
| **GPT-4o-mini** | $0.15 | $0.60 | $0.00015 - $0.00024 |
| **Diferencial** | **94%** | **94%** | **~16x más barato** |

*Basado en 300-800 tokens input, 50-300 tokens output según caso de uso

---

## Escenarios Donde GEPA NO Genera ROI

### 1. Usar Mismo Modelo para Optimización y Producción
**Ejemplo:** GPT-4o → GPT-4o

```
Costo optimización: $0.21
Costo producción: Idéntico con o sin GEPA
Ahorro: $0 (solo mejora calidad, no reduce costo)
```

**Cuándo tiene sentido:** Si la calidad es el único objetivo, no el costo.

**En nuestra experimentación:** 22 runs con GPT-4o + GPT-4o costaron $42.38 (51% del presupuesto) pero NO generan ahorro en producción.

### 2. Volúmenes Muy Bajos (< 100 llamadas totales)
**Ejemplo:** Prototipo personal

```
Text-to-SQL @ 100 llamadas:
  Costo optimización: $0.49
  Ahorro: -$0.26 (ROI negativo)
```

**Cuándo tiene sentido:** Si planeas escalar en el futuro, optimiza desde el inicio.

---

## Comparación: Experimentación vs Producción

### Costo de Aprender GEPA: $82.91
Este costo nos permitió:
- Probar 4 casos de uso diferentes
- Experimentar con 3 combinaciones de modelos
- Iterar 245 veces para encontrar prompts óptimos
- Validar la estrategia profesor-estudiante

### Retorno en Producción (asumiendo 10k llamadas/mes por caso):

| Caso | Ahorro Mensual | Ahorro Anual | Meses para ROI Total |
|------|---------------|--------------|---------------------|
| **Email Urgency** | $11.66 | $139.92 | < 1 mes |
| **CV Extraction** | $37.38 | $448.56 | < 1 mes |
| **Text-to-SQL** | $23.00 | $276.00 | < 1 mes |
| **RAG Optimization** | $41.95 | $503.40 | < 1 mes |
| **TOTAL** | **$114.00** | **$1,367.88** | **< 1 mes** |

**Los $82.91 invertidos en experimentación se recuperan en menos de 1 mes de producción** (asumiendo volúmenes moderados).

A escala de 100k llamadas/mes: **$1,140/mes de ahorro = ROI completo en ~2.5 días**.

---

## Beneficios No Cuantificables

Además del ahorro económico directo, GEPA aporta:

1. **Mejora de Performance:** Baseline → Optimized promedio de +20-35%
2. **Consistencia:** Prompts especializados reducen variabilidad
3. **Mantenibilidad:** Prompts documentados y versionados
4. **Time-to-Market:** Optimización automática vs días de ajuste manual
5. **Conocimiento:** Aprender qué combinaciones de modelos funcionan mejor

---

## Recomendaciones

### Para Equipos de Producto
- **Optimizar desde MVP:** El punto de equilibrio es tan bajo (58-210 llamadas) que vale la pena hacerlo desde el inicio
- **Priorizar casos de alto volumen:** Text-to-SQL tiene mayor costo de optimización ($0.49), enfocarse primero en casos simples
- **Usar estrategia profesor-estudiante:** Siempre GPT-4o como profesor, GPT-4o-mini como estudiante

### Para Equipos de FinOps
- **Medir impacto:** Usar `budget_per_case.py` para tracking de costos
- **Evitar experimentos GPT-4o + GPT-4o:** No generan ROI, solo mejora de calidad
- **Documentar en metricas_optimizacion.csv:** Registrar modelo profesor/tarea para análisis
- **Re-optimizar periódicamente:** Si los datos de producción cambian, re-optimizar puede generar nuevas ganancias

### Para Equipos de ML
- **A/B testing:** Comparar modelo caro sin GEPA vs modelo barato con GEPA optimizado
- **Monitor degradación:** Si el score cae en producción, re-optimizar
- **Presupuesto de experimentación:** Asignar ~$0.10-0.50 por caso de uso para iterar

---

## Herramientas Disponibles

### 1. Calculadora de ROI
```bash
python gepa_standalone/utils/roi_calculator.py
```
Muestra ROI para diferentes volúmenes de producción.

### 2. Presupuesto por Caso
```bash
python gepa_standalone/utils/budget_per_case.py
```
Analiza presupuesto gastado en experimentación por caso y combinación de modelos.

---

## Datos Técnicos

**Fuente de datos:** `results/experiments/metricas_optimizacion.csv` (245 experimentos)

**Modelos analizados:**
- GPT-4o (profesor)
- GPT-4o-mini / GPT-4.1-mini (tarea)

**Presupuestos de optimización (max_metric_calls):**
- Email Urgency: 50
- CV Extraction: 40
- Text-to-SQL: 150
- RAG Optimization: 60

**Estimaciones de tokens por caso:**
- Email Urgency: 300 input / 50 output
- CV Extraction: 800 input / 200 output
- Text-to-SQL: 400 input / 150 output
- RAG Optimization: 600 input / 300 output

**Nota:** Estos son promedios. Casos reales pueden variar ±30%.

---

## Conclusión

### GEPA es económicamente viable desde ~100 llamadas en producción

**La inversión inicial de optimización ($0.09 - $0.49 por caso) se recupera en horas o días**, y el ahorro acumulado puede ser de **cientos o miles de dólares anuales** dependiendo del volumen.

**Nuestra experimentación de $82.91:**
- Nos costó menos de un almuerzo para 4 personas
- Se recupera en < 1 mes con volúmenes moderados (10k llamadas/mes)
- Genera $1,368/año de ahorro a esa escala
- ROI total de experimentación: **1,550%** en el primer año

**Regla de oro:** Si esperas hacer más de 500 llamadas en los próximos 6 meses, optimiza con GEPA.

**Regla de platino:** Siempre usa Profesor GPT-4o + estudiante GPT-4o-mini para máximo ROI.
