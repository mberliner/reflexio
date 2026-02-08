# Reflexio Dicta - Centro de Experimentacion DSPy + GEPA

## Proposito del Proyecto

Este proyecto es un laboratorio de experimentacion para optimizar sistemas  que usan LLM mediante DSPy y GEPA.

## Documentación de Referencia

A continuación se lista la documentación disponible en `docs/`. Cada archivo actúa como SSOT para su dominio específico.

### General e Integracion
- **`docs/LLM_CONFIG.md`**: SSOT para configuracion LLM unificada (shared/llm). Variables de entorno, formatos de modelo, uso en codigo.
- **`docs/YAML_CONFIG_REFERENCE.md`**: SSOT para campos de configuracion YAML de ambos proyectos. Tablas de referencia rapida con tipos, defaults y descripciones.
- **`docs/ANALISIS_UTILIDADES.md`**: SSOT para utilidades de analisis compartidas (shared/analysis). CLI unificado, leaderboard, ROI, estadisticas.
- **`docs/GEPA_STANDALONE_EN_DSPY_ANALISIS.md`**: SSOT para la arquitectura de integracion y metodologia de 3 conjuntos. Analisis detallado de diferencias entre GEPA standalone y DSPy.
- **`docs/LECCIONES_APRENDIDAS.md`**: Recopilacion de hallazgos criticos, errores comunes (metrica exacta, efecto techo) y comparativas de rendimiento (ingles vs espanol) obtenidos durante la experimentacion.

### DSPy (Framework)
- **`docs/DSPY_DOCUMENTACION.md`**: Visión general de DSPy, arquitectura, conceptos core y flujo de trabajo.
- **`docs/DSPY_GUIA_DISENO.md`**: Guía estratégica para diseñar sistemas (selección de componentes, patrones, métricas).
- **`docs/DSPY_ARTEFACTOS_SALIDA.md`**: Referencia técnica sobre objetos de salida (Prediction, JSON, Pickle), persistencia y arquitectura de almacenamiento.
- **`docs/DSPY_PREDICTORES_AVANZADOS.md`**: Detalle profundo sobre predictores (CoT, ReAct, BestOfN, Refine) y cuándo usarlos.

### GEPA (Optimizador)
- **`docs/GEPA_DOCUMENTACION.md`**: Visión general de GEPA, algoritmo de optimización reflexiva y configuración.
- **`docs/GEPA_MANEJO_ERRORES.md`**: Manejo específico de errores técnicos (descarte vs score 0) en GEPA standalone.

## Estructura del Proyecto

Para descripcion completa del proyecto y sus componentes, ver `/README.md`.

Estructura de alto nivel:

```
reflexio/
+-- analyze                 # CLI unificado para análisis
+-- shared/llm/             # Configuración LLM unificada (LiteLLM)
+-- shared/paths/           # Gestión centralizada de rutas (BasePaths, GEPAPaths, DSPyPaths)
+-- shared/display/         # Formateo consistente para terminal
+-- shared/logging/         # Logger CSV compartido (BaseCSVLogger)
+-- shared/validation/      # Validación de configuración
+-- shared/analysis/        # Utilidades de análisis compartidas
+-- dspy_gepa_poc/          # Integración DSPy + GEPA
+-- gepa_standalone/        # GEPA puro (sin DSPy)
+-- docs/                   # Documentación detallada
```

Cada proyecto tiene su propio `.env` para configuracion LLM independiente.

## Flujo de Trabajo Típico

1.  **Definir/Modificar una `Signature`** en `dspy_gepa_poc/modules.py` para una nueva tarea.
2.  **Crear un `Module`** en `dspy_gepa_poc/modules.py` que use la `Signature`.
3.  **Crear datos de ejemplo** en `dspy_gepa_poc/data.py`.
4.  **Definir una métrica** en `dspy_gepa_poc/metrics.py`.
5.  **Crear un nuevo script en `examples/`** que use los nuevos componentes para ejecutar una tarea o un flujo de optimización.

## Desarrollo

```bash
source .venv/bin/activate        # Entorno virtual (Python 3.13)
pytest tests/ -v                 # 139 tests, ~3s
ruff check .                     # Lint (config en pyproject.toml)
./run_demo.sh --check            # Validar entorno sin ejecutar experimentos
./run_demo.sh gepa               # Ejecutar demo GEPA standalone
./run_demo.sh dspy               # Ejecutar demo DSPy + GEPA
```

CI: `.github/workflows/ci.yml` ejecuta pytest + ruff en cada push/PR.

## Patrones de Arquitectura

- **Factory**: `DynamicModuleFactory` (dspy_gepa_poc/dynamic_factory.py) crea signatures y modules DSPy desde config YAML. Punto central de extension para nuevas tareas.
- **Adapter**: `BaseAdapter` (gepa_standalone/adapters/base_adapter.py) con 4 implementaciones concretas (classifier, extractor, sql, rag). Cada adapter define como evaluar una tarea contra el LLM.
- **BasePaths**: `BasePaths` (shared/paths/base_paths.py) con subclases `GEPAPaths` y `DSPyPaths`. Gestion centralizada de rutas con fallback a ubicaciones legacy. Nunca hardcodear paths.
- **LLM unificado**: shared/llm/ via LiteLLM. Configuracion en `.env` de cada subproyecto. Variables: `LLM_API_KEY`, `LLM_MODEL_TASK`, `LLM_MODEL_REFLECTION`. Ver `docs/LLM_CONFIG.md`.
- **Validacion temprana**: `BaseConfigValidator` y `CSVValidator` (shared/validation/) validan configs YAML y datasets CSV antes de ejecutar. Fallos antes de gastar tokens.
- **Logger compartido**: `BaseCSVLogger` (shared/logging/csv_writer.py) para registro consistente de metricas.

## Invariantes

- Cada subproyecto (dspy_gepa_poc/, gepa_standalone/) tiene su propio `.env` para configuracion LLM independiente.
- Inputs versionados: configs YAML, datasets CSV y prompts JSON se trackean en git.
- Outputs no versionados: todo bajo `**/results/` esta gitignoreado (runs, leaderboards, metricas). Son regenerables.
- Datasets CSV requieren columna `split` con valores `train`/`dev`/`test`.
- Punto de entrada GEPA: `gepa_standalone/universal_optimizer.py --config <yaml>`.
- Punto de entrada DSPy: `dspy_gepa_poc/reflexio_declarativa.py --config <yaml>` (--config es obligatorio).

## Convenciones del Proyecto

- **No usar emoticones** en codigo, comentarios ni documentacion. Mantener un estilo profesional y limpio.
- **Utilizar cada doc para un solo proposito (SSOT)**: cada documento contiene informacion unica, debe ser la fuente de verdad, sin necesidad de repetir la informacion. La SSOT puede referenciarse en otros docs para seguimiento y claridad.
- **Lint con ruff**: line-length 100, reglas E/F/I/N/UP/B/C4. Ver `pyproject.toml`.
