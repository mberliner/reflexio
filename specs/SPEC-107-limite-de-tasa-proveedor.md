# SPEC-107-limite-de-tasa-proveedor — Espera ante limite de tasa del proveedor (429)

Estado: draft
Iteracion: 3 (rev. 2026-11-27)
Depende de: [[SPEC-104-fallas-tecnicas-justas]] (clasificador de la capa 1, FR-011 reintentos, contador y aborto FR-006), [[SPEC-105-punto-llamada-desacoplado]] (punto de llamada unico en `shared/llm/call.py`, contratos de superficies de libreria FR-007), [[SPEC-106-roles-intercambiables]] (sonda de conexion FR-005)
Relacionada con: [[SPEC-108-costo-real-por-resolucion]] (el tiempo de espera no entra en `usage`), docs/GEPA_MANEJO_ERRORES.md, docs/YAML_CONFIG_REFERENCE.md, docs/METADATA_REPRODUCIBILIDAD.md, docs/PROTOCOLO_N_SEEDS.md

Origen: 2026-11-27, dos corridas de un batch abortaron con `litellm.RateLimitError:
AzureException ... gpt-4.1-mini ... in eastus have exceeded token rate limit`
(HTTP 429). SPEC-104 ya clasifica el 429 como `infraestructura` y lo reintenta,
pero con la espera generica de FR-011 (1, 2 y 4 s), insuficiente para un limite
por minuto. La iteracion 2 incorpora una revision contrastada con el entorno
instalado (litellm 1.108.5, openai 3.57.0, httpx 0.28.1, dspy 3.5.0, gepa 0.1.4)
que cierra las cuatro clarificaciones de la iteracion 1 y agrega cinco huecos.
La iteracion 3 (revision del plan, 2026-11-27) agrega FR-013 y SC-012: la
matriz era proporcional por llamada pero no por corrida. Con un 429 que no se
recupera, cada caso gastaba un presupuesto completo (unos 195 s) y el aborto
llegaba recien tras `min_attempts` casos (20 en `task`: de 55 a 65 min en
secuencial).

## User Story (prioridad)

Como persona que lanza corridas largas o batch contra un deployment con cuota de
tokens por minuto, quiero que el tiempo de espera ante un 429 sea proporcional a
cuanto se puede recuperar el error (esperar lo que el proveedor pide cuando la
cuota reabre, no esperar nada cuando no va a reabrir), de forma visible y sin
cambiar el modelo medido, y que si la cuota no se recupera la corrida y el batch
se detengan con una causa clara, para no perder corridas ni tiempo y no mezclar
fallas de cuota con fallas del prompt.
Prioridad: P1

## Contexto (estado al 2026-11-27)

- Clasificacion: `RateLimitError` y `status_code` 429 son `infraestructura`
  (SPEC-104, tabla de reglas).
- Reintento: un unico presupuesto para toda la `infraestructura`
  (`failures.infra_retries`, default 3), con espera `1.0 * 2**n` s fija en codigo
  (`shared/llm/call.py::call_with_infra_retry`). Total acumulado: 7 s.
- Los intentos intermedios van a `DEBUG` (SPEC-104 FR-007) y ningun entry point
  configura el logger raiz en `INFO` (la consola usa `shared.display.log_info`,
  que imprime): durante una espera la corrida no emite nada.
- Persistido el 429: el caso queda NE y, si se supera el umbral, se aborta con
  `RunAborted`. Los umbrales por defecto de `infraestructura` existen para `task`
  y `judge` (0.10); `reflection` no tiene umbral de `infraestructura`: aborta por
  `presupuesto` (0.25) o `total` (0.50), minimo 4 intentos
  (`shared/llm/failures.py::DEFAULT_THRESHOLDS`).
- Los entry points salen con `sys.exit(1)` ante cualquier aborto (130 ante Ctrl+C).
- Cabeceras (verificado interceptando `httpx` en el entorno instalado): en
  litellm 1.108.5 `exc.response.headers` llega vacio y `exc.headers` es `None` en
  Azure, OpenAI y Anthropic. Las cabeceras estan en `exc.litellm_response_headers`
  (`httpx.Headers`): Azure `retry-after` y `x-ms-retry-after-ms`, OpenAI
  `retry-after` y `retry-after-ms`, Anthropic `retry-after`.
- Origen del 429 por tamano: LiteLLM convierte en `RateLimitError` todo error cuyo
  texto contenga "Request too large" (`exception_mapping_utils.py`). Cubre un 429
  real de OpenAI cuando un unico request supera el limite de TPM de la
  organizacion: esperar no lo arregla nunca. Un 413 estandar sin esa frase llega
  como `APIError(413)` y es `configuracion`.
- `insufficient_quota` (saldo agotado en OpenAI o Azure) llega como
  `RateLimitError(429)` sin `Retry-After` y con `exc.body["type"]` y
  `exc.body["code"]` iguales a `insufficient_quota`.
- La sonda de conexion (`probe_completion`, SPEC-106 FR-005) hace una llamada sin
  reintento; un 429 en ella termina la corrida con `sys.exit(1)`. En
  `gepa_standalone/universal_optimizer.py` la sonda corre antes de
  `configure_failure_tracker()`; en `dspy_gepa_poc/reflexio_declarativa.py` despues.
- No existe fallback de modelo ni pausa entre pruebas de los runners batch;
  `shared/utils/seed_protocol.py::run_seeds` trata cualquier `returncode != 0` igual
  y sigue lanzando las seeds restantes.

## Matriz de proporcionalidad (resumen normativo de FR-001 a FR-004)

El tiempo esperado MUST ser proporcional a la recuperabilidad del error. Sin
clases nuevas: es la taxonomia de SPEC-104.

| Tipo de error | Clase SPEC-104 | Reintentos | Espera | Tiempo perdido si es permanente |
|---|---|---|---|---|
| 401/403/404/422, parametros invalidos, 413 estandar (`APIError(413)` en Azure y OpenAI, `BadRequestError` en Anthropic) | `configuracion` | 0 (1 llamada) | 0 s | 0 s (aborta la corrida) |
| Contexto excedido, filtro de entrada, `request_too_large` (Anthropic 413) | `entrada` | 0 (1 llamada; +1 baseline si es tarea) | 0 s | 0 s |
| 429 no transitorio: (i) `Retry-After` > `rate_limit_max_wait`, (ii) `insufficient_quota` en `exc.body`, (iii) "request too large" (sin distinguir mayusculas) en el mensaje | `infraestructura` | 0 (1 llamada) | 0 s | 0 s |
| 429 transitorio CON cabecera | `infraestructura` | `rate_limit_retries` (default 6) | Lo que pide la cabecera, sin jitter hacia abajo | Solo lo pedido por el proveedor |
| 429 transitorio SIN cabecera | `infraestructura` | `rate_limit_retries` (default 6) | `min(5 * 2**n, 60)` s con jitter [0.8, 1.2] | 195 s como maximo por caso (156 a 234 s con jitter) |
| Cualquier 429 transitorio con el rol en corte por limite persistente (FR-013) | `infraestructura` | 0 (1 llamada) | 0 s | Un solo presupuesto completo por rol hasta que una llamada responda |
| Resto de `infraestructura` (timeout, red, 408, 409, 500, 502, 503, 504, 529) | `infraestructura` | `infra_retries` (default 3) | 1, 2 y 4 s (SPEC-104 FR-011) | 7 s |

## Requisitos funcionales

- FR-001 `shared/llm` MUST distinguir el limite de tasa (`RateLimitError` o
  `status_code` 429 tras el clasificador de la capa 1) del resto de las fallas de
  `infraestructura` y MUST darle un presupuesto de reintentos propio (FR-004). La
  clase sigue siendo `infraestructura`: no se agrega clase ni clave de conteo.
  `LLMFailure` MUST llevar `es_limite_tasa: bool` (default `False`), que el
  contador usa para FR-010.
- FR-002 Antes de cada reintento de un 429 transitorio el sistema MUST esperar:
  - Con cabecera: al menos el valor que indique el proveedor, sin jitter hacia abajo
    (esperar menos que lo pedido quema un intento y reintenta antes de que reabra la
    ventana). MAY sumarse un jitter positivo uniforme de [0, 0.25] s para dispersar
    hilos.
  - Sin cabecera: `min(5 * 2**n, 60)` s, con jitter multiplicativo en [0.8, 1.2].
  - Las cabeceras MUST leerse de la excepcion raiz (`root_exception`) en este orden
    defensivo: `litellm_response_headers`, `response.headers`, `headers`.
  - Prioridad de cabeceras: 1) `retry-after-ms` (milisegundos / 1000), 2)
    `x-ms-retry-after-ms` (milisegundos / 1000), 3) `retry-after` (segundos, o fecha
    HTTP convertida con `email.utils.parsedate_to_datetime` menos el instante
    actual, acotada a >= 0).
  - MUST NOT usarse `x-ratelimit-reset-requests` ni `x-ratelimit-reset-tokens`: en
    limites mixtos reportan horas aunque el bloqueo real sea de segundos (el propio
    SDK de OpenAI los ignora).
  - `litellm_response_headers` es simbolo publico de LiteLLM: MUST agregarse como
    superficie a `SURFACES` y `MUTATIONS` de `tests/test_lib_contracts.py`
    (SPEC-105 FR-007) para que un upgrade que lo cambie ponga el CI en rojo.
- FR-003 Ante un 429 no transitorio el sistema MUST NOT esperar: 1 llamada HTTP,
  falla inmediata como `infraestructura`, mensaje con la causa. Es no transitorio
  cuando se cumple alguna de:
  - (i) `Retry-After` supera `failures.rate_limit_max_wait` (default 120 s): el
    mensaje MUST citar la espera pedida; `es_limite_tasa=True`.
  - (ii) `exc.body` trae `code` o `type` igual a `insufficient_quota`:
    `es_limite_tasa=True` (si aborta la corrida, sale con FR-010 y frena el batch).
  - (iii) el mensaje contiene "request too large" (sin distinguir mayusculas):
    `es_limite_tasa=False`, porque es un exceso de tamano del caso frente al techo
    del modelo, no una cuota agotada del batch.
  El orden es el de SPEC-104 FR-015 (campos estructurados primero). La frase de (iii)
  es la unica excepcion textual y esta justificada porque es el criterio con el que
  LiteLLM mismo enruta ese error a `RateLimitError`; MUST documentarse como enmienda
  de SPEC-104 FR-015.
- FR-004 El presupuesto de un 429 transitorio MUST ser `failures.rate_limit_retries`
  (entero >= 0, default 6 = 7 intentos) y su tope de espera
  `failures.rate_limit_max_wait` (numero >= 0 en segundos, default 120). Las demas
  fallas de `infraestructura` MUST conservar `failures.infra_retries` y su espera de
  1, 2 y 4 s sin cambios (SPEC-104 FR-011). Las claves MUST agregarse a
  `FAILURES_KEYS` y validarse en `BaseConfigValidator` antes de gastar tokens, con
  las reglas de `infra_retries` (rechazar negativos, no numericos y booleanos).
- FR-005 Cada espera por limite de tasa MUST ser visible en la consola de una
  corrida real: una linea `INFO` con rol, modelo, intento n/m y segundos, emitida
  por `logger.info` en `shared.llm` y mostrada con un handler `INFO` acotado a ese
  logger (MUST NOT elevar el logger raiz a `INFO`: despertaria los logs internos de
  litellm, httpx y dspy). `call_with_infra_retry` MUST recibir el modelo
  (`checked_response` lo pasa desde `kwargs`). Enmienda SPEC-104 FR-007 solo para
  este aviso: no es una falla y MUST NOT sumar a `failures.counts` ni a `usage`.
- FR-006 La espera MUST ser interrumpible: se duerme en tramos de a lo sumo 5 s y
  entre tramos MUST verificarse el estado de aborto del contador (`check_abort`);
  un `RunAborted` o Ctrl+C no queda bloqueado en una espera larga.
- FR-007 Con `optimization.num_threads > 1` el sistema MUST compartir por rol un
  `cooldown_until = monotonic() + espera` fijado al recibir un 429 con espera, y
  los demas hilos del rol MUST esperar hasta ese instante antes de llamar. No es un
  control proactivo de tasa: solo propaga la espera reactiva ya recibida, para no
  disparar llamadas condenadas al 429 durante la ventana. El estado MUST ser
  thread-safe y reiniciarse junto con el contador (`FailureTracker.reset`).
- FR-008 Ante limite de tasa el sistema MUST NOT sustituir el modelo ni el
  deployment del rol por otro. El modelo de cada rol es parte de la identidad del
  experimento (terna Tarea/Profesor/Juez de SPEC-100 y SPEC-106). Un fallback a
  otro deployment del mismo modelo queda fuera de alcance.
- FR-009 `run.json` MUST registrar `failures.rate_limit_waits`, emitido por
  `FailureTracker.snapshot()`: por cada rol de `ROLES`
  `{"waits": int, "seconds": float, "cortes": int}`. `waits` cuenta las esperas
  iniciadas (una por linea `INFO` de espera de FR-005), `cortes` las activaciones
  del corte de FR-013 y `seconds` los segundos efectivamente dormidos, incluidos
  los tramos parciales si FR-006 interrumpe y acumulados por hilo si
  `num_threads > 1`. El campo vive dentro de `failures` (no es una clave nueva de
  primer nivel), no toca `failures.counts` ni `usage`, y MUST describirse en
  `docs/METADATA_REPRODUCIBILIDAD.md`.
- FR-010 Una corrida abortada por limite de tasa MUST salir con el codigo 75
  (`EX_TEMPFAIL`), definido como constante unica `EXIT_RATE_LIMIT = 75` en
  `shared/llm/failures.py` y reexportada en `shared/llm/__init__.py`; no colisiona
  con 0, 1, 2 (CLI) ni 130 (Ctrl+C) y se conserva bajo Git Bash y winpty.
  `FailureTracker.is_rate_limit_abort()` MUST decidirlo asi, para el rol R y la
  clave K del aborto (`abort["clase"]`, `abort["rol"]`):
  - `K == "infraestructura"` (task, judge): limite de tasa dominante si las fallas
    con `es_limite_tasa` de R son mayoria estricta (> 50%) de las fallas de
    `infraestructura` de R.
  - `K == "total"` (reflection, que no tiene umbral de `infraestructura`): dominante
    si las fallas con `es_limite_tasa` de R son mayoria estricta de las fallas
    totales de R.
  - Cualquier otra clave de aborto: no es limite de tasa (sale con 1).
  Ambos entry points (`dspy_gepa_poc.reflexio_declarativa`,
  `gepa_standalone.universal_optimizer`) MUST aplicarlo en su manejo de `RunAborted`
  y documentar el codigo en `docs/DEVELOPMENT.md`.
- FR-011 La sonda de conexion (`probe_completion`, Paso 2 de SPEC-106 FR-005) MUST
  aplicar solo la espera de limite de tasa (FR-002 y FR-003) cuando la excepcion es
  un 429, y mantener 0 reintentos para toda otra clase (credencial, 404, red, 5xx).
  Si el 429 persiste o es no transitorio, la corrida MUST salir con 75.
  `gepa_standalone/universal_optimizer.py` MUST llamar a `configure_failure_tracker()`
  antes de `validate_llm_connections()` (como ya hace `dspy_gepa_poc`), para que la
  sonda use el presupuesto configurado. Enmienda SPEC-106 FR-005 y
  `docs/LLM_CONFIG.md`.
- FR-012 Los runners MUST propagar el codigo 75:
  - `run_dspy_total.sh` y `run_demos_gepa.sh` MUST soportar `BATCH_COOLDOWN`
    (segundos, entero >= 0, default 0) como pausa entre pruebas consecutivas (no
    antes de la primera, no tras la ultima ni tras una detencion). Un valor invalido
    MUST detener el runner con un error claro antes de la primera prueba. Ante el
    codigo 75 el runner MUST detenerse siempre, aun con `CONTINUE_ON_FAIL=1`, y su
    resumen MUST decir que la causa fue el limite del proveedor y cuantas pruebas
    quedaron sin ejecutar.
  - `shared/utils/seed_protocol.py::run_seeds` MUST cortar de inmediato las seeds
    restantes ante `returncode == 75`, informando "limite del proveedor", y SHOULD
    respetar `BATCH_COOLDOWN` cuando `--jobs 1`.
- FR-013 Corte por limite persistente, por rol. El tiempo de espera MUST ser
  proporcional tambien por corrida: un 429 que no se recupera MUST costar a lo
  sumo un presupuesto completo de FR-004 por rol, no uno por caso.
  - Cuando una llamada agota `rate_limit_retries` ante un 429 transitorio, el
    contador MUST marcar el rol como "en corte". El estado MUST ser thread-safe
    y reiniciarse con `FailureTracker.reset`.
  - Con el rol en corte, todo 429 transitorio de ese rol MUST fallar de
    inmediato: 1 llamada HTTP, 0 s de espera, `infraestructura`,
    `es_limite_tasa=True` y un mensaje que nombra el corte. La llamada se hace
    igual (no se suprime), para detectar que la cuota reabrio. Un hilo que ya
    estaba esperando cuando se activo el corte termina esa espera y su 429
    siguiente falla sin esperar.
  - Cualquier llamada del rol que responda sin excepcion del proveedor MUST
    levantar el corte: el 429 siguiente vuelve a esperar con el presupuesto
    completo.
  - El corte no cambia la clasificacion, los conteos ni los umbrales de SPEC-104:
    el aborto sigue la regla de FR-006 de SPEC-104 y sale con 75 por FR-010. No
    afecta a las demas fallas de `infraestructura` (`infra_retries`) ni a los 429
    no transitorios de FR-003, que ya fallan sin esperar.
  - Cada activacion y cada levantamiento MUST emitir una linea `INFO` por el
    mismo logger de FR-005, con rol y modelo. No es una espera: no suma a
    `waits`. Las activaciones suman a `cortes` (FR-009).
  - La sonda de conexion (FR-011) no activa ni consulta el corte: si agota su
    presupuesto, la corrida sale con 75.

## Criterios de exito (medibles, agnosticos a tecnologia)

- SC-001 Un 429 con `Retry-After: 2` seguido de una respuesta sana se resuelve con
  una espera de al menos 2 s (nunca menos) y menos que el tope; el caso queda
  evaluado y el contador registra 0 fallas.
- SC-002 Interceptando `httpx` con un 429 real de cada proveedor, el sistema lee la
  cabecera esperada en Azure (`x-ms-retry-after-ms` / `retry-after`), OpenAI
  (`retry-after-ms` / `retry-after`) y Anthropic (`retry-after`), y la prioridad de
  FR-002 se respeta (en milisegundos antes que en segundos).
- SC-003 Un 429 transitorio sin cabecera y permanente hace `1 + rate_limit_retries`
  llamadas HTTP con esperas dentro de [0.8, 1.2] x `min(5 * 2**n, 60)`, termina como
  `infraestructura` y cuenta una sola falla por caso.
- SC-004 Los tres 429 no transitorios de FR-003 hacen 1 llamada HTTP y 0 s de
  espera: `Retry-After` mayor que el tope (mensaje con la espera pedida),
  `insufficient_quota` y "request too large" (el payload `413_too_large` de
  `tests/litellm_failure_payloads.py`).
- SC-005 Timeout, red, 408, 409, 5xx y 529 siguen haciendo `1 + infra_retries`
  llamadas con 1, 2 y 4 s: 0 diferencias de conteo frente a SPEC-104 SC-009 en los
  payloads que no son 429.
- SC-006 Cada espera deja exactamente una linea `INFO` visible en consola (no solo
  en `caplog`), con modelo incluido, y `run.json["failures"]["rate_limit_waits"]`
  coincide en `waits` con el numero de lineas de espera (y en `cortes` con las de
  activacion del corte), sin alterar `failures.counts`
  (SPEC-104 SC-005) ni el conjunto de claves de primer nivel (SPEC-104 SC-006).
- SC-007 Con `num_threads > 1` y un 429 con espera de T s en un hilo, ninguna otra
  llamada del mismo rol sale antes de `T` s (reloj simulado); el estado se reinicia
  con `FailureTracker.reset`.
- SC-008 `is_rate_limit_abort()`: un aborto de `task` por `infraestructura` con 2
  de 3 fallas por limite de tasa da `True`; el mismo aborto con 1 de 3 da `False`;
  un aborto de `reflection` por `total` con 3 de 4 fallas por limite de tasa da
  `True`; un 429 de tamano (`es_limite_tasa=False`) no suma. Los entry points salen
  con 75 en los casos `True` y con 1 en los demas.
- SC-009 Un 429 en `probe_completion` espera segun FR-002; si persiste o es no
  transitorio la corrida sale con 75, y las demas clases siguen sin reintento.
- SC-010 Con `BATCH_COOLDOWN=N` y K pruebas (python simulado, sin LLM) los runners
  hacen K - 1 pausas de N s y 0 tras una detencion; un valor invalido se rechaza
  antes de la primera prueba. Ante el codigo 75 se detienen tambien con
  `CONTINUE_ON_FAIL=1`, y `run_seeds` corta las seeds restantes.
- SC-011 Valores invalidos de `failures.rate_limit_retries` o
  `failures.rate_limit_max_wait` (negativo, no numerico, booleano) fallan en la
  validacion de la config, antes de gastar tokens.
- SC-012 Con `num_threads=1`, un 429 sin cabecera que no se recupera en ninguna
  llamada del rol `task` y los umbrales por defecto: la espera total del rol no
  supera un presupuesto completo (234 s con jitter), cada llamada posterior al
  corte hace 1 llamada HTTP y 0 s de espera, `cortes` vale 1 y la corrida sale
  con 75. Si despues del corte una llamada responde, el corte se levanta y el
  429 siguiente vuelve a hacer `1 + rate_limit_retries` llamadas.

## Escenarios (Given/When/Then)

- Given un deployment con la cuota por minuto agotada y un 429 con `Retry-After: 20`,
  When corre el caso de tarea, Then la consola muestra que espera 20 s, reintenta y,
  si responde, el caso se evalua como cualquier otro.
- Given un 429 transitorio sin cabecera que no se recupera, When se agota el
  presupuesto, Then espero 5, 10, 20, 40, 60 y 60 s (con jitter) y el caso queda NE
  por `infraestructura`.
- Given un 429 con `Retry-After: 3600` (cuota diaria), When llega el primer 429,
  Then no hay espera y el mensaje dice que el proveedor pide 3600 s.
- Given un 429 con `insufficient_quota`, When llega, Then 1 llamada, 0 s de espera
  y, si la corrida aborta, sale con 75 y el batch se detiene.
- Given un prompt que por si solo excede el TPM de la organizacion ("Request too
  large"), When llega el 429, Then 1 llamada, 0 s de espera, el caso queda NE y no
  cuenta como limite de tasa del batch.
- Given `num_threads=4` y un 429 con `Retry-After: 10` en un hilo, When los otros
  hilos van a llamar, Then esperan esos 10 s en lugar de recibir 429.
- Given un batch con `BATCH_COOLDOWN=60` y tres pruebas, When las dos primeras
  terminan bien, Then hay dos pausas de 60 s y ninguna despues de la tercera.
- Given una prueba que sale con 75 dentro de un batch o de `seed_protocol`, When el
  runner la recibe, Then se detiene, informa "limite del proveedor" y las
  pruebas o seeds restantes quedan sin ejecutar.
- Given una cuota que no reabre y un 429 sin cabecera (p. ej. Azure
  `insufficient_quota`), When el primer caso agota su presupuesto, Then los
  casos siguientes del rol fallan sin esperar y la corrida aborta con 75 tras
  unos 195 s de espera en total, no tras una hora.
- Given un rol en corte, When una llamada del rol responde, Then el corte se
  levanta, se informa en consola y el 429 siguiente vuelve a esperar.
- Given un batch cuya prueba k agoto el TPM, When la prueba k+1 arranca y su sonda
  de conexion recibe un 429, Then la sonda espera segun la cabecera en lugar de
  terminar con 1.

## Fuera de alcance

- Fallback de modelo o deployment (FR-008).
- Control proactivo de la tasa (token bucket, limitar hilos segun la cuota): FR-007
  solo propaga la espera reactiva ya recibida. La concurrencia sigue siendo
  `optimization.num_threads`.
- Cuotas diarias o mensuales: solo se detectan (FR-003), no se esperan.

## Alternativas descartadas

- Solo subir `failures.infra_retries`: espera exponencial desde 1 s, no distingue 429
  de timeout y no respeta `Retry-After`.
- Fallback a otro modelo: contamina la comparabilidad de seeds (D-017 muestra que
  modelos distintos se comportan distinto con los mismos demos).
- Un tope de espera acumulada por caso para el 413 generico: FR-003 lo resuelve sin
  esperar nada y sin acotar por tiempo.
- Leer `x-ratelimit-reset-*` para calcular la espera: reportan horas en limites mixtos.
- Para el 429 cronico (FR-013): abortar la corrida en cuanto una llamada agota el
  presupuesto (un solo caso corta una corrida larga y rompe la regla de umbrales
  de SPEC-104 FR-006); un tope de espera acumulada por corrida con clave nueva
  (no se rearma si la cuota reabre); aceptar el costo de un presupuesto por caso
  (hasta una hora en secuencial antes del aborto).

## Tests y docs existentes que esta spec obliga a ajustar

Tests (los conteos de 429 pasan a `1 + rate_limit_retries` con espera simulada, sin
dormir de verdad, o a 1 llamada en los 429 no transitorios):

- `tests/test_litellm_failure_mapping.py::test_retry_counts_checked_lm` (el caso
  `413_too_large` pasa a 1 llamada HTTP)
- `tests/test_reflection_guard.py` y `tests/test_single_call_point.py` (conteo
  esperado por clase)
- `tests/test_sc005_logs_vs_run_json.py` (usa `429_rate_limit`: fijar
  `rate_limit_retries` o inyectar el reloj)
- `tests/test_lib_contracts.py` (nueva superficie `litellm_response_headers`)
- `tests/test_role_probe.py` (la sonda espera ante 429)
- Tests de `seed_protocol` y del manejo de `RunAborted` en ambos entry points

Docs y specs con enmienda trazada en `historial/sdd.md`:

- SPEC-104: FR-007 (aviso `INFO` de espera), FR-011 (presupuesto y espera del 429) y
  FR-015 (excepcion textual "request too large")
- SPEC-106: FR-005 (la sonda espera ante 429)
- `docs/GEPA_MANEJO_ERRORES.md` (afirma un unico presupuesto de 3 reintentos y todo
  intento intermedio a `DEBUG`), `docs/LLM_CONFIG.md`,
  `docs/YAML_CONFIG_REFERENCE.md`, `docs/METADATA_REPRODUCIBILIDAD.md`,
  `docs/DEVELOPMENT.md` y `docs/PROTOCOLO_N_SEEDS.md`

## Coverage mapping (requisito -> derivado)

Todo pendiente de implementacion (spec en `draft`); el plan de fases se crea al
aprobar la spec (`docs/plans/PLAN_SPEC-107_limite_de_tasa_proveedor.md`).

| Requisito | Derivado previsto (codigo/test/config) |
|---|---|
| FR-001 | `shared/llm/failures.py` (`LLMFailure.es_limite_tasa`, clasificacion), `shared/llm/call.py`; `tests/test_rate_limit_wait.py` |
| FR-002 | `shared/llm/call.py` (lectura de cabeceras, espera, reloj inyectable); `tests/test_rate_limit_wait.py`; `tests/test_lib_contracts.py` (superficie `litellm_response_headers`) |
| FR-003 | `shared/llm/call.py`, `shared/llm/failures.py`; `tests/test_rate_limit_wait.py`, `tests/test_litellm_failure_mapping.py` |
| FR-004 | `shared/llm/failures.py` (`FailureTracker.configure`, defaults), `shared/validation/base_validator.py` (`FAILURES_KEYS`); `docs/YAML_CONFIG_REFERENCE.md` |
| FR-005 | `shared/llm/call.py` (aviso `INFO`, parametro `model`), handler acotado a `shared.llm` en los entry points; `tests/test_sc005_logs_vs_run_json.py` |
| FR-006 | `shared/llm/call.py` (espera en tramos con `check_abort`); `tests/test_rate_limit_wait.py` |
| FR-007 | `shared/llm/call.py` (cooldown por rol), `FailureTracker.reset`; `tests/test_rate_limit_wait.py` |
| FR-008 | `tests/test_rate_limit_wait.py` (el modelo del rol no cambia entre intentos) |
| FR-009 | `shared/llm/failures.py::FailureTracker.snapshot`; `docs/METADATA_REPRODUCIBILIDAD.md`; `tests/test_sc006_no_failure_regression.py` |
| FR-010 | `shared/llm/failures.py` (`EXIT_RATE_LIMIT`, `is_rate_limit_abort`), `shared/llm/__init__.py`; `dspy_gepa_poc/reflexio_declarativa.py`, `gepa_standalone/universal_optimizer.py`; `docs/DEVELOPMENT.md` |
| FR-011 | `shared/llm/call.py::probe_completion`, `shared/llm/config.py`; `gepa_standalone/universal_optimizer.py` (orden); `tests/test_role_probe.py`; `docs/LLM_CONFIG.md` |
| FR-012 | `dspy_gepa_poc/run_dspy_total.sh`, `gepa_standalone/run_demos_gepa.sh`, `shared/utils/seed_protocol.py`; `docs/DEVELOPMENT.md`, `docs/PROTOCOLO_N_SEEDS.md` |
| FR-013 | `shared/llm/failures.py` (estado del corte, `cortes` en `snapshot`), `shared/llm/call.py` (bucle); `tests/test_rate_limit_wait.py`, `tests/test_failures.py` |
| SC-001, SC-003, SC-004, SC-005 | `tests/test_rate_limit_wait.py`, `tests/test_litellm_failure_mapping.py`, `tests/test_single_call_point.py` |
| SC-002 | `tests/test_rate_limit_wait.py` (intercepta `httpx` por proveedor); `tests/test_lib_contracts.py` |
| SC-006 | `tests/test_sc005_logs_vs_run_json.py` (extension), `tests/test_sc006_no_failure_regression.py` |
| SC-007 | `tests/test_rate_limit_wait.py` |
| SC-008 | `tests/test_failures.py`; pruebas de ambos entry points |
| SC-009 | `tests/test_role_probe.py` |
| SC-010 | prueba de los runners con python simulado (sin LLM) y de `run_seeds`; donde vive: por decidir en el plan |
| SC-011 | `tests/test_failures.py` o el test del validador de `failures` |
| SC-012 | `tests/test_rate_limit_wait.py` |
