# Plan de implementacion — SPEC-107 limite de tasa del proveedor

Fuente del plan de ejecucion de [[SPEC-107-limite-de-tasa-proveedor]]. La spec
define que debe cumplirse (FR/SC); este documento define en que orden se
implementa, con que modelo de agente, que decisiones de diseno ya estan tomadas
y en que estado esta cada subfase. Si cambia un requisito, se edita la spec y
aca solo se ajusta la referencia.

Creado: 2026-11-27. Base: `e1a97e8` (SPEC-107 iteracion 2, `draft`; la
iteracion 3, del mismo dia, agrega FR-013 y SC-012, ver D18 y C9). Dependencias
cumplidas: SPEC-104, SPEC-105 y SPEC-106 `active`. Estado del plan: aprobado el
2026-11-27 (C1 a C8 confirmadas, ver "Decisiones a confirmar"); sin subfases
ejecutadas.

## Criterio de modelo

"Modelo" es el modelo del agente de codigo que ejecuta cada subfase.

- Opus 5.5 (`claude -p ... --model claude-opus-5-5`, perfil por defecto):
  cambios que cruzan el punto de llamada y la clasificacion de fallas
  (SPEC-104/105), concurrencia, sonda de conexion, enmiendas normativas a specs
  `active`, revision integral y cierre.
- Sonnet 5.5 (`claude-e -p ... --model claude-sonnet-5-5`, perfil de empresa):
  implementacion guiada por la spec, por las decisiones D1 a D17 de este plan y
  por tests ya escritos.

Leccion registrada (SPEC-104, subfase 2a): una subfase del punto de llamada
lanzada con Sonnet tuvo que relanzarse con Opus. Ante la duda en el punto de
llamada (`shared/llm/call.py`, `failures.py`, `attribution.py`), Opus.

Las decisiones de diseno se fijaron al escribir este plan, leyendo el codigo
(no hay subfases de diseno aparte). Si una decision choca con el codigo, la
sesion lo anota como bloqueo (ver Reglas) y no improvisa.

## Reglas de ejecucion

- La spec queda en `draft` hasta el Cierre. Ninguna subfase la pasa a `active`
  ni toca su fila en `specs/SPECS_REGISTRY.md`.
- Tests primero. Cuando RED y GREEN van en la misma subfase, la sesion escribe
  primero los tests, verifica que fallan por la razon correcta y despues
  implementa. Cuando van en subfases distintas (fase 1), los tests RED se marcan
  `@pytest.mark.xfail(strict=True, reason="SPEC-107 <subfase que los cierra>")`
  para que `ci_local.sh` quede verde; la subfase GREEN quita la marca. Los
  simbolos que aun no existen se importan dentro del test (no a nivel de
  modulo), para que el RED sea `xfail` y no un error de coleccion.
- Los tests verifican la spec, no el codigo actual (`docs/ARCHITECTURE.md`,
  Invariantes). Respuestas de LLM con `litellm.ModelResponse` via el helper de
  `tests/conftest.py`; excepciones de proveedor desde
  `tests/litellm_failure_payloads.py` (un payload nuevo se agrega ahi, D16).
  Sin red: ningun test llama a una API. Ningun test duerme de verdad (D15).
- Cada subfase cierra con `./shared/utils/ci_local.sh` verde y un commit
  `feat(spec-107): <subfase> <resumen>` (o `test(...)`, `docs(...)`). Commits
  sin trailer `Co-Authored-By`. Sin mezclar `-n`/`-q` con `git commit` en el
  mismo comando.
- Al cerrar una subfase: marcarla `hecho (<hash>)` en la tabla y pasar a
  vigente la fila del Coverage mapping de la spec que corresponda, en un commit
  aparte `docs(spec-107): estado de <subfase>`.
- "Archivos" del Detalle es la lista cerrada que usa el control de salida: el
  diff MUST NOT tocar otros (este plan siempre se puede editar). Si hace falta
  otro archivo, la sesion lo anota como bloqueo en "Bloqueos" y no commitea.
  Excepcion (decision del usuario, 2026-11-27, vigente desde SPEC-106): la spec
  manda y los tests se adaptan a ella. Un test existente, de cualquier archivo,
  cuya asercion fija una conducta que la spec cambia MAY ajustarse para que
  verifique la conducta nueva (asercion, fixture o constante que la spec
  modifica), sin bloqueo, listandolo en el resumen y en la nota de la subfase
  con el FR que lo motiva. Cualquier otro cambio fuera de la lista sigue siendo
  bloqueo.
- Arquitectura (`docs/ARCHITECTURE.md`): toda llamada al LLM pasa por
  `shared/llm/call.py::_raw_completion`; `shared/` no importa `gepa_standalone`
  ni `dspy_gepa_poc`; en `shared/` solo `dspy_lm.py` importa `dspy`; solo API
  publica de `dspy`, `gepa` y `litellm` (`litellm_response_headers` entra como
  superficie, FR-002). Sin emoticones. ASCII. Un doc, un proposito.

## Consumo de tokens (aplica a toda sesion `-p`)

- Leer solo: la spec, de este plan las secciones "Reglas de ejecucion",
  "Consumo de tokens", las decisiones que nombra la fila y el "Detalle" de la
  subfase. `AGENTS.md` ya llega por `CLAUDE.md`. No leer otros planes, ni
  `historial/sdd.md` (salvo 4b y Cierre), ni docs que la subfase no edita.
- Archivos de mas de 300 lineas: ubicar con Grep el simbolo y leer solo ese
  rango (`offset`/`limit`). Los rangos de "Puntos de entrada" son orientativos
  al `e1a97e8`.
- Durante el trabajo, pytest dirigido (`-q -x` sobre los tests de la subfase).
  `ci_local.sh` una vez al final, con la salida recortada (`| tail -n 40`); se
  repite solo si fallo.
- No explorar librerias instaladas: la verificacion de LiteLLM ya esta hecha en
  este plan ("Verificacion empirica"). Si una subfase la necesita, es un bloqueo.
- Resumen final de la sesion: maximo 15 lineas (subfase, commit, tests nuevos,
  tests existentes ajustados con su FR, desvios o bloqueos). El detalle va al
  plan, no a la salida.

## Fases

| Fase | Subfase | Requisitos | Decisiones | Modelo | Estado |
|---|---|---|---|---|---|
| 1 Nucleo (`shared/llm`) | 1a Tests RED: funciones puras de limite de tasa, contador, validador y punto de llamada (xfail strict por subfase); payloads 429 nuevos | FR-001 a FR-004, FR-006 a FR-010 (contador), FR-013, SC-001 a SC-005, SC-007, SC-008 (contador), SC-011, SC-012 | D1 a D8, D11, D15, D16, D18 | Sonnet 5.5 | pendiente |
| | 1b `shared/llm/rate_limit.py` (decision, cabeceras, backoff, reloj), `LLMFailure.es_limite_tasa`, `FailureTracker` (presupuesto, conteo, esperas, cooldown, corte, `snapshot`, `is_rate_limit_abort`, `EXIT_RATE_LIMIT`), validador y reloj simulado autouse (GREEN de lo marcado "1b") | FR-001 (campo), FR-002, FR-003 (decision), FR-004, FR-009, FR-010 (contador), FR-013 (estado), SC-002, SC-008 (contador), SC-011 | D1, D2, D5 (estado), D7, D8, D11, D15, D18 (estado) | Sonnet 5.5 | pendiente |
| | 1c Punto de llamada: presupuesto propio del 429, espera por cabecera o backoff, 429 no transitorio sin espera, espera interrumpible, aviso `INFO` con modelo, corte por limite persistente; ajuste de los conteos de tests existentes (GREEN de "1c") | FR-001, FR-002, FR-003, FR-004, FR-005 (emision), FR-006, FR-008, FR-013, SC-001, SC-003, SC-004, SC-005, SC-012 | D2, D3, D4, D6, D18 | Opus 5.5 | pendiente |
| | 1d Cooldown compartido por rol entre hilos y propagacion de `es_limite_tasa` por la atribucion contra el baseline (GREEN de "1d") | FR-007, FR-001 (propagacion), SC-007 | D2, D5 | Opus 5.5 | pendiente |
| 2 Sonda y entry points | 2a Sonda con espera solo ante 429; `LLMConnectionError.rate_limited`; mensaje por causa | FR-011 (sonda), SC-009 (sonda) | D9 | Opus 5.5 | pendiente |
| | 2b Entry points: codigo 75, orden `configure_failure_tracker` antes de la sonda en GEPA, handler `INFO` acotado, claves nuevas del YAML; SC-006 visible en consola | FR-005 (consola), FR-010, FR-011 (orden), SC-006, SC-008, SC-009 | D6, D8, D10, D11, D17 | Sonnet 5.5 | pendiente |
| 3 Runners | 3a `BATCH_COOLDOWN` y corte ante 75 en `run_dspy_total.sh` y `run_demos_gepa.sh` (helper comun), tests con python simulado | FR-012 (runners), SC-010 (runners) | D12, D13 | Sonnet 5.5 | pendiente |
| | 3b `run_seeds`: corte ante 75 y `BATCH_COOLDOWN` con `--jobs 1` | FR-012 (`run_seeds`), SC-010 (`run_seeds`) | D14 | Sonnet 5.5 | pendiente |
| 4 Docs y enmiendas | 4a Docs: `GEPA_MANEJO_ERRORES.md`, `LLM_CONFIG.md`, `YAML_CONFIG_REFERENCE.md`, `METADATA_REPRODUCIBILIDAD.md`, `DEVELOPMENT.md`, `PROTOCOLO_N_SEEDS.md` | FR-004, FR-005, FR-009, FR-010, FR-011, FR-012 (docs) | todas | Sonnet 5.5 | pendiente |
| | 4b Enmiendas de SPEC-104 (FR-007, FR-011, FR-015) y SPEC-106 (FR-005) con traza en `historial/sdd.md`; enmiendas aprobadas de SPEC-107 (H1 a H6 y las decisiones C2, C4, C5, C6) | FR-003, FR-005, FR-011 | - | Opus 5.5 | pendiente |
| 5 Revision | 5 Revision integral sin red contra la spec (diff `e1a97e8..HEAD`); hallazgos al plan | todos | todas | Opus 5.5 | pendiente |
| 6 Verificacion (sesion interactiva, opcional) | Corrida corta real por subproyecto sin 429 forzado (regresion: `rate_limit_waits` en cero, salida 0); el 429 se verifica simulado | SC-005, SC-006 (regresion) | - | Sonnet 5.5 | pendiente |
| Cierre (sesion interactiva) | `[SDD-Check]`, spec y registro a `active`, Coverage mapping vigente, deuda | todos | - | Opus 5.5 | pendiente |

## Dependencias

- 1a -> 1b -> 1c -> 1d. Todo lo demas requiere 1b.
- 2a requiere 1c. 2b requiere 2a y 1d.
- 3a y 3b requieren 1b (usan `EXIT_RATE_LIMIT`); son independientes de la fase 2.
- 4a requiere 2b, 3a y 3b. 4b requiere 4a y las "Decisiones a confirmar".
- 5 requiere 4b. 6 requiere 5 y sus correcciones. Cierre requiere 6 (o su
  omision decidida por el usuario).

Orden lineal recomendado: 1a, 1b, 1c, 1d, 2a, 2b, 3a, 3b, 4a, 4b, 5, 6, Cierre.

## Verificacion empirica (2026-11-27, al escribir el plan)

Entorno `.venv`: litellm 1.108.5, openai 3.57.0, httpx 0.28.1, dspy 3.5.0,
gepa 0.1.4. Sin red: `httpx.Client.send` interceptado con el mismo mecanismo de
`tests/test_litellm_failure_mapping.py::intercept_httpx`, llamando a
`litellm.completion(..., num_retries=0)` como `_raw_completion`. Scripts y salida
fuera del repo (`$HOME/spec107_logs/`: `test_verify_headers.py`,
`test_verify_azure_quota.py`, `test_verify_runner_fake_python.py`), corridos con
`.venv/Scripts/python.exe -m pytest <script> -s -p no:cacheprovider
--rootdir=<dir>`; no dejan archivos en el arbol.

Resultados (una llamada HTTP en todos los casos, `classify_exception` como se
indica):

| Caso (proveedor, respuesta) | Excepcion raiz | Clase SPEC-104 | `response.headers` | `headers` | `litellm_response_headers` | `body` |
|---|---|---|---|---|---|---|
| Azure 429 TPM, `retry-after: 20`, `x-ms-retry-after-ms: 19500` | `RateLimitError` 429 | infraestructura | `{}` | `None` | `httpx.Headers` con ambas | `None` |
| OpenAI 429 TPM, `retry-after: 2`, `retry-after-ms: 1500` | `RateLimitError` 429 | infraestructura | `{}` | `None` | `httpx.Headers` con ambas | dict (`code=rate_limit_exceeded`) |
| Anthropic 429, `retry-after: 7` | `RateLimitError` 429 | infraestructura | `{}` | `None` | `httpx.Headers` con `retry-after` | `None` |
| OpenAI 429 `insufficient_quota` | `RateLimitError` 429 | infraestructura | `{}` | `None` | sin `retry-after` | dict, `type` y `code` = `insufficient_quota` |
| Azure 429 `insufficient_quota` | `RateLimitError` 429 | infraestructura | `{}` | `None` | sin `retry-after` | `None` (ver H1) |
| OpenAI 429 "Request too large for ... (TPM)" | `RateLimitError` 429 | infraestructura | `{}` | `None` | sin `retry-after` | dict |
| OpenAI 413 "Request too large" (payload `413_too_large`) | `RateLimitError` 429 | infraestructura | `{}` | `None` | sin `retry-after` | dict |
| Azure 413 "Request too large" (payload `413_too_large`) | `APIError` 413 | configuracion | sin atributo `response` | sin atributo | `httpx.Headers` | `None` (ver H2) |
| OpenAI 429 `retry-after` en fecha HTTP | `RateLimitError` 429 | infraestructura | `{}` | `None` | la fecha tal cual (texto) | dict |

Conclusiones:

- Confirmado lo que afirma la spec sobre cabeceras: en los tres proveedores
  `exc.response.headers` llega vacio, `exc.headers` es `None` y las cabeceras
  del proveedor estan en `exc.litellm_response_headers` (`httpx.Headers`). Lo
  verificado es el transporte (lo que el proveedor envie llega ahi); que cada
  proveedor envie esas cabeceras concretas sale de su documentacion y de la
  revision externa, no se puede verificar sin red.
- Confirmado para OpenAI: `insufficient_quota` llega como `RateLimitError(429)`
  sin `Retry-After` y con `exc.body["type"]` y `exc.body["code"]` =
  `insufficient_quota`. NO confirmado para Azure: hallazgo H1.
- La conversion de "Request too large" a `RateLimitError` existe solo en la
  rama de mapeo OpenAI de LiteLLM (`exception_mapping_utils.py`, ~L432); en
  Azure el mismo texto queda `APIError(413)`: hallazgo H2 (solo redaccion).
- Runners: la prueba con python simulado funciona en Windows (Git Bash) con
  `.venv/bin/python` como script bash, `sleep` falso en `PATH`, stdin en bytes
  (`b"all\n1\n"`; en texto, Windows convierte a CRLF y el runner rechaza la
  seleccion), `SKIP_ENV_CHECK=1` y `KEEP_AWAKE=0`. Linea base registrada: hoy,
  con `CONTINUE_ON_FAIL=1`, una prueba que sale con 75 no detiene el batch
  (RED de SC-010). Cada invocacion del runner tarda 10 a 17 s en este equipo.

## Hallazgos (spec vs codigo o entorno) y enmiendas propuestas

No se edito la spec. Cada enmienda la aplica 4b si el usuario la aprueba.

- H1 (media, FR-003 (ii) y Contexto). En Azure, `insufficient_quota` llega como
  `RateLimitError(429)` con `exc.body = None`; el cuerpo con `type`/`code` =
  `insufficient_quota` solo queda en la cadena implicita `__context__`
  (`AzureOpenAIError` interna de LiteLLM y `openai.RateLimitError`), no en
  `__cause__` ni en un atributo publico. Atributos de la raiz: `code='429'`,
  `type='throttling_error'`, `rate_limit_type=None`, `category=
  'vendor_rate_limit'`; el texto solo dice "You exceeded your current quota".
  Consecuencia con el diseno de este plan: en Azure ese caso se trata como 429
  transitorio sin cabecera (7 llamadas, hasta 195 s por caso) y, si aborta,
  sale igual con 75 (`es_limite_tasa=True`). Enmienda propuesta: FR-003 (ii) y
  el Contexto dicen "en OpenAI"; "en Azure (litellm 1.108.5) el cuerpo no llega
  a `exc.body` y el caso se trata como transitorio sin cabecera"; un test de
  contrato fija `body is None` en Azure para que un upgrade que lo preserve se
  note. Alternativas descartadas: recorrer `__context__` (implicito, no es API
  publica, SPEC-105 FR-007) y buscar "exceeded your current quota" en el texto
  (excepcion textual nueva a SPEC-104 FR-015). Decision a confirmar C1.
- H2 (baja, Contexto, redaccion). "LiteLLM convierte en `RateLimitError` todo
  error cuyo texto contenga 'Request too large'" vale para la rama OpenAI del
  mapeo; Azure conserva `APIError(413)` (`configuracion`), como ya dice la
  fila de la matriz. Enmienda: "en la rama OpenAI del mapeo de LiteLLM".
- H3 (baja, FR-005, precision). Un handler en el logger `shared.llm` mismo
  desactiva el `lastResort` de Python para los WARNING/ERROR de
  `shared.llm.failures` (que hoy salen por `lastResort`, sin formato) y los
  pasaria por ese handler. El plan usa un logger hijo dedicado,
  `shared.llm.rate_limit` (D6). Enmienda: "acotado al logger
  `shared.llm.rate_limit`".
- H4 (baja, FR-011). "Si el 429 persiste o es no transitorio, la corrida MUST
  salir con 75" incluye literalmente el 429 de tamano (iii), que FR-003 marca
  `es_limite_tasa=False`. En la sonda (5 tokens) es inalcanzable. El plan sale
  con 75 si y solo si `es_limite_tasa` (coherente con FR-010). Enmienda: "si el
  429 por limite de tasa persiste o es no transitorio".
- H5 (baja, FR-004). Resuelta (C3, 2026-11-27): `failures.rate_limit_max_wait`
  acota solo el `Retry-After` (FR-003 (i)), no el backoff sin cabecera. Con los
  defaults no importa (60 < 120); con `rate_limit_max_wait: 10` el backoff
  llegaria igual a 60 s. La enmienda de FR-004 lo deja escrito en 4b.
- H6 (baja, matriz de proporcionalidad, redaccion). "195 s como maximo por
  caso" vale por llamada: un caso con varias llamadas (tarea y juez en RAG, o
  sonda de atribucion contra el baseline) puede sumar mas de una espera
  completa. Enmienda: "por llamada" en la matriz y en SC-003 donde aplique.

Decisiones del plan que interpretan o extienden la letra de la spec y que 4b
MUST llevar al texto de SPEC-107 (para que al Cierre la spec describa la
conducta implementada): C2 (FR-012: `seed_protocol` salta tambien los
`--config` restantes y devuelve 75), C4 (FR-005 y FR-009: las esperas por
cooldown emiten linea `INFO` y cuentan en `waits`/`seconds`), C5 (FR-009 y
FR-011: las esperas de la sonda cuentan en `rate_limit_waits`) y C6 (FR-012:
los runners salen con 75 al detenerse por limite del proveedor).

## Decisiones de diseno

D1. Modulo nuevo `shared/llm/rate_limit.py` (sin `dspy`; importa solo
`failures.py` para `root_exception`). Funciones puras y reloj:
- `RATE_LIMIT_LOGGER = "shared.llm.rate_limit"` (D6).
- `is_rate_limit(exc) -> bool`: sobre `root_exception(exc)`, clase
  `RateLimitError` en el MRO o `status_code == 429`. Solo se consulta cuando
  `classify_exception` dio `infraestructura` (FR-001).
- `response_headers(root) -> Mapping[str, str]`: primer no vacio de
  `root.litellm_response_headers`, `root.response.headers`, `root.headers`
  (FR-002, orden defensivo; `getattr` con default, sin lanzar; claves sin
  distinguir mayusculas: `httpx.Headers` ya lo hace, un dict se normaliza).
- `retry_after_seconds(headers, now_wall) -> tuple[float, str] | None`:
  prioridad `retry-after-ms` (/1000), `x-ms-retry-after-ms` (/1000),
  `retry-after` (segundos `float`, o fecha HTTP con
  `email.utils.parsedate_to_datetime` menos `now_wall`, fecha sin zona = UTC,
  acotada a >= 0). Devuelve `(segundos, nombre_de_cabecera)`. Un valor no
  numerico, negativo, `nan` o `inf` se ignora y se pasa a la siguiente; ninguna
  valida = `None` (sin cabecera). MUST NOT leer `x-ratelimit-reset-*`.
- `RateLimitDecision` (dataclass frozen): `transitorio: bool`, `espera_pedida:
  float | None`, `fuente: str | None` (cabecera o `None`), `motivo: str | None`
  (`"insufficient_quota"`, `"retry_after_excede_tope"`, `"request_too_large"`),
  `es_limite_tasa: bool`.
- `decide(exc, max_wait, now_wall) -> RateLimitDecision`, orden (FR-003, campos
  estructurados primero): (ii) `exc.body` dict con `code` o `type` =
  `insufficient_quota` -> no transitorio, `es_limite_tasa=True`; (i) cabecera
  valida > `max_wait` -> no transitorio, `es_limite_tasa=True`, `espera_pedida`
  para el mensaje; (iii) "request too large" en `str(root).lower()` -> no
  transitorio, `es_limite_tasa=False`; si no, transitorio con la cabecera (o sin
  ella), `es_limite_tasa=True`. Igual a `max_wait` es transitorio.
- `backoff_seconds(n, uniform) = min(5 * 2**n, 60) * uniform(0.8, 1.2)` (n desde
  0); `header_wait(s, uniform) = s + uniform(0, 0.25)` (jitter positivo, el MAY
  de FR-002 se adopta; C7).
- Reloj inyectable: protocolo `Clock` con `monotonic()`, `time()` (pared, para
  la fecha HTTP), `sleep(s)` y `uniform(a, b)`. `SystemClock` resuelve
  `time.sleep`/`time.monotonic`/`time.time`/`random.uniform` en cada llamada
  (los parches globales vigentes de `time.sleep` siguen valiendo).
  `get_clock()`, y `use_clock(clock)` (context manager) para tests. Solo la
  espera de limite de tasa usa el reloj; el backoff de 1, 2 y 4 s de las demas
  fallas sigue con `time.sleep` (SC-005: 0 diferencias).

D2. `es_limite_tasa` hasta el contador (FR-001, FR-010):
- `LLMFailure.es_limite_tasa: bool = False` (ultimo campo, con default: las
  construcciones posicionales vigentes no cambian). Lo fija la capa de llamada
  (`call_with_infra_retry`, `probe_completion`) con `decision.es_limite_tasa`
  cuando la clase es `infraestructura` y `is_rate_limit`; en todo otro caso
  `False`.
- `with_case` y `dataclasses.replace` lo conservan. `BaselineOutcome` gana
  `es_limite_tasa: bool = False` (lo llena `BaselineProbe.outcome` desde la
  falla); `attribute_failure`, cuando sustituye la clase del caso por la del
  baseline, toma tambien su `es_limite_tasa` (1d). `failure_to_dict` lo incluye
  por `asdict` (la falla por caso de `base_adapter` gana la clave).
- `FailureTracker.record(failure)`: despues del filtro de `entrada_dato`
  repetido, suma `_rate_limit_failures[rol]` si `failure.es_limite_tasa`. No es
  una clave de conteo: `counts` no cambia (FR-001).

D3. Firma y bucle del punto de llamada (FR-001 a FR-005, FR-008):
- `call_with_infra_retry(fn, role, *, model=None, infra_retries=None,
  backoff_base=1.0, rate_limit_retries=None, rate_limit_max_wait=None)`. `None`
  = lo del `FailureTracker`. `model` es keyword con default `None` para no
  romper llamadas directas de tests; produccion siempre lo pasa y el aviso usa
  `"(sin modelo)"` si falta. `checked_response` pasa `model=kwargs.get("model")`
  (cubre `checked_completion*` y `CheckedEngine.complete`, que ya pone `model`
  en `kwargs`). Sin parametros nuevos en `checked_*`.
- Dos contadores independientes por llamada: `attempt_infra` (presupuesto
  `infra_retries`, espera `backoff_base * 2**n` con `time.sleep` y log DEBUG,
  igual que hoy) y `attempt_rl` (presupuesto `rate_limit_retries`). Un 429 solo
  consume el suyo; un 5xx solo el suyo.
- 429 (`infraestructura` y `is_rate_limit`): `decide(...)`. No transitorio ->
  lanza `LLMCallFailure` sin esperar, con `es_limite_tasa` de la decision y
  mensaje con la causa (`insufficient_quota`; "el proveedor pide N s, mayor que
  failures.rate_limit_max_wait=M s"; "request too large"). Transitorio con
  intentos -> espera `header_wait` o `backoff_seconds(attempt_rl)`, fija el
  cooldown del rol (D5), espera (D4) y reintenta. Agotado -> `LLMCallFailure`
  `infraestructura` con `es_limite_tasa=True` y mensaje "limite de tasa
  persistente tras N esperas".
- FR-008: el bucle llama siempre al mismo `fn` (mismos kwargs); el test lo fija
  comparando el `model` de cada llamada HTTP interceptada.

D4. Espera interrumpible (FR-006, FR-009): `_rate_limit_wait(role, model,
seconds, intento, total, fuente)` en `call.py`:
- Emite una linea `INFO` (D6) y llama `tracker.start_rate_limit_wait(rol)`
  (`waits += 1`). Una linea = una espera.
- Duerme en tramos de `RATE_LIMIT_CHUNK_S = 5.0` como maximo sobre una duracion
  planificada (no se re-sondea `monotonic` para decidir cuanto falta: con
  `time.sleep` parcheado a no-op el bucle no gira en vacio). Antes de cada tramo
  `tracker.check_abort()`. Cada tramo se mide con `clock.monotonic()` antes y
  despues, en `try/finally`, y suma a `tracker.add_rate_limit_seconds(rol, s)`:
  un `RunAborted` o Ctrl+C deja contado el tramo parcial.

D5. Cooldown por rol (FR-007, confirmado por el usuario):
- Estado en `FailureTracker` bajo su lock: `_cooldown_until: dict[rol, float]`
  (valores de `clock.monotonic()`, opacos para el tracker),
  `extend_cooldown(rol, until)` (conserva el maximo) y `cooldown_until(rol)`.
  `reset()` lo limpia (vive en `_init_state`).
- Lo fija el hilo que recibe un 429 transitorio, antes de dormir:
  `until = monotonic() + espera` (cabecera o backoff: ambos son "un 429 con
  espera").
- Antes de cada llamada (`fn()` en `call_with_infra_retry`), mientras
  `cooldown_until(rol) - monotonic() > 0`: espera ese resto con D4 (linea `INFO`
  con `fuente=cooldown`, cuenta en `waits` y `seconds`; C4). El hilo que fijo el
  cooldown no espera dos veces: al despertar, `monotonic() >= until`. La espera
  por cooldown MUST NOT consumir `attempt_rl` ni `attempt_infra`: el hilo no
  recibio un 429, solo difiere su llamada.
- Limitacion aceptada (letra de FR-007, "por rol"): el cooldown no se comparte
  entre roles aunque usen el mismo deployment (SPEC-106 permite, p. ej., tarea y
  juez sobre el mismo modelo); el 429 de un rol no difiere las llamadas del
  otro. Queda como deuda en el Cierre.
- Es reactivo: no limita hilos ni tasa (fuera de alcance de la spec). En
  `gepa_standalone` no hay hilos (no existe `num_threads`); aplica a
  `dspy_gepa_poc` (`dspy.Evaluate` y `dspy.GEPA` con `num_threads`).

D6. Aviso visible (FR-005, H3):
- Logger dedicado `shared.llm.rate_limit` (hijo de `shared.llm`), `logger.info`.
  Mensaje fijo (lo parsea SC-006): `Limite de tasa: rol=<rol> modelo=<modelo>
  intento <n>/<m> espera <s>s fuente=<retry-after-ms|x-ms-retry-after-ms|
  retry-after|backoff|cooldown>`, con `n` = intento que se va a hacer y `m = 1 +
  rate_limit_retries`; `s` con un decimal. En una espera por cooldown (D5) el
  hilo no recibio un 429: `n = attempt_rl + 1` de esa llamada (la llamada que
  difiere), sin consumir intento.
- `enable_rate_limit_console()` en `rate_limit.py`, exportada: agrega a ese
  logger (y solo a ese) un handler `INFO` que escribe en el `sys.stdout`
  vigente al emitir (subclase de `StreamHandler` con `stream` resuelto en
  `emit`, para que `capsys` lo vea), formato `"[INFO]  %(message)s"` (mismo
  prefijo que `shared.display.log_info`, sin importarlo), fija el nivel del
  logger en `INFO` y es idempotente. `propagate` queda en `True` (`caplog` lo
  captura; la raiz no tiene handlers, no hay duplicado). MUST NOT tocar el
  logger raiz ni `shared.llm`.
- La llaman los `main()` de ambos entry points tras `configure_stdio()` (2b) y
  `dspy_gepa_poc/scripts/baseline_only.py` (SHOULD, mismo commit).
- No es una falla: no pasa por `record`, no suma a `counts` ni a `usage`.

D7. `run.json` (FR-009, SC-006): `FailureTracker.snapshot()` agrega
`"rate_limit_waits": {rol: {"waits": int, "seconds": float, "cortes": int}}`
(`cortes`: D18) para cada rol de
`ROLES`, siempre (ceros sin esperas), `seconds` redondeado a 3 decimales. Vive
dentro de `failures`; las claves de primer nivel de `run.json` no cambian
(`create_run` pasa `failures` tal cual). `tests/test_sc006_no_failure_regression.py`
asevera campos sueltos, no el dict completo: sigue verde y gana la asercion de
ceros.

D8. Codigo de salida (FR-010, SC-008):
- `EXIT_RATE_LIMIT = 75` en `failures.py`, reexportado en
  `shared/llm/__init__.py`.
- `FailureTracker.is_rate_limit_abort() -> bool`, bajo el lock, sobre el aborto
  fijado (`clave` K y rol R): sin aborto -> `False`; K = `infraestructura` ->
  `_rate_limit_failures[R] / counts["infraestructura"][R] > 0.5`; K = `total` ->
  `_rate_limit_failures[R] / sum(counts[*][R]) > 0.5`; denominador 0 u otra K ->
  `False`. Lee el estado del contador, no la excepcion: vale aunque GEPA se haya
  tragado el `RunAborted` y lo relance `check_abort`.
- `exit_code_for(exc) -> int` en `shared/llm/errors.py` (importa `failures`; no
  hay ciclo), exportada: `RunAborted` -> 75 si `is_rate_limit_abort()`, si no 1;
  `LLMConnectionError` con `rate_limited` (D9) -> 75, si no 1; otra -> 1. Unica
  regla para ambos entry points.

D9. Sonda (FR-011, SC-009): `probe_completion(kwargs, role)` pasa a un bucle:
- Excepcion `infraestructura` con `is_rate_limit` -> `decide(...)` con la
  configuracion del tracker: no transitorio -> `LLMCallFailure` inmediata;
  transitorio con intentos -> espera D4 (mismo aviso, cuenta en
  `rate_limit_waits`) y reintenta; agotado -> `LLMCallFailure` con
  `es_limite_tasa=True`. Cualquier otra clase -> `LLMCallFailure` inmediata, 0
  reintentos (credencial, 404, red, 5xx: igual que hoy).
- Sigue sin `record_usage`, sin `record` y sin `abort` (no hay corrida).
- `LLMConnectionError` gana `rate_limited: bool = False`. `validate_connection`
  lo fija con `failure.es_limite_tasa` y, en ese caso, el mensaje dice "limite de
  tasa del proveedor (429)" con la causa (persistente tras N esperas, o no
  transitorio con la espera pedida o `insufficient_quota`) en lugar del texto
  generico de `infraestructura`.
- El entry point sale con `exit_code_for(e)` (D8): 75 con `rate_limited`.

D10. Orden en `gepa_standalone/universal_optimizer.py::run` (FR-011): mover
`self.configure_failure_tracker()` a justo despues de `build_llm_configs()` y
antes de `validate_llm_connections()`, y quitar la llamada de ~L258 (un segundo
`reset()` borraria las esperas de la sonda y el cooldown). Entre ambos puntos no
hay llamadas al LLM (`load_data`, `initialize_adapter` y `set_baseline` no
llaman; `set_baseline` solo crea el probe). `get_tracker().reset()` (uso) queda
donde esta. En `dspy_gepa_poc` el orden ya es el correcto (`setup_models`).
Consecuencia: las esperas de la sonda cuentan en `rate_limit_waits` en ambos
subproyectos (C5).

D11. Configuracion (FR-004, SC-011):
- `FailureTracker`: `DEFAULT_RATE_LIMIT_RETRIES = 6`,
  `DEFAULT_RATE_LIMIT_MAX_WAIT = 120.0`; propiedades `rate_limit_retries` y
  `rate_limit_max_wait`; `configure(..., rate_limit_retries=None,
  rate_limit_max_wait=None)`: `rate_limit_retries` entero >= 0 no booleano
  (regla de `infra_retries`); `rate_limit_max_wait` `int`/`float` >= 0, no
  booleano, finito. `ValueError` si no.
- `FAILURES_KEYS` agrega `rate_limit_retries` y `rate_limit_max_wait`;
  `_validate_failures` los pasa a `FailureTracker().configure(...)` (falla antes
  de gastar tokens). `configure_failure_tracker()` de ambos entry points los
  lee de la seccion `failures` del YAML.

D12. Runners (FR-012, SC-010):
- Helper nuevo `shared/utils/batch_control.sh` (lo hacen `source` ambos
  runners; SSOT de la logica comun): `EXIT_RATE_LIMIT=75`,
  `batch_cooldown_require` (valida `BATCH_COOLDOWN` con `^[0-9]+$`, default 0;
  invalido -> `[ERROR]` claro y `exit 1`; se llama junto a `python_env_require`,
  antes de los prompts y de la primera prueba) y `batch_cooldown_pause
  <current_test>` (pausa `sleep "$BATCH_COOLDOWN"` con una linea `>>> Pausa
  BATCH_COOLDOWN=N s` solo si `current_test > 1` y N > 0; se llama al inicio de
  cada prueba, asi no hay pausa antes de la primera, tras la ultima ni tras una
  detencion).
- Captura del codigo: `rc=0; ejecutar_prueba ... || rc=$?`. Con `rc == 75`:
  `aborted=1`, `rate_limited=1`, `>>> BATCH DETENIDO: limite del proveedor
  (codigo 75)` y `break 2`, tambien con `CONTINUE_ON_FAIL=1`. Resumen: `Causa:
  limite del proveedor (codigo 75)` y `N sin ejecutar`. El runner sale con 75 en
  ese caso (propaga el codigo; C6), con 1 ante otras fallas y 0 sin fallas.
- `sleep` se invoca como comando externo (bash no tiene `sleep` builtin): el
  test lo sustituye en `PATH`.
- `tests/test_batch_runners.py` fija que `EXIT_RATE_LIMIT` del helper es igual a
  la constante de Python (una sola cifra en dos lenguajes, con test).

D13. Prueba de los runners sin LLM (SC-010), en `tests/test_batch_runners.py`
(harness en el mismo archivo), tecnica verificada en este plan:
- Repo temporal en `tmp_path` con copia del runner, de
  `shared/utils/{keep_awake,python_env,batch_control}.sh` y tres YAML vacios; un
  `.venv/bin/python` falso (script bash: devuelve el k-esimo codigo de
  `FAKE_EXIT_CODES` y registra la llamada) y un `sleep` falso al frente del
  `PATH` (registra el argumento). Sin `.venv/Scripts/python.exe`, el helper
  elige `.venv/bin/python` en Windows y en Linux (CI en ubuntu).
- `subprocess.run([bash, runner], input=b"all\n1\n")` (bytes: CRLF), env
  `SKIP_ENV_CHECK=1`, `KEEP_AWAKE=0`, sin `TERM`. `bash` via `shutil.which`,
  excluyendo el lanzador de WSL (`System32`); sin bash -> `skip`.
- Casos (maximo 6 invocaciones: 10 a 17 s cada una en Windows): K=3 con
  `BATCH_COOLDOWN=7` -> 2 pausas de 7 s; 75 en la segunda -> 0 pausas despues,
  1 sin ejecutar, salida 75, aun con `CONTINUE_ON_FAIL=1`; falla 1 con
  `CONTINUE_ON_FAIL=1` sigue (sin regresion); `BATCH_COOLDOWN=abc` -> error
  antes de la primera prueba (0 llamadas). Un runner parametrizado por
  `run_dspy_total.sh` y `run_demos_gepa.sh` donde aplique.
- Limite: el camino `winpty` (stdout en terminal) no se prueba (sin tty); la
  conservacion de 75 bajo winpty queda para la verificacion manual (riesgo).

D14. `seed_protocol.run_seeds` (FR-012, SC-010):
- Devuelve `SeedRunResult(failures: int, rate_limited: bool, not_run: int)`
  (dataclass; hoy ningun test llama a `run_seeds`). Parametros inyectables
  `runner=subprocess.run`, `popen=subprocess.Popen` y `sleep=time.sleep` para
  tests sin procesos ni espera.
- `--jobs 1`: tras cada seed, `returncode == 75` -> `[STOP] limite del
  proveedor (codigo 75): N seeds sin ejecutar` y corta. `BATCH_COOLDOWN` (misma
  validacion que D12, en `main` antes de la primera seed; invalido ->
  `parser.error`) pausa entre seeds (no antes de la primera, no tras la ultima ni
  tras un corte).
- `--jobs > 1`: al drenar un lote, si algun proceso salio con 75 no se lanza
  ninguno mas; los que ya corren se esperan (no se matan). `BATCH_COOLDOWN` no
  aplica (SHOULD solo con `--jobs 1`); si esta definido se avisa una vez.
- `main`: con `rate_limited`, informa el caso con lo que haya, marca los
  `--config` restantes `[SKIP] limite del proveedor` y devuelve 75 (C2).

D15. Tests sin dormir: `tests/conftest.py` gana `FakeClock` (monotonic y pared
simulados, `sleep(s)` avanza el reloj y registra `s` con el hilo, `uniform`
determinista configurable) y un fixture autouse que lo instala con `use_clock`
en todo test (1b). Ningun test de la suite duerme por limite de tasa aunque no
lo sepa; el fixture `fake_clock` expone las esperas a quien las mide.

D16. Payloads: `tests/litellm_failure_payloads.py` gana una tabla
`RATE_LIMIT_CASES` con los casos de la "Verificacion empirica" (429 con
cabeceras por proveedor, `insufficient_quota` OpenAI y Azure, "Request too large"
429 de OpenAI, `retry-after` en fecha HTTP, Anthropic sin cabecera), con
`headers`, `expected_exception`, `expected_body_code` y un campo nuevo
`expected_retry_after` (segundos y cabecera de origen). `RETRY_CASES` no cambia:
sus `expected_http_calls` miden a LiteLLM, no al punto de llamada.

D17. Mensaje del aborto: `shared/display/formatting.py::format_abort_error`
gana el parametro `rate_limited: bool = False` y, con `True`, agrega "Causa:
limite de tasa del proveedor; el batch se detiene (codigo 75)". Quien decide es
el `abort_message` de cada orquestador, que llama a
`get_failure_tracker().is_rate_limit_abort()` y pasa el flag: `shared/display`
MUST NOT leer el estado del contador (hoy solo importa `shared.scoring`). Sin
cambiar el resto del texto (lo parsea SC-005 de SPEC-104 solo en la linea ERROR
del contador, que no cambia).

D18. Corte por limite persistente (FR-013, SC-012; C9):
- Estado en `FailureTracker` bajo su lock, en `_init_state` (lo limpia
  `reset()`): `_rate_limit_cut: set[rol]` y `_cortes: dict[rol, int]`.
  `activate_rate_limit_cut(rol) -> bool` (True solo si no estaba activo; suma a
  `cortes` solo en ese caso), `clear_rate_limit_cut(rol) -> bool` (True si
  estaba activo) y `rate_limit_cut(rol) -> bool`. No toca `counts`, umbrales ni
  `abort`.
- En `call_with_infra_retry` (1c):
  - `fn()` que vuelve sin excepcion -> `clear_rate_limit_cut(rol)` antes de
    devolver; si devolvio True, linea `INFO` `Limite de tasa: rol=<rol>
    modelo=<modelo> corte levantado`. Cuenta cualquier respuesta, aunque despues
    `raise_for_response` la clasifique (`sin_texto`, etc.): la cuota respondio.
  - 429 transitorio (tras `decide`) con `rate_limit_cut(rol)` -> `LLMCallFailure`
    inmediata, `infraestructura`, `es_limite_tasa=True`, mensaje "rol <rol> en
    corte por limite de tasa persistente (sin espera)". Sin espera, sin
    cooldown, sin consumir `attempt_rl`. Se consulta en cada 429, no solo al
    empezar la llamada: un hilo que ya esperaba falla sin esperar en su 429
    siguiente.
  - Presupuesto agotado (`attempt_rl == rate_limit_retries`) ->
    `activate_rate_limit_cut(rol)`; si devolvio True, linea `INFO`
    `Limite de tasa: rol=<rol> modelo=<modelo> corte activado tras <m>
    intentos`; despues lanza como en D3.
  - Las lineas de corte no contienen ` espera `: el parser de SC-006 cuenta
    `waits` solo con las lineas de espera y `cortes` con las de activacion.
- `probe_completion` (D9) no llama a ninguno de los tres metodos.
- 429 no transitorios (FR-003) y demas `infraestructura`: sin cambio.

`dspy_gepa_poc/scripts/baseline_only.py` (decision explicita): recibe el handler
de D6 pero sigue saliendo con 1 ante cualquier aborto. FR-010 nombra solo los dos
entry points y ningun runner invoca `baseline_only.py`.

## Tests existentes que la spec obliga a ajustar (con su FR)

Lista de partida; la subfase indicada los ajusta bajo la excepcion de "Reglas" y
los nombra en su nota.

- `tests/test_litellm_failure_mapping.py::test_retry_counts_checked_lm` (1c): 429
  -> `1 + DEFAULT_RATE_LIMIT_RETRIES`; `openai_retry_413_too_large` -> 1 llamada
  (FR-003 (iii), FR-004).
- `tests/test_reflection_guard.py` (~L125) y `tests/test_single_call_point.py`
  (~L68): intentos esperados por clase, 429 aparte (FR-004) (1c).
- `tests/test_sc005_logs_vs_run_json.py`: `_rate_limit()` sin cabecera pasa por
  el presupuesto del 429 (FR-004); se extiende con SC-006 (FR-005, FR-009) (2b).
- `tests/test_lib_contracts.py`: superficie `litellm.response_headers` en
  `SURFACES` y su `Mutation` (cabeceras movidas fuera de
  `litellm_response_headers` -> contrato rojo) (FR-002) (1b).
- `tests/test_role_probe.py::test_infraestructura_is_not_retried`: usa 429; pasa
  a 5xx/timeout y se agrega el 429 con espera (FR-011) (2a).
- `tests/test_sc006_no_failure_regression.py`: asercion de
  `rate_limit_waits` en cero (FR-009) (2b).
- Probables, a confirmar al correr la suite en 1c: `tests/test_failure_call.py`,
  `tests/test_attribution.py`, `tests/test_gepa_adapters_failures.py`
  (`configure(infra_retries=0)` con `RateLimitError`),
  `tests/test_universal_optimizer_failures.py`,
  `tests/test_dspy_call_failures.py`, `tests/test_dspy_orchestrator_failures.py`,
  `tests/test_shared_llm.py::test_error_429` (mensaje de la sonda, 2a),
  `tests/test_shared_validation.py` (lista de claves validas de `failures`, 1b).
  Regla: un 429 que hoy espera `1 + infra_retries` pasa a `1 +
  rate_limit_retries` o se fija `rate_limit_retries` en el test; nunca se cambia
  una asercion de otra clase.

## Riesgos del plan

- 1c cambia el bucle del punto de llamada de todas las corridas. Mitigacion:
  SC-005 (0 diferencias en los payloads que no son 429) se escribe en 1a y queda
  verde con el codigo de hoy (no `xfail`), antes de tocar el bucle.
- Hilos (1d): un reloj simulado compartido suma las esperas de varios hilos.
  SC-007 solo exige la cota inferior ("ninguna llamada antes de T"), que el reloj
  aditivo respeta; el test registra el instante simulado de cada llamada.
- Un handler mal ubicado silencia los WARNING del contador (H3). Mitigacion: D6
  y un test que, con el handler instalado, verifica que una falla sigue saliendo
  a WARNING por `lastResort`/`caplog` sin formato `[INFO]`.
- Runners: la tecnica no cubre `winpty` (D13) y cada invocacion es lenta en
  Windows. Mitigacion: maximo 6 invocaciones; verificacion manual en la fase 6.
- H1: en Azure, `insufficient_quota` se trata como 429 transitorio sin
  cabecera. Sin D18 costaba un presupuesto por caso (unos 195 s) hasta llegar a
  `min_attempts` (20 en `task`): de 55 a 65 min en secuencial. Con D18 (FR-013)
  cuesta un solo presupuesto por rol; los casos siguientes fallan sin esperar y
  el aborto sale con 75 y frena el batch.
- D18 levanta el corte con cualquier respuesta del rol: con una cuota que
  oscila, cada reapertura rearma un presupuesto completo. Es lo pedido ("esperar
  cuando la cuota reabre"); el costo por corrida queda acotado por los umbrales
  de SPEC-104.

## Detalle por subfase

Toda sesion de subfase lee antes la spec y, de este plan, lo indicado en
"Consumo de tokens". "Archivos" es la lista cerrada del control de salida.

### 1a Tests RED del nucleo — Sonnet 5.5

- `tests/test_rate_limit_wait.py` (nuevo). Imports de simbolos nuevos dentro de
  cada test. Marcas `xfail(strict=True)` por subfase que los cierra:
  - "SPEC-107 1b": `retry_after_seconds` (prioridad ms antes que s, fecha HTTP,
    invalidos ignorados, `x-ratelimit-reset-*` ignorado); `response_headers`
    (orden defensivo); `decide` (los tres no transitorios con `es_limite_tasa`
    de FR-003, igual al tope = transitorio); `backoff_seconds` en [0.8, 1.2] x
    `min(5 * 2**n, 60)`; `header_wait` >= cabecera y <= cabecera + 0.25. SC-002
    con `RATE_LIMIT_CASES` e `intercept_httpx` (cabecera leida por proveedor).
  - "SPEC-107 1c": SC-001 (`Retry-After: 2` y respuesta sana: espera >= 2 s y <
    tope, 0 fallas); SC-003 (sin cabecera persistente: `1 + rate_limit_retries`
    llamadas, esperas en rango, una falla `infraestructura` por caso); SC-004
    (tres no transitorios: 1 llamada, 0 esperas, mensaje con la espera pedida en
    (i)); FR-006 (aborto fijado por otro hilo durante la espera -> `RunAborted`
    en el tramo siguiente, tramo parcial contado); FR-008 (mismo `model` en
    todas las llamadas); una linea `INFO` por espera en `caplog` con rol,
    modelo, intento n/m y segundos. SC-012 y FR-013: con `num_threads=1` y 429
    sin cabecera permanente en `task`, espera total <= 234 s simulados, las
    llamadas tras el corte hacen 1 llamada HTTP y 0 esperas, una linea de
    activacion, `cortes == 1` y aborto con `is_rate_limit_abort()`; una
    respuesta sana tras el corte lo levanta (linea `INFO`) y el 429 siguiente
    vuelve a `1 + rate_limit_retries` llamadas; un 5xx con el rol en corte sigue
    con `infra_retries`; un hilo que esperaba al activarse el corte falla sin
    esperar en su 429 siguiente.
  - "SPEC-107 1d": SC-007 (dos hilos, `Retry-After: 10` en uno: ninguna llamada
    del rol antes de 10 s simulados; otro rol no espera; `reset()` limpia).
  - Sin marca (verde hoy): SC-005, 1 + `infra_retries` llamadas con 1, 2 y 4 s
    para todos los payloads de `RETRY_CASES` que no son 429.
- `tests/test_failures.py` (existente, se agrega): `es_limite_tasa` default;
  `configure` de las claves nuevas (SC-011); `snapshot()["rate_limit_waits"]`
  con los tres roles en cero; `start_rate_limit_wait`/`add_rate_limit_seconds`;
  `is_rate_limit_abort` con los cuatro casos de SC-008; `EXIT_RATE_LIMIT == 75`;
  estado del corte (D18: activar dos veces suma un solo `corte`, `clear`
  devuelve si estaba activo, `cortes` en `snapshot`); `reset` limpia conteo,
  esperas, cooldown y corte. Marca "SPEC-107 1b".
- Validador: test en el archivo de tests del validador de `failures` (ubicarlo
  con Grep `FAILURES_KEYS`) para SC-011 (negativo, no numerico, booleano, `nan`
  en `rate_limit_max_wait`). Marca "SPEC-107 1b".
- `tests/litellm_failure_payloads.py`: `RATE_LIMIT_CASES` (D16).
- `FakeClock` provisorio dentro de `tests/test_rate_limit_wait.py` (pasa a
  `tests/conftest.py` en 1b).
- Archivos: `tests/test_rate_limit_wait.py`, `tests/test_failures.py`, el test
  del validador, `tests/litellm_failure_payloads.py`.

### 1b Modulo, contador y validador (GREEN "1b") — Sonnet 5.5

- Implementa D1, D2 (campo y conteo en `record`), D5 (solo estado), D7, D8
  (constante, metodo; `exit_code_for` va en 2b), D11 y D15 (mover `FakeClock` a
  `tests/conftest.py` con el fixture autouse). Exporta `EXIT_RATE_LIMIT` en
  `shared/llm/__init__.py` (`enable_rate_limit_console` se implementa y exporta
  en 1c).
- `tests/test_lib_contracts.py`: superficie y mutacion de
  `litellm_response_headers` (FR-002).
- Quita las marcas "SPEC-107 1b".
- Archivos: `shared/llm/rate_limit.py` (nuevo), `shared/llm/failures.py`,
  `shared/llm/__init__.py`, `shared/validation/base_validator.py`,
  `tests/conftest.py`, `tests/test_rate_limit_wait.py`, `tests/test_failures.py`,
  el test del validador, `tests/test_lib_contracts.py`,
  `tests/test_shared_validation.py` (si fija la lista de claves validas).

### 1c Punto de llamada (GREEN "1c") — Opus 5.5

- Implementa D3, D4, D6 (emision y `enable_rate_limit_console`, sin llamarla
  desde entry points) y D18 (bucle). Quita las marcas "SPEC-107 1c". Corre la suite completa
  y ajusta los conteos de 429 de los tests de la lista "Tests existentes"
  (FR-004, FR-003 (iii)), listandolos.
- Test extra (riesgo H3): con `enable_rate_limit_console()` instalado, una falla
  del contador sigue a WARNING sin prefijo `[INFO]`.
- Archivos: `shared/llm/call.py`, `shared/llm/rate_limit.py`,
  `shared/llm/__init__.py`, `tests/test_rate_limit_wait.py` y los tests
  existentes que caen en la excepcion de "Reglas".
- Puntos de entrada: `call_with_infra_retry` (~L58), `checked_response` (~L176).
- Parada obligatoria al terminar: el usuario revisa el bucle del punto de
  llamada.

### 1d Cooldown y atribucion (GREEN "1d") — Opus 5.5

- Implementa D5 (espera previa a cada llamada) y la parte de D2 de
  `BaselineOutcome`/`attribute_failure`. Quita las marcas "SPEC-107 1d".
- Tests nuevos: atribucion con baseline rate-limited conserva `es_limite_tasa`
  en la falla sustituida (`tests/test_attribution.py`); cooldown con
  `ThreadPoolExecutor` y `FakeClock`.
- Archivos: `shared/llm/call.py`, `shared/llm/failures.py`,
  `shared/llm/attribution.py`, `tests/test_rate_limit_wait.py`,
  `tests/test_attribution.py`.

### 2a Sonda — Opus 5.5

- Tests primero en `tests/test_role_probe.py`: 429 con `Retry-After: 2` y luego
  200 -> conexion valida tras una espera >= 2 s y una linea `INFO`; 429
  persistente -> `LLMConnectionError` con `rate_limited` y `1 +
  rate_limit_retries` llamadas; `Retry-After: 3600` e `insufficient_quota` -> 1
  llamada, 0 esperas, `rate_limited`; 401/404/5xx/timeout -> 1 llamada (el test
  vigente de 429 sin reintento pasa a 5xx/timeout, FR-011); la sonda sigue sin
  uso y sin aborto.
- Implementa D9.
- Archivos: `shared/llm/call.py`, `shared/llm/config.py`,
  `shared/llm/errors.py`, `tests/test_role_probe.py`, `tests/test_shared_llm.py`
  (tests de mensaje de la sonda ante 429).
- Parada obligatoria al terminar: el usuario revisa la sonda.

### 2b Entry points — Sonnet 5.5

- Implementa `exit_code_for` (D8), D10, la llamada a
  `enable_rate_limit_console()` (D6), las claves nuevas en
  `configure_failure_tracker()` (D11) y D17.
- Tests: SC-008 en ambos entry points (`main()` con `RunAborted` simulado por el
  contador: 2 de 3 -> `SystemExit(75)`, 1 de 3 -> 1; reflexion por `total` 3 de
  4 -> 75); SC-009 (`LLMConnectionError` con `rate_limited` -> 75, sin -> 1); en
  GEPA, `configure_failure_tracker` antes de la primera sonda (orden de
  llamadas) y una sola vez; SC-006 extendiendo
  `tests/test_sc005_logs_vs_run_json.py`: corrida con 429 con cabecera, la linea
  `INFO` sale en `capsys` (consola, no solo `caplog`) con el modelo, `waits` de
  `run.json` = numero de lineas, `counts` y claves de primer nivel sin cambio;
  `tests/test_sc006_no_failure_regression.py` con `rate_limit_waits` en cero.
- Archivos: `shared/llm/errors.py`, `shared/llm/__init__.py`,
  `shared/display/formatting.py` (D17), `dspy_gepa_poc/reflexio_declarativa.py`,
  `dspy_gepa_poc/scripts/baseline_only.py`,
  `gepa_standalone/universal_optimizer.py`, `tests/test_sc005_logs_vs_run_json.py`,
  `tests/test_sc006_no_failure_regression.py`, un test nuevo
  `tests/test_rate_limit_exit.py`, y los tests existentes de los entry points
  que fijen el orden viejo o el `sys.exit(1)` ante `RunAborted`.
- Puntos de entrada: `main` (DSPy ~L919, GEPA ~L737), `run` de GEPA (~L206),
  `configure_failure_tracker` (DSPy ~L151, GEPA ~L119).

### 3a Runners — Sonnet 5.5

- Tests primero (`tests/test_batch_runners.py`, D13): fallan hoy por la razon
  correcta (no hay pausas, 75 no detiene con `CONTINUE_ON_FAIL=1`).
- Implementa D12 en ambos runners via `shared/utils/batch_control.sh`.
- Archivos: `shared/utils/batch_control.sh` (nuevo),
  `dspy_gepa_poc/run_dspy_total.sh`, `gepa_standalone/run_demos_gepa.sh`,
  `tests/test_batch_runners.py` (nuevo).

### 3b `run_seeds` — Sonnet 5.5

- Tests primero en `tests/test_seed_protocol.py` (sin procesos: `runner`/`popen`
  falsos con codigos de salida; `sleep` falso): `--jobs 1` corta ante 75 con N
  sin ejecutar y el texto "limite del proveedor"; `BATCH_COOLDOWN=N` -> K - 1
  pausas y 0 tras el corte; invalido -> error antes de la primera seed;
  `--jobs 2` no lanza mas tras un 75; `main` devuelve 75 y salta los `--config`
  restantes (si C2 se aprueba).
- Implementa D14.
- Archivos: `shared/utils/seed_protocol.py`, `tests/test_seed_protocol.py`.

### 4a Documentacion — Sonnet 5.5

- `docs/GEPA_MANEJO_ERRORES.md` (presupuesto propio del 429, matriz de
  proporcionalidad enlazada a la spec, aviso `INFO` como excepcion al "todo
  intermedio a DEBUG", cooldown, codigo 75); `docs/LLM_CONFIG.md` (la sonda espera
  ante 429, H1 si se aprueba); `docs/YAML_CONFIG_REFERENCE.md`
  (`failures.rate_limit_retries`, `failures.rate_limit_max_wait`);
  `docs/METADATA_REPRODUCIBILIDAD.md` (`failures.rate_limit_waits`);
  `docs/DEVELOPMENT.md` (codigo 75, `BATCH_COOLDOWN`, corte de los runners);
  `docs/PROTOCOLO_N_SEEDS.md` (corte de `run_seeds`, `BATCH_COOLDOWN` con
  `--jobs 1`). Enlazar a la spec, no copiar la matriz (SSOT).
- Archivos: esos seis y las filas del Coverage mapping de la spec.

### 4b Enmiendas — Opus 5.5

- SPEC-104: FR-007 (el aviso `INFO` de espera es la unica excepcion a "intentos
  intermedios a DEBUG"), FR-011 (el 429 tiene presupuesto y espera propios,
  enlace a SPEC-107 FR-002/FR-004), FR-015 (excepcion textual "request too
  large", justificada por el enrutado de LiteLLM). SPEC-106: FR-005 (la sonda
  espera ante 429). SPEC-107: las enmiendas H1 a H5 que el usuario apruebe.
  Cada una trazada en `historial/sdd.md` (entrada fechada).
- Archivos: `specs/SPEC-104-fallas-tecnicas-justas.md`,
  `specs/SPEC-106-roles-intercambiables.md`,
  `specs/SPEC-107-limite-de-tasa-proveedor.md` (solo texto de FR/Contexto
  aprobado, sigue `draft`), `historial/sdd.md`. Las enmiendas de SPEC-107
  incluyen H1 a H6 y las decisiones C2, C4, C5 y C6 (ver "Hallazgos").

### 5 Revision integral — Opus 5.5

- Diff `e1a97e8..HEAD` contra el texto de cada FR y SC (no contra los
  resumenes de las sesiones). Verifica sin red SC-001 a SC-011 y las reglas de
  arquitectura; corre una vez los runners con python simulado.
- Salida: seccion "Hallazgos de la revision" en este plan, cada uno con
  severidad, archivo y FR. No corrige: cada hallazgo aprobado va a `5-fix-N`
  (Sonnet 5.5, test RED previo; Opus si toca el punto de llamada).
- Archivos: solo este plan.

### 6 Verificacion — sesion interactiva, opcional

- Forzar un 429 real exige agotar el TPM del deployment (costo y espera): no se
  hace. El 429 queda verificado simulado (SC-001 a SC-011 por `httpx`
  interceptado, runners con python simulado).
- Corrida corta real por subproyecto (presupuesto minimo, como la fase 7 de
  SPEC-106): salida 0, `failures.rate_limit_waits` en cero, sin lineas `INFO` de
  espera, `counts` sin cambio. Si durante la corrida aparece un 429 real, se
  registra la linea `INFO` y la cabecera leida. Un runner real con 1 prueba bajo
  winpty para ver que el 0 se conserva.
- Registrar el resultado en este plan.

### Cierre — sesion interactiva, Opus 5.5

- `[SDD-Check]` en `historial/sdd.md`; Coverage mapping de "previsto" a vigente
  en todas las filas; spec y `specs/SPECS_REGISTRY.md` a `active`; deuda nueva
  (p. ej. H1 si queda como limite, winpty sin test, cooldown por rol y no por
  deployment, D5); plan marcado cerrado.

## Lanzamiento por CLI (modo no interactivo)

Cada subfase de las fases 1 a 5 corre como una sesion `-p` aparte, desde Git
Bash en la raiz del repo, con el modelo de la tabla. La fase 6 y el Cierre van
en sesion interactiva.

- Subfases Opus 5.5: `claude -p ... --model claude-opus-5-5`.
- Subfases Sonnet 5.5: `claude-e -p ... --model claude-sonnet-5-5` (perfil de
  empresa; ver la referencia de los wrappers en la memoria del proyecto).

```bash
SUB=1a                                   # subfase a ejecutar
CLI=claude-e; MODEL=claude-sonnet-5-5    # Opus: CLI=claude; MODEL=claude-opus-5-5
export PYTHONUTF8=1                      # salida redirigida en Windows (cp1252)
mkdir -p "$HOME/spec107_logs"            # logs fuera del repo
"$CLI" -p "Implementar SPEC-107 subfase $SUB segun docs/plans/PLAN_SPEC-107_limite_de_tasa_proveedor.md. \
Leer solo lo indicado en 'Consumo de tokens' del plan. \
Los tests MUST verificar el comportamiento de la spec, sin red y sin dormir (reloj simulado, D15). \
Al cerrar: ci_local.sh verde, commit de la subfase y, en commit aparte de docs, estado en la tabla del plan y Coverage mapping de la spec. \
No pasar la spec a active. \
Sesion no interactiva: si algo exige decision del usuario o un archivo fuera de la lista, no improvisar; \
anotarlo en 'Bloqueos' del plan, no commitear y terminar." \
  --model "$MODEL" \
  --permission-mode acceptEdits \
  --allowedTools "Bash(./shared/utils/ci_local.sh:*) Bash(.venv/Scripts/python.exe -m pytest:*) Bash(.venv/Scripts/python.exe -m ruff:*) Bash(git status) Bash(git diff:*) Bash(git log:*) Bash(git add:*) Bash(git commit:*)" \
  | tee "$HOME/spec107_logs/$SUB.log"
```

Reglas:

- Una subfase por invocacion, en el orden de Dependencias.
- En este equipo el interprete es `.venv/Scripts/python.exe` (Windows); en
  Unix, `.venv/bin/python`, y se ajusta `--allowedTools`.
- 3a necesita ademas ejecutar `bash` desde pytest (lo hace el propio test, no la
  sesion): no requiere permisos extra.
- Un relanzamiento tras bloqueo continua sobre el arbol sin commitear; la
  resolucion se registra antes en este plan (commit solo del plan).

## Seguimiento

Una sesion interactiva de Opus 5.5 supervisa las fases 1 a 5. No implementa ni
guarda estado propio: el estado es la columna Estado de este plan.

Arranque: "Supervisar SPEC-107 segun la seccion Seguimiento de
docs/plans/PLAN_SPEC-107_limite_de_tasa_proveedor.md".

Ciclo por subfase:

1. Tomar la primera subfase `pendiente` cuyas dependencias esten `hecho`.
2. Lanzarla con el comando de "Lanzamiento por CLI" en segundo plano y esperar
   el aviso de fin (sin polling).
3. Aplicar el control de salida. Si pasa, volver a 1. Si falla, detenerse e
   informar al usuario: no relanzar ni corregir por cuenta propia.

Control de salida (todos deben cumplirse):

- Commit nuevo (`git log -1`) y arbol limpio (`git status`).
- `./shared/utils/ci_local.sh` verde.
- La subfase figura `hecho` con el hash y no hay bloqueo nuevo en "Bloqueos".
- `git diff --stat` del commit toca solo los "Archivos" de la subfase (mas los
  tests existentes de la excepcion, listados en la nota).
- El diff cumple los FR de la fila, contrastado con el texto de la spec. Diff
  completo en 1c, 1d y 2a, y cuando otro punto falla.
- Ningun test nuevo duerme de verdad (la duracion de `ci_local.sh` no crece mas
  que la de los tests de runners de 3a).
- La spec sigue en `draft`.

Paradas obligatorias (la sesion se detiene y espera al usuario):

- Antes de 1a: el usuario aprueba el plan y responde "Decisiones a confirmar".
- Despues de 1c (punto de llamada) y despues de 2a (sonda).
- Antes de 4b: enmiendas a specs `active`.
- Despues de 5: el usuario aprueba los hallazgos que se corrigen.

Contexto del supervisor: de cada log leer solo el final (`tail -n 40`); abrir el
log completo o el diff solo cuando un control falla.

## Decisiones a confirmar

Estado: C1 a C8 CONFIRMADAS por el usuario el 2026-11-27 con el valor
"Recomendado: si" de cada una (C6 consultada aparte: salida 75 de los runners,
codigo definido en `shared/llm/failures.py`, traducido por
`exit_code_for` en `shared/llm/errors.py` y propagado por
`shared/utils/batch_control.sh`). Las enmiendas H1 a H5 pasan a la subfase 4b.

- C1 (H1). Azure `insufficient_quota`: aceptar el limite (transitorio sin
  cabecera en Azure, test de contrato que fija `body is None`, enmienda de
  FR-003 (ii)). Recomendado: si.
- C2 (D14). `seed_protocol` ante 75: ademas de cortar las seeds del caso, saltar
  los `--config` restantes y devolver 75. Recomendado: si (mismo proveedor y
  cuota). La spec solo dice "las seeds restantes".
- C3 (H5). `rate_limit_max_wait` no acota el backoff sin cabecera. Recomendado:
  si (letra de la spec); alternativa: `min(backoff, max_wait)`.
- C4 (D5). Las esperas por cooldown de otros hilos emiten su linea `INFO` y
  cuentan en `waits`/`seconds` (lectura de "acumulados por hilo" y de SC-006).
  Recomendado: si.
- C5 (D10). Las esperas de la sonda cuentan en `rate_limit_waits` de la corrida.
  Recomendado: si.
- C6 (D12). Los runners salen con 75 (no 1) cuando se detienen por limite del
  proveedor. Recomendado: si ("propagar el codigo 75").
- C7 (D1). Adoptar el jitter positivo [0, 0.25] s sobre la espera de cabecera
  (MAY de FR-002). Recomendado: si.
- C8. Aprobar las enmiendas de redaccion H2, H3 y H4 para 4b.
- C9 (D18, revision del plan, 2026-11-27). Ante un 429 que no se recupera, corte
  por rol que se levanta solo (opcion A) en lugar de abortar al agotar el
  presupuesto, un tope de espera acumulada o aceptar el costo. CONFIRMADA por el
  usuario; llevada a la spec como FR-013 y SC-012 (iteracion 3).

## Bloqueos

(ninguno)

## Proxima sesion

Plan creado y aprobado el 2026-11-27 (C1 a C8 confirmadas). Siguiente:
arranque de 1a (Sonnet 5.5, `claude-e -p`) con el comando de "Lanzamiento por
CLI" o por la sesion de Seguimiento (Opus 5.5, `claude`).
