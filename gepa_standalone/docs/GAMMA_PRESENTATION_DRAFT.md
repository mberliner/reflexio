# Prompt para Gamma - Presentación GEPA (BORRADOR)

**NOTA:** Este es un borrador temporal para generar slides en Gamma.app antes de la demo.

---

## INSTRUCCIONES PARA GAMMA

Crea una presentación de 7 a 10 slides para una audiencia técnica (desarrolladores, arquitectos de software, ML engineers) sobre GEPA - Framework de Optimización Automática de Prompts.

Tono: Profesional, técnico pero accesible, sin marketing fluff.
Estilo visual: Moderno, limpio, con diagramas cuando sea posible.

---

## SLIDE 1: PORTADA
Título: "GEPA: Optimización Automática de Prompts con Reflexión"
Subtítulo: "Cómo un LLM 'profesor' mejora automáticamente tus prompts mediante análisis de errores"
Pie: "Demo Técnica - Reflexio Dicta Lab"

---

## SLIDE 2: EL PROBLEMA
Título: "Optimizar Prompts es Lento y Manual"

Contenido en dos columnas:

Columna 1 - "Antes de GEPA":
- Escribes un prompt genérico
- Pruebas manualmente con casos
- Ves errores, ajustas por intuición
- Repites... horas después, mejora marginal
- Resultado depende de tu experiencia

Columna 2 - "Con GEPA":
- Defines prompt inicial + casos de prueba
- GEPA ejecuta, analiza errores automáticamente
- LLM "profesor" genera variantes mejoradas
- Búsqueda evolutiva encuentra el mejor candidato
- Resultado: prompt especializado en minutos

---

## SLIDE 3: QUÉ HACE GEPA
Título: "Test-Driven Develeopmentg... pero para Prompts"

Diagrama de 3 pasos (usa íconos o flechas):

1. EJECUTAR
   Prompt actual → Micro-lotes (3 casos) → Observar errores/aciertos
   *Evaluación ágil para iteración ultra-rápida.*

2. REFLEXIONAR
   LLM Profesor lee los errores → Razona qué falló → Propone mejoras
   Ejemplo: "El prompt olvidó mencionar límites monetarios, debería enfatizar precisión numérica"

3. EVOLUCIONAR
   Generar variantes del prompt → Evaluar → Mantener las mejores
   Repetir hasta alcanzar score objetivo

Nota al pie: "Búsqueda evolutiva Pareto-eficiente: mantiene candidatos complementarios, no solo el mejor"

---

## SLIDE 3b: EL CAMBIO DE PARADIGMA
Título: "De la Artesanía a la Ingeniería: GEPA es TDD para Prompts"
Subtítulo: "Profesionalizando el desarrollo de IA Generativa"

Contenido Principal:
- **El Problema Actual:** "Prompting basado en Intuición" (*Vibe-based prompting*). Escribimos, probamos un caso, y "creemos" que funciona.
- **La Solución GEPA:** Aplicamos **Test-Driven Development (TDD)** al lenguaje natural.

El Cambio:
- En lugar de escribir prompts → definimos **Tests** (Datasets).
- En lugar de adivinar mejoras → medimos **Métricas**.
- En lugar de refactorizar a mano → el **Optimizador** itera automáticamente.

Caja destacada (Footer):
"GEPA no solo valida el prompt; **lo escribe por ti** hasta que los tests pasan en verde."

---

## SLIDE 3c: LA ANALOGÍA PERFECTA
Título: "TDD Clásico vs. Flujo GEPA"

Tabla comparativa:

| Fase TDD (Software) | Fase GEPA (Prompt Engineering) |
| :--- | :--- |
| **1. Write Test** | **Definir Dataset de Validación** *(Inputs + Salidas Esperadas)* |
| **2. Red (Falla)** | **Baseline Run**  *(Prompt inicial con baja precisión, ej: 40%)* |
| **3. Code & Refactor** | **Optimización Automática**  *(Modelo Profesor reescribe basándose en errores)* |
| **4. Green (Pasa)** | **Prompt Optimizado**  *(Alcanza métrica objetivo, ej: >90%)* |
| **5. Integration Test** | **Prueba de Robustez**  *(Validar generalización en Test Set)* |

Diferencia Crítica ("El Superpoder"):
- En TDD, **tú** escribes el código.
- En GEPA, **la IA** analiza el error y reescribe el prompt. Es **TDD Autónomo**.

---

## SLIDE 4: ESTRATEGIA PROFESOR-ESTUDIANTE
Título: "El Secreto: Desacoplar Inteligencia de Inferencia"

Diagrama en dos fases:

FASE 1: OPTIMIZACIÓN (una sola vez)
- Modelo PROFESOR (GPT-4o): Alta capacidad analítica
- Analiza errores, redacta prompt maestro
- Costo: Inversión inicial controlada

↓ RESULTADO: Prompt Especializado

FASE 2: PRODUCCIÓN (miles de llamadas)
- Modelo EFICIENTE (GPT-4.1-mini): Ejecuta con prompt optimizado
- Calidad de nivel GPT-4o, costo de GPT-4.1-mini
- Costo: Reducción del 90% en producción

Caja de valor destacada:
"Inteligencia de GPT-4o al costo de GPT-4.1-mini"

---

## SLIDE 5: RESULTADOS REALES
Título: "Impacto Medido en el Laboratorio"

Tabla de resultados (Estrategia estudiante GPT-4.1-mini):

| Caso | Mejora | Detalle |
|------|--------|---------|
| Email Urgency | **+38%** | 59.1% → 85.5% precisión |
| CV Extraction | **+24%** | 60.0% → 84.3% precisión |
| Text-to-SQL | **+41%** | 32.5% → 59.2% precisión |
| RAG Optimization | **+42%** | 51.7% → 85.2% precisión |

Caja de valor:
"Mejoras consistentes de +25% a +40% en todos los casos sin cambiar de modelo, solo optimizando el prompt."

---

## SLIDE 6: ROI - ¿CUÁNTO CUESTA?
Título: "Inversión Mínima, Retorno Masivo"

Sección superior - Experimentación real:

COSTO DE OPTIMIZACIÓN:
  • Llamadas Task Model: 510 × $0.00 = $0.04
  • Llamadas Reflection Model: 25 × $0.00 = $0.08
  • TOTAL OPTIMIZACIÓN: $0.12

ROI EN PRODUCCIÓN (usando modelo barato con prompt optimizado):

    Llamadas |     Sin GEPA |     Con GEPA |       Ahorro |        ROI |   Recuperado
-------------+--------------+--------------+--------------+------------+-------------
         100 |        $0.12 |        $0.13 |       $-0.01 |      -7.9% |           NO
         500 |        $0.62 |        $0.19 |        $0.43 |     360.3% |           SI
       1,000 |        $1.25 |        $0.27 |        $0.98 |     820.5% |           SI
       5,000 |        $6.25 |        $0.87 |        $5.38 |   4,502.5% |           SI
      10,000 |       $12.50 |        $1.62 |       $10.88 |   9,105.0% |           SI
      50,000 |       $62.50 |        $7.62 |       $54.88 |  45,925.1% |           SI
     100,000 |      $125.00 |       $15.12 |      $109.88 |  91,950.2% |           SI

PUNTO DE EQUILIBRIO: 101 llamadas -
Ej 1000 llamadas:
1. La Opción Antigua (Sin hacer nada)
  Modelo potente (GPT-4o) para leer los 1,000 correos.
   * La factura llega por: $1.25 USD.

  2. Con GEPA (Optimizada)
  Aquí pagas dos cosas:
   * La Inversión Inicial: Gastas $0.12 una sola vez para entrenar el sistema.
   * El Consumo: Procesar los 1,000 correos con el modelo barato (GPT-4.1-mini) te cuesta $0.15.
   * Gasto Total: $0.12 + $0.15 = $0.27 USD.

  3. El Ahorro
   * En lugar de pagar $1.25, pagaste $0.27.
   * Te quedan $0.98 USD libres para usar en otra cosa

  4. El ROI (Tu Ganancia)
   * Pusiste 12 centavos de tu dinero para optimizar.
   * El sistema te devolvió esos 12 centavos y te generó 98 centavos extra de ganancia pura.
   * Como ganaste casi 8 veces lo que invertiste, tu retorno de inversión (ROI) es del 820%.

---

## SLIDE 7: DEMO EN VIVO
Título: "Qué Veremos en la Demo"

Lista numerada:

1. Ejecutar optimización de Email Urgency
   - Comando: `python universal_optimizer.py --config experiments/configs/email_urgency.yaml --verbose`
   - **Modo Verbose**: Veremos en tiempo real cómo el "Profesor" analiza los errores.
   - Tiempo: ~3-5 minutos

2. Comparar antes vs después
   - Prompt inicial: Genérico, instrucciones vagas
   - Prompt optimizado: Especializado, criterios precisos
   - Scores: Baseline vs Optimized vs Test

3. Revisar archivos de Entrada y Salida
   - Entrada: `email_urgency.csv` y `email_urgency_v1.json`
   - Salida: `initial_prompt.txt`, `final_prompt.txt`, `results.json` y `metricas_optimizacion.csv`

4. Visualizar Leaderboard Financiero y ROI
   - Generar Reporte Unificado: `python utils/leaderboard.py`
   - **Nuevos Gráficos**: Veremos `gepa_roi_analysis.png` y `gepa_performance_improvement.png`
   - Punto de equilibrio y ahorro proyectado en tiempo real.

Caja de llamado a la acción:
"¿Ahora vemos GEPA en acción?"
