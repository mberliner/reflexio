# Guion de Demo — GEPA Standalone

**Duracion:** 10-12 minutos
**Audiencia:** Tecnica (ingenieros, MLEs, arquitectos de IA)
**Enfoque:** Entradas, operacion y salidas. Sin internos.

Ejecutar `demo.sh` para avanzar entre secciones. El optimizer corre por separado en el paso 3.

---

## 1 — El Problema en Una Frase

> "Optimizar un prompt hoy es trial-and-error manual. GEPA lo automatiza: le das
> datos etiquetados, un prompt inicial y un presupuesto. El devuelve el mejor
> prompt que encontro."

---

## 2 — Que Necesita GEPA (Inputs)

Cuatro inputs. Tres de experimento + uno de infraestructura.

### Input 1: Dataset — `experiments/datasets/email_urgency.csv`

30 filas, 3 columnas. Distribucion: 15 train / 10 val / 5 test.

```
split,text,urgency
train,"URGENTE: ¡Servidor caído! Producción afectada. ¡Necesitamos acción inmediata!",urgent
train,"CRÍTICO: Brecha de seguridad detectada en sistema de pagos. ¡Actúa AHORA!",urgent
train,"Caída del sistema - todos los servicios fuera de línea. Clientes llamando. ¡Por favor escalar ASAP!",urgent
train,"Hola, cuando tengas tiempo, podrías revisar el reporte trimestral? Sin prisa.",low
val,"ASAP: Reunión de junta directiva en 1 hora, ¡falta la presentación!",urgent
val,"Aviso: Nueva política efectiva el próximo mes. Detalles adjuntos.",low
val,"Recordatorio: Reportes de gastos vencen al final de la semana.",normal
val,"Importante: Revisar contrato antes del fin del día para reunión de mañana.",urgent
test,"Alerta roja: ¡Base de datos corrupta! ¡Se necesita restauración de respaldo inmediatamente!",urgent
test,"Compartiendo algunas ideas sobre la estrategia Q3. Avísame qué piensas.",low
test,"Por favor completa el módulo de capacitación antes de fin de mes. Requerido para cumplimiento.",normal
test,"Bug crítico en producción. Usuarios reportando fallas de login. ¡Necesitamos arreglarlo ASAP!",urgent
test,"Recordatorio amable: Evento de integración del equipo el próximo viernes. Confirma si asistes.",low
```

**Para que sirve cada split:**

| Split   | Tamano | Rol durante la optimizacion                                                                  |
|---------|--------|----------------------------------------------------------------------------------------------|
| `train` | 15     | Conjunto de **reflexion**. GEPA evalua el prompt actual aqui y le pasa los errores al LLM Profesor para que proponga mutaciones. Es el material del que el optimizador "aprende". |
| `val`   | 10     | Conjunto de **seleccion**. Cada prompt mutado se prueba contra val. El score en val decide si la mutacion entra al pool de candidatos. Es el "juez" de la optimizacion. |
| `test`  | 5      | Conjunto de **verificacion final**. GEPA NO lo ve durante la optimizacion. Se usa al terminar para medir si el prompt optimizado generaliza, o si solo memorizo train/val (overfitting). |

> "El split `test` es la garantia de honestidad: si el score en test es similar
> al de val, el optimizador encontro un patron real. Si test cae mucho respecto
> a val, hay overfitting al material visto."

### Input 2: Prompt inicial — `experiments/prompts/email_urgency_v1.json`

```json
{
    "system_prompt": "Clasifica la urgencia del siguiente email en: urgent, normal o low.\nResponde solo con el nivel de urgencia."
}
```

> "Una sola instruccion. No tiene que ser buena. GEPA parte de ahi y la
> evoluciona automaticamente usando los errores del modelo como feedback."

### Input 3: Configuracion — `experiments/configs/email_urgency.yaml`

```yaml
case:
  name: "email_urgency"
  title: "Email Urgency"
  description: "Clasificacion de urgencia de emails corporativos"

adapter:
  type: "classifier"
  valid_classes:
    - "urgent"
    - "normal"
    - "low"
  max_text_length: 1000
  max_positive_examples: 2

data:
  csv_filename: "email_urgency.csv"
  input_column: "text"
  output_columns:
    - "urgency"

models:
  temperature: 0.1

prompt:
  filename: "email_urgency_v1.json"

optimization:
  max_metric_calls: 50
  skip_perfect_score: true
  display_progress_bar: true
```

> "`max_metric_calls: 50` es el presupuesto maximo de evaluaciones.
> `skip_perfect_score: true` detiene la busqueda al alcanzar 100%.
> `prompt.filename` apunta al JSON versionado en git."

### Input 4: Modelos — `.env` (estrategia Profesor-Estudiante)

```bash
# Modelo de tarea: corre en cada evaluacion y en produccion. Barato y rapido.
LLM_MODEL_TASK=azure/gpt-4.1-mini

# Modelo de reflexion: solo durante optimizacion. Caro pero potente.
LLM_MODEL_REFLECTION=azure/gpt-4o
```

> "**Aqui esta la clave del ROI.** El modelo caro (Profesor) reflexiona sobre los
> errores y propone mutaciones. El barato (Estudiante) ejecuta la tarea — tanto
> durante optimizacion como despues en produccion. Pagas la inteligencia de
> GPT-4o una sola vez para destilar instrucciones que un modelo 10x mas barato
> sabe seguir."

---

## 3 — La Operacion (optimizer — corre por separado)

```bash
# Desde la raiz del repo
python -m gepa_standalone.universal_optimizer \
    --config gepa_standalone/experiments/configs/email_urgency.yaml
```

Salida esperada:

```
Baseline: 60.0%

GEPA Optimization:  20%|## | 10/50
Iteration 1: Found a better program with score 0.9.
Iteration 3: Found a better program with score 1.0.
Iteration 5: All subsample scores perfect. Skipping.

Baseline:   60.0%
Optimizado: 100.0%
Mejora:     +40.0%
Presupuesto usado: 51 llamadas

DETALLE DE RESULTADOS (TEST SET)
TEXTO (Inicio)                           | PREDICCION | ESPERADO | CORRECTO
Alerta roja: Base de datos corrupta...   | urgent     | urgent   | SI
Compartiendo ideas sobre estrategia Q3...| low        | low      | SI
Por favor completa modulo capacitacion...| normal     | normal   | SI
Bug critico en produccion. Login fail... | urgent     | urgent   | SI
Recordatorio: Evento integracion equipo..| low        | low      | SI
```

> "5 iteraciones de 50 posibles. Se detuvo porque alcanzo score perfecto.
> El test set —que GEPA nunca toco durante la optimizacion— tambien dio 100%.
> **Tiempo: ~1 minuto. Costo aproximado: $0.09 USD.**"

---

## 4 — Que Produce (Outputs)

### Output 1: Archivos del run

```
results/runs/email_urgency/<timestamp>/
  config_snapshot.yaml   # config exacta usada — reproducibilidad garantizada
  final_prompt.txt       # prompt ganador listo para produccion
  initial_prompt.txt     # prompt de partida
  results.json           # scores: baseline, optimizado, test
  run.json               # seed, modelos, timestamp
```

> "El prompt ganador esta listo para produccion. El snapshot garantiza que
> cualquier persona puede reproducir exactamente este experimento."

### Output 2: Prompt inicial vs optimizado

**Inicial (1 linea):**
```
Clasifica la urgencia del siguiente email en: urgent, normal o low.
Responde solo con el nivel de urgencia.
```

**Optimizado (generado por reflexion automatica):**
```
Clasifica la urgencia del siguiente email segun las siguientes categorias:
'urgent', 'normal' o 'low'. Responde unicamente con el nivel de urgencia.

1. Criterios para 'urgent':
   - El mensaje implica una accion inmediata o situacion critica.
   - Amenazas que comprometan operaciones significativas.
   - Solicitudes explicitas de atencion inmediata.

2. Criterios para 'normal':
   - El mensaje requiere atencion razonable, pero no es critico.
   - Recordatorios sin plazos extremadamente cortos.

3. Criterios para 'low':
   - El mensaje no requiere accion inmediata.
   - Correos informativos sin plazos especificos.

4. Errores comunes identificados:
   - "FYI - Cliente considerando competencia. Quizas hacer seguimiento"
     -> clasificar como 'normal', no 'urgent'.
   ...
```

> "GEPA no solo mejora el score: genera documentacion de criterios lista
> para produccion, auditoria y onboarding."

### Output 3: Leaderboard comparativo

```bash
python analyze leaderboard
```

```
Caso                    | Runs | Base%  | Opt%   | Rob%   | Delta%
Email Urgency           | 141  | 59,95  | 81,58  | 83,87  | +23,92
Email Urgency Classif.  |  21  | 60,00  | 88,57  | 99,05  | +39,05
RAG Optimization        |  27  | 52,08  | 84,49  | 93,98  | +41,90
CV Extraction           | 126  | 60,00  | 84,14  | 83,44  | +23,44
Text-to-SQL             | 116  | 36,55  | 55,44  | 69,24  | +32,69
```

### Output 4: Evolucion temporal del caso

```bash
python analyze stats --case "Email Urgency"
```

```
Lote 0 -> Lote 1 -> Lote 2:
  gpt-4.1-mini/gpt-4o  |  Opt: 86.3% v 83.3% v 80.0%  |  Rob: 96.3% v 93.3%
```

> "Con multiples runs se ve si el resultado es estable o fue suerte,
> y si la calidad evoluciona entre sesiones de experimentacion."

---

## 5 — Como Definir el Adapter

El adapter es lo que conecta tu dominio con el motor de GEPA. Hay 4 tipos
built-in; eliges uno en el YAML cambiando una sola linea:

| `adapter.type` | Entrada              | Salida esperada       |
|----------------|----------------------|-----------------------|
| `classifier`   | texto libre          | etiqueta de clase     |
| `extractor`    | texto CV             | campos estructurados  |
| `sql`          | pregunta + schema    | query SQL             |
| `rag`          | pregunta + documentos| respuesta con fuente  |

```yaml
adapter:
  type: "classifier"               # <- elegis el tipo aqui
  valid_classes: [urgent, normal, low]
```

> "Si tu caso encaja en alguno de los 4 tipos, no escribis codigo: solo
> configuras el YAML. Si necesitas un tipo nuevo, heredas de `BaseAdapter`
> e implementas 2 metodos. El resto del framework lo heredas gratis."

---

## 6 — ROI en Tres Numeros

```
Costo de una optimizacion:   $0.09 - $0.49  (la que acabamos de correr: $0.09)
Punto de equilibrio:         ~100 llamadas en produccion
ROI a 10,000 llamadas/mes:   4,647% - 17,053%
```

> "Recordas el `.env` con Profesor (gpt-4o) y Estudiante (gpt-4.1-mini)?
> Esto es la consecuencia: gastas el modelo caro UNA vez para destilar
> instrucciones, y corres en produccion con un modelo ~10x mas barato.
> Punto de equilibrio en ~100 llamadas. Ver ROI_ANALYSIS.md."

---

## Preguntas Frecuentes

| Pregunta                    | Respuesta                                                    |
|-----------------------------|--------------------------------------------------------------|
| Cuanto cuesta?              | Entre $0.09 y $0.49 segun el caso y `max_metric_calls`       |
| Como se evita overfitting?  | El split `test` del CSV nunca lo toca GEPA al optimizar      |
| Es reproducible?            | Si. `config_snapshot.yaml` + `run.json` con seed y modelos  |

---

## Comandos del Dia

```bash
# Desde la raiz del repo (necesario para que 'import shared' resuelva)
python -m gepa_standalone.universal_optimizer \
    --config gepa_standalone/experiments/configs/email_urgency.yaml

# Tambien desde la raiz del repo
python analyze leaderboard
python analyze stats --case "Email Urgency"
```
