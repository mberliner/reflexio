# DSPy - Framework para Programación con Modelos de Lenguaje

## Descripcion General

**DSPy** (Declarative Self-improving Python) es un framework desarrollado por Stanford NLP que permite **programar con modelos de lenguaje en lugar de escribir prompts manualmente**.

- **Licencia**: MIT
- **Autor**: Omar Khattab (Stanford)
- **Repositorio**: https://github.com/stanfordnlp/dspy
- **Documentacion**: https://dspy.ai/
- **Versiones**: Ver `requirements.txt` (SSOT)

### Filosofia Central

| Enfoque Tradicional | Enfoque DSPy |
|---------------------|--------------|
| Escribir prompts manualmente | Escribir codigo Python |
| Prompts fragiles y dificiles de mantener | Modulos composables y reutilizables |
| Optimizacion manual por prueba y error | Optimizacion automatica con datos |
| Acoplado a un modelo especifico | Portable entre modelos |

---

## Arquitectura del Proyecto

### Estructura de Directorios

```
DSPy/
├── dspy/                          # Paquete principal (~135 archivos Python, 1.3MB)
│   ├── __init__.py                # Exportaciones del paquete
│   │
│   ├── predict/                   # Modulos de prediccion
│   │   ├── predict.py             # Clase base Predict
│   │   ├── chain_of_thought.py    # Razonamiento paso a paso (CoT)
│   │   ├── react.py               # Agentes ReAct con herramientas
│   │   ├── program_of_thought.py  # Razonamiento matematico
│   │   ├── refine.py              # Refinamiento iterativo
│   │   ├── best_of_n.py           # Seleccion de N candidatos
│   │   └── parallel.py            # Ejecucion paralela
│   │
│   ├── signatures/                # Especificaciones de tareas
│   │   ├── signature.py           # Clase Signature
│   │   └── field.py               # InputField/OutputField
│   │
│   ├── teleprompt/                # Algoritmos de optimizacion (10+)
│   │   ├── bootstrap.py           # BootstrapFewShot
│   │   ├── copro_optimizer.py     # COPRO
│   │   ├── mipro_optimizer_v2.py  # MIPROv2
│   │   ├── gepa/                  # GEPA (mas reciente)
│   │   └── ...                    # Otros optimizadores
│   │
│   ├── clients/                   # Clientes de modelos de lenguaje
│   │   ├── lm.py                  # Cliente principal (LiteLLM)
│   │   ├── cache.py               # Sistema de cache
│   │   ├── embedding.py           # Modelos de embeddings
│   │   └── openai.py              # Proveedor OpenAI
│   │
│   ├── adapters/                  # Adaptadores de formato de salida
│   │   ├── chat_adapter.py        # Formato chat
│   │   ├── json_adapter.py        # Salida JSON
│   │   ├── xml_adapter.py         # Salida XML
│   │   └── types/                 # Tipos (Image, Audio, etc.)
│   │
│   ├── evaluate/                  # Framework de evaluacion
│   │   ├── evaluate.py            # Clase Evaluate
│   │   └── metrics.py             # Metricas integradas
│   │
│   ├── retrievers/                # Recuperacion de informacion (RAG)
│   │   ├── databricks_rm.py       # Databricks Vector Search
│   │   ├── embeddings.py          # Basado en embeddings
│   │   ├── weaviate_rm.py         # Weaviate
│   │   └── colbertv2.py           # ColBERT
│   │
│   ├── datasets/                  # Datasets incluidos
│   │   ├── hotpotqa.py            # HotPotQA (multi-hop QA)
│   │   ├── math.py                # MATH (razonamiento matematico)
│   │   └── ...                    # Otros datasets
│   │
│   ├── primitives/                # Estructuras de datos core
│   │   ├── module.py              # Clase base Module
│   │   ├── example.py             # Objetos Example/datos
│   │   ├── prediction.py          # Prediction/Completions
│   │   └── python_interpreter.py  # Ejecucion de codigo
│   │
│   ├── streaming/                 # Streaming en tiempo real
│   ├── utils/                     # Utilidades (async, cache, logging)
│   └── experimental/              # Caracteristicas experimentales
│
├── docs/                          # Sitio de documentacion (MKDocs)
│   └── docs/
│       ├── learn/                 # Materiales de aprendizaje
│       │   ├── programming/       # Guia de programacion
│       │   ├── optimization/      # Guia de optimizacion
│       │   └── evaluation/        # Guia de evaluacion
│       └── tutorials/             # 15+ tutoriales
│
├── tests/                         # Suite de tests
│   ├── examples/                  # Programas de ejemplo
│   └── reliability/               # Tests de confiabilidad
│
└── pyproject.toml                 # Configuracion del paquete
```

### Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────────┐
│                         APLICACION                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │  Signatures  │───▶│   Modules    │───▶│  Predictions │       │
│  │  (Tareas)    │    │  (Logica)    │    │  (Salidas)   │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│         │                   │                   │                │
│         ▼                   ▼                   ▼                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Adapters   │    │  Retrievers  │    │   Evaluate   │       │
│  │  (Formatos)  │    │    (RAG)     │    │  (Metricas)  │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                              │                                   │
├──────────────────────────────┼───────────────────────────────────┤
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────┐       │
│  │                    TELEPROMPT                         │       │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐        │       │
│  │  │ Bootstrap  │ │  MIPROv2   │ │    GEPA    │  ...   │       │
│  │  │  FewShot   │ │            │ │            │        │       │
│  │  └────────────┘ └────────────┘ └────────────┘        │       │
│  └──────────────────────────────────────────────────────┘       │
│                              │                                   │
├──────────────────────────────┼───────────────────────────────────┤
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────┐       │
│  │                  CLIENTS (LiteLLM)                    │       │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐         │       │
│  │  │ OpenAI │ │Anthropic│ │ Local  │ │ Custom │  ...   │       │
│  │  └────────┘ └────────┘ └────────┘ └────────┘         │       │
│  └──────────────────────────────────────────────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Instalacion

### Instalacion Basica

```bash
# Desde PyPI (recomendado)
pip install dspy

# Version de desarrollo
pip install git+https://github.com/stanfordnlp/dspy.git
```

### Dependencias

Para la lista completa de dependencias y versiones exactas, consulte el archivo central `requirements.txt`.

### Dependencias Opcionales

```bash
# Para Anthropic Claude
pip install dspy[anthropic]

# Para Weaviate
pip install dspy[weaviate]

# Para LangChain
pip install dspy[langchain]
```

### Configuracion Inicial

```python
import dspy

# Configurar modelo de lenguaje
lm = dspy.LM("openai/gpt-4o", api_key="sk-...")
dspy.configure(lm=lm)

# O usar variable de entorno OPENAI_API_KEY
import os
os.environ["OPENAI_API_KEY"] = "sk-..."
lm = dspy.LM("openai/gpt-4o")
dspy.configure(lm=lm)
```

---

## Conceptos Fundamentales

### 1. Signatures (Firmas)

Las Signatures definen **que** hace una tarea: sus entradas y salidas.

#### Forma Inline (String)

```python
# Sintaxis: "entrada1, entrada2 -> salida1, salida2"

# Clasificacion simple
classify = dspy.Predict("sentence -> sentiment: bool")

# Pregunta-respuesta
qa = dspy.Predict("context, question -> answer")

# Multiples salidas
analyze = dspy.Predict("text -> summary, keywords: list[str], score: float")
```

#### Forma con Clase (Tipada)

```python
class QuestionAnswering(dspy.Signature):
    """Responde preguntas usando el contexto proporcionado."""

    # Campos de entrada
    context: str = dspy.InputField(desc="hechos relevantes")
    question: str = dspy.InputField(desc="pregunta del usuario")

    # Campos de salida
    answer: str = dspy.OutputField(desc="respuesta corta y factual")
    confidence: float = dspy.OutputField(desc="confianza 0-1")
```

#### Tipos Soportados

| Tipo | Ejemplo |
|------|---------|
| `str` | Texto libre |
| `bool` | True/False |
| `int` | Numeros enteros |
| `float` | Numeros decimales |
| `list[str]` | Lista de strings |
| `Literal["a", "b"]` | Opciones fijas |
| `dict` | Diccionarios |

### 2. Modules (Modulos)

Los Modules definen **como** se ejecuta la logica.

#### Modulos Integrados

| Modulo | Descripcion | Uso |
|--------|-------------|-----|
| `Predict` | Prediccion basica | Tareas simples |
| `ChainOfThought` | Razonamiento paso a paso | Tareas complejas |
| `ReAct` | Razonamiento + Accion | Agentes con herramientas |
| `ProgramOfThought` | Genera codigo Python | Problemas matematicos |
| `BestOfN` | Genera N candidatos | Cuando se necesita diversidad |
| `Refine` | Refinamiento iterativo | Mejora de respuestas |
| `Parallel` | Ejecucion paralela | Multiples subtareas |

#### Ejemplo: Predict vs ChainOfThought

```python
# Predict: respuesta directa
predict = dspy.Predict("question -> answer")
result = predict(question="Cual es la capital de Francia?")
# result.answer = "Paris"

# ChainOfThought: incluye razonamiento
cot = dspy.ChainOfThought("question -> answer")
result = cot(question="Si tengo 3 manzanas y doy 1, cuantas me quedan?")
# result.reasoning = "Empiezo con 3 manzanas. Doy 1. 3 - 1 = 2."
# result.answer = "2"
```

#### Creacion de Modulos Personalizados

```python
class MiModulo(dspy.Module):
    def __init__(self, num_pasajes=3):
        super().__init__()
        self.retrieve = dspy.Retrieve(k=num_pasajes)
        self.generate = dspy.ChainOfThought("context, question -> answer")

    def forward(self, question):
        # Recuperar contexto
        context = self.retrieve(question).passages

        # Generar respuesta
        resultado = self.generate(
            context="\n".join(context),
            question=question
        )

        return dspy.Prediction(
            context=context,
            answer=resultado.answer
        )
```

### 3. Optimizers (Optimizadores)

Los Optimizers mejoran automaticamente el rendimiento usando datos de entrenamiento.

#### Optimizadores Disponibles

| Optimizador | Estrategia | Mejor Para |
|-------------|------------|------------|
| `BootstrapFewShot` | Selecciona mejores demos | Inicio rapido |
| `BootstrapFewShotWithRandomSearch` | Bootstrap + busqueda | Mejor rendimiento |
| `COPRO` | Optimiza prompts geneticamente | Instrucciones |
| `MIPROv2` | Multi-etapa | Alto rendimiento |
| `GEPA` | Evolucion reflexiva | Estado del arte |
| `BootstrapFinetune` | Fine-tuning | Modelos pequenos |

#### Flujo de Optimizacion

```python
# 1. Definir metrica
def metric(example, prediction):
    return prediction.answer.lower() == example.answer.lower()

# 2. Preparar datos
trainset = [
    dspy.Example(question="...", answer="...").with_inputs("question"),
    # ...
]

# 3. Crear optimizador
optimizer = dspy.BootstrapFewShot(
    metric=metric,
    max_bootstrapped_demos=4,
    max_labeled_demos=16
)

# 4. Compilar programa
programa_original = MiModulo()
programa_optimizado = optimizer.compile(
    programa_original,
    trainset=trainset
)

# 5. El programa optimizado tiene mejores demos/prompts
resultado = programa_optimizado(question="...")
```

### 4. Evaluate (Evaluacion)

```python
# Crear evaluador
evaluator = dspy.Evaluate(
    devset=devset,           # Datos de validacion
    metric=metric,           # Funcion de metrica
    num_threads=4,           # Paralelismo
    display_progress=True    # Mostrar progreso
)

# Evaluar programa
score = evaluator(programa)
print(f"Precision: {score:.2%}")

# Evaluacion detallada
results = evaluator(programa, return_outputs=True)
for example, prediction, score in results:
    print(f"Q: {example.question}")
    print(f"A: {prediction.answer}")
    print(f"Score: {score}")
```

#### Metricas Integradas

```python
from dspy.evaluate import metrics

# Coincidencia exacta
dspy.evaluate.answer_exact_match(example, pred)

# Contenido en pasaje
dspy.evaluate.answer_passage_match(example, pred)

# F1 semantico
semantic_f1 = dspy.SemanticF1()
score = semantic_f1(example, pred)
```

---

## Flujo de Trabajo Completo

### Diagrama de Flujo

```
┌─────────────────┐
│  1. DEFINIR     │
│     TAREA       │
│  (Signature)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  2. ESCRIBIR    │
│    PROGRAMA     │
│   (Modules)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  3. RECOLECTAR  │
│     DATOS       │
│  (Examples)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  4. DEFINIR     │
│    METRICA      │
│  (metric fn)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  5. EVALUAR     │
│   ZERO-SHOT     │
│  (baseline)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  6. OPTIMIZAR   │
│  (teleprompt)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  7. EVALUAR     │
│   OPTIMIZADO    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  8. ITERAR O    │
│    DESPLEGAR    │
└─────────────────┘
```

### Ejemplo Completo: Sistema RAG

```python
import dspy
from dspy.datasets import HotPotQA

# ============================================
# 1. CONFIGURACION
# ============================================

# Configurar modelo
lm = dspy.LM("openai/gpt-4o-mini", temperature=0.7)
dspy.configure(lm=lm)

# Configurar retriever (opcional)
# rm = dspy.ColBERTv2(url="http://...")
# dspy.configure(rm=rm)

# ============================================
# 2. DEFINIR SIGNATURES
# ============================================

class GenerateSearchQuery(dspy.Signature):
    """Genera una consulta de busqueda para responder la pregunta."""
    context: str = dspy.InputField(desc="contexto actual")
    question: str = dspy.InputField(desc="pregunta a responder")
    query: str = dspy.OutputField(desc="consulta de busqueda")

class GenerateAnswer(dspy.Signature):
    """Responde la pregunta basandose en el contexto."""
    context: str = dspy.InputField(desc="hechos relevantes")
    question: str = dspy.InputField(desc="pregunta del usuario")
    answer: str = dspy.OutputField(desc="respuesta en 1-5 palabras")

# ============================================
# 3. CREAR MODULO
# ============================================

class MultiHopRAG(dspy.Module):
    """RAG con multiples saltos de razonamiento."""

    def __init__(self, passages_per_hop=3, max_hops=2):
        super().__init__()
        self.max_hops = max_hops
        self.retrieve = dspy.Retrieve(k=passages_per_hop)
        self.generate_query = [
            dspy.ChainOfThought(GenerateSearchQuery)
            for _ in range(max_hops)
        ]
        self.generate_answer = dspy.ChainOfThought(GenerateAnswer)

    def forward(self, question):
        context = []

        for hop in range(self.max_hops):
            # Generar query de busqueda
            query_result = self.generate_query[hop](
                context=context,
                question=question
            )

            # Recuperar pasajes
            passages = self.retrieve(query_result.query).passages

            # Acumular contexto (sin duplicados)
            context = list(set(context + passages))

        # Generar respuesta final
        answer_result = self.generate_answer(
            context="\n".join(context),
            question=question
        )

        return dspy.Prediction(
            context=context,
            answer=answer_result.answer
        )

# ============================================
# 4. CARGAR DATOS
# ============================================

dataset = HotPotQA(train_seed=1, eval_seed=2023)
trainset = [x.with_inputs("question") for x in dataset.train[:100]]
devset = [x.with_inputs("question") for x in dataset.dev[:50]]

# ============================================
# 5. DEFINIR METRICA
# ============================================

def validate_answer(example, pred, trace=None):
    """Metrica: respuesta correcta y fundamentada."""
    # Verificar respuesta correcta
    answer_match = dspy.evaluate.answer_exact_match(example, pred)

    # Verificar que la respuesta esta en el contexto
    if hasattr(pred, 'context') and pred.context:
        context_text = " ".join(pred.context).lower()
        grounded = pred.answer.lower() in context_text
    else:
        grounded = True

    return answer_match and grounded

# ============================================
# 6. EVALUAR ZERO-SHOT
# ============================================

rag = MultiHopRAG()

evaluator = dspy.Evaluate(
    devset=devset,
    metric=validate_answer,
    num_threads=4
)

baseline_score = evaluator(rag)
print(f"Baseline (zero-shot): {baseline_score:.2%}")

# ============================================
# 7. OPTIMIZAR
# ============================================

optimizer = dspy.BootstrapFewShot(
    metric=validate_answer,
    max_bootstrapped_demos=4,
    max_labeled_demos=16
)

rag_optimized = optimizer.compile(rag, trainset=trainset)

# ============================================
# 8. EVALUAR OPTIMIZADO
# ============================================

optimized_score = evaluator(rag_optimized)
print(f"Optimizado: {optimized_score:.2%}")
print(f"Mejora: +{(optimized_score - baseline_score):.2%}")

# ============================================
# 9. GUARDAR MODELO
# ============================================

rag_optimized.save("rag_optimized.json")

# Cargar despues
rag_loaded = MultiHopRAG()
rag_loaded.load("rag_optimized.json")
```

---

## Casos de Uso Comunes

### 1. Clasificacion de Texto

```python
class SentimentClassifier(dspy.Signature):
    """Clasifica el sentimiento del texto."""
    text: str = dspy.InputField()
    sentiment: Literal["positive", "negative", "neutral"] = dspy.OutputField()

classifier = dspy.Predict(SentimentClassifier)
result = classifier(text="Me encanta este producto!")
print(result.sentiment)  # "positive"
```

### 2. Extraccion de Entidades

```python
class EntityExtractor(dspy.Signature):
    """Extrae entidades del texto."""
    text: str = dspy.InputField()
    personas: list[str] = dspy.OutputField(desc="nombres de personas")
    lugares: list[str] = dspy.OutputField(desc="nombres de lugares")
    fechas: list[str] = dspy.OutputField(desc="fechas mencionadas")

extractor = dspy.Predict(EntityExtractor)
result = extractor(text="Juan viajo a Paris el 15 de marzo de 2024")
```

### 3. Generacion de Codigo

```python
class CodeGenerator(dspy.Signature):
    """Genera codigo Python."""
    task: str = dspy.InputField(desc="descripcion de la tarea")
    code: str = dspy.OutputField(desc="codigo Python funcional")

generator = dspy.ChainOfThought(CodeGenerator)
result = generator(task="funcion que calcule el factorial de un numero")
```

### 4. Agente con Herramientas (ReAct)

```python
def calculator(expression: str) -> str:
    """Evalua una expresion matematica."""
    return str(eval(expression))

def search(query: str) -> str:
    """Busca informacion."""
    # Implementar busqueda real
    return f"Resultado de busqueda para: {query}"

agent = dspy.ReAct(
    "question -> answer",
    tools=[calculator, search],
    max_iters=5
)

result = agent(question="Cuanto es 15% de 200 mas 50?")
```

### 5. Resumenes

```python
class Summarizer(dspy.Signature):
    """Resume el documento."""
    document: str = dspy.InputField()
    summary: str = dspy.OutputField(desc="resumen en 2-3 oraciones")
    key_points: list[str] = dspy.OutputField(desc="puntos clave")

summarizer = dspy.ChainOfThought(Summarizer)
```

---

## Caracteristicas Avanzadas

### Cache y Rendimiento

```python
# Cache habilitado por defecto (30GB disco)
lm = dspy.LM("openai/gpt-4o")

# Deshabilitar cache
lm = dspy.LM("openai/gpt-4o", cache=False)

# Cache solo en memoria
lm = dspy.LM("openai/gpt-4o", cache_in_memory=True)

# Ver historial de llamadas
print(lm.history)
```

### Streaming

```python
# Habilitar streaming
lm = dspy.LM("openai/gpt-4o")
dspy.configure(lm=lm)

predict = dspy.Predict("question -> answer")

# Streaming de respuesta
with dspy.streaming():
    for chunk in predict.stream(question="..."):
        print(chunk, end="")
```

### Async/Paralelo

```python
import asyncio

# Ejecucion asincrona
async def procesar_batch(preguntas):
    tasks = [predict.acall(question=q) for q in preguntas]
    return await asyncio.gather(*tasks)

# Ejecucion paralela
from dspy.predict import Parallel

parallel = Parallel(
    [dspy.Predict(sig1), dspy.Predict(sig2)],
    reduce_fn=lambda results: results
)
```

### Observabilidad

```python
# Callbacks
def mi_callback(call_info):
    print(f"Modelo: {call_info['model']}")
    print(f"Tokens: {call_info['usage']}")

lm = dspy.LM("openai/gpt-4o", callbacks=[mi_callback])

# Inspeccion de trazas
result = predict(question="...")
print(dspy.inspect_history(n=1))
```

### Guardado y Carga

```python
# Guardar programa optimizado
programa_optimizado.save("modelo.json")

# Cargar
programa = MiModulo()
programa.load("modelo.json")
```

---

## Resultados Tipicos

### Mejoras con Optimizacion

| Tarea | Zero-shot | BootstrapFewShot | MIPROv2 |
|-------|-----------|------------------|---------|
| QA Simple | 45% | 72% | 78% |
| Multi-hop QA | 25% | 58% | 68% |
| Clasificacion | 60% | 85% | 89% |
| Extraccion | 40% | 70% | 76% |

### Factores que Afectan Rendimiento

1. **Calidad de datos de entrenamiento**: Mas ejemplos diversos = mejor
2. **Eleccion de optimizador**: MIPROv2/GEPA > BootstrapFewShot para tareas complejas
3. **Modelo base**: Modelos mas grandes generalmente mejor
4. **Diseno de signature**: Descripciones claras mejoran resultados

---

## Proveedores de Modelos Soportados

### Via LiteLLM

| Proveedor | Ejemplo de Modelo |
|-----------|-------------------|
| OpenAI | `openai/gpt-4o`, `openai/gpt-4o-mini` |
| Anthropic | `anthropic/claude-3-opus` |
| Google | `google/gemini-pro` |
| Cohere | `cohere/command` |
| Mistral | `mistral/mistral-large` |
| Local (Ollama) | `ollama/llama2` |
| Azure | `azure/gpt-4` |
| AWS Bedrock | `bedrock/anthropic.claude-v2` |

### Configuracion de Proveedor

```python
# OpenAI
lm = dspy.LM("openai/gpt-4o", api_key="sk-...")

# Anthropic
lm = dspy.LM("anthropic/claude-3-opus-20240229", api_key="...")

# Local con Ollama
lm = dspy.LM("ollama/llama2", api_base="http://localhost:11434")

# Azure
lm = dspy.LM(
    "azure/gpt-4",
    api_key="...",
    api_base="https://xxx.openai.azure.com"
)
```

---

## Recursos y Referencias

### Documentación Interna del Proyecto

Para profundizar en temas específicos, consultar:

- **Diseño de Sistemas**: `docs/DSPY_GUIA_DISENO.md` (Patrones, elección de módulos y optimizadores)
- **Predictores**: `docs/DSPY_PREDICTORES_AVANZADOS.md` (Detalle de CoT, ReAct, BestOfN, etc.)
- **Artefactos y Persistencia**: `docs/DSPY_ARTEFACTOS_SALIDA.md` (Manejo de JSON, Pickles, Predictions)

### Documentación Oficial

- **Sitio web**: https://dspy.ai/
- **GitHub**: https://github.com/stanfordnlp/dspy
- **Tutoriales**: https://dspy.ai/tutorials/

### Papers Academicos

1. **DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines** (Oct 2023)
2. **DSPy Assertions: Computational Constraints for Self-Refining Language Model Pipelines** (Dec 2023)
3. **Demonstrate-Search-Predict: Composing Retrieval and Language Models** (Dec 2022)
4. **GEPA: Generalized Prompt Adaptation** (Jul 2025)

### Comunidad

- Discord: https://discord.gg/dspy
- Twitter: @lateinteraction

---

## Resumen

DSPy transforma la manera de construir aplicaciones con LLMs:

| Aspecto | Beneficio |
|---------|-----------|
| **Programacion** | Codigo Python en lugar de prompts |
| **Modularidad** | Componentes reutilizables |
| **Optimizacion** | Mejora automatica con datos |
| **Portabilidad** | Funciona con multiples LLMs |
| **Evaluacion** | Framework integrado de testing |
| **Produccion** | Cache, async, streaming |

**Flujo recomendado**:
1. Definir Signature con tipos claros
2. Usar ChainOfThought para tareas complejas
3. Optimizar con BootstrapFewShot o MIPROv2
4. Evaluar y iterar
