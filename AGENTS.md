# Reflexio Dicta - Centro de Experimentacion DSPy + GEPA

Laboratorio de experimentacion para optimizar sistemas que usan LLM mediante
DSPy y GEPA.

> Este archivo es el entry file del agente. `AGENTS.md` y `GEMINI.md` son copias
> identicas: cualquier cambio aqui MUST replicarse en las tres.

## Reglas-gatillo (siempre activas)

- MUST: tras cualquier modificacion de codigo, pasar el pipeline local
  `./shared/utils/ci_local.sh` antes de cerrar (replica el CI: lint + security +
  tests, cobertura 85%). No basta con `pytest`/`ruff check` sueltos.
- MUST: invocar los entry points con `python -m` desde la raiz del repo; nunca el
  script directo (rompe `import shared`).
- MUST NOT usar emoticones en codigo, comentarios ni documentacion.
- MUST: un doc, un proposito (SSOT). No duplicar informacion entre docs; enlazar.
- SDD activo (tramos 0-1): usar lenguaje normativo `MUST`/`SHOULD`/`MAY`, dejar
  `[NEEDS CLARIFICATION: ...]` ante ambiguedad, y cerrar entregas no triviales con
  el bloque `[SDD-Check]`.

## A donde ir a buscar (protocolo de navegacion)

Leer el SSOT correspondiente ANTES de actuar sobre su dominio. No asumir lo que
un SSOT ya define.

| Cuando necesites... | Lee |
|---|---|
| Orientarte: estructura del repo y mapa completo de SSOTs | `00-INDEX.md` |
| Correr el proyecto, comandos, pipeline local, entry points, setup `.venv` | `docs/DEVELOPMENT.md` |
| Patrones de arquitectura (Factory, Adapter, BasePaths, ...) e invariantes | `docs/ARCHITECTURE.md` |
| Convenciones de codigo/docs y workflow (incl. protocolo SDD) | `docs/CONTRIBUTING.md` |
| Detalle y plantilla del protocolo SDD, `[SDD-Check]`, deuda arrastrada | `docs/SDD_PROTOCOLO.md` |
| Configuracion LLM unificada (variables, formatos) | `docs/LLM_CONFIG.md` |
| Campos de configuracion YAML de ambos subproyectos | `docs/YAML_CONFIG_REFERENCE.md` |
| Hallazgos criticos y errores comunes | `docs/LECCIONES_APRENDIDAS.md` |
| Medir senal vs ruido al evaluar cambios (N seeds) | `docs/PROTOCOLO_N_SEEDS.md` |
| Estado de cada capacidad / specs vigentes | `specs/SPECS_REGISTRY.md` |

El mapa completo de SSOTs por dominio (DSPy, GEPA, analisis, metadata, etc.) esta
en `00-INDEX.md`. El `README.md` es la puerta para humanos (referencia secundaria).
