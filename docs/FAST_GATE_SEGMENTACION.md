# Segmentacion del caso Fast Gate: triage_v1 + fast_gate_v1

SSOT de la decision de discontinuar el caso unificado de intake (Triage + Fast
Gate) y reemplazarlo por dos casos independientes y versionados.

## Resumen

El caso unificado existia en dos formas equivalentes:
- DSPy: `Intake_Pipeline` (`dspy_gepa_poc/configs/intake_pipeline.yaml`, modulo
  `pipeline` con dos predictores y routing por gate).
- GEPA standalone: `fast_gate`
  (`gepa_standalone/experiments/configs/fast_gate.yaml`, un solo extractor con
  los 9 campos).

Se reemplazo por:
- `triage_v1`: decide la rama de triage (avanza_fast_gate vs rechazos/devoluciones).
- `fast_gate_v1`: dado un caso que avanza, clasifica P1-P5 y deriva el color.

## Por que se discontinuo el caso unificado

1. **GEPA optimizaba dos funciones a la vez.** La metrica mezclaba aciertos del
   triage con los de P1-P5; el reflection_lm proponia prompts que compromiso
   entre ambos dominios, con secciones largas para cada subproblema que agotaban
   el budget rapido.
2. **La metrica estaba contaminada por el gate estructural.** Los casos que no
   avanzan (REJ) rellenaban `p1..p5 = no_aplica` "gratis", inflando el score
   baseline y reduciendo el margen visible de mejora. Esto enmascaraba el
   rendimiento real del Fast Gate sobre los casos que efectivamente avanzan.
3. **Val=16 era insuficiente para discriminar candidatos** cuando el espacio de
   errores combina 8 campos correlacionados. GEPA aceptaba/rechazaba candidatos
   en base a samples ruidosos del LLM, generando trayectorias inestables.

Ver tambien el patron general en `LECCIONES_APRENDIDAS.md`.

## Cifras del historico (rondas de benchmark, budget 90-150)

Escalas distintas por motor: GEPA standalone reporta en 0-1; DSPy en 0-100.

### GEPA standalone (caso `fast_gate`, budget 90)

| Fecha | Baseline | Optimizado | Test |
|---|---|---|---|
| 2026-05-20 19:38 | 0.612 | 0.622 | 0.708 |
| 2026-05-20 20:26 | 0.664 | 0.703 | 0.958 |
| 2026-05-20 21:26 | 0.643 | 0.701 | 0.924 |
| 2026-05-20 22:21 | 0.685 | 0.703 | 0.861 |
| 2026-05-20 23:15 | 0.693 | 0.768 | 0.958 |
| 2026-05-21 15:03 | 0.555 | 0.523 | 0.833 |
| 2026-05-21 16:37 | 0.641 | 0.781 | 0.917 |
| 2026-05-21 17:12 | 0.617 | 0.688 | 0.917 |

Test medio cuando el prompt cambia: ~0.91 (91%). El prompt cambio en ~83% de
las corridas.

### DSPy pipeline (caso `Intake_Pipeline`, budget 90-150)

| Fecha | Baseline | Optimizado | Test |
|---|---|---|---|
| 2026-05-20 18:54 | 71.56 | 81.01 | 71.02 |
| 2026-05-20 21:14 | 71.46 | 74.48 | 84.54 |
| 2026-05-20 22:14 | 81.11 | 80.10 | 90.28 |
| 2026-05-20 23:07 | 76.98 | 71.32 | 91.39 |
| 2026-05-21 12:50 | 86.46 | 79.48 | 90.28 |
| 2026-05-21 14:57 | 79.27 | 75.42 | 90.28 |
| 2026-05-21 16:33 | 79.27 | 85.00 | 92.22 |
| 2026-05-21 17:09 | 85.73 | 80.21 | 81.94 |

Test medio ~89%. Cifras aceptables, pero no separaban triage de fast_gate, por
lo que no permitian iterar cada subproblema de forma honesta.

Copia local (gitignoreada, no versionada) de los `results.json` / `run.json`
ganadores en `docs/historico/intake_pipeline_pre_segmentacion/`. Las cifras
relevantes son las tablas de arriba; los crudos quedan fuera de git por la
convencion de no trackear outputs de `results/`.

## Datasets segmentados

| Caso | Filas | Split | Notas |
|---|---|---|---|
| `triage_v1` | 42 | 20 / 16 / 6 | Todos los casos; etiquetas del dataset maestro |
| `fast_gate_v1` | 32 | 17 / 11 / 4 | Solo `triage_decision = avanza_fast_gate` |

El split de `fast_gate_v1` conserva las asignaciones originales del maestro (no
se re-estratifico): ya queda balanceado por `clasificacion` (test = 1 de cada
color Verde/Amarillo/Rojo/Negro; train 5/4/4/4). Hash identico entre ambos
motores (`dspy_gepa_poc/datasets/` y `gepa_standalone/experiments/datasets/`).

## Orquestacion en produccion

Los dos casos se componen en cascada:

1. Correr `triage_v1` sobre la ficha.
2. Si `triage_decision == avanza_fast_gate`, correr `fast_gate_v1` sobre la
   misma ficha para obtener `p1..p5` y `clasificacion`.
3. Si la decision es cualquier otra (rechazo/devolucion), no se invoca
   `fast_gate_v1`; los campos P1-P5 quedan `no_aplica` por convencion del Marco.

Cada caso se optimiza por separado con su propio prompt y dataset, evitando los
tres problemas del caso unificado.

## Artefactos

| Caso | DSPy config | GEPA config | Prompt GEPA | Dataset |
|---|---|---|---|---|
| triage_v1 | `dspy_gepa_poc/configs/triage_v1.yaml` | `gepa_standalone/experiments/configs/triage_v1.yaml` | `gepa_standalone/experiments/prompts/triage_v1.json` | `triage_v1.csv` |
| fast_gate_v1 | `dspy_gepa_poc/configs/fast_gate_v1.yaml` | `gepa_standalone/experiments/configs/fast_gate_v1.yaml` | `gepa_standalone/experiments/prompts/fast_gate_v1_only.json` | `fast_gate_v1.csv` |
