# Mejoras Pendientes: Reflexio

> **Tipo:** Documento efimero de implementacion
> **Fecha de revision:** 2026-02-08
> **Eliminar despues de:** Implementar todas las mejoras

---

## Resumen Ejecutivo

Arquitectura solida (~7,361 lineas de produccion). Modulos compartidos integrados.
45 tests existentes con 19% de cobertura en `shared/`. Zero TODOs o hacks en codigo.

**Problema principal:** La base funcional esta bien construida pero desprotegida (sin CI,
cobertura baja en modulos criticos) y con friccion de onboarding (sin quickstart ejecutable).

**Estrategia:** Primero proteger lo que ya funciona (CI + tests criticos), luego hacer
el proyecto accesible (quickstart), despues iterar sobre mejoras incrementales.

---

## Estado Actual del Codebase

| Componente | Lineas | Tests | Cobertura |
|---|---|---|---|
| `shared/paths/` | 429 | 33 | 77-100% |
| `shared/llm/` | 359 | 2 (smoke) | 12-22% |
| `shared/validation/` | 520 | 1 (smoke) | 24-31% |
| `shared/logging/` | 288 | 1 (smoke) | 27-40% |
| `shared/display/` | 116 | 1 (smoke) | 7% |
| `shared/analysis/` | 1,676 | 0 | 0% |
| `dspy_gepa_poc/` | 1,446 | 7 (smoke) | - |
| `gepa_standalone/` | 2,570 | 0 | - |

### Fortalezas (Mantener)

- Patron Factory en DynamicModuleFactory
- Validacion temprana con ConfigValidator
- Separacion clara de capas (shared, dspy, gepa)
- Zero-code experimentation via YAML
- Soporte multilingue (ES/EN)
- Manejo de errores robusto (137 sitios, excepciones custom)
- Cero TODOs/FIXMEs/HACKs en codigo

### Duplicacion Restante

| Categoria | Lineas Duplicadas | Similitud |
|---|---|---|
| Data loading | ~70 lineas | 60% |
| Orquestacion | ~200 lineas | 50% |

---

## Tier 1 - Alto Impacto, Bajo Esfuerzo

Proteger la base funcional y desbloquear el onboarding.

### [T1-1] Pipeline de CI (tests + lint)

- **Objetivo:** GitHub Actions basico que ejecute `pytest` y un linter en cada push/PR.
- **Justificacion:** 45 tests que nadie ejecuta automaticamente. Un bug en `shared/llm/`
  o en los adapters afecta todos los experimentos. CI es la red de seguridad minima.
- **Alcance:** pytest, ruff o flake8, fail en coverage < umbral.
- **Esfuerzo:** Bajo.

### [T1-2] Tests para shared/llm/ y shared/validation/

- **Objetivo:** Cobertura real (no solo imports) para los dos modulos mas criticos.
- **Justificacion:** `shared/llm/config.py` (252 lineas, 22% cobertura) es el punto de
  entrada de toda interaccion con LLMs. `shared/validation/` (520 lineas, 24-31%)
  previene errores de configuracion. Un bug en cualquiera de estos rompe todo el proyecto.
- **Alcance:**
  - `shared/llm/config.py`: validacion de conexion, parsing de modelos, manejo de errores.
  - `shared/llm/errors.py`: formateo de diagnosticos.
  - `shared/validation/base_validator.py`: validacion de campos, tipos, valores permitidos.
  - `shared/validation/csv_validator.py`: estructura de CSVs.
  - `shared/validation/errors.py`: formateo de errores de validacion.
- **Esfuerzo:** Bajo-Medio.

### [T1-3] Datasets de ejemplo versionados

- **Objetivo:** 1-2 CSV pequenos commiteados y documentados para que `git clone` +
  `pip install` + un comando = resultado visible.
- **Justificacion:** Bloqueador #1 de onboarding. Ya existen 13 CSVs en el proyecto;
  falta verificar que los esenciales esten commiteados y documentar cual usar primero.
- **Esfuerzo:** Bajo.

---

## Tier 2 - Alto Impacto, Esfuerzo Medio

Reproducibilidad, accesibilidad y cobertura de logica critica.

### [T2-1] Reproducibilidad y trazabilidad

- **Objetivo:** Guardar semillas, version de modelos y config usada junto a cada run.
- **Justificacion:** Sin seeds ni version de modelo, dos ejecuciones del mismo config
  dan resultados diferentes sin explicacion. Invalida comparaciones y el leaderboard
  pierde sentido como herramienta de decision.
- **Alcance:** Snapshot de config + seed + model version en el directorio de cada run.
- **Esfuerzo:** Medio.

### [T2-2] Quickstart ejecutable

- **Objetivo:** Un flujo end-to-end con dataset pequeno y un solo comando
  (ej: `make demo` o `./quickstart.sh`).
- **Justificacion:** El README tiene instrucciones pero no hay forma de validar que
  todo funciona en un paso. Reduce friccion de "quiero probarlo" a minutos.
- **Dependencia:** Requiere [T1-3] datasets de ejemplo.
- **Esfuerzo:** Medio.

### [T2-3] Tests para adapters (gepa_standalone)

- **Objetivo:** Tests unitarios para los 4 adapters en `gepa_standalone/adapters/`.
- **Justificacion:** 829 lineas de logica critica con 0% cobertura. El RAG adapter
  (354 lineas) tiene logica compleja de retry y content filters. Los adapters definen
  directamente la calidad de la optimizacion GEPA. Un bug aqui produce optimizaciones
  silenciosamente incorrectas.
- **Alcance:**
  - `simple_classifier_adapter.py` (117 lineas)
  - `simple_extractor_adapter.py` (203 lineas)
  - `simple_sql_adapter.py` (105 lineas)
  - `simple_rag_adapter.py` (354 lineas) - prioridad por complejidad
- **Esfuerzo:** Medio.

---

## Tier 3 - Impacto Medio, Esfuerzo Medio

Mejoras incrementales sobre base ya funcional.

### [T3-1] Tests para shared/analysis/

- **Objetivo:** Cobertura para el modulo de analisis (1,676 lineas, 0% cobertura).
- **Justificacion:** Importante para confiabilidad del leaderboard y calculos de ROI,
  pero no bloquea funcionalidad core (es post-procesamiento).
- **Alcance:** leaderboard.py, roi_calculator.py, stats_evolution.py, budget_breakdown.py.
- **Esfuerzo:** Medio.

### [T3-2] Naming definitivo de dspy_gepa_poc

- **Objetivo:** Decidir si el nombre refleja el estado actual del proyecto.
- **Justificacion:** "POC" comunica algo temporal y experimental. Si el proyecto ya es
  funcional y se usa en produccion, el nombre deberia reflejarlo. Renombrar afecta
  imports en todo el proyecto.
- **Opciones consideradas:**
  - Mantener `dspy_gepa_poc` (si sigue siendo experimental)
  - `dspy_gepa` (si ya supero la fase POC)
  - `reflexio_dspy` (alineado con nombre del proyecto)
- **Esfuerzo:** Medio (renombrar modulo + actualizar imports).

### [T3-3] Validacion de config mejorada

- **Objetivo:** Mensajes de error mas claros y validacion mas granular en YAMLs.
- **Justificacion:** Ya existe validacion (base_validator 31% cobertura), el valor
  es incremental. Menos tiempo perdido por typos y campos invalidos.
- **Esfuerzo:** Medio.

---

## Tier 4 - Valioso, Puede Esperar

Mejoras de percepcion, documentacion y escalabilidad futura.

### [T4-1] Actualizar README.md

- **Objetivo:** README orientado a humanos, con diferencia clara entre modos de operacion.
- **Justificacion:** El actual es funcional pero denso. Mejora percepcion, no funcionalidad.
- **Esfuerzo:** Bajo.

### [T4-2] Estructura de resultados unificada

- **Objetivo:** Esquema fijo para outputs (metricas, prompts optimizados, logs).
- **Justificacion:** Ya existen CSVs y directorios por run. Formalizar el esquema
  facilita analisis posterior y automatizacion.
- **Esfuerzo:** Medio.

### [T4-3] Guias de contribucion y arquitectura

- **Objetivo:** CONTRIBUTING.md, ARCHITECTURE.md, SECURITY.md, DEVELOPMENT.md.
- **Justificacion:** Solo relevante si se esperan colaboradores externos pronto.
  Sin colaboradores activos, es documentacion sin audiencia.
- **Esfuerzo:** Alto.

### [T4-4] Reducir duplicacion restante

- **Objetivo:** Unificar ~70 lineas de data loading y ~200 de orquestacion.
- **Justificacion:** Duplicacion baja (50-60% similitud). Riesgo actual es minimo
  dado que cada proyecto tiene necesidades ligeramente diferentes.
- **Esfuerzo:** Medio.

---

## Checklist Consolidado (por Tier)

### Tier 1 - Hacer ahora
- [ ] [T1-1] Pipeline de CI (GitHub Actions: pytest + lint)
- [ ] [T1-2] Tests para shared/llm/ y shared/validation/
- [ ] [T1-3] Datasets de ejemplo versionados

### Tier 2 - Hacer pronto
- [ ] [T2-1] Reproducibilidad (semillas, versiones, config snapshot)
- [ ] [T2-2] Quickstart ejecutable (depende de T1-3)
- [ ] [T2-3] Tests para adapters de gepa_standalone

### Tier 3 - Planificar
- [ ] [T3-1] Tests para shared/analysis/
- [ ] [T3-2] Naming definitivo de dspy_gepa_poc
- [ ] [T3-3] Validacion de config mejorada

### Tier 4 - Backlog
- [ ] [T4-1] Actualizar README.md
- [ ] [T4-2] Estructura de resultados unificada
- [ ] [T4-3] Guias de contribucion y arquitectura
- [ ] [T4-4] Reducir duplicacion restante

---

> **Nota:** Este documento es efimero. Eliminar despues de implementar todas las mejoras y verificar funcionamiento.
