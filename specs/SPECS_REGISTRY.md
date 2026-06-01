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
- Una spec MAY declarar `Depende de:` y `Relacionada con:` (links `[[id]]`).
- Cierre de iteracion -> bloque `[SDD-Check]` citando specs leidas, includes/excludes verificados y SSOTs afectados.
- Formato de spec: anatomia hibrida (User Story con prioridad P1/P2/P3 + `FR-NNN MUST` + `SC-NNN` medibles + Given/When/Then + coverage mapping). Plantilla en `docs/SDD_PROTOCOLO.md` (Tramo 2).
- Sin emoticones. Fechas en formato YYYY-MM-DD. No duplicar contenido de otros SSOTs: referenciar.

## Specs vigentes

| ID | Titulo | Estado | Iter | Archivo |
|---|---|---|---|---|
| _(ninguna aun — el registro arranca vacio; se crea la primera spec cuando aparezca una capacidad nueva donde estrenar el formato)_ | | | | |

## Roadmap de iteraciones

Ver `historial/sdd.md` para el log evolutivo SDD y la deuda arrastrada.
