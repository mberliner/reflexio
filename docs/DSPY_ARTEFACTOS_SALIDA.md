# DSPy - Artefactos de Salida y Almacenamiento

## Descripcion General

DSPy genera varios tipos de artefactos dependiendo de la fase de trabajo. Esta guía explica **dónde y cómo** se almacena el conocimiento, los prompts y los resultados.

---

## 1. Arquitectura de Almacenamiento

| Componente | Ubicación | Persistente | Descripción |
|-----------|-----------|-------------|-------------|
| **Prompts dinámicos** | En memoria (runtime) | No | Se generan en cada llamada al módulo |
| **Signature docstrings** | Código Python | Sí | Instrucciones base en el código |
| **Few-shot examples** | Memoria / .json | Opcional | Ejemplos guardados con `.save()` |
| **Instrucciones optimizadas**| Archivo .json | Sí | Resultado de la optimización (GEPA) |
| **Cache de respuestas** | .dspy_cache/ | Opcional | Evita llamadas duplicadas al LLM |

### Prompts Dinámicos (No Persistentes)
Los prompts **no se guardan** completos. DSPy los construye en memoria combinando:
1.  Instrucciones del `signature` (docstring).
2.  Few-shot examples (`demos`).
3.  Formato de entrada/salida definido.

### Estado del Módulo (Estructura en Memoria)
Para inspeccionar un módulo (ej: `analyzer`):
- `analyzer.predictor.signature.__doc__`: Instrucciones actuales.
- `analyzer.predictor.demos`: Lista de ejemplos (vacía inicialmente).
- `type(analyzer.predictor).__name__`: Tipo de predictor (ej: `ChainOfThought`).

---

## 2. Prediction (Predicciones)

**Tipo:** Objeto Python | **Fase:** Ejecucion
**Uso:** Contiene las salidas inmediatas del programa.

```python
result = programa(question="¿Cual es la capital de Francia?")
print(result.answer)      # Acceso por atributo
print(result.reasoning)   # Si usa ChainOfThought
dict_result = result.toDict()
```

---

## 3. Archivos JSON (Estado del Programa)

**Tipo:** Archivo JSON | **Fase:** Optimizacion
**Uso:** Guardar estado optimizado (prompts + demos) sin la arquitectura.

### Guardado y Carga
```python
# Guardar después de GEPA
programa_optimizado.save("modelo.json")

# Cargar en un módulo nuevo (debe tener la misma arquitectura)
nuevo_programa = MiModulo()
nuevo_programa.load("modelo.json")
```

### ¿Qué cambia tras la optimización?
- **Antes**: Docstring básico, `demos` vacíos.
- **Después**: Docstring reescrito por el optimizador, `demos` poblados con ejemplos seleccionados.

---

## 4. Archivos Pickle (.pkl)

**Tipo:** Archivo binario | **Uso:** Objetos no serializables en JSON (Image, Audio, datetime).
**Advertencia:** Solo cargar de fuentes confiables (riesgo de ejecución de código).

---

## 5. Directorios de Programa Completo

**Tipo:** Carpeta | **Desde:** DSPy >= 2.6.0
**Uso:** Guarda **arquitectura + estado**. No requiere recrear el objeto antes de cargar.

```python
programa.save("./mi_modelo/", save_program=True)
programa = dspy.load("./mi_modelo/")
```

---

## 6. Resultados de Evaluación (CSV/JSON)

**Uso:** Exportar métricas para análisis externo.

```python
evaluator = dspy.Evaluate(devset=devset, metric=metric, save_as_csv="eval.csv")
```

| Columna | Descripción |
|---------|-------------|
| Input fields | Campos de entrada del Example |
| `predicted_*` | Campos generados por el modelo |
| `score` | Puntuación asignada por la métrica |

---

## 7. Trazas y Logs (Debug)

### Historial de Llamadas
```python
print(lm.history) # Ver prompts y respuestas crudas
dspy.inspect_history(n=3) # Ver últimas 3 llamadas formateadas
```

### Cache de Respuestas
DSPy cachea por defecto en `.dspy_cache/` para ahorrar tokens y acelerar el desarrollo. Se puede configurar en `dspy.LM(cache=True/False)`.

---

## Mejores Practicas

1.  **Preferir JSON sobre Pickle** para máxima portabilidad y seguridad.
2.  **Versionado**: Guardar la versión de DSPy y la fecha junto al modelo optimizado.
3.  **No modificar el JSON manualmente** a menos que sea necesario para corregir un ejemplo específico.
4.  **Limpiar la cache** (`.dspy_cache/`) si se realizan cambios profundos en las instrucciones que requieren una re-evaluación fresca.

*Documento actualizado: 2026-02-03*