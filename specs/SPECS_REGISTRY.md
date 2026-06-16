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

- Estado: `draft` | `active` | `superseded` | `archived`.
- Cada spec tiene un ID estable (`SPEC-NNN-slug`) y un archivo en este directorio.
- Numeracion: las nuevas capacidades se numeran desde `SPEC-100` en adelante. El
  rango `SPEC-001`..`SPEC-099` queda RESERVADO para formalizar retrospectivamente
  capacidades preexistentes (las que ya viven en el codigo sin spec). Asi el
  numero bajo no implica "primera en el tiempo" y hay espacio para documentar lo
  anterior sin renumerar.
- Una spec MAY declarar `Depende de:` y `Relacionada con:` (links `[[id]]`).
- Cierre de iteracion -> bloque `[SDD-Check]` citando specs leidas, includes/excludes verificados y SSOTs afectados.
- Formato de spec: anatomia hibrida (User Story con prioridad P1/P2/P3 + `FR-NNN MUST` + `SC-NNN` medibles + Given/When/Then + coverage mapping). Plantilla en `docs/SDD_PROTOCOLO.md` (Tramo 2).
- Sin emoticones. Fechas en formato YYYY-MM-DD. No duplicar contenido de otros SSOTs: referenciar.

## Specs vigentes

| ID | Titulo | Estado | Iter | Archivo |
|---|---|---|---|---|
| SPEC-100-veredicto-senal-ruido | Veredicto senal-vs-ruido del protocolo de N seeds | active | 2 | `SPEC-100-veredicto-senal-ruido.md` |
| SPEC-101-triaje-casos-nseeds | Triaje de casos para el protocolo de N seeds | active | 1 | `SPEC-101-triaje-casos-nseeds.md` |
| SPEC-102-flujo-intents | Atencion multipaso de intents (Marco de Gobierno IA) | draft | 1 | `SPEC-102-flujo-intents.md` |

## Roadmap de iteraciones

Ver `historial/sdd.md` para el log evolutivo SDD y la deuda arrastrada.
