# Configuracion LLM Unificada

Este documento describe el sistema de configuracion LLM del proyecto Reflexio Dicta, implementado en el modulo `shared/llm`.

## Arquitectura

```
reflexio/
├── shared/llm/              # Modulo compartido
│   ├── __init__.py          # Exports: LLMConfig, LLMConnectionError
│   ├── config.py            # LLMConfig dataclass
│   └── errors.py            # LLMConnectionError
│
├── gepa_standalone/
│   ├── .env                 # Configuracion propia
│   └── core/llm_factory.py  # Usa LLMConfig.get_lm_function()
│
└── dspy_gepa_poc/
    ├── .env                 # Configuracion propia
    └── config.py            # Usa LLMConfig.get_dspy_lm()
```

## Configuracion por Proyecto

Cada proyecto tiene su propio archivo `.env` con configuracion independiente:

### gepa_standalone/.env

```bash
# Conexion
LLM_API_KEY=tu-api-key
LLM_API_BASE=https://tu-recurso.openai.azure.com
LLM_API_VERSION=2024-02-15-preview

# Modelos
LLM_MODEL_TASK=azure/gpt-4.1-mini
LLM_MODEL_REFLECTION=azure/gpt-4o
```

Los limites de longitud y los ejemplos positivos de los adapters NO van en el
`.env`: se fijan en la seccion `adapter` del YAML (ver
`docs/YAML_CONFIG_REFERENCE.md`, seccion 2).

### dspy_gepa_poc/.env

```bash
# Conexion
LLM_API_KEY=tu-api-key
LLM_API_BASE=https://tu-recurso.openai.azure.com
LLM_API_VERSION=2024-02-15-preview

# Modelos
LLM_MODEL_TASK=azure/gpt-4.1-mini
LLM_MODEL_REFLECTION=azure/gpt-4o
```

## Variables de Entorno

| Variable | Descripcion | Requerida |
|----------|-------------|-----------|
| `LLM_API_KEY` | API key de la conexion por defecto (ver "Conexion por rol") | Si, salvo que cada rol defina la suya |
| `LLM_API_BASE` | Endpoint base (solo Azure, o proxy `openai/`) | Solo Azure |
| `LLM_API_VERSION` | Version de API Azure | No (default: 2024-02-15-preview) |
| `LLM_API_KEY_<ROL>`, `LLM_API_BASE_<ROL>`, `LLM_API_VERSION_<ROL>` | Conexion propia de un rol | No (ver "Conexion por rol") |
| `LLM_MODEL_TASK` | Modelo para tareas (estudiante) | Si, sin default |
| `LLM_MODEL_REFLECTION` | Modelo para reflexion (profesor) | Si, sin default |
| `LLM_MODEL_JUDGE` | Modelo del juez (solo RAG en `gepa_standalone`) | No (sin ella, el juez usa la configuracion del profesor) |
| `LLM_ENV_FILE` | Ruta de un `.env` adicional | No |
| `LLM_CACHE` | Cache de respuestas DSPy. Solo `false`: `true` falla al armar el LM de DSPy porque una respuesta cacheada no pasaria por el punto de llamada propio (sin uso de tokens ni `finish_reason`; SPEC-105 FR-009) | No (default: false) |

### Estrategia Profesor-Estudiante

`LLM_MODEL_TASK` y `LLM_MODEL_REFLECTION` cumplen roles distintos por diseño:

| Rol | Variable | Cuándo se usa | Perfil recomendado |
|-----|----------|---------------|--------------------|
| **Profesor** (reflexión) | `LLM_MODEL_REFLECTION` | Solo durante optimización. Lee errores del Estudiante y propone mutaciones del prompt. | Caro y potente (ej: gpt-4o) |
| **Estudiante** (tarea) | `LLM_MODEL_TASK` | Cada evaluación durante optimización Y todas las llamadas en producción. | Barato y rápido (ej: gpt-4.1-mini) |

**Por qué importa configurarlos asimétricamente:** pagás la inteligencia del modelo caro una sola vez para destilar instrucciones que un modelo ~10x más barato sabe seguir. Con esa configuración, el ROI se materializa después de ~100 llamadas en producción. Justificación económica completa con números reales en `gepa_standalone/docs/ROI_ANALYSIS.md`.

Si configurás ambos al mismo modelo (ej: gpt-4o/gpt-4o), GEPA sigue funcionando, pero perdés la ventaja económica: solo mejorás calidad, no reducís costo de inferencia.

`LLM_MODEL_TASK` y `LLM_MODEL_REFLECTION` son obligatorias y no tienen default
(SPEC-106 D12): si faltan o estan vacias, la validacion local falla antes de
cualquier llamada, nombrando el rol y la variable. Un default silencioso podria
gastar API con un modelo que nadie eligio y fijar un proveedor ancla equivocado.

## Conexion por rol (SPEC-106)

Cada rol (`task`, `reflection`, `judge` y los adicionales) resuelve su conexion
desde `LLM_API_KEY_<ROL>`, `LLM_API_BASE_<ROL>` y `LLM_API_VERSION_<ROL>`. Una
variable vacia (`VAR=`) cuenta como no definida.

**Proveedor ancla.** Las variables globales (`LLM_API_KEY`, `LLM_API_BASE`,
`LLM_API_VERSION` y su default) son la conexion por defecto y pertenecen al
proveedor de `LLM_MODEL_TASK`:

- Un rol del mismo proveedor que `task` hereda cada global que no define.
- Un rol de otro proveedor NO hereda ninguna (ni el default de
  `LLM_API_VERSION`). Si le falta la credencial, la validacion local falla antes
  de cualquier llamada, nombrando rol, proveedor y `LLM_API_KEY_<ROL>`.
- `azure`, `openai` y `anthropic` son proveedores distintos. Un modelo sin
  prefijo cuenta como `openai` (convencion de LiteLLM).
- Un `.env` sin variables por rol y con todos los roles del mismo proveedor envia
  los mismos parametros que antes (SPEC-106 FR-002).

### Ejemplo: estudiante Azure y profesor Claude

```bash
# Conexion por defecto: pertenece a Azure (proveedor de LLM_MODEL_TASK)
LLM_API_KEY=tu-api-key-azure
LLM_API_BASE=https://tu-recurso.openai.azure.com
LLM_API_VERSION=2024-02-15-preview
LLM_MODEL_TASK=azure/gpt-4.1-mini

# El profesor es de otro proveedor: su clave es propia y no hereda las globales
LLM_MODEL_REFLECTION=anthropic/claude-sonnet-5-5
LLM_API_KEY_REFLECTION=sk-ant-...
```

Sin `LLM_API_KEY_REFLECTION`, el arranque falla nombrando `reflection`,
`anthropic` y esa variable; la clave de Azure nunca se envia a Anthropic.

### Juez (solo RAG, `gepa_standalone`)

- Sin `LLM_MODEL_JUDGE`, el juez usa la configuracion resuelta del profesor
  (modelo, conexion, effort, razonamiento). Si hay alguna variable `LLM_*_JUDGE`
  definida, se ignora con un `[WARN]`.
- Con `LLM_MODEL_JUDGE`, el juez es un rol mas: `LLM_API_KEY_JUDGE`,
  `LLM_API_BASE_JUDGE`, `LLM_API_VERSION_JUDGE`, `LLM_EFFORT_JUDGE` y
  `LLM_THINKING_JUDGE`. Los overrides `models:` del YAML se aplican al juez igual
  que al profesor.
- Se valida en el mismo paso que tarea y profesor, y su uso va a un bucket
  propio (`docs/METADATA_REPRODUCIBILIDAD.md`).
- Fuera de RAG no se construye, no se valida ni se registra.

### Validacion al arrancar

Cada entry point valida solo los roles que usa (el optimizador: tarea y
profesor, mas el juez en RAG; `baseline_only.py`: solo tarea). Primero la
validacion local de todos los roles (sin red) y despues una sonda por el punto de
llamada comun, sin reintentos. Un error de credencial, modelo o endpoint nombra
el rol y la variable concreta (`LLM_API_KEY_REFLECTION`, no `LLM_API_KEY`), se
clasifica segun `docs/GEPA_MANEJO_ERRORES.md` (credencial o modelo invalido:
`configuracion`; 429 o timeout: `infraestructura`) y aborta antes de la primera
llamada de optimizacion, sin escribir `run.json`. El arranque imprime una linea
por rol: rol, proveedor, modelo y host del endpoint (nunca la credencial).

### `LLM_ENV_FILE`

Se carga cuando no hay ninguna credencial definida (ni `LLM_API_KEY` ni alguna
`LLM_API_KEY_<ROL>`), no solo cuando falta `LLM_API_KEY`. Aplica a
`shared/llm/config.py` y a `shared/utils/check_deployments.py`.

### `check_deployments.py`

Verifica cada rol (`task`, `reflection` y `judge` si hay `LLM_MODEL_JUDGE`)
contra su propio endpoint y credencial. Un rol que no es Azure se informa como
"no aplica", no como error.

## Formato de Modelos

Se usa el formato LiteLLM: `provider/model`

### Azure OpenAI
```bash
LLM_MODEL_TASK=azure/gpt-4.1-mini
LLM_MODEL_REFLECTION=azure/gpt-4o
```

### OpenAI Directo
```bash
LLM_API_KEY=sk-...
LLM_API_BASE=           # Dejar vacio
LLM_MODEL_TASK=openai/gpt-4o-mini
LLM_MODEL_REFLECTION=openai/gpt-4o
```

### Anthropic

Formato `anthropic/<id>`. La matriz de modelos soportados y sus restricciones
(que parametros se envian, effort aceptado, razonamiento) es el contrato de
[SPEC-103](../specs/SPEC-103-proveedor-anthropic.md#matriz-de-soporte); no se
copia aca. Un `<id>` puede llevar sufijo de snapshot (`-YYYYMMDD`) y recibe las
restricciones de su alias.

```bash
LLM_API_KEY=sk-ant-...
LLM_MODEL_TASK=anthropic/claude-haiku-5-5
LLM_MODEL_REFLECTION=anthropic/claude-sonnet-5-5
```

IDs vigentes: `claude-haiku-4-5`, `claude-opus-4-5`, `claude-sonnet-4-6`,
`claude-opus-4-6`, `claude-opus-4-7`, `claude-opus-4-8`, `claude-sonnet-5`,
`claude-opus-5`, `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`,
`claude-fable-5`, `claude-fable-5-1`, `claude-fable-5-2`. Un ID `anthropic/`
fuera de la matriz funciona sin restricciones y emite un aviso al arrancar.

#### `LLM_API_BASE` con Anthropic

- `validate()` no exige `LLM_API_BASE` ni `LLM_API_VERSION`; `api_version` no se envia.
- Un `LLM_API_BASE` global NO se envia a `anthropic/` ni se hereda (por ejemplo el
  endpoint Azure que quedo de otra configuracion): se emite un aviso al arrancar si
  el rol no define `LLM_API_BASE_<ROL>`. Dejarlo vacio.
- Para un proxy o gateway, `LLM_API_BASE_<ROL>` explicito SI se envia y no genera
  aviso (SPEC-106 FR-003).

#### `LLM_EFFORT_<ROL>` y `LLM_THINKING_<ROL>`

Se configuran por rol (`TASK`, `REFLECTION`, ...) en el `.env`, no en el YAML.

| Variable | Valores | Default | Efecto |
|----------|---------|---------|--------|
| `LLM_EFFORT_<ROL>` | `low`, `medium`, `high`, `xhigh`, `max` (segun el modelo) | `medium` en modelos que aceptan effort; nada en los que no | Se envia como `output_config={"effort": ...}` |
| `LLM_THINKING_<ROL>` | `default`, `off` | `default` (no envia nada) | `off` envia el mecanismo de apagado de la matriz (nada si ya esta apagado) |

- Se ignoran mayusculas y espacios; una variable vacia equivale a no configurada.
- Un valor fuera de lo permitido, un effort que el modelo no acepta, o apagar el
  razonamiento donde no se permite (o con un effort incompatible), produce un
  `LLMConfigError` al validar, con la lista de valores aceptados.
- `temperature` se omite siempre en los modelos que no la aceptan, venga de donde
  venga (YAML incluido).
- Con razonamiento activo, `max_tokens` se eleva a un minimo de 16000.
- `describe()` y `run.json` muestran los valores efectivos enviados
  (ver `docs/METADATA_REPRODUCIBILIDAD.md`).
- Con modelos `azure/` u `openai/`, `LLM_EFFORT_<ROL>` y `LLM_THINKING_<ROL>`
  no se envian: un valor valido se ignora sin aviso. Solo un valor fuera de la
  lista de la tabla produce error.
- La lista de effort es la misma para todo proveedor: `minimal` y `none`, que
  la API de OpenAI acepta, se rechazan tambien en `azure/` y `openai/`.

## Uso en Codigo

### LLMConfig

```python
from shared.llm import LLMConfig

# Cargar desde variables de entorno
task_config = LLMConfig.from_env("task")
reflection_config = LLMConfig.from_env("reflection")

# Acceder a valores
print(task_config.model)  # "azure/gpt-4.1-mini"
print(task_config.api_key)  # "tu-api-key"
print(task_config.api_base)  # "https://..."
```

### Para DSPy (dspy_gepa_poc)

```python
from shared.llm import LLMConfig
import dspy

# Obtener instancia dspy.LM
config = LLMConfig.from_env("task")
lm = config.get_dspy_lm()

# Configurar DSPy globalmente
dspy.configure(lm=lm)
```

### Para LiteLLM Directo (gepa_standalone)

```python
from shared.llm import LLMConfig

# Obtener funcion lm_func(prompt) -> str
config = LLMConfig.from_env("reflection")
lm_func = config.get_lm_function()

# Usar con GEPA
response = lm_func("Analiza este texto...")
```

### Validacion de Conexion

```python
from shared.llm import LLMConfig, LLMConnectionError

config = LLMConfig.from_env("task")

# Validar configuracion
config.validate()  # Lanza LLMConnectionError si falta config

# Probar conexion
try:
    config.validate_connection()
    print("Conexion exitosa")
except LLMConnectionError as e:
    print(e)  # Mensaje con sugerencias
```

## Modelos Adicionales

Puedes agregar modelos adicionales definiendo nuevas variables:

```bash
# En .env
LLM_MODEL_EMBEDDING=azure/text-embedding-3-small
LLM_MODEL_SUMMARY=azure/gpt-4o-mini
LLM_MODEL_CHEAP=openai/gpt-3.5-turbo
```

```python
# En codigo
embedding_config = LLMConfig.from_env("embedding")
summary_config = LLMConfig.from_env("summary")
cheap_config = LLMConfig.from_env("cheap")
```

## Overrides en Codigo

Puedes sobrescribir valores al cargar:

```python
config = LLMConfig.from_env("task", temperature=0.0, max_tokens=500)
```

## Errores y Diagnostico

`LLMConnectionError` proporciona mensajes estructurados con sugerencias:

```
============================================================
LLM CONNECTION ERROR
============================================================

Message: Authentication failed - invalid API key

Configuration:
  - Provider: azure
  - Model: azure/gpt-4.1-mini
  - Endpoint: https://tu-recurso.openai.azure.com

Original error:
  401 Unauthorized

Suggested actions:
  1. Verify LLM_API_KEY in .env file (o la variable del rol, ej. LLM_API_KEY_REFLECTION)
  2. Regenerate API key in Azure/OpenAI portal

============================================================
```

## Migracion desde Configuracion Anterior

### Antes (variables separadas)
```bash
AZURE_OPENAI_API_KEY=xxx
AZURE_OPENAI_ENDPOINT=https://...
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini
AZURE_OPENAI_REFLECTION_DEPLOYMENT=gpt-4o
```

### Despues (formato unificado)
```bash
LLM_API_KEY=xxx
LLM_API_BASE=https://...
LLM_MODEL_TASK=azure/gpt-4.1-mini
LLM_MODEL_REFLECTION=azure/gpt-4o
```

## Dependencias

El modulo usa **LiteLLM** como cliente unificado. 

Para consultar las versiones exactas de las librerías utilizadas, consulte el archivo central de dependencias:

**SSOT de Versiones:** `requirements.txt`

## Referencias

- [LiteLLM Documentation](https://docs.litellm.ai/)
- [LiteLLM Azure Configuration](https://docs.litellm.ai/docs/providers/azure)
- [DSPy Language Models](https://dspy.ai/learn/programming/language_models/)
