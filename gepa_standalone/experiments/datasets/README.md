# Datasets

Formato CSV esperado:
- Columna `split`: train/val/test
- Columna `text`: entrada del modelo
- Columnas adicionales: salidas esperadas

Datasets disponibles:
- `triage_v1.csv`: fichas de intent con la decisión de triage (42 casos). Ver `docs/FAST_GATE_SEGMENTACION.md`.
- `fast_gate_v1.csv`: subconjunto de 32 casos `avanza_fast_gate` con derivaciones P1-P5 y clasificación de color.
