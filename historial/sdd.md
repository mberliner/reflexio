# Historial SDD — log evolutivo y deuda arrastrada

Registro vivo de la adopcion de SDD en el proyecto. Dos partes:

1. **Deuda arrastrada**: pendientes que se re-explicitan en cada entrada hasta
   resolverse. Es el mecanismo anti "cascada encubierta": un pendiente no
   desaparece por olvido, sigue listado hasta que alguien lo cierra o lo descarta
   con justificacion. SSOT del protocolo: `../docs/SDD_PROTOCOLO.md`.
2. **Log de fases**: entradas datadas (YYYY-MM-DD) con que cambio y por que.

Regla: cuando una entrega produce un bloque `[SDD-Check]` con "Deuda arrastrada"
distinta de "ninguna", ese item MUST aparecer en la tabla de abajo. Al
resolverse, se mueve a "Deuda resuelta" con la fecha y el cierre.

---

## Deuda arrastrada (abierta)

| ID | Descripcion | Origen | Estado |
|---|---|---|---|
| D-001 | Datasets CV `_v2` con `gold_verificado=no` pendientes de revision humana | Protocolo N seeds (`docs/PROTOCOLO_N_SEEDS.md`) | Abierta — bloquea conclusiones definitivas sobre v2 |
| D-002 | Primera spec de capacidad con formato hibrido (esqueleto listo, registro vacio) | `docs/SDD_PROTOCOLO.md`, `specs/SPECS_REGISTRY.md` | Abierta — esperando primera capacidad nueva donde estrenar el formato |

## Deuda resuelta

| ID | Descripcion | Resuelta | Cierre |
|---|---|---|---|
| — | — | — | — |

---

## Log de fases

### 2026-06-01 — Adelgazamiento de entry files: extraccion a SSOTs

Se aplica el principio SSOT del propio repo a los entry files, siguiendo el modelo
del testigo `agent-test-suite` (entry files finos + detalle en `docs/`). Motivado
por dos sintomas: (a) el pipeline local `shared/utils/ci_local.sh` no se aplicaba
porque no estaba documentado como paso canonico; (b) triplicacion CLAUDE/AGENTS/
GEMINI con drift real (GEMINI tenia `split=dev` contra `val` correcto en
`csv_validator.py`).

Cambios:
- Nuevos SSOTs: `docs/DEVELOPMENT.md` (setup, comandos, pipeline local, entry
  points), `docs/ARCHITECTURE.md` (patrones e invariantes), `docs/CONTRIBUTING.md`
  (convenciones y workflow).
- Entry files reducidos a reglas-gatillo + protocolo de navegacion hacia los
  SSOTs. CLAUDE/AGENTS/GEMINI quedan identicos (regenerados por copia).
- `00-INDEX.md`: registra los 3 SSOTs nuevos y corrige la descripcion del entry.
- Se corrige la invariante `split`: `train`/`val`/`test` (fuente:
  `shared/validation/csv_validator.py` `VALID_SPLITS`).

[SDD-Check]
- Spec leida: n/a (cambio de documentacion; no hay spec de capacidad asociada).
- Includes: extraccion de Desarrollo/Patrones/Invariantes/Convenciones a docs/,
  entry files finos, 00-INDEX actualizado. Excludes: sin cambios de codigo.
- Validaciones: pendiente correr `./shared/utils/ci_local.sh` (CI ignora `**.md`,
  pero se corre para confirmar entorno sano).
- SSOT afectado: 3 docs nuevos + 00-INDEX.md + 3 entry files.
- Derivados: memoria de feedback `local_ci_pipeline` repunteada a DEVELOPMENT.md.
- Deuda arrastrada: ninguna nueva.
- Riesgos: los 3 entry files MUST mantenerse identicos a mano (decision explicita
  de no usar stubs); riesgo de drift futuro si se edita uno solo.

### 2026-06-01 — Tramo 2 esqueleto: registro de specs de capacidad

Se crea `specs/SPECS_REGISTRY.md` (vacio, solo capacidades) y la plantilla de
spec hibrida en `docs/SDD_PROTOCOLO.md`, siguiendo el modelo del testigo
`agent-test-suite`: specs de capacidad en `specs/`, docs en `docs/`, ambos unidos
por el Mapa de SSOTs de `00-INDEX.md` sin duplicarse. No se migra ningun doc ni
codigo existente. La primera spec real queda pendiente (D-002) hasta que aparezca
una capacidad nueva donde estrenar el formato.

### 2026-06-01 — Tramo 1 activo: circuito de aprendizaje

Se crea este archivo (`historial/sdd.md`) con la seccion *Deuda arrastrada*,
adoptando el mecanismo anti-cascada del proyecto testigo `agent-test-suite`
(ver `../../analisis/SDD/software/COMPARATIVA-SPECKIT-VS-TESTIGO.md`). Diferencia
clave frente a Spec Kit: el feedback bidireccional no queda como principio a
disciplina, sino instrumentado en un artefacto obligatorio.

Se inicializa la tabla con dos deudas reales preexistentes (D-001 datasets v2,
D-002 Tramo 2 SDD).

### 2026-06-01 — Tramo 0 activo: convenciones de salida

Alta del SSOT `docs/SDD_PROTOCOLO.md` y de la seccion "Protocolo SDD" en los tres
entry files (CLAUDE.md / AGENTS.md / GEMINI.md). Convenciones: bloque
`[SDD-Check]` por entrega, marcador `[NEEDS CLARIFICATION]`, lenguaje normativo
MUST/SHOULD/MAY. No invasivo: sin cambios en codigo ni estructura.
