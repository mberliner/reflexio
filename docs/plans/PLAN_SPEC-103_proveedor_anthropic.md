# Plan de implementacion — SPEC-103 proveedor Anthropic

Fuente del plan de ejecucion de [[SPEC-103-proveedor-anthropic]]. La spec define
que debe cumplirse (FR/SC); este documento define en que orden se implementa,
con que modelo de agente, que decisiones de diseno ya estan tomadas y en que
estado esta cada subfase. Si cambia un requisito, se edita la spec y aca solo se
ajusta la referencia.

## Criterio de modelo

"Modelo" es el modelo del agente de codigo que ejecuta cada subfase, no los
modelos bajo prueba de la matriz de la spec.

- Opus 5.5: diseno que cruza modulos, interaccion con internals de librerias
  (GEPA, DSPy, LiteLLM), analisis de resultados y revision.
- Sonnet 5.5: implementacion guiada por la spec y por tests ya escritos.

## Reglas de ejecucion

- Tests primero (RED) y luego implementacion (GREEN). Los tests RED se marcan
  `@pytest.mark.xfail(strict=True, reason="SPEC-103 <subfase que los cierra>")`
  para que `ci_local.sh` quede verde; la subfase GREEN quita la marca.
- Cada fase cierra con `./shared/utils/ci_local.sh` y un commit.
- La fase 6 gasta API real: va en una sesion aparte y respeta el tope de SC-003.
- Al cerrar una subfase: actualizar su estado aca (`pendiente` -> `hecho`, con
  el hash del commit) y pasar a vigente la fila del Coverage mapping de la spec
  que corresponda.
- Si una decision de diseno de este plan choca con el codigo, se corrige aca
  antes de seguir; no se improvisa en la implementacion.

## Fases

| Fase | Subfase | Requisitos | Modelo | Estado |
|---|---|---|---|---|
| 1 Nucleo (`shared/llm/config.py`) | 1a Tests sin red: matriz, combinaciones invalidas, regresion Azure/OpenAI (RED) | SC-001, SC-002, SC-006 | Sonnet 5.5 | pendiente |
| | 1b Diseno: tabla de familias, resolucion de alias/snapshot, campos de `LLMConfig`, `apply_constraints`, `effective_params` | FR-001, FR-002 | Opus 5.5 | pendiente |
| | 1c Implementacion de `from_env`, `apply_constraints`, `to_kwargs`, `validate`, `validate_connection` (GREEN) | FR-003, FR-004, FR-005, FR-006, FR-007, FR-008 | Sonnet 5.5 | pendiente |
| | 1d Revision de regresion silenciosa en `azure/` y `openai/` | SC-006 | Opus 5.5 | pendiente |
| 2 Caminos de llamada | 2a `SimpleRAGAdapter` y `call_llm` al punto unico (tarea y juez) | FR-002 | Sonnet 5.5 | pendiente |
| | 2b Respuesta sin texto en LiteLLM: helper comun, adapters de `gepa_standalone`, juez, reflexion de `get_lm_function`; `docs/GEPA_MANEJO_ERRORES.md` | FR-009 | Sonnet 5.5 | pendiente |
| | 2c Respuesta sin texto en DSPy: LM envuelto de `get_dspy_lm` (tarea: log; reflexion: excepcion) y verificacion contra `dspy.GEPA` | FR-009 | Opus 5.5 | pendiente |
| 3 Costos | 3a Precios desde la pagina oficial y tabla de `docs/ANALISIS_UTILIDADES.md` | FR-011 | Sonnet 5.5 | pendiente |
| | 3b `normalize_model`, `get_model_pricing` y test de tokens de razonamiento en `usage.py` | FR-011 | Sonnet 5.5 | pendiente |
| 4 Reporte y metadata | 4a `describe()` desde `effective_params`, con `max_tokens` por adapter | FR-010 | Sonnet 5.5 | pendiente |
| | 4b Configs unicas por corrida en `universal_optimizer`; `run.json` con parametros efectivos | FR-012 | Sonnet 5.5 | pendiente |
| 5 Docs | `docs/LLM_CONFIG.md`, `docs/PROTOCOLO_N_SEEDS.md`, `docs/METADATA_REPRODUCIBILIDAD.md` | FR-012, FR-013 | Sonnet 5.5 | pendiente |
| 6 Verificacion real (sesion aparte) | 6a Estimacion de costo y, si hace falta, YAML de verificacion | SC-003 | Sonnet 5.5 | pendiente |
| | 6b Ejecucion de las 14 corridas | SC-003 | Sonnet 5.5 | pendiente |
| | 6c Analisis: conteo sin texto, costo vs tabla, registro en `historial/sdd.md` | SC-004, SC-005 | Opus 5.5 | pendiente |
| Cierre | Code review integral y `[SDD-Check]`; pasar la spec a `active` | todos | Opus 5.5 | pendiente |

## Dependencias

- 1a -> 1b -> 1c -> 1d. Las fases 2, 3 y 4 requieren la fase 1.
- 2b requiere 2a (el helper se usa en `_call_llm_with_retry`). 2c es
  independiente de 2a y 2b.
- 3b requiere 3a. La fase 3 es independiente de la 2 y de la 4.
- 4b requiere 4a.
- La fase 5 va despues de 1 a 4. La fase 6 requiere 1 a 4.

## Decisiones de diseno (insumo de 1b; 1b las confirma o corrige aca)

D1. Tabla de familias. En `shared/llm/config.py`, una tupla de
`AnthropicFamily` (dataclass `frozen`) con `aliases: tuple[str, ...]`,
`sends_temperature: bool`, `efforts: frozenset[str] | None` (None = no acepta
effort), `default_reasoning: "off" | "adaptive" | "always"`,
`off_mechanism: None | "noop" | "disabled" | "between_tools"` (None = no se
permite apagar) y `off_max_effort: str | None` (tope de effort con `off`). Una
fila por fila de la matriz de la spec; Opus 4.7/4.8 y Fable 5/5.1/5.2 comparten
fila mediante `aliases`.

D2. Resolucion. `resolve_anthropic_family(model) -> AnthropicFamily | None`:
quita `anthropic/`, quita un sufijo `-\d{8}$` y busca coincidencia exacta del
alias. No hay prefijos parciales (`claude-opus-5` no debe resolver
`claude-opus-5-5`). Fuera de la matriz: `None`, sin restricciones y con aviso
(FR-001).

D3. Campos nuevos de `LLMConfig`: `role: str = "task"`, `effort: str | None =
None` y `thinking: str = "default"`. `from_env` lee `LLM_EFFORT_<ROL>` y
`LLM_THINKING_<ROL>` con `strip().lower()` (vacio = no configurado) y guarda el
valor crudo. La validez se decide en `validate()` (FR-008: "al validar"), no en
`from_env`.

D4. Punto unico. `apply_constraints(kwargs) -> dict` reemplaza a
`apply_reasoning_constraints`: se renombran sus tres usos (`to_kwargs`,
`call_llm`, RAG) y no queda alias. Devuelve un dict nuevo (sin mutar la
entrada). Rama OpenAI sin cambios. Rama Anthropic: quita `api_base` y
`api_version`, quita `temperature` si `sends_temperature` es falso, agrega
`output_config={"effort": effort or "medium"}` si la familia acepta effort,
agrega `thinking` segun `off_mechanism` si `thinking == "off"` y eleva
`max_tokens` a `_REASONING_MIN_MAX_TOKENS` si el razonamiento queda activo
(FR-006). Todo override por llamada (`temperature`, `max_tokens`) se aplica
antes de llamar a `apply_constraints`.

D5. Errores y avisos. `LLMConfigError` en `shared/llm/errors.py` hereda de
`LLMConnectionError`, para que los entry points que ya la atrapan sigan
funcionando. El mensaje nombra modelo, rol, parametro y valores aceptados.
`validate()` emite los avisos de arranque (ID fuera de la matriz, `LLM_API_BASE`
ignorado) con el logger del proyecto, una vez por config.

D6. Valores efectivos. `effective_params(max_tokens: int | None = None) -> dict`
devuelve `model`, `temperature` (None si se omite), `temperature_omitted`,
`effort`, `thinking`, `max_tokens` y `max_tokens_requested`. Lo usan
`describe()` (4a) y `collect_model_info` (4b), asi la logica no se duplica.
`max_tokens` permite reportar el valor por llamada de un adapter (FR-010).

D7. Respuesta sin texto (LiteLLM). `EmptyResponseError(role, finish_reason)` en
`errors.py` y un helper `response_text(response, role) -> str` en `config.py`
que registra la causa y lanza la excepcion si el contenido es `None` o vacio
tras `strip()`. Lo usan `get_lm_function`, `call_llm` y `_call_llm_with_retry`.
Los adapters ya convierten la excepcion en score 0.0; el juez la reporta como
"Error del Juez"; GEPA la atrapa en reflexion y saltea la iteracion.

D8. Respuesta sin texto (DSPy). `get_dspy_lm()` devuelve una subclase de
`dspy.LM` que revisa cada salida. Rol `reflection`: lanza
`EmptyResponseError`. Rol `task`: solo registra la causa y deja que DSPy
falle el parseo, porque lanzar contaria para `max_errors` y podria cortar la
corrida. 2c verifica las dos conductas contra dspy 3.2.1 y GEPA 0.0.27.

## Detalle por subfase

### 1a Tests sin red (RED) — Sonnet 5.5

- Mover los fixtures `capture_anthropic_post` y `capture_azure_post` de
  `tests/test_litellm_regression.py` a `tests/conftest.py`.
- Nuevo `tests/test_anthropic_matrix.py` (no crecer `test_shared_llm.py`):
  - SC-001: un caso por conducta distinta, no el producto cartesiano. Los tres
    caminos comparten `apply_constraints` y los alias de una misma fila se
    comportan igual. Sobre el cuerpo HTTP interceptado:
    - `get_lm_function`: cada fila de la matriz con valores por defecto (12),
      un effort explicito por fila que lo acepta (~11) y `thinking=off` una vez
      por mecanismo (`disabled`, `between_tools`, no-op) (~4).
    - `call_llm` (env por `monkeypatch`) y `get_dspy_lm` (llamada `lm("hi")`
      con `cache=False`, sin `drop_params`): 2 filas cada uno (Haiku 4.5 y
      Opus 5.5).
    - Un solo alias por fila; la resolucion de snapshot y de alias compartido
      se prueba aparte, contra `resolve_anthropic_family`.
    - Tope: unos 30 casos para el test de matriz y unos 90 en todo el archivo.
    Afirma temperature presente/ausente, `output_config`, `thinking`,
    `max_tokens >= 16000` cuando corresponde, ausencia de
    `api_base`/`api_version` y el header `anthropic-version`. El camino RAG va
    en un test marcado para 2a.
  - SC-002: parametrizado sobre las combinaciones invalidas; `validate()` lanza
    `LLMConfigError` con modelo y parametro en el mensaje.
  - FR-008: mayusculas/espacios, vacio, valores desconocidos.
  - FR-001/FR-007: aviso por ID fuera de la matriz y por `LLM_API_BASE`;
    `validate()` sin `LLM_API_BASE` no falla.
  - Escenarios Given/When/Then de la spec, uno por test.
- SC-006: tests que fijan como literales los `to_kwargs()` y cuerpos HTTP
  actuales de `azure/gpt-4.1-mini`, `azure/gpt-5.4-mini`, `azure/gpt-4o` y
  `openai/gpt-4o-mini`. Pasan en verde desde el inicio y quedan como guardia.
- Riesgo a resolver aca: si `dspy.LM` no pasa por `HTTPHandler.post`, ajustar
  el fixture (o interceptar `litellm.completion`) y anotarlo.
- Cierre: los tests nuevos estan marcados `xfail(strict=True)` y fallan por
  falta de implementacion, no por errores del test: verificarlo con
  `.venv/bin/python -m pytest tests/test_anthropic_matrix.py -rx` y revisar los
  motivos. Los de SC-006 y `tests/test_litellm_regression.py` pasan sin marca.
  `ci_local.sh` verde.

### 1b Diseno — Opus 5.5

- Confirmar o corregir D1 a D6 en este documento, contrastando con los tests de
  1a y con LiteLLM 1.108.5.
- Dejar en `config.py` solo los esqueletos (tabla, firmas y docstrings) para
  que 1c sea implementacion pura.
- Cierre: decisiones fijadas aca; los tests de 1a siguen en rojo por las razones
  previstas.

### 1c Implementacion (GREEN) — Sonnet 5.5

- `from_env`, `apply_constraints`, `to_kwargs`, `validate`, `effective_params` y
  `validate_connection` (la sonda fija `max_tokens=5` y despues aplica
  `apply_constraints`, asi los modelos con razonamiento reciben 16000).
- Renombrar los usos de `apply_reasoning_constraints`.
- Quitar la marca `xfail` de los tests de 1a (salvo el de RAG, que la quita 2a).
- Cierre: tests de 1a en verde (salvo el de RAG) y `ci_local.sh` verde.
  `config.py` por debajo de 800 lineas.

### 1d Revision — Opus 5.5

- Diff de `config.py` y de `llm_factory.py` contra los caminos `azure/` y
  `openai/`: orden de aplicacion, mutaciones, `drop_params` y kwargs nuevos que
  pudieran filtrarse a Azure.
- Cierre: SC-006 en verde y hallazgos resueltos o anotados aca.

### 2a Punto unico en RAG y `call_llm` — Sonnet 5.5

- `SimpleRAGAdapter._call_llm_with_retry` y `call_llm`: override por llamada y
  luego `apply_constraints`. Usar la config del juez cuando corresponde.
- Revisar que `BaseAdapter.call_model` pase `temperature` del constructor como
  override, y que `apply_constraints` lo quite en las familias "no se envia".
- Cierre: test RAG de 1a en verde (tarea y juez).

### 2b Respuesta sin texto en `gepa_standalone` — Sonnet 5.5

- D7: `EmptyResponseError`, helper `response_text` y su uso en los tres caminos
  LiteLLM. RAG deja de tratar `None` como content filter.
- Tests: respuesta falsa con contenido `None`/`""` y `finish_reason`
  `max_tokens`/`refusal`, en cada adapter (score 0.0, `len(outputs)` intacto,
  causa en el log), en el juez (causa "juez") y en la reflexion de
  `get_lm_function` (lanza la excepcion).
- `docs/GEPA_MANEJO_ERRORES.md`: seccion de respuesta sin texto por rol.

### 2c Respuesta sin texto en DSPy — Opus 5.5

- D8: LM envuelto en `get_dspy_lm`, con el rol tomado de `LLMConfig.role`.
- Verificar con tests sin red: (a) reflexion vacia en `dspy.GEPA` saltea la
  iteracion y no crea candidato `""`; (b) tarea vacia cuenta como 0.0 en la
  metrica y no dispara `max_errors`. Si (b) no se cumple, ajustar la metrica en
  `dspy_gepa_poc/metrics.py`.
- Cierre: FR-009 completo; nota en la spec si alguna conducta de GEPA/DSPy
  difiere de lo que describe FR-009.

### 3a Precios — Sonnet 5.5

- Consultar la pagina oficial de precios de Anthropic y cargar en
  `DEFAULT_PRICING` cada alias de la matriz.
- Sincronizar la tabla de `docs/ANALISIS_UTILIDADES.md` con la fecha de la
  consulta.

### 3b Normalizacion y tokens — Sonnet 5.5

- `normalize_model` quita `azure/`, `openai/` y `anthropic/`, y resuelve los
  snapshots al alias via `resolve_anthropic_family`. `get_model_pricing` la usa
  (hoy repite el `replace`).
- `tests/test_shared_analysis.py`: precio para alias y snapshot de cada fila,
  sin aviso de "modelo sin precio".
- `tests/test_shared_usage.py`: los tokens de razonamiento cuentan como salida
  sin doble conteo (`completion_tokens` de LiteLLM ya los incluye para
  Anthropic y OpenAI; el test lo fija).

### 4a `describe()` — Sonnet 5.5

- `describe(max_tokens=None)` se arma desde `effective_params`: temperature
  enviada u omitida (con el valor de config ignorado), effort, razonamiento y
  `max_tokens` final, con su elevacion.
- Cada adapter expone su `max_tokens` por llamada (clasificador 50, SQL 200,
  extractor `max_response_tokens`, RAG 400 y juez 200), y
  `universal_optimizer` describe despues de crear el adapter.

### 4b Configs unicas y `run.json` — Sonnet 5.5

- `UniversalOptimizer` construye una vez `self.task_config` y
  `self.reflection_config` (con los overrides del YAML) y los reutiliza en
  validacion, adapter, reflexion y `save_results`.
  `create_reflection_lm_function` acepta la config ya armada.
- `collect_model_info` guarda `effective_params()` por rol (mas el juez en RAG).
  `reflexio_declarativa.py` ya pasa las configs usadas.
- Tests en `tests/test_shared_metadata.py`; `metricas_optimizacion.csv` sin
  cambios.

### 5 Docs — Sonnet 5.5

- `docs/LLM_CONFIG.md` (FR-013): formato, `LLM_EFFORT_<ROL>`,
  `LLM_THINKING_<ROL>`, tratamiento de `LLM_API_BASE` y enlace a la matriz de
  la spec, sin copiarla.
- `docs/METADATA_REPRODUCIBILIDAD.md`: campos nuevos de `run.json`.
- `docs/PROTOCOLO_N_SEEDS.md`: advertencia de FR-012 sobre no mezclar effort ni
  razonamiento en un lote.

### 6 Verificacion real — sesion aparte

- 6a: estimar el costo de las 14 corridas con precios de 3a y
  `max_metric_calls: 50`; si supera USD 10, crear un YAML de verificacion y
  registrarlo en `historial/sdd.md`.
- 6b: 10 corridas (5 modelos "real" x 2 subproyectos) mas 4 con
  `LLM_THINKING_TASK=off` (Haiku 5.5 y Sonnet 5.5 x 2 subproyectos).
- 6c: 0 errores 4xx, menos de 1% sin texto con causa en el log, costo sin aviso
  de precio y registro en `historial/sdd.md`.

### Cierre — Opus 5.5

- Code review integral del diff de la spec, `[SDD-Check]`, Coverage mapping sin
  `pendiente`, spec a `active` y `specs/SPECS_REGISTRY.md` actualizado.

## Arranque de cada sesion

Leer la spec y este plan, tomar la primera subfase `pendiente` cuyas
dependencias esten hechas, y usar el modelo indicado. Ejemplo:
"Implementar SPEC-103 subfase 1a segun docs/plans/PLAN_SPEC-103_proveedor_anthropic.md".

## Lanzamiento por CLI (modo no interactivo)

Cada subfase puede correr como una sesion `-p` aparte, con el modelo de la
tabla. `claude-e` es el mismo CLI con el perfil de empresa (API key propia), y
acepta los mismos flags.

- Subfases Opus 5.5: `claude -p ... --model claude-opus-5-5`
- Subfases Sonnet 5.5: `claude -p ... --model claude-sonnet-5-5` (se dejo de
  usar `claude-e` por falta de credito en la API key de empresa, 2026-11-22)

```bash
SUB=1a   # subfase a ejecutar
mkdir -p "$HOME/spec103_logs"   # logs fuera del repo
claude -p "Implementar SPEC-103 subfase $SUB segun docs/plans/PLAN_SPEC-103_proveedor_anthropic.md. \
Sesion no interactiva: si algo exige decision del usuario, no improvisar; \
registrarlo en el plan como bloqueo, no commitear y terminar." \
  --model claude-sonnet-5-5 \
  --permission-mode acceptEdits \
  --allowedTools "Bash(./shared/utils/ci_local.sh) Bash(.venv/bin/python -m pytest:*) Bash(git status) Bash(git diff:*) Bash(git add:*) Bash(git commit:*)" \
  | tee "$HOME/spec103_logs/$SUB.log"
```

Reglas:

- Una subfase por invocacion, en el orden de Dependencias. Antes de lanzar la
  siguiente, revisar `git log -1` y el estado de la subfase en este plan.
- `--permission-mode acceptEdits` y `--allowedTools` son necesarios: sin ellos
  la sesion `-p` no puede editar ni correr `ci_local.sh` y termina sin hacer
  nada.
- Si una subfase deja un bloqueo, se resuelve en una sesion interactiva y se
  relanza.
- La fase 6 (API real con tope de USD 10) y el Cierre van en sesion interactiva,
  no en `-p`.

## Seguimiento

Una sesion interactiva de Opus 5.5 supervisa las fases 1 a 5. No implementa ni
guarda estado propio: el estado es la columna Estado de este plan. Si la
sesion se corta, otra retoma leyendo el plan.

Arranque: "Supervisar SPEC-103 segun la seccion Seguimiento de
docs/plans/PLAN_SPEC-103_proveedor_anthropic.md".

Ciclo por subfase:

1. Tomar la primera subfase `pendiente` cuyas dependencias esten `hecho`.
2. Lanzarla con el comando de "Lanzamiento por CLI" en segundo plano, con el
   modelo de la tabla, y esperar el aviso de fin (sin polling).
3. Aplicar el control de salida. Si pasa, volver a 1. Si falla, detenerse e
   informar al usuario: no relanzar ni corregir por cuenta propia.

Control de salida (todos deben cumplirse):

- Hay un commit nuevo (`git log -1`) y el arbol queda limpio (`git status`).
- `./shared/utils/ci_local.sh` pasa.
- La subfase figura como `hecho` en la tabla, con el hash del commit.
- No quedo un bloqueo anotado en este plan.
- El diff (`git diff --stat HEAD~1`) toca solo los archivos previstos en el
  detalle de la subfase.
- Si la subfase implementa lo decidido en D1 a D8, el diff lo respeta. Se
  revisa el diff completo solo en las subfases de la fase 1 o cuando un punto
  anterior falla.

Paradas obligatorias (la sesion se detiene y espera al usuario):

- Despues de 1b: el usuario aprueba las decisiones de diseno.
- Despues de 1d: el usuario aprueba el nucleo antes de abrir las fases 2 a 4.
- Al terminar la fase 5: la fase 6 gasta API real y va en otra sesion.

Contexto: de cada log leer solo el final (`tail -n 40`); entrar al log completo
o al diff solo cuando un control falla.
