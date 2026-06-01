# CONTRIBUTING — Convenciones y workflow

SSOT de como trabajar en el repo: convenciones de codigo y documentacion, y el
cierre de entregas bajo el protocolo SDD. Para setup y comandos ver
`docs/DEVELOPMENT.md`; para patrones e invariantes ver `docs/ARCHITECTURE.md`.

## Convenciones del proyecto

- MUST NOT usar emoticones en codigo, comentarios ni documentacion. Mantener un
  estilo profesional y limpio.
- MUST: un doc, un proposito (SSOT). Cada documento es la fuente de verdad de su
  dominio y no repite informacion de otro; las SSOTs se referencian, no se
  copian. El mapa completo esta en `00-INDEX.md`.
- Lint con ruff: line-length 100, reglas E/F/I/N/UP/B/C4. Ver `pyproject.toml`.
- MUST: antes de cerrar un cambio, pasar el pipeline local
  `./shared/utils/ci_local.sh` (ver `docs/DEVELOPMENT.md`).

## Protocolo SDD (en adopcion por tramos)

SSOT del protocolo: `docs/SDD_PROTOCOLO.md`. Tramos 0 y 1 activos; Tramo 2 con
esqueleto listo (no invasivos):

- **Lenguaje normativo**: usar `MUST`/`SHOULD`/`MAY` al inicio de la sentencia en
  requisitos, invariantes y reglas.
- **Marcador `[NEEDS CLARIFICATION: ...]`**: dejarlo dentro del doc ante
  ambiguedad que no deba resolverse por cuenta propia, en vez de asumir.
- **Bloque `[SDD-Check]`**: al cerrar una entrega no trivial, cerrar con el bloque
  de verificacion (spec leida, incluye/excluye, validaciones, SSOT afectado,
  derivados, deuda arrastrada, riesgos). Detalle y plantilla en el SSOT.
- **Deuda arrastrada** (`historial/sdd.md`): si el `[SDD-Check]` deja deuda
  distinta de "ninguna", registrarla en la tabla del historial hasta cerrarla.
- **Specs de capacidad** (`specs/SPECS_REGISTRY.md`): toda capacidad nueva SHOULD
  crearse con la plantilla hibrida del SSOT y registrarse ahi. Los docs siguen en
  `docs/` (no van al registro).
