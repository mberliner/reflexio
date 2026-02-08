# Mejoras Pendientes: dspy_gepa_poc

> **Tipo:** Documento efimero de implementacion
> **Fecha de revision:** 2026-02-02
> **Estado:** Fases 1-4 completadas (modulos compartidos integrados)
> **Eliminar despues de:** Implementar todas las mejoras

---

## Resumen Ejecutivo

Revision exhaustiva del proyecto `dspy_gepa_poc`. Quedan pendientes mejoras menores de codigo y gaps de documentacion.

**Evaluacion general:** Arquitectura solida. Modulos compartidos integrados. Pendiente documentacion y calidad.

---

## 1. PROBLEMAS DE CODIGO

### [P5] Magic Numbers para Deteccion de Escala

**Archivo:** `reflexio_declarativa.py:149-150`

**Problema actual:**
```python
if baseline_score > 1.0: print(f"Baseline Score: {baseline_score:.2f}%")
else: print(f"Baseline Score: {baseline_score:.2%}")
```

**Solucion propuesta:**
```python
# Al inicio del archivo
NORMALIZED_SCORE_MAX = 1.0  # Scores <= 1.0 son normalizados, > 1.0 son porcentajes

def format_score(score: float) -> str:
    """Formatea score segun escala detectada."""
    if score > NORMALIZED_SCORE_MAX:
        return f"{score:.2f}%"
    return f"{score:.2%}"

# Uso:
print(f"Baseline Score: {format_score(baseline_score)}")
```

**Archivos a modificar:**
- `dspy_gepa_poc/reflexio_declarativa.py`

---

## 3. DOCUMENTACION FALTANTE

### [D2] docs/YAML_CONFIG_REFERENCE.md
- **Estado:** No existe
- **Accion:** Crear documentacion de campos YAML

**Contenido sugerido:**
```markdown
# Referencia de Configuracion YAML

## Secciones Requeridas

### case
- `name` (string): Nombre del experimento

### module
- `type` (string): Tipo de modulo. Valores: "dynamic"

### data
- `csv_filename` (string): Archivo CSV en datasets/
- `input_column` (string): Columna de entrada

### optimization
- `max_metric_calls` (int): Budget de llamadas a metrica

## Secciones Opcionales

### signature (para type="dynamic")
- `instruction` (string): Prompt base
- `inputs` (list): Lista de {name, desc}
- `outputs` (list): Lista de {name, desc}

### optimization (campos opcionales)
- `auto_budget` (string): "light", "medium", "heavy"
- `use_few_shot` (bool): Habilitar few-shot
- `few_shot_count` (int): Numero de ejemplos
- `ignore_in_metric` (list): Campos a ignorar
- `predictor_type` (string): "cot" o "predict"
```

### [D4] Actualizar README.md
- Readme para seres humanos
- Actualizar seccion Features, diferencia entre gepa standalone y dspyt + gepa
- Referenciar forma de configuracion de yamsl que no existe

### [D5] Documentación de arquitectura y buenas practicas de SW
- traer de otros proyectos o crear ad hoc?
- Contribuciones

---

## 4. CHECKLIST DE IMPLEMENTACION

### Codigo
- [ ] [P5] Extraer constantes magic numbers (reflexio_declarativa.py)

### Documentacion
- [ ] [D2] Crear docs/YAML_CONFIG_REFERENCE.md
- [ ] [D4] Actualizar README.md

---

## 5. NOTAS ADICIONALES

### Fortalezas Identificadas (Mantener)
- Patron Factory en DynamicModuleFactory
- Validacion temprana con ConfigValidator
- Separacion clara de capas
- Zero-code experimentation via YAML
- Soporte multilingue

## 6. MODULOS COMPARTIDOS PROPUESTOS

> **Fecha de analisis:** 2026-02-02

Analisis de funcionalidades duplicadas entre `dspy_gepa_poc/` y `gepa_standalone/` que pueden extraerse a `shared/`.

### 6.1 Estructura Implementada

```
shared/
├── llm/           # Configuracion LLM unificada
├── validation/    # ConfigValidator base + validacion CSV
├── logging/       # Logger CSV compartido (BaseCSVLogger)
├── paths/         # Gestion centralizada de rutas (BasePaths -> GEPAPaths, DSPyPaths)
├── display/       # Formateo terminal
└── analysis/      # Utilidades de analisis (leaderboard, ROI)
```

### 6.2 Pendiente

- [ ] Agregar tests unitarios para modulos compartidos

### 6.3 Metricas de Duplicacion Restante

| Categoria | Lineas Duplicadas | Similitud |
|-----------|-------------------|-----------|
| Data loading | ~70 lineas | 60% |
| Orquestacion | ~200 lineas | 50% |

---

## 7. Verificar nombres de dspy_gepa_poc
    Es POC? o mas...
    Es un optimizador o una plataforma de intención diferente?
    Declarative Self-improving Python

---

## 9. Pipeline de CI
- Test unitarios, lint, seguridad, calidad de codigo
- CD?

---

## 10. Documentacion Nueva (DX)

### [M1] Quickstart ejecutable y minimo
- **Objetivo:** Un flujo end-to-end con dataset pequeño y un solo comando.
- **Impacto:** Onboarding inmediato y validacion rapida de instalacion.

### [M7] Guia de contribucion y convenciones
- **Objetivo:** `CONTRIBUTING.md` con flujo para agregar modulos, metricas y scripts.
- **Impacto:** Escalabilidad del proyecto con colaboradores.

---

## 11. Validacion / DX

### [M2] Validacion de config + errores claros
- **Objetivo:** Validar YAMLs en `dspy_gepa_poc` y `gepa_standalone` con mensajes legibles.
- **Impacto:** Menos tiempo perdido por typos y campos invalidos.

---

## 12. Reproducibilidad

### [M3] Reproducibilidad y trazabilidad
- **Objetivo:** Guardar semillas, version de modelos y config usada junto a cada run.
- **Impacto:** Comparabilidad entre experimentos sin ambiguedad.

---

## 13. Resultados / Artefactos

### [M4] Estructura de resultados unificada
- **Objetivo:** Esquema fijo para outputs (metricas, prompts optimizados, logs).
- **Impacto:** Analisis posterior y automatizacion mas simple.

---

## 14. Datos de Ejemplo

### [M5] Datasets pequenos de ejemplo versionados
- **Objetivo:** 1-2 CSV tiny en `dspy_gepa_poc/datasets/` con tareas simples.
- **Impacto:** Demo sin dependencias externas.

---

## 15. Calidad / Tests

### [M6] Tests minimos de humo
- **Objetivo:** Tests basicos de import y ejecucion de un pipeline minimo.
- **Impacto:** Deteccion temprana de roturas.

---

> **Nota:** Este documento es efimero. Eliminar despues de implementar todas las mejoras y verificar funcionamiento.
