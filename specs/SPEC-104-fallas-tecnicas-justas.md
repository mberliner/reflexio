# SPEC-104-fallas-tecnicas-justas — Fallas tecnicas visibles y medicion justa

Estado: draft
Iteracion: 2 (rev. 2026-11-23)
Cierra: D-019 y D-021 (`historial/sdd.md`)
Reemplaza: SPEC-103 FR-009 en los roles tarea y juez (la respuesta sin texto deja
de puntuar 0.0 y pasa a clasificarse por su causa, ver "Clasificacion de
fallas"). El rol reflexion de SPEC-103 FR-009 se conserva y se generaliza en
FR-005. Motivo registrado en `historial/sdd.md` (2026-11-23, SPEC-104 iteracion 2).
Relacionada con: [[SPEC-103-proveedor-anthropic]] (completa la parte de "cortadas
por `max_tokens`" de su SC-004), [[SPEC-100-veredicto-senal-ruido]],
[[SPEC-105-roles-intercambiables]], `docs/GEPA_MANEJO_ERRORES.md`,
`docs/METADATA_REPRODUCIBILIDAD.md`, `docs/YAML_CONFIG_REFERENCE.md`,
`docs/ARCHITECTURE.md`
Plan de implementacion: docs/plans/PLAN_SPEC-104_fallas_tecnicas_justas.md

## User Story (prioridad)

Como persona que experimenta con DSPy y GEPA, quiero que cada falla tecnica de
una llamada al LLM se clasifique por su causa, quede registrada y contada, y se
le cargue al prompt candidato solo cuando el prompt la provoco, para que los
scores y las comparaciones entre prompts midan calidad y no fallas de
infraestructura, de configuracion o del dato, y para que una corrida con
demasiadas fallas se detenga en vez de reportar resultados enganosos.
Prioridad: P1

## Contexto (estado al 2026-11-23)

Hallazgos de la revision posterior a la fase 6 de SPEC-103 y de la revision de
la iteracion 1 de esta spec:

- `gepa_standalone`: `simple_classifier_adapter.py` y `simple_sql_adapter.py`
  descartan el ejemplo ante cualquier excepcion en runtime (incluidos 401, 5xx y
  errores de conexion: `LLMConnectionError` solo se lanza en `validate()`), y
  solo lo avisan con `print`. `universal_optimizer.py` promedia sobre los
  ejemplos que sobrevivieron: baseline y optimizado se comparan sobre
  subconjuntos distintos. Dentro de GEPA rompe el alineamiento entre `outputs` y
  el batch. `simple_extractor_adapter.py` y `simple_rag_adapter.py` puntuan 0.
- `dspy_gepa_poc`: `dspy.Evaluate` atrapa cualquier excepcion hasta
  `max_errors` y la puntua 0.0; ante una excepcion del LM, `ChatAdapter`
  reintenta con `JSONAdapter` (varias llamadas LLM por un solo caso,
  `tests/test_empty_response_dspy.py`). `ReflectiveMutationProposer.propose`
  (GEPA 0.0.27) atrapa cualquier excepcion de la reflexion y saltea la
  iteracion. Consecuencia: lanzar una excepcion no alcanza para cortar una
  corrida.
- Nada revisa `finish_reason=length`: un texto truncado se puntua como completo
  y una propuesta de reflexion truncada se adopta como candidato.
- El juez de `simple_rag_adapter.py` convierte sus fallas, y un puntaje que no
  puede leer, en score 0.0 del candidato, sin registro.
- SPEC-103 FR-009 puntua 0 toda respuesta sin texto de tarea y juez, sin mirar
  su causa.
- Reintentos (verificado 2026-11-23 contra `litellm==1.108.5`, `openai==3.57.0`,
  interceptando el transporte HTTP): `shared/` y `gepa_standalone` no pasan
  `num_retries`, pero el SDK de openai ya reintenta 2 veces en Azure y OpenAI
  ante 408/409/429/5xx/red (3 llamadas) y Anthropic no reintenta (1 llamada).
  `num_retries` de LiteLLM reintenta todos los errores, incluidos 400, 401,
  403, 404 y filtros, y en Azure/OpenAI se apila sobre el SDK (`num_retries=3`:
  4 llamadas ante un 401, 7 ante un 5xx). `dspy.LM` pasa `num_retries=3` por
  defecto, asi que hoy `dspy_gepa_poc` repite 4 veces un 401. El unico
  reintento propio, `SimpleRAGAdapter._call_llm_with_retry`, reintenta solo
  `content_filter` / `jailbreak` y propaga los 5xx, timeouts y 429.
- Mapeo de errores de LiteLLM 1.108.5 con `openai==3.57.0` (misma
  verificacion): varios filtros de entrada y excesos de contexto reales de
  Azure y OpenAI llegan como `BadRequestError` generico y no como su subclase
  (el SDK ya no deja el JSON del error en `str(e)`, donde LiteLLM lo busca),
  pero `exc.body` conserva `code`; un 403 de Azure/OpenAI llega como `APIError`
  con `status_code=403`, no como `PermissionDeniedError`. En Anthropic
  `exc.body` es `None`.
- El prompt baseline solo se evalua en val (`universal_optimizer.py`,
  `reflexio_declarativa.py`), nunca en train ni test.
- 8 de 10 CSV de `gepa_standalone/experiments/datasets/` y 12 de 20 de
  `dspy_gepa_poc/datasets/` no tienen `case_id`; `gepa_standalone/data/data_loader.py`
  no conserva columnas fuera de `input_column`/`output_columns`.
- `universal_optimizer.py` evalua test dos veces: `_eval_repeated` para el score
  y otra `adapter.evaluate` solo para `print_detailed_results`.
- Los avisos de los adapters son `print`; `run.json` no guarda cuantas fallas
  hubo de cada tipo.

## Alcance

Incluye: clasificacion de fallas de las llamadas de tarea, reflexion y juez;
tratamiento de cada clase por rol; reintentos de infraestructura en
`shared/llm`; registro y conteo en log y `run.json`; umbrales y mecanismo de
corte; metricas reportadas (baseline, optimizado, test) sobre casos evaluados y
delta pareado dentro de una corrida; identificador canonico de caso; exclusion
de los casos no evaluados del dataset reflexivo. Entry points:
`gepa_standalone/universal_optimizer.py`, `dspy_gepa_poc/reflexio_declarativa.py`
y `dspy_gepa_poc/scripts/baseline_only.py`. Actualizacion de los SSOT afectados.

Excluye:
- Cambios en la logica de optimizacion de GEPA o DSPy. El corte y el descarte
  se hacen desde los envoltorios y el orquestador (FR-006, FR-005).
- Structured outputs nativos (`response_format`/`json_schema`), por la misma
  razon que SPEC-103.
- El veredicto senal-ruido de SPEC-100 y el esquema de su CSV (SPEC-100 FR-007):
  SPEC-100 sigue consumiendo los promedios agregados; el delta pareado vive en
  `run.json` y en el reporte (FR-003).
- `dspy_gepa_poc/run_inference.py` (sigue en D-020) y los scripts de diagnostico
  (`diagnose_*.py`, `per_field_accuracy.py`, `witness_eval.py`), que no reportan
  metricas comparables.

Desvios respecto del estado vigente (registrados en `historial/sdd.md`):
reemplazo parcial de SPEC-103 FR-009; reintentos de LiteLLM, del SDK de openai
y de `dspy.LM` desactivados y reemplazados por un reintento propio solo de
infraestructura en `shared/llm` (FR-011); controles de aborto en los
orquestadores.

## Clasificacion de fallas

Las clases describen la causa, no el rol. El tratamiento depende de la clase y
del rol (tabla de tratamiento). La clase sale de una de dos capas:

1. Respuesta del LLM: excepcion de LiteLLM, `finish_reason` normalizado y
   `message.refusal`. Nunca la sola ausencia de texto.
2. Parseo de la respuesta (adapter, metrica, juez o envoltorio de reflexion):
   solo para `formato`, y solo cuando la capa 1 no detecto falla.

| Clase | Capa | Causa |
|---|---|---|
| `configuracion` | 1 | 4xx de autenticacion, permisos, modelo inexistente o parametros invalidos |
| `entrada` | 1 | Rechazo antes de generar: filtro de contenido de entrada o ventana de contexto excedida (`ContextWindowExceededError`) |
| `presupuesto` | 1 | `finish_reason=length`, con texto parcial o sin texto |
| `filtro_salida` | 1 | `finish_reason=content_filter` o `message.refusal` presente, con HTTP 200 |
| `sin_texto` | 1 | HTTP 200 sin texto, con `finish_reason=stop` o sin causa, y sin `refusal` |
| `infraestructura` | 1 | Red, timeout, 429 o 5xx que persiste tras los reintentos (FR-011) |
| `formato` | 2 | Hay texto pero no cumple el formato esperado (definicion por adapter en FR-010) |

### Reglas de deteccion de la capa 1

Verificadas el 2026-11-23 contra `litellm==1.108.5`, `openai==3.57.0`,
`httpx==0.28.1` y `dspy==3.2.1`, con payloads HTTP de Azure, OpenAI y
Anthropic. Las reglas MUST evaluarse en este orden (la primera que aplica
decide). Todas las excepciones de LiteLLM heredan de `openai.APIError` y las
especializadas de `BadRequestError`, por eso `entrada` e `infraestructura` van
antes que `configuracion`. `exc.body` MUST leerse en forma defensiva (puede ser
`None` o no ser dict).

| # | Clase | Regla |
|---|---|---|
| 1 | `entrada` | `ContentPolicyViolationError` o `ContextWindowExceededError` (de LiteLLM, o el de DSPy que lo envuelve, ver abajo); o `BadRequestError` con `body["code"]` en {`content_filter`, `content_policy_violation`, `context_length_exceeded`} o `body["innererror"]["code"] == "ResponsibleAIPolicyViolation"`; o `request_too_large` en el mensaje (HTTP 413 de Anthropic) |
| 2 | `infraestructura` | `RateLimitError`, `Timeout`, `APIConnectionError`, `InternalServerError`, `ServiceUnavailableError`, `BadGatewayError`; o `APIError` de cualquier subclase (incluido `BadRequestError`) con `status_code` en {408, 409, 429} o `>= 500` (cubre 529, el 409 de Azure/OpenAI como `APIError` y el de Anthropic como `BadRequestError(409)`) |
| 3 | `configuracion` | `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`, `UnsupportedParamsError`, `UnprocessableEntityError`, `BadRequestError` restante; `APIError` con `400 <= status_code < 500` restante (cubre el 403 de Azure/OpenAI); `litellm.completion` que devuelve `None` (bug de 422 con `openai/` y `drop_params`); cualquier excepcion de la llamada no clasificada por las reglas anteriores, con su tipo y mensaje en el error |
| 4 | `filtro_salida` | HTTP 200 con `finish_reason == "content_filter"` o `bool(getattr(message, "refusal", None))`, con o sin texto. `refusal` MUST leerse con `getattr` (el atributo puede no existir: siempre en Anthropic, y en OpenAI cuando el JSON omite la clave; cuando existe vale `None` en respuestas normales) |
| 5 | `presupuesto` | HTTP 200 con `finish_reason == "length"`, con texto parcial o sin texto |
| 6 | `sin_texto` | HTTP 200 con contenido `None` o vacio tras `strip()` |

Notas de la verificacion (detalle en `tests/test_litellm_failure_mapping.py`):

- `exc.body` no es una fuente uniforme: `ContextWindowExceededError` llega con
  `body=None` (LiteLLM no lo pasa), y en el `ContentPolicyViolationError` de
  Azure LiteLLM simplifica `body` y mueve `innererror` a
  `exc.provider_specific_fields`. Por eso la regla 1 chequea primero la clase y
  usa `body` solo para los `BadRequestError` genericos, donde si se preserva.
- `dspy==3.2.1` atrapa `litellm.ContextWindowExceededError` en `dspy.LM.forward`
  y relanza `dspy.utils.exceptions.ContextWindowExceededError`, que no hereda de
  `openai.APIError` y conserva el original en `__cause__`. En `dspy_gepa_poc` el
  clasificador MUST reconocer esa excepcion (o recorrer `__cause__`) antes de la
  regla 3; si no, caeria en "excepcion no clasificada" y abortaria la corrida.
  `shared/` mantiene diferido el import de `dspy` (`docs/ARCHITECTURE.md`): el
  chequeo vive en `shared/llm/dspy_lm.py` o se hace por `__cause__`.

Sin falla en la capa 1, la respuesta pasa a la capa 2. La deteccion MUST
aplicarse sobre el objeto de respuesta completo en ambos subproyectos: en
`gepa_standalone` en `shared/llm` y en `dspy_gepa_poc` en
`CheckedLM._process_lm_response`, que recibe la respuesta con `finish_reason` y
`message` intactos (hoy solo revisa contenido vacio).

`entrada` y `presupuesto` en el rol tarea llevan una atribucion contra el
baseline (FR-004): `candidato` (el prompt candidato la provoco: el baseline no
falla en ese caso) o la causa externa (el baseline tambien falla). En los
conteos figuran como `entrada_candidato` / `entrada_dato` y
`presupuesto_candidato` / `presupuesto`.

### Tratamiento por rol

"NE" (no evaluado): el caso no suma ni resta al score reportado, se cuenta y se
registra. "Descarta": la propuesta de reflexion no se adopta (FR-005).

| Clase | Tarea | Juez | Reflexion |
|---|---|---|---|
| `configuracion` | Aborta | Aborta | Aborta |
| `entrada` | `entrada_candidato`: score 0. `entrada_dato`: NE y lista de casos problematicos | NE | Descarta |
| `presupuesto` | `presupuesto_candidato`: score 0. `presupuesto`: NE | NE | Descarta |
| `filtro_salida` | NE | NE | Descarta |
| `sin_texto` | NE | NE | Descarta |
| `infraestructura` | NE | NE | Descarta |
| `formato` | Score 0 | NE, tras los reintentos de FR-009 | Descarta |

Durante la optimizacion (minibatches de GEPA y `dspy.GEPA`) cada caso necesita un
score numerico: un caso NE MUST recibir 0.0 solo como valor tecnico para GEPA,
MUST quedar contado (y acotado por los umbrales de FR-006) y MUST NOT llegar al
Profesor como error del prompt (FR-012). Las metricas reportadas de FR-003 lo
excluyen siempre.

## Requisitos funcionales

- FR-001 El sistema MUST clasificar cada falla en `shared/llm` (clasificador de
  la capa 1 y contador de fallas thread-safe, con `threading.Lock` y `reset()`
  por corrida, mismo patron que `shared/llm/usage.py`). `shared/` MUST NOT
  importar `gepa_standalone` ni `dspy_gepa_poc` (`docs/ARCHITECTURE.md`). Los
  adapters de `gepa_standalone`, la metrica y los envoltorios de `dspy_gepa_poc`
  MUST reportar al contador las fallas de capa 2 y el identificador del caso, y
  MUST NOT decidir el tratamiento de una falla por su cuenta.
- FR-002 El sistema MUST tratar cada clase como indica la tabla de tratamiento.
  Un caso MUST NOT desaparecer en silencio de una evaluacion: casos evaluados
  mas no evaluados MUST igualar el tamano del lote (salvo corrida abortada,
  FR-006).
- FR-003 Las metricas reportadas (baseline, optimizado, test) MUST calcularse
  solo sobre casos evaluados y mostrar `n_evaluados / n_total`. El delta
  optimizado - baseline de una corrida MUST calcularse pareado, sobre los casos
  de val evaluados con ambos prompts, y reportarse junto a los dos scores sobre
  sus propios casos evaluados. Con `n_evaluados == 0` (o interseccion vacia) la
  metrica MUST reportarse como "sin casos evaluados", MUST NOT reportarse como
  0.0 y MUST NOT dividir por cero. Con `eval_repeats > 1`, el score de un caso es
  el promedio de sus repeticiones evaluadas, un caso cuenta como evaluado si lo
  fue en al menos una repeticion, y se reporta aparte el numero de repeticiones
  NE. El CSV de resultados MUST NOT cambiar de esquema (SPEC-100 FR-007).
- FR-004 Ante `entrada` o `presupuesto` en el rol tarea con un prompt distinto
  del baseline, el sistema MUST evaluar el prompt baseline sobre ese caso con
  los mismos parametros (mismo `max_tokens`; una sola llamada, cacheada por caso
  para toda la corrida, compartida por ambas clases y valida en cualquier
  split; un resultado `infraestructura` no se cachea y se vuelve a consultar la
  proxima vez que el caso lo necesite) y atribuir:
  - `entrada`: `entrada_dato` si el baseline tambien es rechazado,
    `entrada_candidato` si no.
  - `presupuesto`: `presupuesto` si el baseline tambien termina con
    `finish_reason=length`, `presupuesto_candidato` si no.

  Si el prompt evaluado es el baseline, la atribucion MUST ser la causa externa
  (`entrada_dato` o `presupuesto`). Si la llamada de atribucion falla por otra
  clase, el caso MUST quedar NE con la clase de esa falla. La atribucion MUST
  registrar el `finish_reason` de ambas llamadas.
- FR-005 Una propuesta de reflexion con falla de cualquier clase (incluido
  `formato`: salida sin el bloque que GEPA extrae como instruccion, o
  instruccion vacia) MUST descartarse en el envoltorio del `reflection_lm`
  lanzando una excepcion con la causa, antes de que GEPA la procese (mecanismo
  de SPEC-103 FR-009, verificado para GEPA 0.0.27). Se cuenta como falla de
  reflexion con su clase y el candidato vigente no cambia. `configuracion` en
  reflexion MUST ademas activar el aborto de FR-006.
- FR-006 El contador MUST llevar las fallas por (clase, rol) y MUST pasar a
  estado "abortado" cuando `configuracion` ocurra una vez o cuando la tasa de una
  clase en un rol supere su umbral. La tasa es fallas de la clase / casos
  intentados en ese rol, y se evalua solo a partir de un minimo de intentos.
  `entrada_dato` cuenta casos unicos (un mismo caso evaluado con varios
  candidatos cuenta una vez). `formato`, `entrada_candidato` y
  `presupuesto_candidato` en tarea no tienen umbral: son score del candidato. Como las excepciones no atraviesan
  `Evaluate` ni GEPA, el corte MUST hacerse por estado: los envoltorios MUST
  consultar el estado antes de cada llamada y no llamar al LLM si esta abortado,
  y los orquestadores MUST consultarlo despues de cada paso y antes de
  `save_results()` y detenerse con un error que nombre la clase, el rol, el
  conteo y la causa probable. El mensaje de `presupuesto` MUST indicar que el
  baseline tambien se corta en esos casos (en tarea), MUST sugerir subir
  `max_tokens` y MUST sugerir bajar el effort solo si el modelo del rol lo soporta
  (`docs/LLM_CONFIG.md`). Los umbrales MUST ser configurables en el YAML en una
  seccion opcional comun a ambos subproyectos, validada en `BaseConfigValidator`
  antes de gastar tokens; un YAML sin la seccion MUST usar los defaults.
- FR-007 Cada falla MUST registrarse con `logger` (no `print`) una sola vez por
  caso, con rol, clase, atribucion si aplica, causa (`finish_reason` o tipo de
  error) e identificador del caso. Los intentos intermedios (reintentos de red,
  fallback de `ChatAdapter` a `JSONAdapter`, reintentos del juez) MUST
  registrarse a nivel `DEBUG` y MUST NOT sumar al contador.
- FR-008 `run.json` (via `MetadataManager`) MUST guardar: estado de la corrida
  (`completed` o `aborted`, con clase, rol y causa del aborto), conteos por
  (clase, rol), lista de casos `entrada_dato` y `n_evaluados / n_total` de cada
  metrica. Una corrida abortada MUST NOT escribir fila en el CSV de resultados ni
  presentar metricas como validas; los artefactos ya escritos (p. ej.
  `candidates.json`) MAY quedar en el directorio de la corrida, que queda marcada
  como `aborted`.
- FR-009 El juez MUST pedir su puntaje como JSON en el prompt (sin structured
  outputs nativos), MUST validar que sea un numero en [0.0, 1.0] y MUST
  reintentar ante un puntaje ilegible o fuera de rango (default 2 reintentos)
  antes de clasificarlo como `formato` del juez.
- FR-010 `formato` en tarea MUST definirse por adapter: clasificador, respuesta
  que no normaliza a una de `valid_classes`; extractor, JSON no parseable;
  DSPy, `AdapterParseError` tras el fallback de adapters; SQL y RAG, no aplica
  (texto libre).
- FR-011 Reintentos:
  - Toda llamada de `shared/llm` MUST pasar `num_retries=0` a LiteLLM, y el LM
    de DSPy (`CheckedLM` / `get_dspy_lm`) MUST construirse con `num_retries=0`.
    Verificado: `num_retries=0` tambien fija `max_retries=0` en el SDK de
    openai y da exactamente 1 llamada HTTP por intento en los 3 proveedores.
    `num_retries` de LiteLLM MUST NOT usarse para reintentar: reintenta todas
    las clases (incluidos 401 y filtros) y se apila sobre el SDK.
  - `shared/llm` MUST reintentar con un loop propio solo cuando el clasificador
    de la capa 1 devuelve `infraestructura`, con backoff exponencial, en todos
    los roles y en ambos subproyectos (en `dspy_gepa_poc`, dentro de
    `CheckedLM`). Numero de reintentos configurable, default 3 (4 intentos), el
    mismo para los 3 proveedores. Los intentos intermedios van a `DEBUG`
    (FR-007); solo el resultado final se clasifica y se cuenta.
  - Las demas clases MUST NOT reintentarse. El reintento actual de
    `SimpleRAGAdapter` ante `content_filter` MUST eliminarse: un filtro no es
    transitorio y pasa a ser `entrada` o `filtro_salida`.
- FR-012 En `gepa_standalone`, `make_reflective_dataset` MUST excluir los casos
  NE. En `dspy_gepa_poc`, la metrica con feedback MUST devolver para un caso NE
  un feedback que diga que fue una falla externa y no del prompt.
- FR-013 Los loaders de ambos subproyectos MUST conservar un identificador
  canonico por caso: `case_id` si el CSV lo tiene, si no `<split>:<fila>` (fila
  0-based dentro del split). En reflexion el identificador es la iteracion de
  GEPA.
- FR-014 `universal_optimizer.py` MUST reutilizar los resultados de test ya
  calculados para `print_detailed_results`, sin una segunda evaluacion.
- FR-015 La deteccion MUST ser agnostica al proveedor: se apoya en el
  `finish_reason`, `message.refusal`, los tipos de error normalizados de LiteLLM
  y `exc.body`, segun las reglas de la capa 1 (verificadas para Azure, OpenAI y
  Anthropic). MUST NOT depender de frases del mensaje de error, salvo
  `request_too_large` (Anthropic, sin `body`). Las reglas MUST quedar cubiertas
  por tests con payloads HTTP de los tres proveedores interceptando el
  transporte (SC-009), para que una actualizacion de LiteLLM o del SDK de
  openai que cambie el mapeo falle en CI.
- FR-016 `docs/GEPA_MANEJO_ERRORES.md`, `docs/METADATA_REPRODUCIBILIDAD.md` y
  `docs/YAML_CONFIG_REFERENCE.md` MUST actualizarse con la clasificacion, los
  campos nuevos de `run.json` y la seccion de umbrales.

### Umbrales por defecto (FR-006)

Propuesta inicial, a recalibrar con la verificacion real del plan.

| Clase | Rol | Umbral (tasa) | Minimo de intentos |
|---|---|---|---|
| `configuracion` | todos | primera ocurrencia | - |
| `presupuesto` | tarea, juez | 0.05 | 20 |
| `presupuesto` | reflexion | 0.25 | 4 |
| `infraestructura`, `sin_texto`, `filtro_salida` | tarea, juez | 0.10 | 20 |
| `entrada_dato` | tarea | 0.10 de los casos unicos intentados en tarea en la corrida | 20 casos unicos |
| `entrada` | juez | 0.10 | 20 |
| `formato` | juez | 0.10 | 20 |
| cualquier clase sumada | reflexion | 0.50 | 4 |

### Limites conocidos de la deteccion

Con `litellm==1.108.5` y `openai==3.57.0`. Se re-verifican en cada
actualizacion de LiteLLM o del SDK (SC-009, D-023).

- Anthropic `stop_reason="model_context_window_exceeded"` con HTTP 200 llega
  como `finish_reason="stop"` sin rastro en la respuesta (LiteLLM solo emite un
  WARNING "Unmapped finish_reason"). Con texto parcial se evalua como respuesta
  completa; sin texto cae en `sin_texto`. No es detectable sin parchear LiteLLM.
- Anthropic 400 por politica de uso con un texto distinto de "Output blocked by
  content filtering policy" llega como `BadRequestError` sin `body` y cae en
  `configuracion`: aborta la corrida en vez de quedar como `entrada`. Es
  conservador y visible (el error muestra el mensaje original).
- Con `openai/` y `drop_params=True`, un HTTP 422 hace que `litellm.completion`
  devuelva `None` en vez de lanzar: se clasifica como `configuracion`. Con
  `drop_params=False` (CheckedLM por defecto) lanza `BadRequestError(422)`, que
  tambien es `configuracion`. `litellm.drop_params` es global y lo activan
  `get_lm_function` y `LLMConfig.validate()`, asi que tras `validate()` el bug
  puede alcanzar tambien a `dspy_gepa_poc` en el mismo proceso; en ambos casos
  la clase es la misma.
- Un HTTP 413 generico (sin `request_too_large` en el cuerpo) se mapea distinto
  por proveedor: `RateLimitError(429)` en OpenAI (cae en `infraestructura`, se
  reintenta y queda NE), `APIError(413)` en Azure y `BadRequestError(400)` en
  Anthropic (ambos `configuracion`, abortan). No se corrige por frase (FR-015).

## Decisiones de diseno

- `filtro_salida` NE y no atribuido al candidato (decision del usuario,
  2026-11-23: el filtro solo es culpa del candidato si actua antes del LLM).
  Riesgo de sesgo de supervivencia: un candidato que provoca rechazos sacaria
  casos de su denominador. Mitigacion: en la optimizacion esos casos valen 0.0
  (no premian al candidato ante GEPA) y el delta reportado es pareado (el caso
  sale de los dos lados). Los conteos por rol quedan en `run.json`.
- La respuesta sin texto deja de ser score 0 (reemplazo de SPEC-103 FR-009):
  sin texto por presupuesto, por `stop` vacio o por filtro de salida no prueba
  que el prompt sea peor, y puntuarla 0 mezcla infraestructura con calidad.
- La atribucion de `entrada` y `presupuesto` se hace a demanda (FR-004) y no
  corriendo el baseline en todos los splits: cuesta una llamada por caso
  rechazado o cortado y cubre train y test sin cambiar el flujo.
- `presupuesto` se atribuye al candidato cuando el baseline, con el mismo
  `max_tokens`, no se corta en ese caso (decision del usuario, 2026-11-23,
  opcion B de la revision). Afina la regla "el presupuesto no es culpa del
  candidato": lo es solo con evidencia de que el prompt lo provoco. Motivo: en
  adapters de respuesta corta (clasificador, `task_max_tokens=50`, igualdad
  exacta) un candidato que provoca explicaciones puntuaba 0 si la explicacion
  entraba en el tope y quedaba NE si lo excedia, un incentivo invertido que
  ademas abortaba la corrida por un problema del prompt. Alternativas
  descartadas: mantenerlo NE (incentivo invertido), evaluar el texto parcial
  (cambia el scoring y no sirve para JSON ni SQL truncados) y tratarlo como
  `formato` solo en adapters de respuesta corta (contradice la regla si
  `task_max_tokens` esta mal configurado). Limite conocido: con temperatura > 0
  o modelos reasoning la atribucion tiene ruido (el baseline podria cortarse en
  una pasada y no en otra); se acepta porque la llamada se cachea y la
  atribucion queda registrada con el `finish_reason` de ambas llamadas.
- El aborto es por estado y no por excepcion (FR-006) porque `Evaluate` y GEPA
  atrapan las excepciones; asi no se toca la logica de GEPA ni de DSPy.
- Reintento propio en vez de `num_retries` de LiteLLM o `RetryPolicy` (FR-011,
  verificado 2026-11-23): `num_retries` reintenta todas las clases y se apila
  sobre el SDK (7 llamadas en Azure/OpenAI contra 4 en Anthropic); `RetryPolicy`
  no cubre 502, `APIConnectionError` ni 529 y tambien se apila. Un loop propio
  guiado por el clasificador reintenta solo `infraestructura` y se comporta
  igual en los tres proveedores. Cambia el comportamiento vigente de
  `dspy_gepa_poc` (`dspy.LM` reintentaba todo 3 veces) y el de Azure/OpenAI
  (el SDK reintentaba 2 veces): se registra como desvio.

## Criterios de exito (medibles, agnosticos a tecnologia)

Todos se verifican con LLM simulado (respuestas y errores inyectados), salvo que
se diga otra cosa.

- SC-001 Con fallas inyectadas de cada clase salvo `configuracion`, el 100% de
  los casos queda evaluado o contado como no evaluado: ningun lote pierde casos
  sin registro.
- SC-002 Con un mismo prompt, respuestas fijas y `infraestructura` inyectada en
  el 10% de los casos (bajo el umbral), la metrica reportada coincide con la de
  la corrida sin fallas sobre los mismos casos evaluados, y el reporte muestra
  `n_evaluados / n_total`.
- SC-003 Ninguna propuesta de reflexion con falla de cualquier clase produce un
  candidato.
- SC-004 Superar el umbral de cualquier clase, o una sola falla
  `configuracion` en cualquier rol, detiene la corrida con un error que nombra
  la clase y el rol; ninguna corrida abortada escribe fila en el CSV ni
  `run.json` con estado `completed`.
- SC-005 Los conteos de `run.json` coinciden con las fallas registradas a nivel
  `WARNING` o superior en el log en el 100% de las corridas de prueba,
  completadas o abortadas.
- SC-006 Sin fallas, scores y `run.json` de una corrida son iguales a los de
  antes del cambio salvo los campos nuevos (sin regresion). Excepcion: los
  scores del juez de RAG pueden cambiar por el prompt JSON de FR-009.
- SC-007 Con baseline y optimizado evaluados sobre conjuntos distintos de casos,
  el delta reportado se calcula sobre la interseccion y difiere del delta de
  promedios cuando las fallas no son simetricas.
- SC-008 Un caso NE nunca aparece en el dataset reflexivo de `gepa_standalone`
  ni con feedback de error de prompt en `dspy_gepa_poc`.
- SC-009 Con los payloads HTTP de la verificacion del 2026-11-23 (filtros de
  entrada y salida, contexto excedido, `refusal`, `length`, 400/401/403/404/
  408/409/413/422/429/5xx/529 y errores de red; Azure, OpenAI y Anthropic)
  inyectados en el transporte HTTP, el 100% recibe la clase esperada en ambos
  subproyectos, y un error persistente produce exactamente 1 llamada HTTP si no
  es `infraestructura` y 1 + reintentos configurados si lo es. Se mide por caso
  evaluado, no por llamada al LM: en `dspy_gepa_poc` el fallback de adapters de
  DSPy (`ChatAdapter` -> `JSONAdapter`) MUST NOT repetir la llamada ante una
  falla ya clasificada.

## Escenarios (Given/When/Then)

- Given un clasificador con 30 casos y un 5xx persistente en 3, When se evalua,
  Then la metrica se calcula sobre 27, el reporte muestra 27/30 y el log y
  `run.json` cuentan 3 `infraestructura` del rol tarea.
- Given una respuesta de tarea con `finish_reason=length` con un prompt
  candidato, When el baseline con el mismo `max_tokens` no se corta en ese caso,
  Then puntua 0 como `presupuesto_candidato` y no cuenta para el umbral.
- Given una respuesta de tarea con `finish_reason=length`, When el baseline
  tambien se corta en ese caso, Then queda NE como `presupuesto`; y When las
  fallas `presupuesto` superan su umbral, Then la corrida se detiene sugiriendo
  subir `max_tokens` (y bajar el effort solo si el modelo lo soporta).
- Given un caso de test rechazado por el filtro de entrada con el prompt
  optimizado, When el baseline no es rechazado en ese caso, Then puntua 0 como
  `entrada_candidato`; When el baseline tambien es rechazado, Then queda NE y
  figura en la lista de casos problematicos de `run.json`.
- Given un juez que devuelve un puntaje ilegible, When se agotan los
  reintentos, Then el caso queda NE como `formato` del juez y el candidato no
  recibe 0 en la metrica reportada.
- Given un juez cortado por `max_tokens`, When se evalua, Then el caso queda NE
  como `presupuesto` del rol juez.
- Given una propuesta de reflexion truncada o sin el bloque de instruccion, When
  el envoltorio del `reflection_lm` la recibe, Then lanza una excepcion con la
  causa, se cuenta y el candidato vigente no cambia.
- Given un 401 en el rol reflexion, When ocurre, Then el contador pasa a
  abortado, no se hacen mas llamadas al LLM y la corrida termina con error y
  `run.json` en estado `aborted`, aunque GEPA haya atrapado la excepcion.
- Given una respuesta HTTP 200 con `finish_reason=stop`, sin texto y con
  `message.refusal`, When se clasifica, Then es `filtro_salida`, no `sin_texto`.
- Given un filtro de entrada de Azure u OpenAI que LiteLLM entrega como
  `BadRequestError` generico con `body["code"] == "content_filter"` o
  `"content_policy_violation"`, When se clasifica, Then es `entrada` y no
  `configuracion`.
- Given un 401 en `dspy_gepa_poc`, When ocurre, Then se envia una sola llamada
  HTTP (hoy `dspy.LM` envia 4) y la corrida aborta.
- Given un 503 persistente en Azure, When se agotan los reintentos propios,
  Then se enviaron 4 llamadas HTTP (no 7) y el caso queda NE como
  `infraestructura`.
- Given `dspy_gepa_poc` y una falla del LM de tarea que dispara el fallback de
  `ChatAdapter` a `JSONAdapter`, When el caso termina, Then se registra y se
  cuenta una sola falla.
- Given un lote en el que todos los casos quedan NE, When se reporta, Then la
  metrica figura como "sin casos evaluados" y no como 0.0.
- Given baseline evaluado en 28/30 y optimizado en 29/30 con interseccion de 27,
  When se reporta, Then el delta se calcula sobre los 27 y se muestran ambos
  scores con su `n_evaluados / n_total`.

## Coverage mapping (requisito -> derivado)

| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | parcial: `shared/llm/failures.py`, `shared/llm/call.py` (clasificador y contador, vigente); `tests/test_single_call_point.py` (punto unico de llamada, vigente); conteo por los adapters de `gepa_standalone` vigente (3c); envoltorios de `dspy_gepa_poc` pendiente (3e) |
| FR-002 | parcial: `gepa_standalone/adapters/*.py`, `shared/llm/attribution.py`; `tests/test_gepa_adapters_failures.py` (tratamiento por clase en los cuatro adapters de `gepa_standalone`, vigente); `dspy_gepa_poc` pendiente (3e) |
| FR-003 | pendiente |
| FR-004 | parcial: `gepa_standalone/adapters/*.py`, `shared/llm/attribution.py`, `shared/llm/call.py` (`capture_finish_reason`, `finish_reason` del baseline sano), `shared/llm/failures.py`; `tests/test_attribution.py`, `tests/test_gepa_adapters_failures.py` (`TestAttribution`, vigente); `dspy_gepa_poc` pendiente (3e) |
| FR-005 | `shared/llm/reflection.py` (`ReflectionGuard`, `reflection_format_failure`), `gepa_standalone/core/llm_factory.py` (`ReflectionLM`), `shared/llm/dspy_lm.py` (`CheckedLM` rol `reflection`); `tests/test_reflection_guard.py` (verificado contra `gepa==0.0.27` y `dspy==3.2.1`, vigente); `case_id` = iteracion de GEPA via callback, cableado en los orquestadores pendiente (4b) |
| FR-006 | pendiente |
| FR-007 | parcial: rol `reflection` (un WARNING por propuesta desde `FailureTracker.record`, log de la capa de llamada a DEBUG; `shared/llm/config.py`, `tests/test_reflection_guard.py`, `tests/test_empty_response_dspy.py`, vigente); tarea de `gepa_standalone` vigente (3c); tarea de `dspy_gepa_poc` (3e) y juez pendiente |
| FR-008 | pendiente |
| FR-009 | `gepa_standalone/adapters/simple_rag_adapter.py` (prompt JSON, validacion de rango, `judge_retries` default 2, `formato` del juez; reintentos desde el YAML pendiente en 4c); `tests/test_rag_judge_json.py` (vigente) |
| FR-010 | parcial: `formato` por adapter en `gepa_standalone/adapters/simple_classifier_adapter.py` y `simple_extractor_adapter.py`; `tests/test_gepa_adapters_failures.py` (`TestFormatFailures`, vigente); `dspy_gepa_poc` pendiente (3e) |
| FR-011 | parcial: `shared/llm/call.py`, `shared/llm/dspy_lm.py` (`num_retries=0` y reintento propio solo de `infraestructura`, vigente); `tests/test_failure_call.py`, `tests/test_single_call_point.py`; reintentos desde el YAML pendiente (4c) |
| FR-012 | parcial: resultado por caso (`case_id`, `evaluated`, `failure`) en `gepa_standalone/adapters/base_adapter.py`; `tests/test_gepa_adapters_failures.py` (`TestNoCaseDisappears`, vigente); prediccion NE de DSPy pendiente (3e) |
| FR-013 | `gepa_standalone/data/data_loader.py`, `dspy_gepa_poc/data_loader.py` (`case_id` del CSV o `<split>:<fila>`, vigente); `tests/test_case_id_loaders.py`; `case_id` de las fallas en los adapters de `gepa_standalone` vigente (3c); envoltorios de `dspy_gepa_poc` pendiente (3e) |
| FR-014 | pendiente |
| FR-015 | `tests/litellm_failure_payloads.py`, `tests/test_litellm_failure_mapping.py` (evidencia del comportamiento de LiteLLM, vigente); `shared/llm/failures.py`, `tests/test_failures.py` (clasificador, vigente) |
| FR-016 | pendiente |
| SC-001 | parcial: `tests/test_gepa_adapters_failures.py` (fallas inyectadas en los cuatro adapters de `gepa_standalone`: ningun caso desaparece, vigente); `dspy_gepa_poc` pendiente (3e) |
| SC-002 | pendiente |
| SC-003 | `tests/test_reflection_guard.py` (`gepa.optimize` y `dspy.GEPA` reales: propuesta con respuesta 200 `presupuesto`, `filtro_salida`, `sin_texto` o `formato` (y `configuracion` en `gepa.optimize`) no crea ni evalua candidato; las 99 fallas de capa 1 se lanzan desde el envoltorio en ambos subproyectos, vigente) |
| SC-004 | pendiente |
| SC-005 | pendiente |
| SC-006 | pendiente |
| SC-007 | pendiente |
| SC-008 | parcial: `tests/test_gepa_adapters_failures.py` (`TestReflectiveDatasetExcludesNE`: un caso NE nunca entra al dataset reflexivo de `gepa_standalone`, vigente); `dspy_gepa_poc` pendiente (3e) |
| SC-009 | payloads en `tests/litellm_failure_payloads.py` (102 casos, campo de clase esperada incluido, vigente); `tests/test_failures.py` (clasificador sobre los 102 payloads, vigente); `tests/test_single_call_point.py` (1 llamada HTTP por caso via `dspy.Predict`, 1 + reintentos si es `infraestructura`, vigente) |
