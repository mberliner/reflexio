# Plan: Sistema de Extraccion de Requerimientos desde Transcripciones con DSPy

## Contexto

### Problema
El proyecto necesita extraer **requerimientos detallados** desde transcripciones de conversaciones (2h+) entre usuarios, testers y desarrolladores. Estas conversaciones describen:
- Funcionalidad existente del producto
- Intenciones y expectativas de negocio
- Casos de uso para desarrollo y testing

### Por que DSPy es la solucion adecuada

**DSPy es excelente para este caso de uso porque:**

1. **Optimizacion automatica de prompts**: En lugar de iterar manualmente prompts para extraer requerimientos, GEPA optimiza automaticamente las instrucciones mediante reflexion evolutiva.

2. **Estructura modular**: Las Signatures de DSPy permiten definir exactamente que campos extraer (funcionales, no funcionales, reglas de negocio) de forma declarativa.

3. **Metricas configurables**: Permite validar la calidad de extraccion con metricas personalizadas (recall, precision, completitud estructural).

4. **Predictores avanzados**: ChainOfThought y Refine son ideales para tareas de analisis profundo de texto que requieren razonamiento.

5. **Componentes reutilizables**: El proyecto ya tiene `DynamicModuleFactory`, metricas dinamicas, y adaptadores probados para extraccion estructurada.

### Objetivos del plan

- **Primario**: Validar viabilidad de DSPy para extraccion de requerimientos con un MVP funcional
- **Secundario**: Establecer arquitectura escalable para transcripciones muy largas (futuro)
- **Restricciones**: Presupuesto moderado ($10-30), balance costo/calidad

---

## Enfoque de Implementacion

### Estrategia: MVP incremental en 2 fases

Dado que estamos explorando viabilidad y no hay dataset anotado completo, implementaremos en fases:

**Fase 1: MVP Simple (Recomendado para validacion inicial)**
- Usar `DynamicModuleFactory` existente con configuracion 100% YAML
- Predictor: `ChainOfThought` (balance costo/calidad)
- Transcripciones completas cuando entren en presupuesto de contexto, con fallback automatico para outliers
- Dataset minimo: 5-10 transcripciones anotadas (manualmente o con bootstrap LLM)
- Costo estimado: $4-6 para validacion

**Fase 2: Escalado Avanzado (Solo si MVP es exitoso)**
- Endurecer el router de longitud (chunking por defecto si el p95 de tokens lo requiere)
- Upgrade a predictor `Refine` (mejora iterativa)
- Expandir dataset a 30-50 ejemplos
- Metricas avanzadas con LLM-as-a-Judge

**Este plan se enfoca en Fase 1** para validar viabilidad rapidamente.

---

## Arquitectura de la Solucion (MVP)

### Componentes Principales

```
Transcripcion
    |
[Preflight de tokens + Length Policy]
    |-----------------------------|
    |                             |
Ruta A: Full transcript       Ruta B: Chunk + Consolidacion
    |                             |
    |-----------------------------|
                |
[ChainOfThought Predictor]
        |
5 campos de texto separados:
  - functional_requirements
  - non_functional_requirements
  - business_rules
  - assumptions
  - constraints
```

**Nota sobre truncamiento**: En el runtime actual, `adapter.max_text_length` no garantiza control efectivo de longitud dentro de GEPA. Por eso el plan incorpora control explicito en el pipeline: estimacion de tokens por ejemplo, umbral de seguridad por modelo, y enrutamiento automatico a `chunk + consolidacion` solo cuando el transcript supera el umbral.

**Nota sobre outputs**: Se usan 5 columnas separadas en lugar de 1 JSON monolitico. Esto es consistente con el patron existente del proyecto (ver `extraction_hard.csv` donde cada campo es una columna independiente). La `DynamicModuleFactory` ya soporta multiples outputs en la signature.

### Flujo de Trabajo

1. **Cargar transcripcion** desde CSV
2. **Calcular tokens estimados** y aplicar `length_policy`
3. **Rutear** a: transcript completo (si cabe) o chunking + consolidacion (si excede umbral)
4. **Extraer** 5 campos separados como texto
5. **Validar** con metrica custom (estructura + conteo de requerimientos)
6. **Optimizar** con GEPA (budget medium: 50-100 llamadas)
7. **Evaluar** en test set

### Configuracion de Modelos

- **Task Model**: `openai/gpt-4o-mini` (economico, suficiente para extraccion estructurada)
- **Reflection Model**: `openai/gpt-4o` (mas fuerte para reflexion GEPA)
- **Temperatura**: 0.1 (salida deterministica)
- **Cache**: `false` (evitar cache DSPy que oculta mejoras de GEPA)

---

## Estructura de Datos

### Dataset CSV: `requirements_extraction.csv`

**Columnas requeridas:**
```csv
split,transcript,functional_requirements,non_functional_requirements,business_rules,assumptions,constraints
```

- **`split`**: `train` (5 ejemplos) / `val` (3 ejemplos) / `test` (2 ejemplos)
- **`transcript`**: Texto completo de la transcripcion
- **`functional_requirements`**: Lista de requerimientos funcionales (texto)
- **`non_functional_requirements`**: Lista de requerimientos no funcionales (texto)
- **`business_rules`**: Lista de reglas de negocio (texto)
- **`assumptions`**: Lista de suposiciones del proyecto (texto)
- **`constraints`**: Lista de restricciones del proyecto (texto)

### Formato de cada campo de salida

Cada campo contiene una lista de items como texto, uno por linea. Sin IDs artificiales (FR-001, NFR-001, etc.) ya que el LLM inventara los suyos propios y la metrica no puede hacer matching confiable de IDs inventados.

**Ejemplo de `functional_requirements`:**
```
- El sistema debe permitir login con email y contrasena
- El email debe validarse segun RFC 5322
- La contrasena debe tener minimo 8 caracteres
- El sistema debe enviar email de verificacion al registrarse
```

**Ejemplo de `non_functional_requirements`:**
```
- El tiempo de respuesta del login no debe exceder 2 segundos bajo carga de 100 usuarios concurrentes
- El sistema debe soportar 99.9% de disponibilidad
```

**Ejemplo de `business_rules`:**
```
- Los usuarios con rol admin pueden crear otros usuarios
- Solo el propietario de la cuenta puede modificar datos de facturacion
```

**Ejemplo de `assumptions`:**
```
- La base de datos esta alojada en AWS
- Se asume disponibilidad del servicio de email SMTP
```

**Ejemplo de `constraints`:**
```
- Presupuesto maximo: $50,000
- Debe completarse en 3 meses
```

### Como crear el dataset inicial

Ya que se tienen **transcripciones sin anotar**, el proceso sera:

1. **Seleccionar 10 transcripciones representativas** (variedad de temas, longitudes)
2. **Anotar manualmente** los 10 ejemplos:
   - Leer transcripcion
   - Identificar requerimientos funcionales mencionados
   - Extraer requerimientos no funcionales (performance, seguridad, etc.)
   - Capturar reglas de negocio, suposiciones, restricciones
   - Escribir cada campo como lista de items (un requerimiento por linea)
3. **Dividir**:
   - `train`: 5 ejemplos (para optimizacion GEPA)
   - `val`: 3 ejemplos (para validacion durante optimizacion)
   - `test`: 2 ejemplos (para evaluacion final sin sesgo)

**Estimacion realista de tiempo**: 15-20 horas para 10 transcripciones de 2h. Cada transcripcion requiere ~1.5-2h de lectura cuidadosa y anotacion.

**Estrategia de bootstrap con LLM** (reduce a ~5h):
1. Ejecutar el sistema sin optimizar sobre las 10 transcripciones
2. Usar la salida del LLM como borrador inicial del ground truth
3. Revisar y corregir manualmente cada borrador (~30min por transcripcion)
4. Esto reduce el esfuerzo de 15-20h a ~5h

**Tip**: Empezar con transcripciones **cortas** (10-15 minutos, ~5000 palabras) para agilizar anotacion manual. Expandir a transcripciones largas despues de validar MVP.

---

## Configuracion YAML

### Archivo: `dspy_gepa_poc/configs/requirements_extraction_mvp.yaml`

```yaml
case:
  name: "Requirements Extraction MVP"

module:
  type: "dynamic"

signature:
  instruction: |
    Eres un analista de requerimientos experto. Extrae requerimientos detallados,
    estructurados y accionables desde transcripciones de conversaciones entre
    usuarios, testers y desarrolladores.

    INSTRUCCIONES CRITICAS:
    1. DISTINGUE entre requerimientos funcionales (que hace el sistema) y
       no funcionales (como lo hace: performance, seguridad, usabilidad).
    2. IDENTIFICA reglas de negocio explicitas e implicitas mencionadas.
    3. CAPTURA suposiciones (assumptions) y restricciones (constraints) del proyecto.
    4. Genera cada campo como una lista de items, uno por linea, con guion inicial.
    5. Si no hay items para un campo, escribe "Ninguno identificado".

  inputs:
    - name: "transcript"
      desc: "Transcripcion completa de la conversacion entre usuarios, testers y desarrolladores."

  outputs:
    - name: "functional_requirements"
      desc: "Lista de requerimientos funcionales. Un requerimiento por linea, con guion inicial. Cada uno describe QUE debe hacer el sistema."
    - name: "non_functional_requirements"
      desc: "Lista de requerimientos no funcionales. Un requerimiento por linea, con guion inicial. Cada uno describe COMO debe comportarse el sistema (performance, seguridad, usabilidad, etc.)."
    - name: "business_rules"
      desc: "Lista de reglas de negocio. Una regla por linea, con guion inicial. Cada una describe una restriccion o logica del dominio."
    - name: "assumptions"
      desc: "Lista de suposiciones del proyecto. Una por linea, con guion inicial."
    - name: "constraints"
      desc: "Lista de restricciones del proyecto. Una por linea, con guion inicial."

data:
  csv_filename: "requirements_extraction.csv"
  input_column: "transcript"

adapter:
  max_text_length: 50000       # Limite de compatibilidad; NO usar como control principal de longitud
  max_positive_examples: 1     # Solo 1 ejemplo few-shot (transcripciones largas consumen contexto)

length_policy:
  enabled: true
  mode: "route"                # fail | truncate | route
  max_input_tokens: 90000      # Umbral operativo (80-90% del contexto real del modelo)
  chunk_tokens: 12000          # Tamano de chunk cuando se activa fallback
  chunk_overlap_tokens: 1200   # Overlap para preservar continuidad
  consolidate: true            # Consolidar y deduplicar resultados de chunks
  token_estimator: "auto"      # auto -> tiktoken si disponible, fallback chars/4

optimization:
  max_metric_calls: 100        # Budget moderado (GEPA medium)
  auto_budget: "medium"
  use_few_shot: false           # Desactivado: transcripciones largas + few-shot agota contexto
  ignore_in_metric: []          # Evaluar todos los campos de output
  match_mode: "normalized"      # Normalizar espacios/puntuacion en comparaciones
  fuzzy_threshold: 0.85         # Umbral de similitud para fuzzy matching
  metric_module: "dspy_gepa_poc.requirements_metric"
  metric_function: "requirements_completeness_metric"

models:
  temperature: 0.1             # Salida deterministica
  cache: false                 # CRITICO: evitar cache DSPy que oculta mejoras GEPA
```

**Campos eliminados vs plan original:**
- `output_columns` en modulo `dynamic`: no es necesario; los outputs se definen en `signature.outputs` (en otros tipos de modulo puede seguir aplicando).
- `few_shot_count`: Irrelevante con `use_few_shot: false`.
- `max_text_length` como control de truncamiento: reemplazado por `length_policy` en el pipeline.

---

## Metrica de Evaluacion

### Metrica adaptada a 5 outputs separados

Dado que ahora tenemos 5 campos de texto (no un JSON monolitico), la metrica evalua cada campo individualmente.

**Nivel 1: Campos no vacios (40% del score)**
- Cada uno de los 5 campos debe contener contenido (no vacio, no "Ninguno identificado" cuando el ground truth tiene items)
- Penaliza campos faltantes o vacios

**Nivel 2: Conteo de requerimientos (60% del score)**
- Compara la cantidad de items extraidos vs ground truth por campo
- Usa ratio min(pred, gold) / max(pred, gold) para penalizar tanto omisiones como exceso
- No intenta matching de IDs (inutil con texto generado por LLM)

### Implementacion

**Archivo a crear: `dspy_gepa_poc/requirements_metric.py`**

```python
"""
Metrica de evaluacion para extraccion de requerimientos.

Evalua 5 campos separados: functional_requirements, non_functional_requirements,
business_rules, assumptions, constraints.
"""

import re


REQUIREMENT_FIELDS = [
    "functional_requirements",
    "non_functional_requirements",
    "business_rules",
    "assumptions",
    "constraints",
]


def requirements_completeness_metric(
    gold, pred, trace=None, pred_name=None, pred_trace=None
):
    """
    Evalua la calidad de extraccion de requerimientos.

    Scoring:
    - 40%: Campos no vacios (presencia de contenido)
    - 60%: Conteo de requerimientos vs ground truth

    Interfaz compatible con GEPA: acepta pred_name para feedback.

    Args:
        gold: Ejemplo con campos de ground truth
        pred: Prediction con campos generados
        trace: Opcional, para debugging
        pred_name: Si no es None, GEPA solicita feedback (retorna dict)
        pred_trace: Trace del predictor

    Returns:
        float (0.0-1.0) para evaluacion normal
        dict {"score": float, "feedback": str} cuando GEPA solicita feedback
    """
    # Nivel 1: Campos no vacios (40%)
    presence_score = _evaluate_presence(gold, pred)

    # Nivel 2: Conteo de requerimientos (60%)
    count_score, field_details = _evaluate_counts(gold, pred)

    total_score = presence_score * 0.4 + count_score * 0.6

    # Si GEPA solicita feedback, retornar dict
    if pred_name is not None or pred_trace is not None:
        feedback = _generate_feedback(total_score, field_details)
        return {"score": total_score, "feedback": feedback}

    return total_score


def _count_items(text: str) -> int:
    """Cuenta items en un campo de texto (lineas con guion o contenido)."""
    if not text or not text.strip():
        return 0
    text = text.strip()
    # Contar lineas que empiezan con guion
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    bullet_lines = [line for line in lines if re.match(r"^[-*]", line)]
    if bullet_lines:
        return len(bullet_lines)
    # Si no hay guiones, contar lineas no vacias
    return len(lines)


def _evaluate_presence(gold, pred) -> float:
    """Evalua que los campos con contenido en gold tambien tengan contenido en pred."""
    fields_with_content = 0
    fields_present = 0

    for field in REQUIREMENT_FIELDS:
        gold_val = str(getattr(gold, field, "")).strip()
        pred_val = str(getattr(pred, field, "")).strip()

        gold_count = _count_items(gold_val)
        if gold_count > 0:
            fields_with_content += 1
            if _count_items(pred_val) > 0:
                fields_present += 1

    if fields_with_content == 0:
        return 1.0
    return fields_present / fields_with_content


def _evaluate_counts(gold, pred) -> tuple[float, dict]:
    """Evalua conteo de requerimientos por campo."""
    field_scores = {}
    total_score = 0.0
    scored_fields = 0

    for field in REQUIREMENT_FIELDS:
        gold_val = str(getattr(gold, field, "")).strip()
        pred_val = str(getattr(pred, field, "")).strip()

        gold_count = _count_items(gold_val)
        pred_count = _count_items(pred_val)

        if gold_count == 0 and pred_count == 0:
            score = 1.0
        elif gold_count == 0 or pred_count == 0:
            score = 0.0
        else:
            # Ratio: penaliza tanto omisiones como exceso
            score = min(gold_count, pred_count) / max(gold_count, pred_count)

        field_scores[field] = {
            "gold_count": gold_count,
            "pred_count": pred_count,
            "score": score,
        }
        total_score += score
        scored_fields += 1

    avg_score = total_score / scored_fields if scored_fields > 0 else 0.0
    return avg_score, field_scores


def _generate_feedback(total_score: float, field_details: dict) -> str:
    """Genera feedback textual para GEPA."""
    if total_score >= 0.9:
        return "Excelente extraccion. Todos los campos estan bien cubiertos."

    issues = []
    for field, details in field_details.items():
        gold_c = details["gold_count"]
        pred_c = details["pred_count"]
        if gold_c > 0 and pred_c == 0:
            issues.append(f"{field}: campo vacio (esperados {gold_c} items)")
        elif gold_c > pred_c:
            issues.append(
                f"{field}: faltan items ({pred_c}/{gold_c} extraidos)"
            )
        elif pred_c > gold_c * 2:
            issues.append(
                f"{field}: demasiados items ({pred_c} vs {gold_c} esperados)"
            )

    if issues:
        return "Problemas: " + "; ".join(issues)
    return f"Score {total_score:.2f}. Revisar completitud de campos."
```

**Interfaz GEPA correcta**: La metrica usa `pred_name` como parametro (no `trace.feedback = ...`). Cuando GEPA solicita feedback, retorna `{"score": float, "feedback": str}` -- consistente con las metricas existentes en `metrics.py` (ver `sentiment_with_feedback_metric` y `extraction_with_feedback_metric`).

---

## Archivos a Crear

### 1. Dataset

**Archivo**: `dspy_gepa_poc/datasets/requirements_extraction.csv`

**Proceso de creacion**:
1. Seleccionar 10 transcripciones existentes sin anotar
2. Anotar manualmente o con bootstrap LLM (ver seccion "Como crear dataset inicial")
3. Guardar en formato CSV con columnas: `split`, `transcript`, `functional_requirements`, `non_functional_requirements`, `business_rules`, `assumptions`, `constraints`

**Ejemplo de fila:**
```csv
split,transcript,functional_requirements,non_functional_requirements,business_rules,assumptions,constraints
train,"[Usuario]: Necesitamos que el login funcione con email...","- El sistema debe permitir login con email y contrasena
- El email debe validarse segun RFC 5322","- Tiempo de respuesta del login menor a 2 segundos","- Usuarios admin pueden crear otros usuarios","- Base de datos en AWS","- Presupuesto maximo $50000"
```

### 2. Configuracion YAML

**Archivo**: `dspy_gepa_poc/configs/requirements_extraction_mvp.yaml`

(Ver seccion "Configuracion YAML" arriba)

### 3. Metrica Custom

**Archivo**: `dspy_gepa_poc/requirements_metric.py`

(Ver seccion "Metrica de Evaluacion" arriba)

---

## Archivos a Modificar

### 1. `dspy_gepa_poc/reflexio_declarativa.py`

**Cambio**: Agregar soporte para metricas custom desde modulos externos.

**Ubicacion**: Metodo `create_module_and_metric()` (lineas 122-184)

**Modificacion**: Agregar un bloque al inicio de la seccion de creacion de metrica (despues de crear el modulo en linea ~140, antes de crear la metrica dinamica en linea ~142):

```python
def create_module_and_metric(self):
    """Factory method to instantiate the correct Module and Metric."""
    module_type = self.config.raw_config["module"]["type"]
    print(f"Creating module for type: {module_type}")

    if module_type == "dynamic":
        # 1. Create Module from YAML (existente, sin cambios)
        sig_config = self.config.raw_config.get("signature")
        if not sig_config:
            raise ValueError(
                "Module type is 'dynamic' but no 'signature' section found in config."
            )

        predictor_type = self.config.raw_config.get("optimization", {}).get(
            "predictor_type", "cot"
        )
        self.student = DynamicModuleFactory.create_module(
            sig_config, predictor_type=predictor_type
        )

        # 2. Create Metric
        opt_config = self.config.raw_config.get("optimization", {})

        # NUEVO: Soporte para metricas custom desde modulos externos
        if "metric_module" in opt_config and "metric_function" in opt_config:
            import importlib
            module_name = opt_config["metric_module"]
            function_name = opt_config["metric_function"]

            try:
                mod = importlib.import_module(module_name)
                self.metric = getattr(mod, function_name)
                print(f"Loaded custom metric: {module_name}.{function_name}")
            except (ImportError, AttributeError) as e:
                raise ConfigurationError(
                    f"Failed to load custom metric '{module_name}.{function_name}': {e}"
                )
        else:
            # Fallback: crear metrica dinamica (comportamiento actual)
            sig_config = self.config.raw_config.get("signature", {})
            output_fields = [out["name"] for out in sig_config.get("outputs", [])]
            ignore_fields = opt_config.get("ignore_in_metric", [])
            eval_fields = [f for f in output_fields if f not in ignore_fields]
            match_mode = opt_config.get("match_mode", "exact")
            fuzzy_threshold = opt_config.get("fuzzy_threshold", 0.85)

            print(f"Evaluating fields: {eval_fields} (Ignored: {ignore_fields}, Match: {match_mode})")

            self.metric = create_dynamic_metric(
                eval_fields, match_mode=match_mode, fuzzy_threshold=fuzzy_threshold
            )
            self._validate_metric_fields(eval_fields, output_fields)

        # ... resto del metodo (few-shot injection, etc.)
```

**Justificacion**: Permite usar metricas complejas (como `requirements_completeness_metric`) sin modificar la logica core de `create_dynamic_metric`. El patron es consistente: si el YAML especifica `metric_module` y `metric_function`, se importa dinamicamente; si no, se usa el comportamiento existente.

**Nota**: No existe funcion `get_metric()` en el codigo. La metrica se crea dentro de `create_module_and_metric()` (lineas 142-162 de `reflexio_declarativa.py`).

---

## Plan de Implementacion

### Fase 1: Preparacion de Datos (Manual, ~15-20 horas, o ~5h con bootstrap)

**Tareas:**
1. Seleccionar 10 transcripciones representativas de los datos sin anotar
2. Anotar manualmente o con bootstrap LLM:
   - **Opcion A (manual)**: Leer cada transcripcion y extraer requerimientos (~1.5-2h por transcripcion = 15-20h total)
   - **Opcion B (bootstrap + revision)**: Ejecutar el sistema sin optimizar, revisar y corregir salidas (~30min por transcripcion = ~5h total)
3. Crear archivo CSV `requirements_extraction.csv` con 7 columnas
4. Validar CSV con `CSVValidator`

**Output esperado:**
- `dspy_gepa_poc/datasets/requirements_extraction.csv` con 10 filas (5 train, 3 val, 2 test)

---

### Fase 2: Configuracion y Metrica (Codigo, ~2-3 horas)

**Tareas:**
1. Crear `dspy_gepa_poc/requirements_metric.py` con metrica de completitud
2. Crear `dspy_gepa_poc/configs/requirements_extraction_mvp.yaml` con configuracion completa
3. Crear `dspy_gepa_poc/length_guard.py` (estimacion de tokens + chunking semantico + consolidacion)
4. Modificar `dspy_gepa_poc/reflexio_declarativa.py` para soportar:
   - metricas custom
   - `length_policy` y enrutamiento de longitud antes de ejecutar el modulo
5. Validar configuracion YAML con `BaseConfigValidator`

**Orden de implementacion:**
1. `requirements_metric.py` (metrica standalone, testeable independientemente)
2. `requirements_extraction_mvp.yaml` (configuracion declarativa)
3. `length_guard.py` (control de longitud en pipeline)
4. `reflexio_declarativa.py` (metricas custom + enrutamiento por longitud)

**Archivos afectados:**
- `dspy_gepa_poc/requirements_metric.py` (nuevo)
- `dspy_gepa_poc/configs/requirements_extraction_mvp.yaml` (nuevo)
- `dspy_gepa_poc/length_guard.py` (nuevo)
- `dspy_gepa_poc/reflexio_declarativa.py` (modificado, `create_module_and_metric` + hook de preflight/routing)

---

### Fase 3: Validacion Local (Testing, ~1 hora)

**Tareas:**
1. Ejecutar experimento y usar la medicion baseline que el script imprime antes de optimizar:
   ```bash
   python dspy_gepa_poc/reflexio_declarativa.py \
       --config dspy_gepa_poc/configs/requirements_extraction_mvp.yaml
   ```

2. Verificar salida:
   - Campos generados contienen texto (no vacios)
   - Metrica retorna score razonable (>0.3 para baseline)
   - Sin errores tecnicos

3. Revisar logs en `dspy_gepa_poc/results/Requirements Extraction MVP/`:
   - `run.json`: Metadata de reproducibilidad
   - `metrics.csv`: Score por ejemplo
   - `config_snapshot.yaml`: Configuracion usada

**Criterios de exito**: ver seccion **Criterio de Go/No-Go**.

---

### Fase 4: Optimizacion con GEPA (~30-60 minutos de ejecucion)

**Tareas:**
1. Ejecutar optimizacion completa:
   ```bash
   python dspy_gepa_poc/reflexio_declarativa.py \
       --config dspy_gepa_poc/configs/requirements_extraction_mvp.yaml
   ```

2. GEPA ejecutara ~100 llamadas LLM (budget medium):
   - Genera prompts candidatos
   - Evalua en trainset y valset
   - Reflexiona sobre errores
   - Evoluciona instrucciones

3. Monitorear progreso en logs de consola

**Costo estimado:**
- Ver seccion "Presupuesto y Costos" para desglose detallado

---

### Fase 5: Evaluacion y Analisis (~30 minutos)

**Tareas:**
1. Evaluar modulo optimizado en test set:
   ```bash
   # El script ya evalua automaticamente en test set al final
   ```

2. Generar analisis con CLI unificado:
   ```bash
   ./analyze leaderboard --experiment "Requirements Extraction MVP"
   ./analyze roi --experiment "Requirements Extraction MVP"
   ./analyze stats --experiment "Requirements Extraction MVP"
   ```

3. Revisar resultados:
   - **Leaderboard**: Ranking de prompts optimizados por score
   - **ROI**: Mejora baseline -> optimizado vs costo
   - **Stats**: Evolucion de score durante optimizacion

**Criterios de exito**: ver seccion **Criterio de Go/No-Go**.

---

## Validacion de la Solucion
Los criterios de evaluacion del MVP y de avance a fase de produccion se consolidan en la seccion **Criterio de Go/No-Go** para evitar duplicidad.

---

## Consideraciones Especiales

### 1. Manejo de Transcripciones Largas

**Contexto**: Una transcripcion de 2 horas produce aproximadamente 15,000-20,000 palabras (~30k tokens). Los modelos modernos (GPT-4o-mini: 128k tokens, GPT-4o: 128k tokens) pueden procesar esto sin problemas.

**Solucion MVP (Fase 1)**:
- **Control explicito en pipeline** (no confiar en `adapter.max_text_length`):
  1. Estimar tokens por transcript (`tiktoken` o fallback chars/4)
  2. Comparar contra `length_policy.max_input_tokens`
  3. Rutear por ejemplo:
     - Si cabe: transcript completo
     - Si excede: chunking + consolidacion
- Registrar telemetria por run: `% routeados`, `chunks_promedio`, `tokens_estimados`

**Solucion Avanzada (Fase 2, futuro)**:
- Activar **chunking por defecto** si distribucion real lo exige (ej. p95 > `max_input_tokens`)
- Mejorar consolidacion con reglas de deduplicacion por similitud semantica y trazabilidad de evidencia

### 2. Calidad de las Anotaciones (Ground Truth)

**Desafio**: La calidad del MVP depende 100% de la calidad de las anotaciones.

**Mejores practicas**:
1. **Bootstrap con LLM + revision manual**: Mucho mas eficiente que anotar desde cero
2. **Guia de anotacion escrita**:
   - Criterios claros para distinguir funcional vs no funcional
   - Ejemplos de cada tipo de requerimiento
   - Sin IDs artificiales: solo texto descriptivo
3. **Empezar con casos simples**: Transcripciones cortas y claras para calibrar

### 3. Trampas a Evitar (segun LECCIONES_APRENDIDAS.md)

**Trampa 1: Evaluar campos de razonamiento**
- No incluir campo `reasoning` en la signature de output (ChainOfThought lo agrega automaticamente)
- Si se incluye `reasoning` explicito, agregarlo a `optimization.ignore_in_metric`

**Trampa 2: Metrica exacta en campos de texto libre**
- Usar `match_mode: "normalized"` para comparaciones de texto
- La metrica custom evita este problema al comparar conteos en lugar de texto exacto

**Trampa 3: Cache de DSPy contamina evaluacion**
- Configurar `models.cache: false` en YAML (ya incluido en config)
- No ejecutar baseline y optimizado sin limpiar cache

**Trampa 4: Datos demasiado simples (efecto techo)**
- Incluir transcripciones ambiguas, con requerimientos implicitos
- No usar solo transcripciones donde todos los requerimientos son explicitos y obvios
- **Validacion**: Si baseline obtiene >0.8, el dataset es demasiado facil

**Trampa 5: Inconsistencia de idioma**
- Si transcripciones estan en espanol, instrucciones y ground truth tambien en espanol
- Si se mezclan idiomas, documentar claramente en YAML

**Trampa 6: Configuracion en .env en lugar de YAML**
- Solo secrets (API keys) en `.env`
- Toda logica (max_iters, etc.) en YAML
- **Razon**: Permite experimentos paralelos sin colisiones

**Trampa 7: IDs arbitrarios en ground truth**
- No usar IDs como "FR-001", "NFR-001" en el ground truth
- El LLM inventara sus propios IDs y la metrica no puede hacer matching confiable
- Usar texto descriptivo y evaluar por conteo/presencia, no por ID matching

**Trampa 8: Few-shot con inputs largos**
- Con transcripciones de ~30k tokens, inyectar 2-3 ejemplos few-shot agotaria el contexto
- Configurar `use_few_shot: false` y `max_positive_examples: 1`
- GEPA optimiza las instrucciones del prompt, no necesita few-shot para mejorar

**Trampa 9: Confiar en limites de longitud que no se aplican en runtime**
- No asumir que `adapter.max_text_length` truncara automaticamente en GEPA
- Implementar `length_policy` explicita en el pipeline (preflight + routing)

### 4. Presupuesto y Costos

**Precios de referencia (GPT-4o-mini input/output):**
- Input: $0.15/1M tokens
- Output: $0.60/1M tokens
- GPT-4o (reflexion): Input $2.50/1M, Output $10.00/1M

**Desglose de costos realista (sin truncamiento, transcripciones completas):**

| Fase | Operacion | Tokens Input | Tokens Output | Costo |
|------|-----------|-------------|---------------|-------|
| Baseline | 10 ejemplos x 30k tokens input | 300k | 20k | ~$0.06 |
| GEPA Optimization | 100 iteraciones x 30k tokens avg | 3M | 200k | ~$0.57 |
| Reflection (GPT-4o) | 20 reflexiones x 5k tokens | 100k | 50k | ~$0.75 |
| Evaluacion Final | 2 ejemplos test x 30k tokens | 60k | 4k | ~$0.01 |
| **Total MVP** | | | | **~$1.40** |

**Nota**: El calculo anterior asume GPT-4o-mini para task. Con transcripciones reales de 2h, el input por ejemplo es ~30k tokens (no 3k como en el plan original que truncaba a 12k chars). Si las transcripciones son mas cortas (15min), el costo sera proporcional.

**Con multiples ejecuciones y debugging**: Estimar **$4-6 totales** para el MVP completo (incluyendo ejecuciones de prueba, debugging, re-runs).

**Escalado a produccion (post-optimizacion):**
- Costo por transcripcion de 2h: ~30k tokens input x $0.15/1M + ~2k output x $0.60/1M = ~$0.006
- Con presupuesto de $10: ~1,600 transcripciones procesadas

### 5. Extensiones Futuras (Post-MVP)

**Si el MVP es exitoso, considerar:**

1. **Predictor Refine** (mejora iterativa):
   - Configurar `predictor_type: "refine"` en YAML (si se extiende `DynamicModuleFactory`)
   - `max_iters: 2-3`
   - Costo: +50% tokens, calidad: +10-15 puntos

2. **Chunking para transcripciones extremadamente largas**:
   - Activar como default cuando p95 de tokens supere `length_policy.max_input_tokens`
   - Crear modulo custom con ventanas deslizantes + consolidacion

3. **Metricas con LLM-as-a-Judge**:
   - Agregar evaluacion cualitativa (claridad, accionabilidad, testabilidad)
   - Costo: +$0.05 por evaluacion (GPT-4o judge)
   - Util para validar requerimientos complejos

4. **User Stories automaticas**:
   - Extender signature de output para generar formato "As a... I want... So that..."
   - Integracion directa con Jira/Azure DevOps via API

---

## Archivos Criticos

Los **6 archivos mas importantes** para implementar este plan:

### 1. `dspy_gepa_poc/datasets/requirements_extraction.csv`
**Proposito**: Dataset con transcripciones anotadas (ground truth) con 7 columnas (split + transcript + 5 campos de output).

**Por que es critico**: Sin datos de calidad, ninguna optimizacion funcionara. Este dataset define que es un "buen requerimiento".

**Esfuerzo**: 15-20 horas manual, o ~5h con bootstrap LLM.

### 2. `dspy_gepa_poc/configs/requirements_extraction_mvp.yaml`
**Proposito**: Configuracion completa del experimento (signature con 5 outputs, datos, optimizacion, metrica custom).

**Por que es critico**: Es el "cerebro" del sistema. Define estructura de entrada/salida, instrucciones para el LLM, y parametros de optimizacion.

**Esfuerzo**: 30 minutos (copiar template y personalizar).

### 3. `dspy_gepa_poc/requirements_metric.py`
**Proposito**: Metrica de evaluacion (presencia de contenido + conteo de requerimientos por campo).

**Por que es critico**: GEPA usa esta metrica para optimizar. Si la metrica es incorrecta, la optimizacion optimizara para la cosa equivocada.

**Esfuerzo**: 1-2 horas (implementar evaluacion por campo + feedback GEPA).

### 4. `dspy_gepa_poc/length_guard.py`
**Proposito**: Preflight de tokens, politica de enrutamiento (`length_policy`) y fallback a chunking + consolidacion.

**Por que es critico**: Hace efectivo el control de longitud en runtime, evitando depender de limites no garantizados por GEPA.

**Esfuerzo**: 1-2 horas.

### 5. `dspy_gepa_poc/reflexio_declarativa.py` (modificacion)
**Proposito**: Orquestador principal que carga config, crea modulo, ejecuta GEPA.

**Cambio requerido**: Agregar soporte para metricas custom en `create_module_and_metric()` e integrar el hook de `length_policy`.

**Esfuerzo**: 30 minutos.

### 6. `dspy_gepa_poc/dynamic_factory.py` (sin cambios para MVP)
**Proposito**: Factory que crea Signatures y Modules desde YAML. Ya soporta multiples outputs.

**Cambio futuro (Fase 2)**: Agregar soporte para `predictor_type: "refine"`.

---

## Resumen Ejecutivo

### Es DSPy adecuado para este caso de uso?

**SI, DSPy es excelente para extraccion de requerimientos desde transcripciones.**

**Razones clave:**
1. **Optimizacion automatica**: GEPA evoluciona las instrucciones para capturar requerimientos de forma mas completa y precisa
2. **Estructura declarativa**: Se define exactamente que extraer (funcionales, no funcionales, reglas) sin iterar manualmente prompts
3. **Componentes probados**: El proyecto ya tiene factory dinamico, metricas configurables, adaptadores de extraccion
4. **Costo-beneficio**: Con presupuesto de $10-30, se pueden procesar miles de transcripciones despues de optimizacion inicial

### Ruta de Implementacion Recomendada

**Semana 1: MVP Simple**
- Anotar 10 transcripciones (5h con bootstrap LLM, o 15-20h manual)
- Implementar metrica de completitud (1-2 horas)
- Crear config YAML (30 min)
- Ejecutar experimento baseline + GEPA (1 hora)
- Evaluar viabilidad (ROI >1.0 indica exito)

**Semana 2-3: Escalado (solo si MVP exitoso)**
- Expandir dataset a 50 ejemplos
- Endurecer `length_policy` y activar chunking por defecto si p95 de tokens lo requiere
- Upgrade a predictor Refine
- Metricas avanzadas con LLM-judge

### Proximos Pasos

1. **Anotar dataset minimo** (10 transcripciones con 5 campos de requerimientos)
2. **Crear archivos del plan** (CSV, YAML, metrica)
3. **Ejecutar experimento baseline** (validar que funciona sin optimizacion)
4. **Optimizar con GEPA** (budget medium, 100 llamadas)
5. **Evaluar ROI** (mejora vs costo)
6. **Decidir**: Escalar a produccion o iterar MVP?

### Criterio de Go/No-Go

**Continuar a Fase 2 (Produccion) si:**
- Score en test set >0.6
- Mejora baseline -> optimizado >15pp
- ROI >1.0 (mejora justifica costo)
- Campos no vacios en >90% de casos

**Iterar MVP si:**
- Score <0.5: Revisar anotaciones, simplificar campos
- Mejora <10pp: Dataset demasiado simple (efecto techo) o muy dificil
- Campos vacios >20%: Revisar instrucciones del prompt

**Abandonar si:**
- Score baseline <0.2: Modelo no entiende la tarea (problema de instrucciones)
- GEPA no mejora baseline: Metrica incorrecta o datos de baja calidad
