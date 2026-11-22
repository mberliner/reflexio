# Plan de implementacion — SPEC-103 proveedor Anthropic

Fuente del plan de ejecucion de [[SPEC-103-proveedor-anthropic]]. La spec define
que debe cumplirse (FR/SC); este documento define en que orden se implementa,
con que modelo de agente y en que estado esta cada subfase. Si cambia un
requisito, se edita la spec y aca solo se ajusta la referencia.

## Criterio de modelo

"Modelo" es el modelo del agente de codigo que ejecuta cada subfase, no los
modelos bajo prueba de la matriz de la spec.

- Opus 5.5: diseno que cruza modulos, interaccion con internals de librerias
  (GEPA, DSPy, LiteLLM), analisis de resultados y revision.
- Sonnet 5.5: implementacion guiada por la spec y por tests ya escritos.

## Reglas de ejecucion

- Tests primero (RED) y luego implementacion (GREEN).
- Cada fase cierra con `./shared/utils/ci_local.sh` y un commit.
- La fase 6 gasta API real: va en una sesion aparte y respeta el tope de SC-003.
- Al cerrar una subfase, actualizar su estado aqui (`pendiente` -> `hecho`, con
  el hash del commit).

## Fases

| Fase | Subfase | Requisitos | Modelo | Estado |
|---|---|---|---|---|
| 1 Nucleo (`shared/llm/config.py`) | 1a Tests sin red de la matriz, combinaciones invalidas y regresion Azure/OpenAI (RED) | SC-001, SC-002, SC-006 | Sonnet 5.5 | pendiente |
| | 1b Diseno de la tabla de familias, resolucion de alias/snapshot y campos nuevos de `LLMConfig` | FR-001, FR-002 | Opus 5.5 | pendiente |
| | 1c Implementacion de `from_env`, `to_kwargs` y `validate` (GREEN) | FR-003 a FR-008 | Sonnet 5.5 | pendiente |
| | 1d Revision de regresion silenciosa en `azure/` y `openai/` | SC-006 | Opus 5.5 | pendiente |
| 2 Caminos de llamada | 2a Migrar `SimpleRAGAdapter` al punto unico (tarea y juez) | FR-002 | Sonnet 5.5 | pendiente |
| | 2b Respuesta sin texto en tarea y juez: adapters de `gepa_standalone` y metrica DSPy; `docs/GEPA_MANEJO_ERRORES.md` | FR-009 | Sonnet 5.5 | pendiente |
| | 2c Respuesta sin texto en reflexion: excepcion en `get_lm_function` y en el LM de reflexion de `dspy.GEPA` | FR-009 | Opus 5.5 | pendiente |
| 3 Costos | 3a Precios desde la pagina oficial y tabla de `docs/ANALISIS_UTILIDADES.md` | FR-011 | Sonnet 5.5 | pendiente |
| | 3b `normalize_model`, `get_model_pricing` y test de tokens de razonamiento en `usage.py` | FR-011 | Sonnet 5.5 | pendiente |
| 4 Reporte y metadata | 4a `describe()` con valores efectivos por adapter | FR-010 | Sonnet 5.5 | pendiente |
| | 4b Parametros efectivos en `run.json` desde las configs usadas (corrige la recreacion en `save_results`) | FR-012 | Sonnet 5.5 | pendiente |
| 5 Docs | `docs/LLM_CONFIG.md`, `docs/PROTOCOLO_N_SEEDS.md`, `docs/METADATA_REPRODUCIBILIDAD.md` | FR-012, FR-013 | Sonnet 5.5 | pendiente |
| 6 Verificacion real (sesion aparte) | 6a Estimacion de costo y, si hace falta, YAML de verificacion | SC-003 | Sonnet 5.5 | pendiente |
| | 6b Ejecucion de las 14 corridas | SC-003 | Sonnet 5.5 | pendiente |
| | 6c Analisis: conteo sin texto, costo vs tabla, registro en `historial/sdd.md` | SC-004, SC-005 | Opus 5.5 | pendiente |
| Cierre | Code review integral y `[SDD-Check]`; pasar la spec a `active` | todos | Opus 5.5 | pendiente |

## Dependencias

- 1a -> 1b -> 1c -> 1d. Las fases 2, 3 y 4 requieren la fase 1.
- 2c es independiente de 2a y 2b.
- La fase 3 es independiente de la 2 y de la 4.
- La fase 5 va despues de 1 a 4. La fase 6 requiere 1 a 4.

## Arranque de cada sesion

Leer la spec y este plan, tomar la primera subfase `pendiente` cuyas
dependencias esten hechas, y usar el modelo indicado. Ejemplo:
"Implementar SPEC-103 subfase 1a segun docs/plans/PLAN_SPEC-103_proveedor_anthropic.md".
