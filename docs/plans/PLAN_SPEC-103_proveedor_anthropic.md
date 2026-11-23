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
| 1 Nucleo (`shared/llm/config.py`) | 1a Tests sin red: matriz, combinaciones invalidas, regresion Azure/OpenAI (RED) | SC-001, SC-002, SC-006 | Sonnet 5.5 | hecho (22156c2) |
| | 1b Diseno: tabla de familias, resolucion de alias/snapshot, campos de `LLMConfig`, `apply_constraints`, `effective_params` | FR-001, FR-002 | Opus 5.5 | hecho (cc57b22) |
| | 1c Implementacion de `from_env`, `apply_constraints`, `to_kwargs`, `validate`, `validate_connection` (GREEN) | FR-003, FR-004, FR-005, FR-006, FR-007, FR-008 | Sonnet 5.5 | hecho (395fbff) |
| | 1d Revision de regresion silenciosa en `azure/` y `openai/` | SC-006 | Opus 5.5 | hecho (aa1291f) |
| 2 Caminos de llamada | 2a `SimpleRAGAdapter` y `call_llm` al punto unico (tarea y juez) | FR-002 | Sonnet 5.5 | hecho (7466c02) |
| | 2b Respuesta sin texto en LiteLLM: helper comun, adapters de `gepa_standalone`, juez, reflexion de `get_lm_function`; `docs/GEPA_MANEJO_ERRORES.md` | FR-009 | Sonnet 5.5 | hecho (75a51bf) |
| | 2b-fix Respuesta sin texto en clasificador y SQL: score 0.0, `len(outputs)` intacto | FR-009 | Sonnet 5.5 | hecho (12d7f66) |
| | 2c Respuesta sin texto en DSPy: LM envuelto de `get_dspy_lm` (excepcion en tarea y reflexion, B-2c-1), envoltorio de programa/metrica en `dspy_gepa_poc` y verificacion contra `dspy.GEPA` y `Evaluate` | FR-009 | Opus 5.5 | hecho (7627c0f) |
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

Fijado en 1b (confirma D1 a D6 con estas precisiones; 1c las implementa tal cual).
Aprobado por el usuario el 2026-11-22, incluidas las decisiones nuevas
(validacion dentro de `apply_constraints`, IDs fuera de la matriz, claves extra
de `effective_params`, orden de chequeos):

- D1 confirmado. La tabla ya esta en `config.py` (`ANTHROPIC_FAMILIES`, 11
  filas). Constantes: `_EFFORTS` (orden canonico low..max, para listar valores y
  comparar con `off_max_effort`), `_DEFAULT_EFFORT`, `_THINKING_VALUES`,
  `_SNAPSHOT_SUFFIX`. Los no-op (`haiku-4-5` a `opus-4-7/4-8`) usan
  `off_mechanism="noop"`; `off_max_effort="high"` en Opus 5, Haiku 5.5 y Sonnet
  5.5; Sonnet 5 sin tope.
- D2 confirmado. `resolve_anthropic_family` acepta el ID con o sin `anthropic/`;
  cualquier otro prefijo (`azure/...`) da None. Helper `_is_anthropic(model)`:
  la rama Anthropic de `apply_constraints` y los avisos se activan solo con el
  prefijo `anthropic/`.
- D3 confirmado con un ajuste de orden: los campos `role`, `effort`, `thinking` y
  un `_warned: bool = field(default=False, init=False, repr=False,
  compare=False)` (aviso una vez por config) los agrega 1c, no 1b. Motivo:
  agregarlos solos hace XPASS (strict) tests de 1a (`test_default_values
  [claude-haiku-4-5]`, `test_unset_variables_default`, entre otros) y rompe
  `ci_local.sh`. `from_env` fija `role=model_name.lower()`; un override
  `role=` gana.
- D4 confirmado y ampliado:
  - Verificado sin red en LiteLLM 1.108.5 (sonda temporal, borrada):
    `thinking={"type": "disabled"|"between_tools"}` y `output_config` llegan
    intactos al cuerpo con `drop_params` True y False, en `litellm.completion` y
    en `dspy.LM`; no se agregan otros campos de `thinking`.
  - `apply_constraints` es idempotente; asi `call_llm` y RAG pueden seguir
    partiendo de `to_kwargs()`, aplicar overrides y volver a llamarla.
  - 1c separa `_base_kwargs()` (lo que hoy arma `to_kwargs`, sin restricciones);
    `to_kwargs() = apply_constraints(_base_kwargs())`. `effective_params` y
    `validate_connection` parten de `_base_kwargs()`.
  - `apply_constraints` llama a `_check_params()` (las reglas de validez de D5
    sin avisos ni chequeo de claves faltantes) y lanza `LLMConfigError`: ningun
    camino envia una combinacion invalida aunque el entry point no llame a
    `validate()` (hoy `run_inference.py`, `call_llm` y varios scripts no la
    llaman). Esto refuerza SC-002 sin tocar entry points.
  - `anthropic/` fuera de la matriz con effort/thinking configurados: no se
    envian (FR-001, sin restricciones) y el aviso de arranque lo dice.
  - OpenAI/Azure: effort/thinking nunca se envian; la rama queda identica a la
    actual salvo devolver un dict nuevo (SC-006).
- D5 confirmado. Orden de chequeo en `_check_params` (define que parametro nombra
  el error): (1) effort fuera de `_EFFORTS` -> `LLM_EFFORT_<ROL>` con low..max;
  thinking fuera de `_THINKING_VALUES` -> `LLM_THINKING_<ROL>` con `default,
  off` (aplica a todo proveedor, FR-008); si no hay familia, termina; (2)
  `efforts is None` y effort configurado -> `LLM_EFFORT_<ROL>` "no acepta
  effort"; (3) effort fuera de `family.efforts` -> `LLM_EFFORT_<ROL>` con los
  aceptados en orden canonico; (4) `off` y `off_mechanism is None` ->
  `LLM_THINKING_<ROL>`; (5) `off` y effort efectivo (`effort or "medium"`) por
  encima de `off_max_effort` -> `LLM_THINKING_<ROL>` (menciona tambien
  `LLM_EFFORT_<ROL>` y los effort permitidos). `<ROL>` = `role.upper()`.
  `LLMConfigError(message, model, parameter, accepted=None)` llama a
  `LLMConnectionError.__init__` con `provider` del prefijo y `suggestions` con
  los valores aceptados; titulo propio "LLM CONFIGURATION ERROR" (1c agrega un
  atributo de clase `title` en `LLMConnectionError` usado por `format_error`).
  Exportarla en `shared/llm/__init__.py`. Logger:
  `logging.getLogger(__name__)` (propaga a root, como `shared/logging/*`).
- D6 confirmado con dos claves mas: `temperature_requested` y `thinking_param`
  (contrato completo en el docstring de `effective_params`). `thinking` es el
  modo efectivo: `adaptive`, `always`, `off` o None (desconocido); OpenAI
  reasoning models reportan `always`.
- Para 1c: `describe()` hoy lee `to_kwargs()["temperature"]`, que deja de existir
  en las familias "no se envia". 1c debe evitar el `KeyError` (leer de
  `effective_params()`); el formato completo es de 4a.
- `get_lm_function(role=...)` conserva su parametro (bucket de uso y rol de D7);
  no se cambia el default a `self.role` en esta fase.

D8. Respuesta sin texto (DSPy). `get_dspy_lm()` devuelve una subclase de
`dspy.LM` que revisa cada salida. Rol `reflection`: lanza
`EmptyResponseError`. Rol `task`: solo registra la causa y deja que DSPy
falle el parseo, porque lanzar contaria para `max_errors` y podria cortar la
corrida. 2c verifica las dos conductas contra dspy 3.2.1 y GEPA 0.0.27.
Corregida en 2c por la RESOLUCION B-2c-1: la tarea tambien lanza y un
envoltorio en `dspy_gepa_poc` la convierte en 0.0 (ver 2c).

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

Resultado de 1a (109 tests en `tests/test_anthropic_matrix.py`: 100 xfail
strict, 9 guardias en verde; suite completa 596 passed, 100 xfailed):

- Riesgo resuelto: `dspy.LM` (3.2.1) SI pasa por `HTTPHandler.post`; el fixture
  `capture_anthropic_post` sirve sin cambios (verificado con un test temporal,
  ya borrado).
- Motivos de fallo verificados con `--runxfail`: `LLMConfig` sin `role`,
  `effort`, `thinking`; falta `resolve_anthropic_family`,
  `LLMConfigError`, `apply_constraints`, `effective_params`; y en `call_llm`,
  `validate_connection` y RAG, `output_config` ausente / `max_tokens` sin elevar.
- Desvios respecto del detalle de arriba, para que 1b/1c los conozcan:
  - La matriz tiene 11 filas (no 12): Opus 4.7/4.8 y Fable 5/5.1/5.2 comparten
    fila. `claude-opus-4-8`, `claude-fable-5-1` y `claude-fable-5-2` se prueban
    solo en la resolucion de alias.
  - Filas de `call_llm` y `get_dspy_lm`: Sonnet 4.6 y Opus 5.5 (no Haiku 4.5 y
    Opus 5.5). Haiku 4.5 con valores por defecto ya produce hoy el pedido
    esperado y su `xfail(strict=True)` daria XPASS (falla). Haiku 4.5 queda
    cubierto en `get_lm_function`.
  - Tests ya en verde sin marca (guardia): `validate()` sin `LLM_API_BASE` en
    `anthropic/` y los 8 de regresion Azure/OpenAI (`to_kwargs()` literal y
    cuerpo HTTP Azure).
  - Los tests usan la API de D1 a D8 tal cual (`role`, `effort`, `thinking`,
    `LLMConfigError`, `resolve_anthropic_family`, `apply_constraints`,
    `effective_params`); si 1b corrige nombres, hay que ajustar los tests.
  - Test RAG (marcado 2a): hoy falla ya en la temperatura de la llamada de tarea
    (`BaseAdapter` no la pasa como override), lo que coincide con la revision
    prevista en 2a; las aserciones del juez no se llegan a evaluar hasta
    entonces.
  - Los avisos (FR-001/FR-007) se prueban con `caplog` sobre cualquier logger
    (nivel WARNING); D5 debe usar un logger que propague a root.
  - `ruff` no esta permitido en sesiones `-p`: el formato se ajusto a mano
    guiado por `ci_local.sh`.

### 1b Diseno — Opus 5.5

- Confirmar o corregir D1 a D6 en este documento, contrastando con los tests de
  1a y con LiteLLM 1.108.5.
- Dejar en `config.py` solo los esqueletos (tabla, firmas y docstrings) para
  que 1c sea implementacion pura.
- Cierre: decisiones fijadas aca; los tests de 1a siguen en rojo por las razones
  previstas.

Resultado de 1b: decisiones en "Fijado en 1b" (seccion Decisiones). En
`config.py`: `AnthropicFamily`, `ANTHROPIC_FAMILIES` y constantes definitivas;
`_is_anthropic`, `resolve_anthropic_family`, `LLMConfig.apply_constraints` y
`LLMConfig.effective_params` con firma y docstring, cuerpo `NotImplementedError`.
Campos de `LLMConfig` y `LLMConfigError` quedan para 1c (ver D3). Tests de 1a:
9 passed, 101 xfailed; con `--runxfail` fallan por `TypeError` de campos
ausentes (66), `NotImplementedError` (19), atributos/clase ausentes (12),
`KeyError` (3) y la temperatura del test RAG (1). Decisiones nuevas a aprobar
por el usuario: validacion dentro de `apply_constraints`, effort/thinking
ignorados con aviso fuera de la matriz, claves extra de `effective_params`.

### 1c Implementacion (GREEN) — Sonnet 5.5

- `from_env`, `apply_constraints`, `to_kwargs`, `validate`, `effective_params` y
  `validate_connection` (la sonda fija `max_tokens=5` y despues aplica
  `apply_constraints`, asi los modelos con razonamiento reciben 16000).
- Renombrar los usos de `apply_reasoning_constraints`.
- Quitar la marca `xfail` de los tests de 1a (salvo el de RAG, que la quita 2a).
- Cierre: tests de 1a en verde (salvo el de RAG) y `ci_local.sh` verde.
  `config.py` por debajo de 800 lineas.

Resultado de 1c: implementado segun "Fijado en 1b", sin desvios de diseno. Tests
de 1a en verde (109 passed) salvo el de RAG (xfail 2a); suite 696 passed, 1
xfailed; `ci_local.sh` verde; `config.py` 685 lineas. Notas para 1d:

- `apply_reasoning_constraints` borrada; sus usos en `llm_factory.py` y
  `simple_rag_adapter.py` pasan a `apply_constraints`.
- `validate_connection` arma la sonda (`_base_kwargs` + `max_tokens=5` +
  `apply_constraints`) fuera del `try`: un `LLMConfigError` sale sin envolverse
  como falla de red.
- `describe()` lee de `effective_params()` (temperature omitida: "not sent");
  el formato completo sigue siendo de 4a.
- `LLMConnectionError.title` (atributo de clase) usado por `format_error`.
- `_check_params` tambien valida valores desconocidos de effort/thinking para
  OpenAI/Azure (FR-008, "todo proveedor").

### 1d Revision — Opus 5.5

- Diff de `config.py` y de `llm_factory.py` contra los caminos `azure/` y
  `openai/`: orden de aplicacion, mutaciones, `drop_params` y kwargs nuevos que
  pudieran filtrarse a Azure.
- Cierre: SC-006 en verde y hallazgos resueltos o anotados aca.

Resultado de 1d: sin regresion en `azure/` ni `openai/`. Revisado el diff de
`config.py`, `errors.py`, `llm_factory.py` y `simple_rag_adapter.py` desde
6ab172b. Suite 708 passed, 1 xfailed (RAG, 2a); `ci_local.sh` verde.

- Orden de aplicacion: `call_llm` y RAG aplican los overrides (`temperature`,
  `max_tokens`) y despues `apply_constraints`, como antes. La sonda de
  `validate_connection` da el mismo pedido que antes (5, o 16000 con
  temperature 1.0 en reasoning models).
- Mutaciones: `apply_reasoning_constraints` mutaba el dict de entrada;
  `apply_constraints` devuelve uno nuevo. Los tres llamadores reasignan el
  resultado, asi que la conducta no cambia. `get_lm_function` sigue armando los
  kwargs una sola vez, al crear la funcion.
- `drop_params`: sin cambios (`get_lm_function`, `call_llm`, RAG y
  `validate_connection` lo activan; `get_dspy_lm` no).
- Kwargs nuevos: fuera de `anthropic/` nunca se agregan `output_config`,
  `thinking` ni `reasoning_effort`, aunque `LLM_EFFORT_<ROL>` o
  `LLM_THINKING_<ROL>` esten configurados. Los `.env` de los dos subproyectos
  no definen esas variables, asi que ninguna config existente cambia de
  conducta ni puede caer en `LLMConfigError`.
- Guardia nueva `tests/test_sc006_azure_openai_paths.py` (12 tests) para los
  caminos que no cubria `TestAzureOpenAIConfigRegression`: `call_llm` con
  overrides (cuerpo HTTP), `get_dspy_lm` (kwargs y cuerpo HTTP), sonda de
  `validate_connection`, effort/thinking configurados en Azure/OpenAI (no se
  envian y no hay aviso), no mutacion y `describe()`.

Observaciones (no son regresiones ni bloquean; quedan para las fases que se
indican):

- O1 (fase 5): en Azure/OpenAI un `LLM_EFFORT_<ROL>` valido se ignora sin
  aviso (1b: "nunca se envian"). `docs/LLM_CONFIG.md` debe decirlo. Si se
  quiere un aviso de arranque, hay que agregarlo a la spec (FR-001 solo cubre
  `anthropic/` fuera de la matriz).
- O2 (fase 5): valores de effort que OpenAI acepta pero estan fuera de
  low..max (`minimal`, `none`) fallan en Azure por FR-008 ("todo proveedor").
  Coincide con la spec; documentarlo en `docs/LLM_CONFIG.md`.
- O3 (menor): `from_env(..., role=X)` lee las variables con el sufijo de
  `model_name`, pero el error nombra `LLM_*_<X>`. Hoy ningun llamador pasa
  `role=`; no se toca.
- O4 (4b): `shared/logging/run_artifacts.py::_to_serializable` usa
  `__dict__`. Si alguna vez serializara un `LLMConfig`, incluiria `api_key`
  (esto ya pasaba antes), `_warned` y los campos nuevos. Hoy no recibe
  configs; `run.json` debe salir de `effective_params()` (D6).

Nucleo aprobado por el usuario el 2026-11-22. O1 y O2: solo documentar en la
fase 5, sin aviso nuevo ni cambio de spec.

### 2a Punto unico en RAG y `call_llm` — Sonnet 5.5

- `SimpleRAGAdapter._call_llm_with_retry` y `call_llm`: override por llamada y
  luego `apply_constraints`. Usar la config del juez cuando corresponde.
- Revisar que `BaseAdapter.call_model` pase `temperature` del constructor como
  override, y que `apply_constraints` lo quite en las familias "no se envia".
- Cierre: test RAG de 1a en verde (tarea y juez).

Resultado de 2a: `call_llm` y RAG ya usaban `apply_constraints` desde 1c; faltaba
que la llamada de tarea de RAG pasara la temperatura del adapter como override.
`_call_llm_with_retry` la pasa ahora solo en la llamada de tarea (no juez ni
reflexion), igual que `BaseAdapter.call_model`; `apply_constraints` la quita en
las familias "no se envia". Marca xfail del test RAG quitada. Suite 709 passed;
`ci_local.sh` verde. Nota: en RAG con Azure/OpenAI la tarea usa ahora la
temperatura del adapter (la del YAML, ya volcada al env por
`universal_optimizer`) y no la de `LLMConfig.from_env`; coincide con los demas
adapters.

### 2b Respuesta sin texto en `gepa_standalone` — Sonnet 5.5

- D7: `EmptyResponseError`, helper `response_text` y su uso en los tres caminos
  LiteLLM. RAG deja de tratar `None` como content filter.
- Tests: respuesta falsa con contenido `None`/`""` y `finish_reason`
  `max_tokens`/`refusal`, en cada adapter (score 0.0, `len(outputs)` intacto,
  causa en el log), en el juez (causa "juez") y en la reflexion de
  `get_lm_function` (lanza la excepcion).
- Juez de RAG (`SimpleRAGAdapter`, evaluacion con juez): agregar
  `except LLMConnectionError: raise` antes del `except Exception`, como los
  demas adapters, para que un `LLMConfigError` (que hereda de
  `LLMConnectionError`, D5) corte la corrida en vez de dar 0.0 "Error del Juez".
  Test: config de juez invalida -> la excepcion se propaga desde `evaluate`.
  (Aprobado por el usuario al cerrar 1b, 2026-11-22.)
- `docs/GEPA_MANEJO_ERRORES.md`: seccion de respuesta sin texto por rol.

Resultado de 2b: `EmptyResponseError` (`errors.py`, no hereda de
`LLMConnectionError`) y `response_text(response, role)` (`config.py`, exportados
en `shared/llm`) usados en `get_lm_function`, `call_llm` y
`_call_llm_with_retry`. En RAG la excepcion se propaga sin pasar por la rama de
content filter (esta queda solo para excepciones reales); la tarea la convierte
en score 0.0 con la causa en `outputs`, el juez en "Error del Juez" con
`rol=juez` en el log. `_evaluate_with_judge` propaga `LLMConnectionError`.
Precision sobre el detalle: clasificador y SQL descartan el ejemplo (no suman
score 0.0), extractor y RAG puntuan 0.0. Esto NO cumple FR-009 ("MUST contar como
prediccion fallida con score 0.0, en todos los adapters"); lo corrige 2b-fix. Tests en `tests/test_empty_response.py` (25); suite 734 passed;
`ci_local.sh` verde. Fila FR-009 del Coverage mapping: vigente solo en LiteLLM
hasta 2c.

### 2b-fix Respuesta sin texto en clasificador y SQL — Sonnet 5.5

Origen: control de salida de 2b (supervision, 2026-11-22). Alcance (a) aprobado
por el usuario.

- `SimpleClassifierAdapter.evaluate` y `SimpleSQLAdapter.evaluate`: atrapar
  `EmptyResponseError` antes del `except Exception` y registrar el ejemplo como
  prediccion fallida: score 0.0, una entrada en `outputs` con la causa (rol y
  `finish_reason`) y, si `capture_traces`, su trayectoria. Mismo patron que
  `simple_extractor_adapter.py`.
- Fuera de alcance: el `except Exception` (error tecnico) sigue descartando el
  ejemplo como hoy. Es deuda D-019 en `historial/sdd.md`; no tocarlo.
- Tests en `tests/test_empty_response.py`: en clasificador y SQL, contenido
  `None`/`""` con `finish_reason` `max_tokens`/`refusal` -> score 0.0,
  `len(outputs) == len(scores) == len(batch)` y causa en el log. Un test de
  guardia fija que un error tecnico sigue descartandose (para que el cambio de
  D-019 sea explicito).
- Al cerrar: corregir la fila FR-009 del Coverage mapping (vigente en los
  caminos LiteLLM, en todos los adapters; DSPy pendiente 2c).

Resultado de 2b-fix: `SimpleClassifierAdapter` y `SimpleSQLAdapter` atrapan
`EmptyResponseError` antes del `except Exception` y registran score 0.0, una
entrada en `outputs` con `error` (rol y `finish_reason`) y su trayectoria si
`capture_traces`. Tests de 2b que fijaban el descarte reemplazados en
`tests/test_empty_response.py` (35 en total) con guardia de que el error tecnico
sigue descartando (D-019). `docs/GEPA_MANEJO_ERRORES.md` y fila FR-009 del
Coverage mapping corregidos.

### 2c Respuesta sin texto en DSPy — Opus 5.5

- D8: LM envuelto en `get_dspy_lm`, con el rol tomado de `LLMConfig.role`.
- Verificar con tests sin red: (a) reflexion vacia en `dspy.GEPA` saltea la
  iteracion y no crea candidato `""`; (b) tarea vacia cuenta como 0.0 en la
  metrica y no dispara `max_errors`. Si (b) no se cumple, ajustar la metrica en
  `dspy_gepa_poc/metrics.py`.
- Cierre: FR-009 completo; nota en la spec si alguna conducta de GEPA/DSPy
  difiere de lo que describe FR-009.

Resultado de 2c (BLOQUEADO, sesion `-p` 2026-11-22; cambios en el arbol de
trabajo, sin commit; `ci_local.sh` verde, suite 762 passed):

- Implementado D8: `shared/llm/dspy_lm.py::CheckedLM` (subclase de `dspy.LM`);
  `get_dspy_lm()` la devuelve con `role=self.role`. La revision va en
  `_process_lm_response`, despues de que DSPy guarda la entrada en `history`,
  para que `record_dspy_history` siga contando los tokens de la respuesta sin
  texto (si se revisara en `forward`, la llamada se perderia del costo). Es un
  metodo interno de dspy 3.2.1: revalidar si D-018 actualiza DSPy. Rol
  `reflection`: log + `EmptyResponseError`; cualquier otro rol: solo log. Se
  ignoran choices con `tool_calls`. `config.py`: `response_text` factoriza
  `is_empty_text` y `log_empty_response` (mismo mensaje en LiteLLM y DSPy).
- `tests/test_shared_llm.py`: los dos tests de `get_dspy_lm` mockeaban
  `sys.modules["dspy"]`; ya no aplica (la subclase se arma sobre el dspy real).
  Reescritos sobre el objeto devuelto, mas uno de `role`.
- `tests/test_empty_response_dspy.py` (17, sin red, interceptando
  `dspy.clients.lm.litellm_completion` y corriendo `dspy.GEPA` real):
  - (a) se cumple: con `CheckedLM` la reflexion vacia saltea la iteracion, no hay
    candidato nuevo ni evaluaciones de minibatch con otra instruccion. Guardia
    con `dspy.LM` plano: el texto vacio SI se evalua como candidato (gasto que
    FR-009 evita).
  - (b) se cumple dentro de `dspy.GEPA`: la tarea vacia da `AdapterParseError`;
    con trazas (`bootstrap_trace_data`) se vuelve `FailedPrediction` con 0.0;
    sin trazas `Evaluate` usa `failure_score` 0.0 con `max_errors=len(batch)*100`.
    `len(outputs)` intacto; una corrida con toda la tarea vacia termina.
  - LiteLLM normaliza el `stop_reason` `refusal` de Anthropic a
    `finish_reason="content_filter"`: es lo que va a aparecer en el log.
- Hallazgo de costo (no bloquea, informar): cada respuesta de tarea sin texto
  dispara 3 llamadas (ChatAdapter y luego los dos intentos de JSONAdapter por
  `use_json_adapter_fallback`). Medido: 10 ejemplos vacios = 30 llamadas.

BLOQUEO B-2c-1 (decision del usuario): fuera de `dspy.GEPA`, los `Evaluate` de
`dspy_gepa_poc/reflexio_declarativa.py` (baseline sobre valset, test y
`_eval_repeated`) usan `max_errors` por defecto (`dspy.settings.max_errors` =
10). Medido sin red: 12 ejemplos con tarea vacia -> `Exception("Execution
cancelled due to errors or interruption.")` al llegar a 10. Esto viola FR-009
("MUST NOT ... interrumpir la corrida") y el remedio que preve este plan
("ajustar la metrica en `dspy_gepa_poc/metrics.py`") no aplica: el
`AdapterParseError` sale del programa antes de llamar a la metrica. Opciones:

1. Pasar `max_errors` alto (p. ej. `len(devset) * 100`, como `DspyAdapter`) a
   esos `Evaluate`. Simple, pero tambien deja de cortar ante errores tecnicos
   reales (red, auth), que pasarian a puntuar 0.0: cruza con D-019.
2. Atrapar en el modulo DSPy el `AdapterParseError` cuyo origen es una
   respuesta sin texto y devolver una `Prediction` con campos None para que la
   metrica puntue 0.0. No toca `max_errors`, pero hay que distinguir el vacio de
   un error de formato real y cubrir los modulos de `flujo_intents`.
3. Aceptar la conducta actual y anotar en FR-009 la excepcion para la
   evaluacion fuera de GEPA (6c espera menos de 1% sin texto; con valsets de mas
   de 1000 ejemplos el corte seria posible).

Ademas, `dspy_gepa_poc/scripts/baseline_only.py` usa `Evaluate` con la misma
conducta, y `run_inference.py` y los otros scripts llaman al programa directo
(un `AdapterParseError` sale sin atrapar); definir si entran en el alcance.
Al resolver: aplicar la opcion elegida, `docs/GEPA_MANEJO_ERRORES.md` (seccion
DSPy), fila FR-009 del Coverage mapping, `ci_local.sh` y commit de 2c.

RESOLUCION B-2c-1 (usuario, 2026-11-22): opcion 2, con esta correccion de D8.

- D8 corregida: en rol `task` el LM envuelto tambien lanza `EmptyResponseError`
  (con la causa en el log), en lugar de solo registrar. El tipo de excepcion
  separa la respuesta sin texto de un error de formato real, sin heuristicas
  sobre `AdapterParseError`.
- Un envoltorio fino del programa DSPy (un solo lugar, en `dspy_gepa_poc`)
  atrapa `EmptyResponseError` y devuelve una `Prediction` con los campos de
  salida vacios/None, para que la metrica puntue 0.0. Se aplica al programa que
  usan `dspy.GEPA` y los `Evaluate` de `reflexio_declarativa.py` (baseline,
  test, `_eval_repeated`), asi cubre tambien los modulos de `flujo_intents`.
  Cualquier otra excepcion sigue su curso (cuenta para `max_errors`).
- `max_errors` no se toca.
- Verificar de nuevo, sin red: (a) reflexion vacia sigue salteando la
  iteracion; (b) tarea vacia = 0.0 dentro de `dspy.GEPA` y en `Evaluate` con
  mas de 10 ejemplos vacios sin "Execution cancelled"; (c) un error tecnico
  real sigue contando para `max_errors`. Confirmar que el envoltorio no rompe
  `detailed_results` ni `EvaluationResult.results` (fix D-016) ni el guardado
  del programa optimizado (el envoltorio no debe quedar en el artefacto, o
  debe ser transparente al cargarlo).
- Si `ChatAdapter` reintenta con `JSONAdapter` ante la excepcion (llamadas
  extra), anotar el costo; no es bloqueante.
- Alcance: entra `dspy_gepa_poc/scripts/baseline_only.py`. Quedan fuera
  `run_inference.py` y los demas scripts de inferencia directa: deuda D-020 en
  `historial/sdd.md` (ya registrada).
- Partir de los cambios sin commitear que dejo la sesion bloqueada (no
  descartarlos).

Resultado de 2c (cierre, sesion `-p` 2026-11-22, sobre los cambios de la sesion
bloqueada; suite 777 passed; `ci_local.sh` verde):

- `CheckedLM` lanza `EmptyResponseError` en todo rol (se quito el caso "solo
  log" de la tarea). La causa sigue en el log y la llamada en `history`.
- Envoltorio en `dspy_gepa_poc/empty_response.py`, aplicado en un solo lugar:
  `ReflexioDeclarativa.create_module_and_metric` (el cuerpo previo paso a
  `_build_module_and_metric`). Asi lo usan `dspy.GEPA`, los `Evaluate` de
  `run()` (baseline, test, `_eval_repeated`) y `scripts/baseline_only.py`, para
  todo tipo de modulo (dynamic, rule_derived, pipeline de `flujo_intents`).
  - `tolerate_empty_responses(program)`: copia del programa con la clase
    cambiada a una subclase dinamica cuyo `forward` atrapa `EmptyResponseError`
    y devuelve `EmptyResponsePrediction` (campos de salida de los predictores en
    None). Se sobreescribe `forward` y no `__call__` porque
    `bootstrap_trace_data` (ruta con trazas de GEPA) llama a `forward` directo.
    Cambiar la clase (y no anidar el programa en otro modulo) conserva
    `named_predictors`, las claves de candidatos (`candidates.json`) y el JSON
    guardado; `deepcopy`/`reset_copy` conservan la clase.
  - Precision sobre la RESOLUCION: los campos None no bastan para el 0.0.
    `shared.scoring.score_field` trata None como "" (credito en campos con gold
    vacio, p. ej. listas vacias) y la metrica simple compara `str(None)`; en
    `rule_derived` el color derivado no es salida de un predictor. Por eso el
    mismo modulo agrega `zero_on_empty_response(metric)`, aplicado en el mismo
    lugar: puntua 0.0 la `EmptyResponsePrediction` sin llamar a la metrica (con
    feedback de la causa si GEPA lo pide) y deja pasar el resto. No se toco
    `metrics.py` ni `max_errors`.
- Verificado sin red (`tests/test_empty_response_dspy.py`, 32):
  (a) reflexion vacia saltea la iteracion, sin candidato ni evaluaciones
  nuevas; (b) tarea vacia = 0.0 en `DspyAdapter.evaluate` (con y sin trazas,
  `len(outputs)`/`trajectories` intactos), en `dspy.GEPA` con toda la tarea
  vacia, y en `Evaluate` con 12 vacios y `max_errors` por defecto (10) sin
  "Execution cancelled"; guardia: sin envoltorio, se cancela; (c) un error
  tecnico (excepcion de la completion) sigue cancelando el `Evaluate`; un error
  de formato sigue siendo `AdapterParseError`. `EvaluationResult.results` (D-016)
  conserva una entrada por ejemplo; el programa guardado no contiene la clase
  envuelta y se carga en el modulo sin envolver.
- Costo (no bloquea): `ChatAdapter` atrapa la excepcion y reintenta con
  `JSONAdapter` (dos intentos): 3 llamadas por respuesta de tarea sin texto,
  igual que antes con el `AdapterParseError`.
- Docs: seccion DSPy en `docs/GEPA_MANEJO_ERRORES.md`, nota de implementacion
  en FR-009 y fila FR-009 del Coverage mapping de la spec. Fuera de alcance:
  inferencia directa (D-020).

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
