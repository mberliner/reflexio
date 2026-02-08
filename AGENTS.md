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

## Convenciones del Proyecto

- **No usar emoticones** en código, comentarios ni documentación. Mantener un estilo profesional y limpio.
- **Utilizar cada doc para un solo propósito(SSOT)** cada documento contiene información unica, debe ser la fuente de verdad, sin necesidad de repetir la información. Ls SSOT puede referenciarse en otros docs para seguimiento y claridad.
