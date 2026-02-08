# Mejoras Pendientes: dspy_gepa_poc

> **Tipo:** Documento efimero de implementacion
> **Fecha de revision:** 2026-02-02
> **Estado:** Fases 1-3 mayormente completadas, Fase 4 (modulos compartidos) pendiente
> **Eliminar despues de:** Implementar todas las mejoras

---

## Resumen Ejecutivo

Revision exhaustiva del proyecto `dspy_gepa_poc`. Se identificaron **2 problemas de codigo**, **1 debilidad arquitectonica** y **3 gaps de documentacion**.

**Evaluacion general:** Arquitectura solida con oportunidades de mejora en modularidad y consistencia.

---

## 1. PROBLEMAS DE CODIGO

### 1.1 Prioridad Media

#### [P5] Magic Numbers para Deteccion de Escala

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

### 1.2 Prioridad Baja

#### [P9] DataConfig No Utilizada

**Archivo:** `config.py:115-124`

**Problema:** Clase definida pero nunca usada.

```python
@dataclass
class DataConfig:
    train_size: int = 20
    val_size: int = 10
    random_seed: int = 42
```

**Solucion:** Eliminar clase o integrar en AppConfig.

**Archivos a modificar:**
- `dspy_gepa_poc/config.py:115-124`

---

## 2. DEBILIDADES ARQUITECTONICAS

### [A3] Imports Dentro de Funciones

**Archivo:** `reflexio_declarativa.py:139`

```python
def run(self):
    ...
    from dspy.evaluate import Evaluate  # Import dentro de funcion
```

**Solucion:** Mover al inicio del archivo.

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

### Fase 2: Prioridad Media - PARCIALMENTE COMPLETADA (2026-01-17)
- [ ] [P5] Extraer constantes magic numbers (reflexio_declarativa.py:201,227,252)

### Fase 3: Prioridad Baja - PARCIALMENTE COMPLETADA (2026-02-02)
- [ ] [P9] Eliminar DataConfig no utilizada
- [ ] [A3] Mover imports al inicio (reflexio_declarativa.py:142,191)
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

### 6.1 Estructura Propuesta

```
shared/
├── llm/           # Ya existe - Configuracion LLM unificada
├── validation/    # ConfigValidator base + validacion CSV
├── logging/       # ResultsLogger unificado
├── paths/         # Gestion centralizada de rutas
└── display/       # Formateo terminal
```

### 6.2 Candidatos Identificados

#### [S3] shared/paths/ - PRIORIDAD MEDIA

**Estado:** Solo existe en `gepa_standalone/utils/paths.py` (294 lineas)

**Funcionalidades:**
- Gestion centralizada de rutas del proyecto
- Soporte para paths legados
- Creacion automatica de directorios

**Propuesta:**
- Mover a `shared/paths/` para uso en ambos proyectos
- Reemplazar `AppConfig` paths en `dspy_gepa_poc/config.py`

---

#### [S4] shared/display/ - PRIORIDAD BAJA

**Estado:** Solo existe en `gepa_standalone/utils/display.py` (106 lineas)

**Funcionalidades:**
- Formateo consistente para terminal
- Funciones de presentacion de resultados

**Propuesta:**
- Mover a `shared/display/` para consistencia visual entre proyectos

---

### 6.3 Checklist de Implementacion - Modulos Compartidos

#### Fase 4: Modulos Compartidos - EN PROGRESO
- [ ] [S3] Mover `paths.py` a `shared/paths/`
- [ ] [S4] Mover `display.py` a `shared/display/`
- [ ] Agregar tests unitarios para modulos compartidos

### 6.4 Metricas de Duplicacion

| Categoria | Lineas Duplicadas | Similitud | Estado |
|-----------|-------------------|-----------|--------|
| Data loading | ~70 lineas | 60% | Pendiente |
| Orquestacion | ~200 lineas | 50% | Pendiente |
| **Total pendiente** | **~270 lineas** | - | - |

---

## 7. Verificar nombres de dspy_gepa_poc
    Es POC? o mas...
    Es un optimizador o una plataforma de intención diferente?
    Declarative Self-improving Python

---

## 8. Versionar en GIT

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

## 16. Mejoras Detectadas en Revision de Codigo (2026-02-04)

- **Reflexio Declarativa**
- [x] Mover `from dspy.evaluate import Evaluate` al inicio del archivo.
- [x] Extraer helpers `format_score()` y `to_float_score()` para evitar duplicacion en baseline/optimized/test.
- [x] Parametrizar `num_threads` en `Evaluate` desde YAML (`optimization.num_threads`).

- **Inferencia**
- [x] Usar `predictor_type` desde `config_snapshot.yaml` (no hardcodear `"cot"`).
- [x] Cargar `.env` del proyecto de forma consistente (mismo criterio que `config.py`).
- [x] Error claro si falta `config_snapshot.yaml`.
- [x] Eliminar imports no usados.

- **Schema**
- [x] Permitir `optimization.auto_budget` como alternativa a `optimization.max_metric_calls`.
- [x] Validar CSV con `signature.outputs` cuando `module.type == "dynamic"`.

- **Data Loader**
- [x] Warning si hay filas sin `split`.
- [x] Evitar `.strip()` sobre valores `None`.

- **Config**
- [x] Eliminar `DataConfig` no usada o integrarla.
- [x] Usar `yaml.safe_dump` al guardar `config_snapshot.yaml`.

- **Results Logger**
- [x] Warning si `run_dir` no existe al loggear.

---

## 17. Control de Cache DSPy

**Prioridad:** Alta
**Estado:** Completado (2026-02-07)

Implementado en `shared/llm/config.py` con default `False`. Configurable via YAML (`models.cache`), variable de entorno (`LLM_CACHE`) o codigo. Solo se inyecta en `get_dspy_lm()`, no en `litellm.completion()`. Ver `docs/LECCIONES_APRENDIDAS.md` seccion 5 y `docs/LLM_CONFIG.md` para detalles.

---

> **Nota:** Este documento es efimero. Eliminar despues de implementar todas las mejoras y verificar funcionamiento.
