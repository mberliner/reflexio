"""
Display Utilities

SSOT de formato de salida en terminal para ambos proyectos (gepa_standalone
y dspy_gepa_poc). Prefijos estandar de industria: INFO, WARN, ERROR, OK, DEBUG.

Convenciones:
  - log_info / log_warn / log_error / log_ok / log_debug: lineas de log con
    prefijo de severidad alineado (ancho fijo de 7 chars: "[INFO] ").
  - print_header: encabezado principal del experimento (doble linea ===).
  - print_section: separador secundario por fase (linea simple ---).
  - print_step:    cabecera "STEP N/TOTAL - titulo" para fases canonicas.
  - print_kv:      pares clave/valor alineados a ancho fijo (config legible).
  - print_summary: resumen final parametrico (metricas + meta).
  - print_detailed_results: tabla por caso (solo GEPA standalone).

Ancho estandar: 72 columnas para headers/sections.
"""

from collections.abc import Iterable
from typing import Any

# Ancho estandar de separadores. 72 cols entra en cualquier terminal moderno.
WIDTH = 72

# Prefijos de severidad. Ancho fijo de 7 caracteres incluyendo el espacio
# final, para que los mensajes queden alineados verticalmente.
_PREFIX = {
    "info":  "[INFO] ",
    "warn":  "[WARN] ",
    "error": "[ERROR]",
    "ok":    "[OK]   ",
    "debug": "[DEBUG]",
}


def _emit(level: str, msg: str, indent: int = 0) -> None:
    pad = " " * indent
    print(f"{_PREFIX[level]} {pad}{msg}")


def log_info(msg: str, indent: int = 0) -> None:
    """Log informativo (paso en curso, configuracion, progreso)."""
    _emit("info", msg, indent)


def log_warn(msg: str, indent: int = 0) -> None:
    """Log de advertencia (condicion recuperable, default aplicado)."""
    _emit("warn", msg, indent)


def log_error(msg: str, indent: int = 0) -> None:
    """Log de error (fallo bloqueante, antes de excepcion o exit)."""
    _emit("error", msg, indent)


def log_ok(msg: str, indent: int = 0) -> None:
    """Log de exito (validacion pasada, conexion establecida)."""
    _emit("ok", msg, indent)


def log_debug(msg: str, indent: int = 0) -> None:
    """Log de depuracion (detalle interno, opt-in)."""
    _emit("debug", msg, indent)


def print_header(title: str) -> None:
    """Encabezado principal de experimento (doble linea)."""
    print("\n" + "=" * WIDTH)
    print(title)
    print("=" * WIDTH)


def print_section(title: str) -> None:
    """Separador de fase secundario (linea simple)."""
    print("\n" + "-" * WIDTH)
    print(title)
    print("-" * WIDTH)


def print_step(n: int, total: int, title: str) -> None:
    """
    Cabecera de paso numerado dentro del pipeline.

    Imprime: 'STEP n/total - titulo' bajo un separador simple.
    Uso en las 7 fases canonicas:
      1. Config            5. Baseline
      2. LLM check         6. Optimization
      3. Data              7. Test + Summary
      4. Module/Adapter
    """
    print()
    print("-" * WIDTH)
    print(f"STEP {n}/{total} - {title}")
    print("-" * WIDTH)


def print_kv(label: str, value: Any, indent: int = 2, label_width: int = 22) -> None:
    """
    Imprime un par clave/valor alineado.

    Args:
        label: nombre del campo (ej. 'Task LM').
        value: valor a mostrar.
        indent: espacios de indentacion antes del label.
        label_width: ancho fijo para que valores queden en columna.
    """
    pad = " " * indent
    print(f"{pad}{label:<{label_width}} {value}")


def print_summary(
    metrics: dict[str, float] | None = None,
    config: dict[str, Any] | None = None,
    *,
    # Compat retrocompatible con la firma anterior (kwargs sueltos):
    baseline_avg: float | None = None,
    optimized_avg: float | None = None,
    test_avg: float | None = None,
    task_model: str | None = None,
    reflection_model: str | None = None,
    budget_used: int | None = None,
) -> None:
    """
    Resumen final parametrico.

    Modo nuevo (recomendado):
        print_summary(
            metrics={"Baseline": 0.42, "Optimized": 0.78, "Test": 0.74},
            config={"Task LM": "gpt-5", "Reflection LM": "gpt-5",
                    "Budget used": 150},
        )

    Modo legacy (mantenido para no romper llamadas existentes):
        print_summary(baseline_avg=..., optimized_avg=..., test_avg=...,
                      task_model=..., reflection_model=..., budget_used=...)

    Las metricas <= 1.0 se interpretan como fraccion (0.0-1.0) y se muestran
    como porcentaje. Valores > 1.0 se imprimen tal cual con sufijo '%'.
    """
    # Compat: construir metrics/config a partir de kwargs legacy si vinieron.
    if metrics is None:
        metrics = {}
        if baseline_avg is not None:
            metrics["Baseline"] = baseline_avg
        if optimized_avg is not None:
            metrics["Optimized"] = optimized_avg
        if test_avg is not None:
            metrics["Test"] = test_avg

    if config is None:
        config = {}
        if task_model is not None:
            config["Task LM"] = task_model
        if reflection_model is not None:
            config["Reflection LM"] = reflection_model
        if budget_used is not None:
            config["Budget used"] = f"{budget_used} metric calls"

    print_header("RUN COMPLETED")

    if metrics:
        print("\nMetrics:")
        for label, value in metrics.items():
            print_kv(label, _fmt_score(value))

        # Mejora baseline -> optimized si ambos estan presentes.
        if "Baseline" in metrics and "Optimized" in metrics:
            delta = (metrics["Optimized"] - metrics["Baseline"]) * (
                100 if metrics["Baseline"] <= 1.0 else 1
            )
            print_kv("Improvement", f"{delta:+.1f}%")

    if config:
        print("\nConfiguration:")
        for label, value in config.items():
            print_kv(label, value)

    print("\n" + "=" * WIDTH)


def _fmt_score(value: float) -> str:
    """Formato uniforme para scores (fraccion o porcentaje crudo)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if v <= 1.0:
        return f"{v * 100:.1f}%"
    return f"{v:.1f}%"


def print_detailed_results(eval_batch) -> None:
    """
    Imprime una tabla detallada con los resultados de cada caso de prueba.
    Detecta automaticamente el tipo de tarea basado en las claves de salida.
    """
    if not eval_batch.outputs:
        log_warn("No hay resultados para mostrar.")
        return

    print_section("DETALLE DE RESULTADOS (TEST SET)")

    first_out = eval_batch.outputs[0]

    if "field_comparisons" in first_out:
        # Extractor
        print(f"{'TEXTO (Inicio)':<30} | {'SCORE':<6} | {'ERRORES (Campo: Esp -> Obt)'}")
        print("-" * 100)
        for out, score in _zip(eval_batch.outputs, eval_batch.scores):
            text_preview = _truncate(out.get("text", ""), 27)
            score_str = f"{score * 100:.0f}%"

            errors = []
            for fname, comp in out.get("field_comparisons", {}).items():
                if not comp.get("correct"):
                    exp = str(comp.get("expected"))[:10]
                    got = str(comp.get("extracted"))[:10]
                    errors.append(f"{fname}: {exp}->{got}")

            error_str = ", ".join(errors) if errors else "CORRECTO"
            print(f"{text_preview:<30} | {score_str:<6} | {error_str}")

    elif "question" in first_out:
        # SQL
        print(f"{'PREGUNTA':<40} | {'CORRECTO':<8} | {'SQL GENERADO (Inicio)'}")
        print("-" * 100)
        for out, score in _zip(eval_batch.outputs, eval_batch.scores):
            q_preview = _truncate(out.get("question", ""), 37)
            is_correct = "SI" if score == 1.0 else "NO"
            sql_preview = out.get("predicted", "")[:50]
            print(f"{q_preview:<40} | {is_correct:<8} | {sql_preview}")

    else:
        # Classifier (default)
        print(f"{'TEXTO (Inicio)':<40} | {'PREDICCION':<15} | {'ESPERADO':<15} | {'CORRECTO'}")
        print("-" * 100)
        for out, score in _zip(eval_batch.outputs, eval_batch.scores):
            text_preview = _truncate(out.get("text", ""), 37)
            pred = str(out.get("predicted", ""))
            exp = str(out.get("expected", ""))
            is_correct = "SI" if score == 1.0 else "NO"
            print(f"{text_preview:<40} | {pred:<15} | {exp:<15} | {is_correct}")

    print("-" * 100)


def _truncate(text: str, max_len: int) -> str:
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def _zip(a: Iterable, b: Iterable):
    return zip(a, b, strict=False)
