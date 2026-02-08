# Reflexio Dicta o Reflexio - Centro de Experimentacion para crear apps utilizando LLMs a traves de DSPy + GEPA

Este proyecto es un laboratorio de experimentacion para explorar, probar y desarrollar aplicaciones utilizando:

- **DSPy**: Framework de Stanford NLP para programar modelos de lenguaje mediante estructuras declarativas.
- **GEPA**: Optimizador de evolucion reflexiva que mejora automaticamente prompts y programas.

El objetivo es proporcionar un entorno completo para investigar las capacidades de optimizacion automatica en sistemas basados en LLM. Entener y probar la creación de soluciones automejoradas y su ROI directo.

# Reflexio Dicta, in short Reflexio

This project is an experimentation laboratory to explore, test, and develop applications using:

- **DSPy**: Stanford NLP framework for programming language models via declarative structures.
- **GEPA**: Reflexive evolution optimizer that automatically improves prompts and programs.

The goal is to provide a complete environment to investigate automatic optimization capabilities in LLM-based systems. Understanding and testing the creation of self-improving solutions and their direct ROI.

---

**Reflexio Dicta** es un nombre derivado del latín que simboliza la esencia del proyecto:
- **Reflexio**: Representa la *mutación reflexiva* (GEPA), el proceso mediante el cual el sistema analiza sus propios fallos para auto-mejorarse.
- **Dicta**: Se refiere a "lo declarado" o "lo prescrito", representando las *Signatures* declarativas (DSPy) que definen el comportamiento deseado de la IA.

En conjunto, el nombre define un ecosistema donde **la declaración es el objeto de la reflexión**.

## Caracteristicas

- **Arquitectura DSPy Modular**: Separacion clara entre signatures, modulos, metricas y optimizadores.
- **Integracion con GEPA**: Implementacion completa de la evolucion reflexiva de prompts.
- **Mejores Practicas**: Alineacion con la documentacion oficial de DSPy y GEPA.
- **Configuracion Flexible**: Gestion centralizada de modelos y parametros de optimizacion.
- **Metricas Exhaustivas**: Soporte para metricas simples y basadas en feedback.

## Estructura del Proyecto

```
reflexio/
├── shared/                  # Modulos compartidos entre proyectos
│   ├── llm/                 # Configuracion LLM unificada (LiteLLM)
│   ├── paths/               # Gestion centralizada de rutas (BasePaths, GEPAPaths, DSPyPaths)
│   ├── display/             # Formateo consistente para terminal
│   ├── logging/             # Logger CSV compartido (BaseCSVLogger)
│   ├── validation/          # Validacion de configuracion
│   └── analysis/            # Utilidades de analisis (leaderboard, ROI)
├── dspy_gepa_poc/           # Integracion principal DSPy + GEPA
│   ├── configs/             # Configuraciones YAML para experimentos
│   ├── datasets/            # Conjuntos de datos en formato CSV
│   └── reflexio_declarativa.py # Punto de entrada principal
├── gepa_standalone/         # Implementacion de GEPA sin dependencia de DSPy
├── docs/                    # Documentacion detallada (SSOT)
├── requirements.txt         # Dependencias del proyecto unificadas
└── README.md                # Este archivo
```

## Guia de Inicio Rapido

### 1. Instalacion de Dependencias

Se requiere Python 3.10 o superior. Es posible el uso de un entorno virtual `uv` o `pip`.

```bash
pip install -r requirements.txt
```

### 2. Configuracion del Modelo de Lenguaje (LLM)

El proyecto utiliza un sistema de configuracion unificado basado en variables de entorno y archivos `.env`. 

Para una guia detallada sobre como configurar los proveedores (Azure, OpenAI, Anthropic), consulte el documento central de configuracion:

**SSOT de Configuracion:** `docs/LLM_CONFIG.md`

### 3. Ejecucion de Experimentos

El proyecto esta pensado para ejecutar las tareas definidas en archivos YAML de forma declarativa sin necesidad de modificar el codigo fuente.

#### Agregar config con yaml

## Modos de Operación

El proyecto ofrece dos formas principales de utilizar la optimización reflexiva:

### 1. GEPA Standalone (Puro)

Este modo utiliza GEPA directamente para optimizar prompts sin depender de frameworks externos. Es ideal para casos donde se requiere control total sobre el pipeline de evaluación o para optimizar prompts simples fuera de una arquitectura compleja.

- **Funcionamiento**:
  1. Carga una configuración YAML que define el dataset, el prompt inicial y el adaptador (lógica de evaluación).
  2. Ejecuta un bucle de optimización donde el "Profesor LLM" analiza los errores del "Estudiante LLM".
  3. Genera variantes del prompt y selecciona la mejor basada en métricas de evaluación (exactitud, formato, etc.).
  4. El profesor mejora el prompt para que lo use el LLM mas simple o "estudiante" con un resultado medible y similar al del LLM profesor, incrementando el ROI luego al usarlo en producción diariamente.
  
```bash
  # Ejemplo: Clasificación de urgencia de correos
  python gepa_standalone/universal_optimizer.py --config gepa_standalone/experiments/configs/email_urgency.yaml
```

### 2. DSPy + GEPA Integration

Este modo integra GEPA como un *Teleprompter* (optimizador) dentro del ecosistema DSPy. Permite optimizar *Signatures* y *Modules* completos dentro de pipelines declarativos.

- **Funcionamiento**:
  1. Define una `Signature` (inputs/outputs) y una métrica en DSPy.
  2. Utiliza el optimizador `GepaSignatureOptimizer` para compilar el programa DSPy.
  3. GEPA itera sobre las instrucciones y few-shot examples de la Signature para maximizar la métrica definida.
  4. Una vez maximizado el resultado puede ser usando de forma continua en producción sin necesidad de nuevas iteraciones de reflexión y mejora, lo que permite usar un modelo mas simple y con mayor ROI.
  
```bash
  #Ejemplo: Análisis de sentimientos dinámico.
  python dspy_gepa_poc/reflexio_declarativa.py --config dspy_gepa_poc/configs/dynamic_sentiment_hard_es.yaml
```

## Conceptos Core

### Filosofia DSPy
DSPy transforma la construccion de aplicaciones con LLMs al tratar los prompts como artefactos compilados a partir de codigo Python, permitiendo que el sistema sea modular, reutilizable y optimizable.

### Optimizacion con GEPA
GEPA mejora los prompts usados por DSPy mediante un ciclo de evolucion reflexiva: el modelo profesor analiza los fallos del modelo estudiante y propone mutaciones inteligentes en las instrucciones y ejemplos para maximizar el rendimiento segun la metrica definida.

## Documentacion de Referencia

| Dominio | Archivo |
|---|---|
| Configuracion LLM | `docs/LLM_CONFIG.md` |
| Configuracion YAML | `docs/YAML_CONFIG_REFERENCE.md` |
| Guia de DSPy | `docs/DSPY_DOCUMENTACION.md` |
| Diseño de Sistemas | `docs/DSPY_GUIA_DISENO.md` |
| Optimizador GEPA | `docs/GEPA_DOCUMENTACION.md` |
| Persistencia y Estado | `docs/DSPY_ARTEFACTOS_SALIDA.md` |
| Analisis de Integracion | `docs/GEPA_STANDALONE_EN_DSPY_ANALISIS.md` |

## Referencias
- **Sitio oficial DSPy**: https://dspy.ai/
- **Repositorio GEPA**: https://github.com/gepa-ai/gepa
