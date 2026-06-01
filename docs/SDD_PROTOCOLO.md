# Protocolo SDD (Spec-Driven Development) — adopcion por tramos

Este documento es el SSOT del protocolo SDD del proyecto. Reflexio adopta SDD de
forma pragmatica y por tramos, tomando solo las practicas de bajo costo y alto
valor (no invasivas). La referencia metodologica externa esta en
`../../analisis/SDD/` (Linea B / software): `software/ANALISIS-SPEC-KIT.md`,
`software/COMPARATIVA-SPECKIT-VS-TESTIGO.md` e
`IMPLEMENTACION-INICIAL-CONTEXTO-ACTUAL.md`.

Criterio rector (de `IMPLEMENTACION-INICIAL-CONTEXTO-ACTUAL.md`): priorizar
disciplina operativa antes que tooling; no automatizar mientras la disciplina
manual no muestre limites.

## Estado de adopcion

| Tramo | Contenido | Estado |
|---|---|---|
| Tramo 0 | Convenciones de salida: bloque `[SDD-Check]`, marcador `[NEEDS CLARIFICATION]`, lenguaje normativo | Activo |
| Tramo 1 | Circuito de aprendizaje: `historial/sdd.md` con *Deuda arrastrada* | Activo |
| Tramo 2 | Specs de capacidad: `SPECS_REGISTRY.md` central + anatomia hibrida (FR/SC + Given/When/Then + coverage mapping) | Esqueleto listo (sin specs aun) |
| Tramo 3 | Gate de integridad: `CONSTITUTION.md` por referencia + check cableado en `ci_local.sh` | Diferido (solo si T0-T2 prueban valor) |

---

## Tramo 0 — Convenciones de salida (activo)

Estas tres convenciones no tocan codigo ni estructura y son reversibles. Aplican
a entregas del agente sobre documentos y codigo del repo.

### 1. Lenguaje normativo (RFC 2119)

Al redactar requisitos, invariantes o reglas, usar `MUST` / `SHOULD` / `MAY`
(o sus equivalentes `MUST NOT` / `SHOULD NOT`) al inicio de la sentencia, para
que la obligatoriedad sea explicita y grep-able. Reservar `MUST` para lo
no-negociable.

### 2. Marcador `[NEEDS CLARIFICATION: ...]`

Cuando una spec, pedido o doc tenga una ambiguedad que el agente no deba
resolver por su cuenta, dejar el marcador `[NEEDS CLARIFICATION: <pregunta>]`
*dentro* del documento en vez de asumir. Es liviano y grep-able. No elimina la
regla de "MUST preguntar al usuario ante ambiguedad": el marcador es el rastro
escrito de esa pregunta hasta que se resuelve.

### 3. Bloque `[SDD-Check]` por entrega

Al cerrar una entrega no trivial (cambio de doc, de spec, de codigo con impacto
en invariantes o SSOTs), el agente SHOULD incluir al final un bloque
`[SDD-Check]` con estas lineas:

```
[SDD-Check]
- Spec/doc leido: <que SSOT o doc se consulto antes de cambiar>
- Incluye/Excluye verificado: <el cambio cae dentro del alcance declarado>
- Validaciones aplicadas: <tests, ruff, ci_local.sh, refs internas, sin emoticones>
- SSOT afectado: <que SSOT cambia, o "ninguno (doc operativo)">
- Derivados a revisar: <docs/configs/codigo que dependen del cambio, o "ninguno">
- Deuda arrastrada: <pendiente que queda abierto, o "ninguna">
- Riesgos/reservas: <supuestos o limites del cambio>
```

El bloque es disciplina, no gate: su valor es dejar trazabilidad de que se
verifico y que queda pendiente. El campo **Deuda arrastrada** es el puente al
Tramo 1: todo pendiente que aparezca aqui de forma recurrente es candidato a
registrarse en `historial/sdd.md` cuando ese tramo se active.

Para cambios triviales (typo, formato, una linea) el bloque MAY omitirse.

---

## Tramo 1 — Circuito de aprendizaje (activo)

Artefacto: `historial/sdd.md`. Instrumenta el feedback bidireccional (lo que
Spec Kit deja a disciplina) en un registro obligatorio. Dos partes:

- **Deuda arrastrada**: tabla de pendientes con ID (`D-NNN`), descripcion, origen
  y estado. Un pendiente se re-explicita hasta cerrarse; al resolverse pasa a
  "Deuda resuelta" con fecha y cierre. Es el mecanismo anti "cascada encubierta".
- **Log de fases**: entradas datadas (YYYY-MM-DD) de que cambio y por que.

Enlace con el Tramo 0: cuando un bloque `[SDD-Check]` cierra con "Deuda
arrastrada" distinta de "ninguna", ese item MUST registrarse en la tabla de
`historial/sdd.md`. Asi el pendiente sobrevive al fin de la conversacion.

---

## Tramo 2 — Specs de capacidad (esqueleto listo)

Andamiaje creado, sin specs reales todavia. Artefacto: `specs/SPECS_REGISTRY.md`
(registro central, arranca vacio). Modelo: proyecto testigo `agent-test-suite`.

Separacion de alcance (clave para no duplicar SSOTs):

- **Capacidades** (funcionalidad/contrato de software) -> `specs/SPEC-NNN-slug.md`, registradas en `specs/SPECS_REGISTRY.md`.
- **Docs** (arquitectura, guias, conceptos) -> `docs/*.md`, gobernados por el Mapa de SSOTs de `00-INDEX.md`. NO entran al registro.
- El `00-INDEX.md` es el indice maestro: une ambos (una fila apunta al registro de capacidades, las demas a los docs).

Cuando crear la primera spec: recien cuando aparezca una capacidad nueva donde
estrenar el formato. No migrar lo existente (el testigo empezo casero y paso a
hibrido sin reescribir lo viejo).

### Plantilla de spec hibrida

```
# SPEC-NNN-slug — <titulo de la capacidad>

Estado: draft | active | superseded | archived
Iteracion: <N> (rev. YYYY-MM-DD)
Depende de: [[SPEC-MMM-...]]      # opcional
Relacionada con: [[SPEC-...]]     # opcional

## User Story (prioridad)
Como <rol>, quiero <accion>, para <beneficio>.
Prioridad: P1 | P2 | P3   # P1 = MVP minimo, slice testeable de forma aislada

## Requisitos funcionales
- FR-001 El sistema MUST <comportamiento observable>.
- FR-002 El sistema SHOULD <comportamiento>.
- [NEEDS CLARIFICATION: <pregunta abierta si la hay>]

## Criterios de exito (medibles, agnosticos a tecnologia)
- SC-001 <metrica cuantificable, p.ej. "100% de los casos X devuelven Y">.

## Escenarios (Given/When/Then)
- Given <contexto>, When <accion>, Then <resultado esperado>.

## Coverage mapping (requisito -> derivado)
| Requisito | Derivado (codigo/test/config) |
|---|---|
| FR-001 | <archivo o test que lo implementa/verifica> |
| SC-001 | <como se mide> |
```

El coverage mapping es lo que evita "requisitos sin derivado": cada FR/SC MUST
apuntar a donde se implementa o verifica.

---

## Tramo 3 — Gate de integridad (diferido)

El Tramo 3 (`CONSTITUTION.md` por referencia + check cableado en `ci_local.sh`)
se documentara aqui al activarse. No implementarlo por adelantado: se habilita
solo cuando T0-T2 hayan mostrado valor en uso real (criterio de
`IMPLEMENTACION-INICIAL-CONTEXTO-ACTUAL.md`).
