# 00-INDEX — Navegacion del proyecto

Reflexio Dicta: laboratorio de experimentacion para optimizar sistemas que usan
LLM mediante DSPy y GEPA.

## Ruta recomendada

Orden de lectura para ponerse al dia. Empieza por el entry file del agente, no
por el README (que es la puerta para humanos).

1. [CLAUDE.md](CLAUDE.md) — PUNTO DE PARTIDA del agente: invocacion, patrones, invariantes y convenciones (copias equivalentes en `AGENTS.md` y `GEMINI.md`)
2. [docs/GEPA_STANDALONE_EN_DSPY_ANALISIS.md](docs/GEPA_STANDALONE_EN_DSPY_ANALISIS.md) — arquitectura de integracion y metodologia de 3 conjuntos
3. [docs/LLM_CONFIG.md](docs/LLM_CONFIG.md) — configuracion LLM unificada antes de correr nada
4. [docs/YAML_CONFIG_REFERENCE.md](docs/YAML_CONFIG_REFERENCE.md) — campos de configuracion YAML de ambos proyectos
5. [docs/LECCIONES_APRENDIDAS.md](docs/LECCIONES_APRENDIDAS.md) — hallazgos criticos y errores comunes
6. [docs/PROTOCOLO_N_SEEDS.md](docs/PROTOCOLO_N_SEEDS.md) — como medir senal vs ruido al evaluar cambios
7. [README.md](README.md) — orientado a humanos: overview y setup (referencia secundaria)

## Estructura del proyecto

| Directorio / archivo | Contenido |
|---|---|
| `analyze` | CLI unificado para analisis (leaderboard, ROI, estadisticas) |
| `shared/llm/` | Configuracion LLM unificada (LiteLLM) |
| `shared/paths/` | Gestion centralizada de rutas (BasePaths, GEPAPaths, DSPyPaths) |
| `shared/display/` | Formateo consistente para terminal |
| `shared/logging/` | Logger CSV compartido (BaseCSVLogger) y MetadataManager |
| `shared/validation/` | Validacion de configuracion y datasets |
| `shared/analysis/` | Utilidades de analisis compartidas |
| `shared/utils/` | Utilidades operativas (check_deployments, seed_protocol, generadores) |
| `dspy_gepa_poc/` | Integracion DSPy + GEPA (configs, datasets, entry points) |
| `gepa_standalone/` | GEPA puro sin DSPy (configs, datasets, prompts) |
| `docs/` | Documentacion detallada (un archivo = un SSOT) |
| `tests/` | Suite de tests (pytest) |
| `**/results/` | Salidas de ejecuciones — gitignored, regenerables |

Cada subproyecto (`dspy_gepa_poc/`, `gepa_standalone/`) tiene su propio `.env`.

## Mapa de SSOTs

Cada archivo de `docs/` actua como SSOT (single source of truth) para su dominio.

### General e integracion

| Tema | SSOT |
|---|---|
| Configuracion LLM unificada (variables, formatos, uso) | `docs/LLM_CONFIG.md` |
| Campos de configuracion YAML de ambos proyectos | `docs/YAML_CONFIG_REFERENCE.md` |
| Utilidades de analisis (CLI, leaderboard, ROI, estadisticas) | `docs/ANALISIS_UTILIDADES.md` |
| Metadata de reproducibilidad en 3 niveles (environment, experiment, run) | `docs/METADATA_REPRODUCIBILIDAD.md` |
| Arquitectura de integracion y metodologia de 3 conjuntos | `docs/GEPA_STANDALONE_EN_DSPY_ANALISIS.md` |
| Hallazgos criticos y errores comunes (metrica exacta, efecto techo) | `docs/LECCIONES_APRENDIDAS.md` |
| Segmentacion del intake en `triage_v1` + `fast_gate_v1` | `docs/FAST_GATE_SEGMENTACION.md` |
| Protocolo de N seeds, configs/datasets `_v2`, `gold_verificado` | `docs/PROTOCOLO_N_SEEDS.md` |

### DSPy (framework)

| Tema | SSOT |
|---|---|
| Vision general, arquitectura, conceptos core y flujo | `docs/DSPY_DOCUMENTACION.md` |
| Guia de diseno (componentes, patrones, metricas) | `docs/DSPY_GUIA_DISENO.md` |
| Artefactos de salida (Prediction, JSON, Pickle, persistencia) | `docs/DSPY_ARTEFACTOS_SALIDA.md` |
| Predictores avanzados (CoT, ReAct, BestOfN, Refine) | `docs/DSPY_PREDICTORES_AVANZADOS.md` |

### GEPA (optimizador)

| Tema | SSOT |
|---|---|
| Vision general, algoritmo reflexivo y configuracion | `docs/GEPA_DOCUMENTACION.md` |
| Manejo de errores tecnicos (descarte vs score 0) | `docs/GEPA_MANEJO_ERRORES.md` |

### Guias, planes e historico

| Tema | Documento |
|---|---|
| Optimizar prompts con base de conocimiento (archivo de reglas) | `docs/GUIA_CASO_USO_BASE_CONOCIMIENTO.md` |
| Mejoras pendientes (documento efimero de implementacion) | `docs/MEJORAS_PENDIENTES_DSPY_GEPA_POC.md` |
| Plan: extraccion de requerimientos desde transcripciones | `docs/plan_implementcion_toma_requerimientos.md` |
| Documentacion historica (estados previos a refactors) | `docs/historico/` |
