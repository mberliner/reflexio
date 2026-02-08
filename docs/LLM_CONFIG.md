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

# Adapters (opcional)
CLASSIFIER_TEXT_MAX_LENGTH=1000
EXTRACTOR_TEXT_MAX_LENGTH=1000
RAG_CONTEXT_MAX_LENGTH=1500
RAG_MAX_POSITIVE_EXAMPLES=2
EXTRACTOR_MAX_POSITIVE_EXAMPLES=0
```

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
| `LLM_API_KEY` | API key para autenticacion | Si |
| `LLM_API_BASE` | Endpoint base (solo Azure) | Solo Azure |
| `LLM_API_VERSION` | Version de API Azure | No (default: 2024-02-15-preview) |
| `LLM_MODEL_TASK` | Modelo para tareas (estudiante) | No (default: azure/gpt-4.1-mini) |
| `LLM_MODEL_REFLECTION` | Modelo para reflexion (profesor) | No (default: azure/gpt-4o) |
| `LLM_CACHE` | Cache de respuestas DSPy (true/false). False = llamada fresca siempre | No (default: false) |

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
```bash
LLM_API_KEY=sk-ant-...
LLM_API_BASE=           # Dejar vacio
LLM_MODEL_TASK=anthropic/claude-3-haiku-20240307
LLM_MODEL_REFLECTION=anthropic/claude-3-5-sonnet-20241022
```

## Uso en Codigo

### LLMConfig

```python
from shared.llm import LLMConfig

# Cargar desde variables de entorno
task_config = LLMConfig.from_env("task")
reflection_config = LLMConfig.from_env("reflection")

# Acceder a valores
print(task_config.model)      # "azure/gpt-4.1-mini"
print(task_config.api_key)    # "tu-api-key"
print(task_config.api_base)   # "https://..."
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
  1. Verify LLM_API_KEY in .env file
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
