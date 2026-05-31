# Cuándo Aplicar Optimización de Prompts (GEPA / DSPy) y Casos de Uso Reales

SSOT para decidir **si conviene** aplicar este enfoque a un problema y **en qué
casos del mundo real** rinde. No describe el cómo técnico (ver
`docs/GUIA_CASO_USO_BASE_CONOCIMIENTO.md` y las guías de cada framework), sino el
criterio de aplicabilidad y el catálogo de dominios.

## Las 4 condiciones para que pague

El enfoque (optimizar automáticamente el prompt contra una métrica con datos
etiquetados) da valor solo cuando se cumplen las cuatro. Si falta una, no rinde.

1. **Métrica objetiva y automática.** Accuracy, F1, exactitud por campo, query
   ejecutable que devuelve el resultado correcto. No "suena bien".
2. **Datos etiquetados**, aunque sean pocos. 20-50 ejemplos alcanzan (ver
   CV Extraction). El cuello de botella real es construir este dataset gold.
3. **Alto volumen / repetición.** El prompt se ejecuta miles de veces, así que
   +5pp se amortizan. Para una tarea one-shot no vale el budget de optimización.
4. **El error cuesta.** Plata, riesgo legal, o retrabajo humano.

## La regla del baseline 50-80%

Hallazgo de las corridas comparativas (ver `docs/LECCIONES_APRENDIDAS.md`,
secciones 8 y 10): el lift grande está en tareas **no saturadas**.

- **Baseline 50-80% → aplicar.** Es donde GEPA/DSPy convierten un prototipo
  inservible en algo productivo (ej. CV Extraction: ~40% → ~97%).
- **Baseline > 90% → no invertir.** Casi no se mueve la aguja, e incluso puede
  empeorar (ej. CV Triage que regresó 100% → 93% al optimizar un caso saturado).

> Buscá tareas donde el LLM "pelado" rinde 50-80% y el error cuesta. Ahí está el
> valor. Donde ya rinde > 90%, no gastes budget.

## Catálogo de casos de uso reales

### Extracción estructurada de documentos
Mismo patrón que CV Extraction (adapter `extractor`).
- Facturas → campos contables (proveedor, CUIT, montos, items)
- Contratos → cláusulas, vencimientos, partes, penalidades
- Historias clínicas → diagnósticos, medicación, dosis
- Pólizas, escrituras, expedientes legales
- *Por qué paga:* hoy es trabajo manual; +10pp de exactitud = menos auditoría.

### Clasificación / triage de alto volumen
Mismo patrón que CV Triage (adapter `classifier`).
- Tickets de soporte → routing por equipo/prioridad
- Emails entrantes → spam / lead / queja / legal
- Moderación de contenido contra políticas específicas
- Detección de fraude/anomalías con justificación
- *Por qué paga:* cada misclassification = SLA roto o costo de escalamiento.

### Normalización y matching de datos
- Deduplicación de clientes/productos (mismo entity, distinta escritura)
- Mapeo de descripciones libres a catálogos (SKU, ICD, categorías contables)
- Normalización de direcciones sucias

### RAG y Q&A sobre conocimiento propio
Adapter `rag`.
- Asistentes de soporte sobre documentación interna
- Búsqueda legal/regulatoria con citas
- *Por qué paga:* se optimiza el prompt de síntesis para reducir alucinación
  medible contra respuestas gold.

### Generación de SQL / código desde lenguaje natural
Adapter `sql`.
- Analistas no técnicos consultando bases de datos
- *Por qué paga:* la métrica es perfecta y automática — ¿la query ejecuta y
  devuelve el resultado correcto?

### Compliance y QA automatizado
- ¿Este texto cumple la política X? (con ejemplos etiquetados cumple/no cumple)
- Verificación de que reportes/PDFs tengan todos los campos obligatorios

## GEPA solo vs DSPy: no son el mismo tipo de cosa

La confusión común es tratarlos como alternativas simétricas. No lo son:

- **GEPA = el optimizador.** Evoluciona **un prompt** (típicamente el
  `system_prompt`) por reflexión: corre, mira los errores, reescribe la
  instrucción, repite. Eso es todo lo que hace.
- **DSPy = el framework.** Una forma de *programar* sistemas LLM: Signatures
  tipadas, módulos, pipelines multi-etapa, few-shot automático
  (`BootstrapFewShot`) y varios optimizadores —GEPA es solo uno; también
  `MIPROv2`, `BootstrapFewShotWithRandomSearch`.

En una frase: **GEPA solo optimiza un prompt; DSPy optimiza un programa** (que
puede tener varios prompts encadenados, ramas condicionales y ejemplos few-shot).

### Hallazgo empírico (ver `docs/LECCIONES_APRENDIDAS.md`, sección 6)

En una tarea de **un solo prompt** (clasificación de urgencia de emails),
controlando todas las variables, GEPA standalone y DSPy+GEPA llegan al mismo
techo: optimized 86.3% vs 88.0%, robustez 96.3% vs 98.7%. La diferencia no es
significativa dada la varianza (SD ~7-8).

> La optimización reflexiva (GEPA) es el factor dominante, no la infraestructura
> que la ejecuta. En tareas de un prompt, DSPy aporta solo una ventaja marginal
> de estabilidad/robustez, no más accuracy.

### Cuándo DSPy sí marca la diferencia

DSPy gana cuando el problema **no cabe en un solo prompt** (ver
`docs/LECCIONES_APRENDIDAS.md`, sección 7):

1. **Flujos multi-etapa** (clasificar → y según eso, responder): optimiza la
   cadena completa de forma global.
2. **Lógica condicional / ruteo** (si cumple Regla A, evaluá Regla B): permite
   derivar casos simples a modelos baratos = ahorro de costo, no solo calidad.
3. **Razonamiento encadenado** con `ChainOfThought` por etapa (Capa 1 robusta
   para no propagar errores).
4. **Few-shot automático** cuando hay < 15 ejemplos: `BootstrapFewShot` puede
   rendir más que GEPA con tan pocos datos.

### Qué forma usar por caso real

| Aplicación real | Forma | Por qué |
|---|---|---|
| Extracción de facturas/contratos (1 paso) | **GEPA solo** | Un prompt, métrica por campo. DSPy no agrega techo. |
| Triage de tickets/emails (1 etiqueta) | **GEPA solo** | Clasificación de un prompt, budget chico. |
| Optimizar prompt contra archivo de reglas | **GEPA solo** (`rag`) | Si las reglas caben en contexto y son estáticas. |
| Soporte: clasificar → rutear → redactar | **DSPy+GEPA** | Pipeline multi-etapa, optimización global. |
| Análisis legal: detectar tipo → aplicar reglas | **DSPy+GEPA** | Condicional; ramas especializadas. |
| NL→SQL con validación + reintento | **DSPy+GEPA** | Múltiples pasos (generar, validar, corregir). |
| Triage barato + escalamiento si dudoso | **DSPy+GEPA** | Ruteo condicional = ahorro de tokens. |

### Aclaración: "pipeline multi-etapa" no es n8n / Make / Zapier

Las herramientas de workflow (n8n, Make, Zapier) y los pipelines de DSPy operan
en **capas distintas** y son complementarios, no alternativos:

- **n8n / Make = orquestación entre sistemas.** Los nodos son integraciones
  (HTTP, DB, Slack, Salesforce). Resuelven *cómo conecto mis sistemas*. Son
  ejecutores deterministas de la lógica que vos cableás; no optimizan nada.
- **DSPy = orquestación del razonamiento dentro de una tarea LLM.** Los nodos son
  módulos LLM tipados (Signatures). Resuelven *cómo hago que la parte LLM sea lo
  más exacta posible*. La cadena completa se optimiza contra una métrica.

El "multi-etapa" de DSPy no es un proceso de negocio: son sub-pasos de **una
misma tarea** cognitiva, encadenados porque descomponerla da más precisión que un
prompt monolítico. En la práctica, **un programa DSPy es lo que vive dentro de un
nodo de n8n**: n8n trae el dato y guarda el resultado; DSPy es la parte
inteligente y optimizada del medio.

El agregado clave que no tiene n8n: ahí, si un prompt rinde mal, lo reescribís a
mano; en DSPy el optimizador reescribe los prompts de todas las etapas solo,
maximizando el resultado final de la cadena.

Ejemplo concreto en el repo: la cascada `triage_v1` → (condicional)
`fast_gate_v1` de `docs/FAST_GATE_SEGMENTACION.md` (sección "Orquestacion en
produccion") es exactamente esa capa de orquestación, con cada nodo optimizado
por separado.

### Multi-etapa: ¿una corrida conjunta o varias separadas?

Un pipeline de varias etapas en DSPy puede optimizarse de dos formas distintas, y
elegir mal cuesta calidad.

#### Modo A — Una sola corrida, optimización conjunta (DSPy nativo)

El pipeline es **un solo `dspy.Module`** con varios predictores adentro. Se
compila con **un optimizador y una métrica end-to-end**: una única corrida que
ajusta los prompts de todas las etapas a la vez.

```python
class MiPipeline(dspy.Module):
    def __init__(self):
        self.clasificar = dspy.ChainOfThought(ClasificarSig)
        self.extraer    = dspy.ChainOfThought(ExtraerSig)

    def forward(self, doc):
        c = self.clasificar(doc=doc)
        e = self.extraer(doc=doc, categoria=c.categoria)
        return e

# UNA corrida: optimiza ambas etapas juntas contra la métrica final
optimizer.compile(MiPipeline(), trainset=trainset, metric=metrica_final)
```

Ventaja central: **credit assignment entre etapas.** GEPA reflexiona sobre el
fallo final y puede deducir "esto falló porque la etapa 1 clasificó mal" y
reescribir el prompt de la etapa 1 — imposible optimizando cada prompt aislado.

#### Modo B — Corridas separadas + cascada en producción

Cada etapa se optimiza por separado, con **su propio dataset y su propia
métrica**, y se encadenan a mano en runtime. Es lo que hace el repo con el
intake: `triage_v1` y `fast_gate_v1` son dos corridas independientes,
compuestas en cascada (ver `docs/FAST_GATE_SEGMENTACION.md`).

```bash
# Dos corridas independientes, cada una con su config/dataset/métrica:
python -m gepa_standalone.universal_optimizer --config .../triage_v1.yaml
python -m gepa_standalone.universal_optimizer --config .../fast_gate_v1.yaml

# Composición en producción (pseudocódigo):
#   d = triage_v1(ficha)
#   if d.decision == "avanza_fast_gate":
#       resultado = fast_gate_v1(ficha)
#   else:
#       resultado = no_aplica
```

#### Cuándo cada uno

| | Modo A (conjunta) | Modo B (separada + cascada) |
|---|---|---|
| Métrica | Una, end-to-end | Una por etapa |
| Credit assignment entre etapas | **Sí** (fortaleza de DSPy) | No |
| Riesgo | Prompts "de compromiso" si las etapas compiten | Más control, etapas auditables |
| Mejor cuando | Una métrica final única tiene sentido | Objetivos de etapa que compiten o se contaminan |

Hallazgo del repo (ver `docs/LECCIONES_APRENDIDAS.md`, sección 7, punto 5):
optimizar dos funciones con una sola métrica unificada hizo que GEPA propusiera
**prompts de compromiso**, y el gate estructural **contaminaba el baseline** (los
casos que no avanzaban rellenaban campos "gratis"). Por eso el caso unificado de
intake se discontinuó y se segmentó en dos corridas (Modo B).

> Regla: la corrida conjunta es más potente *cuando una métrica final única tiene
> sentido*. Si las etapas tienen objetivos que compiten o una contamina el
> baseline de la otra, segmentar en corridas separadas da prompts más limpios,
> aunque pierdas el credit assignment automático.

### Candidatos naturales a pipeline multi-etapa

Señal de candidato: la tarea se descompone en sub-decisiones secuenciales donde
una etapa intermedia condiciona o alimenta a la siguiente, y existe un resultado
final único medible. Si es un solo juicio, es prompt único; no lo fuerces a
pipeline.

| Caso real | Etapas | Modo |
|---|---|---|
| Extracción condicionada por tipo de documento | clasificar tipo → extraer campos del esquema de ese tipo → validar | **A** (conjunta) |
| Soporte al cliente | clasificar intención → rutear → redactar respuesta | **A** |
| NL→SQL con auto-corrección | generar SQL → ejecutar/validar → corregir con el error como feedback | **A** |
| Análisis legal por ramas | detectar tipo de cláusula → aplicar reglas de ese tipo → extraer riesgos | **B** si las ramas compiten |
| RAG con reformulación | reformular pregunta → recuperar pasajes → sintetizar con citas | **A** |
| Triage médico / derivación | extraer síntomas → clasificar urgencia → derivar a especialidad | **A** |
| Moderación en capas | gate barato → si dudoso, análisis profundo contra política | **B** (gate contamina baseline) |

Recordatorio (Modo A = una corrida conjunta; Modo B = corridas separadas +
cascada; ver subsección anterior). La pista práctica para elegir: **si una etapa
"regala" parte del score de la otra (gate estructural, objetivos que compiten),
separá en Modo B; si las etapas reman hacia una misma métrica final, usá Modo A
y aprovechá el credit assignment.**

#### Lo que NO es candidato (mantener prompt único)

- Extracción de un solo esquema fijo (CV Extraction).
- Clasificación de una etiqueta (CV Triage, urgencia de emails).
- Cualquier tarea sin una decisión intermedia que cambie el paso siguiente.

### Regla práctica

> Empezá siempre con GEPA standalone. Si la tarea es un prompt, quedate ahí: es
> más barato (< 60 llamadas), más simple y rinde igual. Escalá a DSPy solo
> cuando aparezca una segunda etapa, una rama condicional, o necesites few-shot
> con pocos datos. La complejidad de DSPy se justifica por la **estructura del
> problema**, no por buscar más accuracy en un prompt.

## Elección de framework

Para la decisión GEPA standalone vs DSPy+GEPA en un caso concreto, ver
`docs/GUIA_CASO_USO_BASE_CONOCIMIENTO.md` (sección "Cuándo escalar a DSPy + GEPA")
y `docs/LECCIONES_APRENDIDAS.md` (sección 10, comparación justa). Resumen
operativo de las corridas del 2026-05-31: ambos optimizadores llegan a un techo
equivalente (~95-99% en extraction); GEPA mostró menor varianza run-a-run.

## Documentos relacionados

- `docs/LECCIONES_APRENDIDAS.md` — hallazgos experimentales que fundamentan la
  regla del baseline 50-80% y el efecto techo.
- `docs/GUIA_CASO_USO_BASE_CONOCIMIENTO.md` — how-to concreto de un caso.
- `docs/PROTOCOLO_N_SEEDS.md` — cómo medir señal vs ruido al validar un caso.
