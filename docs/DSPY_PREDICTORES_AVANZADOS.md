# DSPy - Predictores Avanzados

## Resumen de Predictores

DSPy ofrece varios tipos de predictores para diferentes necesidades:

| Predictor | Estrategia | Tokens | Latencia | Mejor Para |
|-----------|------------|--------|----------|------------|
| `Predict` | Respuesta directa | Bajo | Rapida | Tareas simples |
| `ChainOfThought` | Razonamiento paso a paso | Medio | Media | Tareas complejas |
| `BestOfN` | N candidatos, elige mejor | Alto (Nx) | Media* | Precision critica |
| `Refine` | Mejora iterativa | Alto | Alta | Completitud |
| `ReAct` | Razonamiento + Herramientas | Variable | Variable | Agentes con tools |
| `ProgramOfThought` | Genera codigo Python | Medio | Media | Matematicas |

*BestOfN puede paralelizarse

---

## 1. Predict (Basico)

### Concepto

Prediccion directa sin razonamiento adicional. El modelo responde inmediatamente.

```
Input ──> LLM ──> Output
```

### Uso

```python
import dspy

# Forma simple (signature inline)
predictor = dspy.Predict("question -> answer")
resultado = predictor(question="Capital de Francia?")
print(resultado.answer)  # "Paris"

# Forma con clase Signature
class Clasificador(dspy.Signature):
    """Clasifica el texto."""
    texto: str = dspy.InputField()
    categoria: str = dspy.OutputField()

predictor = dspy.Predict(Clasificador)
resultado = predictor(texto="Oferta de trabajo remoto")
print(resultado.categoria)  # "empleo"
```

### Caracteristicas

- Mas rapido y economico
- Sin overhead de razonamiento
- Ideal para tareas simples y directas

### Cuando Usar

- Clasificacion simple
- Extraccion directa
- Tareas donde el razonamiento no ayuda
- Cuando el costo/velocidad es prioritario

---

## 2. ChainOfThought

### Concepto

El modelo "piensa en voz alta" antes de responder, mostrando su razonamiento paso a paso.

```
Input ──> Razonamiento ──> Output
```

### Uso

```python
import dspy

# Forma simple
cot = dspy.ChainOfThought("question -> answer")
resultado = cot(question="Si tengo 3 manzanas y doy 1, cuantas quedan?")
print(resultado.reasoning)  # "Empiezo con 3. Doy 1. 3 - 1 = 2"
print(resultado.answer)     # "2"

# Forma con Signature
class Analisis(dspy.Signature):
    """Analiza el problema paso a paso."""
    problema: str = dspy.InputField()
    solucion: str = dspy.OutputField()

cot = dspy.ChainOfThought(Analisis)
resultado = cot(problema="...")
print(resultado.reasoning)  # Razonamiento automatico
print(resultado.solucion)
```

### Caracteristicas

- Agrega campo `reasoning` automaticamente
- Mejora precision en tareas complejas (+15-25%)
- Mas tokens pero mejor calidad

### Cuando Usar

- Problemas matematicos
- Razonamiento logico
- Tareas multi-paso
- Cuando necesitas explicabilidad

---

## 3. BestOfN

### Concepto

Genera **N candidatos** en paralelo y selecciona el mejor segun un criterio.

```
Input ──┬──> Candidato 1 ──┐
        ├──> Candidato 2 ──┼──> Selector ──> Mejor Candidato
        ├──> Candidato 3 ──┤
        └──> Candidato N ──┘
```

### Como Funciona

1. Ejecuta el predictor base N veces (con temperatura > 0)
2. Cada ejecucion produce una respuesta diferente
3. Una funcion `selector` evalua y elige la mejor

### Uso Basico

```python
import dspy

# Con selector por defecto (el LLM elige)
best_of_3 = dspy.BestOfN(
    dspy.Predict("question -> answer"),
    n=3
)

resultado = best_of_3(question="Explica la fotosintesis")
print(resultado.answer)
```

### Con Selector Personalizado

```python
import dspy

# Selector: elegir respuesta mas larga
def selector_mas_largo(candidatos):
    return max(candidatos, key=lambda c: len(c.answer))

# Selector: elegir respuesta con mayor confianza
def selector_confianza(candidatos):
    return max(candidatos, key=lambda c: float(c.confidence))

# Selector: elegir por votacion mayoritaria
def selector_votacion(candidatos):
    from collections import Counter
    votos = Counter(c.answer.lower().strip() for c in candidatos)
    respuesta_ganadora = votos.most_common(1)[0][0]
    return next(c for c in candidatos if c.answer.lower().strip() == respuesta_ganadora)

# Uso
best_of_5 = dspy.BestOfN(
    dspy.ChainOfThought("question -> answer"),
    n=5,
    selector=selector_votacion
)

resultado = best_of_5(question="Cual es la capital de Australia?")
```

### Combinado con ChainOfThought

```python
# Generar 3 razonamientos diferentes, elegir el mejor
best_cot = dspy.BestOfN(
    dspy.ChainOfThought("problema -> solucion"),
    n=3,
    selector=lambda cs: max(cs, key=lambda c: len(c.reasoning))
)
```

### Ventajas

- Mayor diversidad de respuestas
- Reduce errores aleatorios del LLM
- Puede paralelizarse para reducir latencia
- Combinable con cualquier predictor base

### Desventajas

- Costo: N veces mas tokens
- Latencia: N veces mas lento (si no se paraleliza)
- Requiere temperatura > 0 para variacion

### Cuando Usar

- Tareas donde la precision es critica
- Alta variabilidad en respuestas del LLM
- Generacion creativa (explorar opciones)
- Clasificacion con baja confianza

### Configuracion de Temperatura

```python
# Para BestOfN, necesitas temperatura > 0 para obtener variacion
lm = dspy.LM("openai/gpt-4o-mini", temperature=0.7)
dspy.configure(lm=lm)

# Con temperature=0, todos los candidatos serian iguales
```

---

## 4. Refine

### Concepto

Genera una respuesta inicial y la **mejora iterativamente** basandose en auto-critica.

```
Input ──> Respuesta v1 ──> Critica ──> Respuesta v2 ──> Critica ──> Respuesta v3 (final)
```

### Como Funciona

1. Genera respuesta inicial con el predictor base
2. Un "critico" interno evalua la respuesta
3. El predictor genera version mejorada usando el feedback
4. Repite hasta max_iters o condicion de parada

### Uso Basico

```python
import dspy

refiner = dspy.Refine(
    dspy.Predict("topic -> explanation"),
    max_iters=3
)

resultado = refiner(topic="Teoria de la relatividad")
print(resultado.explanation)  # Version refinada
```

### Con Condicion de Parada

```python
import dspy

# Parar cuando la respuesta tenga mas de 200 palabras
def esta_completa(respuesta):
    return len(respuesta.explanation.split()) > 200

refiner = dspy.Refine(
    dspy.ChainOfThought("topic -> explanation"),
    max_iters=5,
    stop_condition=esta_completa
)

resultado = refiner(topic="Mecanica cuantica")
```

### Flujo Interno Detallado

```
Pregunta: "Explica la fotosintesis"

=== Iteracion 1 ===
Input: "Explica la fotosintesis"
Output v1: "Las plantas convierten luz en energia"
Critica interna: "La respuesta es muy breve. Falta mencionar CO2,
                  agua, glucosa y el proceso en los cloroplastos."

=== Iteracion 2 ===
Input: "Explica la fotosintesis" + Critica anterior
Output v2: "La fotosintesis es el proceso donde las plantas usan
            luz solar, CO2 y agua para producir glucosa y oxigeno."
Critica interna: "Mejor, pero podria mencionar donde ocurre
                  (cloroplastos) y la importancia biologica."

=== Iteracion 3 ===
Input: "Explica la fotosintesis" + Critica anterior
Output v3: "La fotosintesis ocurre en los cloroplastos de las celulas
            vegetales. Las plantas capturan luz solar, absorben CO2 del
            aire y agua del suelo para producir glucosa (su alimento)
            y liberar oxigeno. Este proceso es fundamental para la vida
            en la Tierra ya que produce el oxigeno que respiramos."
Critica interna: "Respuesta completa y bien estructurada."

=== Resultado Final ===
Output v3 (ultima iteracion)
```

### Personalizar el Critico

```python
import dspy

class MiCritico(dspy.Signature):
    """Evalua la calidad de la respuesta."""
    respuesta: str = dspy.InputField()
    es_completa: bool = dspy.OutputField()
    sugerencias: str = dspy.OutputField()

# Refine usara este critico internamente
refiner = dspy.Refine(
    dspy.Predict("question -> answer"),
    max_iters=3,
    critic_signature=MiCritico
)
```

### Ventajas

- Mejora progresiva de calidad
- Auto-correccion de errores y omisiones
- Respuestas mas completas y pulidas
- El modelo aprende de sus propios errores

### Desventajas

- Costo: ~2x tokens por iteracion (respuesta + critica)
- Latencia: Secuencial, no paralelizable
- Puede "sobre-refinar" y perder concision
- Riesgo de loops si no mejora

### Cuando Usar

- Respuestas largas o detalladas
- Cuando la primera respuesta suele estar incompleta
- Tareas de escritura/explicacion
- Documentacion tecnica
- Resumenes comprehensivos

---

## 5. ReAct

### Concepto

`ReAct` (Reasoning + Acting) combina **razonamiento** con **acciones** usando herramientas externas. El modelo puede "pensar", ejecutar herramientas, y observar resultados.

```
Input ──> Pensar ──> Actuar (tool) ──> Observar ──> Pensar ──> ... ──> Respuesta
```

### Como Funciona

1. El modelo analiza la pregunta y "piensa" que hacer
2. Decide si necesita usar una herramienta
3. Ejecuta la herramienta y observa el resultado
4. Repite pensamiento/accion hasta tener suficiente info
5. Genera respuesta final

### Definir Herramientas

```python
# Las herramientas son funciones Python con docstrings claros
# El LLM usa el docstring para entender cuando usar cada tool

def calculadora(expresion: str) -> str:
    """
    Evalua una expresion matematica.
    Usa esta herramienta para calculos numericos precisos.
    Ejemplo: calculadora("15 * 0.20") retorna "3.0"
    """
    try:
        resultado = eval(expresion)
        return str(resultado)
    except Exception as e:
        return f"Error: {e}"

def buscar_wikipedia(tema: str) -> str:
    """
    Busca informacion en Wikipedia sobre un tema.
    Usa esta herramienta cuando necesites datos factuales.
    """
    import wikipedia
    try:
        return wikipedia.summary(tema, sentences=3)
    except:
        return f"No se encontro informacion sobre: {tema}"

def obtener_clima(ciudad: str) -> str:
    """
    Obtiene el clima actual de una ciudad.
    Retorna temperatura y condiciones.
    """
    # Implementar con API real (ej: OpenWeatherMap)
    return f"Clima en {ciudad}: 22C, soleado"

def buscar_web(query: str) -> str:
    """
    Busca informacion en la web.
    Usa para informacion actualizada o especifica.
    """
    # Implementar con API de busqueda
    return f"Resultados para '{query}': ..."
```

### Uso Basico

```python
import dspy

# Crear agente con herramientas
agente = dspy.ReAct(
    signature="question -> answer",
    tools=[calculadora, buscar_wikipedia, obtener_clima],
    max_iters=5
)

# Usar
resultado = agente(question="Cuanto es el 15% de 200?")
print(resultado.answer)  # "30"

resultado = agente(question="Cual es la poblacion de Japon?")
print(resultado.answer)  # Busca en Wikipedia y responde
```

### Flujo Interno Detallado

```
Pregunta: "Cuanto es el 15% de 350 y cual es el clima en Madrid?"

=== Paso 1 ===
Pensamiento: "Necesito calcular 15% de 350. Usare la calculadora."
Accion: calculadora("350 * 0.15")
Observacion: "52.5"

=== Paso 2 ===
Pensamiento: "El 15% de 350 es 52.5. Ahora necesito el clima de Madrid."
Accion: obtener_clima("Madrid")
Observacion: "Clima en Madrid: 22C, soleado"

=== Paso 3 ===
Pensamiento: "Tengo toda la informacion necesaria.
              15% de 350 = 52.5, Madrid tiene 22C soleado."
Accion: FINISH
Respuesta Final: "El 15% de 350 es 52.5. El clima en Madrid es
                  22 grados centigrados y soleado."
```

### Ejemplo Completo con Multiples Tools

```python
import dspy
from datetime import datetime

# Definir herramientas
def calculadora(expresion: str) -> str:
    """Evalua expresiones matematicas. Ej: calculadora('2+2')"""
    try:
        return str(eval(expresion))
    except:
        return "Error en calculo"

def fecha_actual() -> str:
    """Retorna la fecha y hora actual."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def convertir_moneda(cantidad: str, de: str, a: str) -> str:
    """
    Convierte entre monedas.
    Ejemplo: convertir_moneda("100", "USD", "EUR")
    """
    # Tasas ficticias para ejemplo
    tasas = {"USD": 1.0, "EUR": 0.85, "GBP": 0.73, "MXN": 17.5}
    try:
        monto = float(cantidad)
        en_usd = monto / tasas.get(de, 1.0)
        resultado = en_usd * tasas.get(a, 1.0)
        return f"{monto} {de} = {resultado:.2f} {a}"
    except:
        return "Error en conversion"

# Crear agente
agente = dspy.ReAct(
    signature="question -> answer",
    tools=[calculadora, fecha_actual, convertir_moneda],
    max_iters=7
)

# Preguntas complejas
resultado = agente(
    question="Cuanto es 500 dolares en euros, y cuanto seria el 10% de eso?"
)
print(resultado.answer)
# El agente:
# 1. Convierte 500 USD a EUR (425 EUR)
# 2. Calcula 10% de 425 (42.5)
# 3. Responde con ambos valores
```

### Manejo de Errores en Tools

```python
def tool_robusta(parametro: str) -> str:
    """Herramienta con manejo de errores."""
    try:
        # Logica principal
        resultado = hacer_algo(parametro)
        return str(resultado)
    except ValueError as e:
        return f"Error de valor: {e}. Intenta con otro formato."
    except ConnectionError:
        return "Error de conexion. El servicio no esta disponible."
    except Exception as e:
        return f"Error inesperado: {e}"
```

### Configuracion Avanzada

```python
agente = dspy.ReAct(
    signature="context, question -> answer",
    tools=[tool1, tool2, tool3],
    max_iters=10,           # Maximo pasos de razonamiento
    backtrack=True,         # Permitir reconsiderar decisiones
    verbose=True            # Mostrar pasos de razonamiento
)
```

### Ventajas

- Acceso a informacion externa y actualizada
- Calculos matematicos precisos (no depende del LLM)
- Interaccion con APIs y sistemas externos
- Tareas multi-paso complejas
- Explicabilidad (puedes ver el razonamiento)

### Desventajas

- Mas complejo de configurar
- Latencia impredecible (depende de las tools)
- Puede hacer loops o usar tools incorrectamente
- Costo variable (depende de iteraciones)
- Requiere manejar errores de tools

### Cuando Usar

- Preguntas que requieren datos externos/actualizados
- Calculos matematicos que deben ser precisos
- Tareas que requieren multiples pasos
- Integracion con APIs (clima, finanzas, bases de datos)
- Agentes autonomos

### Integracion con GEPA

ReAct puede optimizarse con GEPA habilitando `enable_tool_optimization`:

```python
optimizer = dspy.GEPA(
    metric=mi_metrica,
    reflection_lm=reflection_lm,
    enable_tool_optimization=True  # Optimiza uso de herramientas
)

agente_optimizado = optimizer.compile(
    student=agente,
    trainset=trainset,
    valset=valset
)
```

---

## 6. ProgramOfThought

### Concepto

Genera **codigo Python** para resolver el problema, lo ejecuta, y usa el resultado.

```
Input ──> Genera Codigo ──> Ejecuta ──> Resultado ──> Output
```

### Uso

```python
import dspy

pot = dspy.ProgramOfThought("question -> answer")

resultado = pot(question="Cuantos segundos hay en 3.5 horas?")
# Internamente genera: "3.5 * 60 * 60"
# Ejecuta y obtiene: 12600
print(resultado.answer)  # "12600"
```

### Ventajas

- Calculos precisos (ejecuta codigo real)
- Maneja problemas matematicos complejos
- Verificable (puedes ver el codigo generado)

### Desventajas

- Riesgo de seguridad (ejecuta codigo)
- Solo para problemas computables
- Puede generar codigo incorrecto

### Cuando Usar

- Problemas matematicos complejos
- Analisis de datos
- Algoritmos y logica programatica

---

## Comparacion Detallada

| Aspecto | Predict | CoT | BestOfN | Refine | ReAct | PoT |
|---------|---------|-----|---------|--------|-------|-----|
| Tokens | Bajo | Medio | Alto | Alto | Variable | Medio |
| Latencia | Baja | Media | Media* | Alta | Variable | Media |
| Precision | Base | +20% | +15% | +10% | Variable | Alta** |
| Explicable | No | Si | Parcial | Si | Si | Si |
| Paralelizable | - | - | Si | No | No | - |
| Tools externas | No | No | No | No | Si | No |
| Auto-mejora | No | No | No | Si | No | No |

*Paralelizable
**Para calculos

---

## Combinaciones Utiles

### BestOfN + ChainOfThought

```python
# Multiples razonamientos, elige el mejor
best_cot = dspy.BestOfN(
    dspy.ChainOfThought("question -> answer"),
    n=3
)
```

### Refine + ChainOfThought

```python
# Razonamiento que se mejora iterativamente
refined_cot = dspy.Refine(
    dspy.ChainOfThought("question -> answer"),
    max_iters=2
)
```

### ReAct con ChainOfThought interno

```python
# Agente que razona antes de cada accion
agente = dspy.ReAct(
    signature="question -> answer",
    tools=[...],
    predictor=dspy.ChainOfThought
)
```

---

## Implementacion en el Proyecto

Para usar estos predictores en `dspy_gepa_poc/modules.py`:

```python
class SentimentAnalyzer(dspy.Module):
    """
    Analizador de sentimientos con predictor configurable.

    Modos:
    - "predict": Respuesta directa (rapido)
    - "cot": Chain of Thought (razonamiento)
    - "best_of_n": Multiples candidatos
    - "refine": Mejora iterativa
    """

    def __init__(self, mode: str = "cot", n: int = 3, max_iters: int = 2):
        super().__init__()

        if mode == "predict":
            self.predictor = dspy.Predict(SentimentClassification)
        elif mode == "cot":
            self.predictor = dspy.ChainOfThought(SentimentClassification)
        elif mode == "best_of_n":
            self.predictor = dspy.BestOfN(
                dspy.Predict(SentimentClassification),
                n=n
            )
        elif mode == "refine":
            self.predictor = dspy.Refine(
                dspy.Predict(SentimentClassification),
                max_iters=max_iters
            )
        else:
            raise ValueError(f"Modo no soportado: {mode}")

    def forward(self, text: str) -> dspy.Prediction:
        return self.predictor(text=text)
```

---

## Referencias

- DSPy Documentation: https://dspy.ai/
- DSPy Predict API: https://dspy.ai/api/modules/Predict/
- DSPy ChainOfThought: https://dspy.ai/api/modules/ChainOfThought/
- DSPy ReAct: https://dspy.ai/api/modules/ReAct/
- Paper: "ReAct: Synergizing Reasoning and Acting in Language Models"

---

*Documento generado: 2025-12-10*
*Version DSPy: 3.0.4+*
