# SPECS_REGISTRY — Single Source of Truth de specs de capacidad

Este archivo lista las specs de **capacidad** vigentes del proyecto. Cada spec
describe una capacidad concreta del sistema (una funcionalidad o contrato), sus
criterios de aceptacion y su estado. Toda implementacion nueva de una capacidad
SHOULD poder mapearse a una spec aqui registrada.

Alcance: solo **capacidades** (Linea B / software). Los documentos de
arquitectura, guias y conceptos viven en `docs/` y se gobiernan por el Mapa de
SSOTs de `00-INDEX.md`; NO se registran aqui (modelo del proyecto testigo
`agent-test-suite`). SSOT del protocolo SDD: `docs/SDD_PROTOCOLO.md`.

> Las specs son **vivas**: se actualizan tras cada iteracion (spec -> ejecucion
> -> observacion -> ajuste). Los pendientes que dejan van a `historial/sdd.md`
> (Deuda arrastrada).

## Convenciones

- Estado (SSOT de los estados de spec; la plantilla de `docs/SDD_PROTOCOLO.md`
  remite aqui):
  - `draft`: spec en redaccion o aprobada, con implementacion pendiente (al
    menos una fila del Coverage mapping en `pendiente`). Un plan aprobado en
    `docs/plans/` no cambia el estado.
  - `active`: capacidad implementada y vigente. Se pasa de `draft` a `active`
    al cerrar la implementacion: Coverage mapping sin `pendiente` y
    `./shared/utils/ci_local.sh` en verde. Una iteracion nueva sobre una spec
    `active` que agregue requisitos sin implementar MUST volverla a `draft`
    hasta su cierre.
  - `superseded`: reemplazada por otra spec, que MUST citarse en la cabecera
    (`Reemplazada por: [[SPEC-NNN-...]]`). La capacidad sigue existiendo, pero
    su contrato vigente es el de la spec nueva.
  - `archived`: sin vigencia y sin reemplazo (capacidad retirada del codigo o
    spec abandonada antes de implementarse).
  - Todo cambio de estado MUST reflejarse en la spec, en este registro y en
    `historial/sdd.md`.
- Cada spec tiene un ID estable (`SPEC-NNN-slug`) y un archivo en este directorio.
- Numeracion: las nuevas capacidades se numeran desde `SPEC-100` en adelante. El
  rango `SPEC-001`..`SPEC-099` queda RESERVADO para formalizar retrospectivamente
  capacidades preexistentes (las que ya viven en el codigo sin spec). Asi el
  numero bajo no implica "primera en el tiempo" y hay espacio para documentar lo
  anterior sin renumerar.
- Paso entre specs (desde 2026-11-28): cada spec nueva toma el siguiente
  multiplo de 5 libre (`SPEC-110`, `SPEC-115`, `SPEC-120`, `SPEC-125`, ...). Los
  numeros intermedios quedan RESERVADOS para specs que deban ubicarse entre dos
  existentes (p. ej. una capacidad que debe resolverse antes que `SPEC-115` toma
  `SPEC-111`..`SPEC-114`). El rango `SPEC-100`..`SPEC-106` es anterior a la
  regla y queda contiguo; `SPEC-107`..`SPEC-109` quedan libres como reserva.
- El numero expresa el orden previsto de resolucion, no la fecha de creacion.
  Si una spec en `draft` debe adelantarse, MAY renumerarse a un hueco reservado
  mientras no tenga codigo ni commits de implementacion que la citen; al
  renumerar MUST actualizarse el archivo, este registro y los docs vivos que la
  citan, y MUST registrarse en `historial/sdd.md` una tabla de equivalencias
  (numero anterior -> nuevo). Las entradas previas del log y los mensajes de
  commit no se reescriben.
- Una spec MAY declarar `Depende de:` y `Relacionada con:` (links `[[id]]`).
- Cierre de iteracion -> bloque `[SDD-Check]` citando specs leidas, includes/excludes verificados y SSOTs afectados.
- Formato de spec: anatomia hibrida (User Story con prioridad P1/P2/P3 + `FR-NNN MUST` + `SC-NNN` medibles + Given/When/Then + coverage mapping). Plantilla en `docs/SDD_PROTOCOLO.md` (Tramo 2).
- Sin emoticones. Fechas en formato YYYY-MM-DD. No duplicar contenido de otros SSOTs: referenciar.

## Specs vigentes

| ID | Titulo | Estado | Iter | Archivo |
|---|---|---|---|---|
| SPEC-100-veredicto-senal-ruido | Veredicto senal-vs-ruido del protocolo de N seeds | active | 3 | `SPEC-100-veredicto-senal-ruido.md` |
| SPEC-101-triaje-casos-nseeds | Triaje de casos para el protocolo de N seeds | active | 1 | `SPEC-101-triaje-casos-nseeds.md` |
| SPEC-102-flujo-intents | Atencion multipaso de intents (Marco de Gobierno IA) | draft | 1 | `SPEC-102-flujo-intents.md` |
| SPEC-103-proveedor-anthropic | Anthropic como proveedor verificado (Haiku 4.5 a Opus 5.5 / Fable) | active | 4 | `SPEC-103-proveedor-anthropic.md` |
| SPEC-104-fallas-tecnicas-justas | Fallas tecnicas visibles y medicion justa | active | 4 | `SPEC-104-fallas-tecnicas-justas.md` |
| SPEC-105-punto-llamada-desacoplado | Punto de llamada propio, desacoplado de los internos de DSPy y GEPA | active | 5 | `SPEC-105-punto-llamada-desacoplado.md` |
| SPEC-106-roles-intercambiables | Profesor, estudiante y juez intercambiables entre proveedores | active | 2 | `SPEC-106-roles-intercambiables.md` |
| SPEC-110-filtros-modelos-analisis | Filtros combinables por caso, estudiante y profesor en el analisis | draft | 1 | `SPEC-110-filtros-modelos-analisis.md` |
| SPEC-115-limite-de-tasa-proveedor | Espera ante limite de tasa del proveedor (429) | draft | 3 | `SPEC-115-limite-de-tasa-proveedor.md` |
| SPEC-120-costo-real-por-resolucion | Costo real de cada combinacion de roles | draft | 1 | `SPEC-120-costo-real-por-resolucion.md` |

## Roadmap de iteraciones

Ver `historial/sdd.md` para el log evolutivo SDD y la deuda arrastrada.
