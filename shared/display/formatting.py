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

import sys
from collections.abc import Iterable
from typing import Any

# Ancho estandar de separadores. 72 cols entra en cualquier terminal moderno.
WIDTH = 72


def configure_stdio() -> None:
    r"""
    Normaliza stdout/stderr para terminales tipo Unix (Git Bash/mintty) en
    Windows. Debe invocarse al inicio de cada entry point, antes de imprimir.

    Tres ajustes, todos seguros multiplataforma:
      - newline='\n': evita el '\r\n' que emite Python nativo en Windows. En
        mintty el '\r' suelto devuelve el cursor a la columna 0 y la linea
        siguiente pisa a la anterior (texto sobreescrito/garabateado).
      - encoding='utf-8': evita el crash cp1252 al imprimir caracteres no-ASCII
        (p.ej. flechas) cuando stdout no es una consola.
      - line_buffering: la salida sale en orden y en tiempo real al
        redirigir/pipear, sin quedar retenida en buffer de bloque.

    Idempotente y silenciosa: si el stream no soporta reconfigure (p.ej.
    capturado por pytest) o lo rechaza, no hace nada.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", newline="\n", line_buffering=True)
        except (ValueError, OSError):
            pass


# Prefijos de severidad. Ancho fijo de 7 caracteres incluyendo el espacio
# final, para que los mensajes queden alineados verticalmente.
_PREFIX = {
    "info": "[INFO] ",
    "warn": "[WARN] ",
    "error": "[ERROR]",
    "ok": "[OK]   ",
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


def format_candidate(candidate: Any) -> str:
    """
    Normaliza un candidato de GEPA a texto legible.

    GEPA representa cada candidato como un dict componente -> texto:
      - gepa_standalone: {'system_prompt': '...'} (un solo componente).
      - dspy_gepa_poc:   {'predictor_a': '...', 'predictor_b': '...'} (uno por
        predictor del modulo).

    Si hay un unico componente se devuelve su texto pelado. Si hay varios, cada
    bloque se rotula con '[componente]' para no mezclar instructions.
    """
    if isinstance(candidate, str):
        return candidate
    if not isinstance(candidate, dict):
        return str(candidate)

    items = [(name, str(text)) for name, text in candidate.items()]
    if len(items) == 1:
        return items[0][1]

    blocks = []
    for name, text in items:
        blocks.append(f"[{name}]\n{text}")
    return "\n\n".join(blocks)


def print_prompt(label: str, candidate: Any) -> None:
    """
    Imprime un prompt completo (sin truncar) bajo un encabezado de seccion.

    SSOT para mostrar PROMPT INICIAL / PROMPT OPTIMIZADO en ambos motores.
    'candidate' puede ser un string o un dict componente -> texto.
    """
    print_section(label)
    print(format_candidate(candidate))


def print_gepa_evolution(
    candidates: list,
    val_scores: list,
    *,
    best_idx: int | None = None,
    discovery_eval_counts: list | None = None,
) -> None:
    """
    Imprime la cadena de mejoras de GEPA: el prompt completo cada vez que un
    candidato supera el mejor score de validacion visto hasta el momento.

    Solo se vuelcan los candidatos que mejoraron (incluida la semilla, idx 0),
    no todos los explorados. Cada bloque muestra indice, score de validacion,
    metric calls al momento del descubrimiento (si esta disponible) y el prompt
    completo.

    Args:
        candidates: lista de candidatos (dict componente -> texto) en orden de
            descubrimiento.
        val_scores: score agregado de validacion por candidato (paralelo a
            candidates).
        best_idx: indice del mejor candidato final (se rotula 'mejor final').
        discovery_eval_counts: metric calls acumuladas al descubrir cada
            candidato (paralelo a candidates), opcional.
    """
    if not candidates or not val_scores:
        log_warn("No hay candidatos de GEPA para mostrar la evolucion.")
        return

    print_section("EVOLUCION GEPA (mejor de cada etapa)")

    running_max = float("-inf")
    shown = 0
    n = min(len(candidates), len(val_scores))
    for i in range(n):
        score = val_scores[i]
        is_seed = i == 0
        is_improvement = score > running_max
        if not (is_seed or is_improvement):
            continue

        if is_seed:
            tag = "semilla"
        elif best_idx is not None and i == best_idx:
            tag = "nuevo mejor / mejor final"
        else:
            tag = "nuevo mejor"

        evals = ""
        if discovery_eval_counts and i < len(discovery_eval_counts):
            evals = f", metric calls: {discovery_eval_counts[i]}"

        print(f"\n[etapa {i}] val={_fmt_score(score)} ({tag}{evals})")
        print(format_candidate(candidates[i]))

        running_max = max(running_max, score)
        shown += 1

    print_kv("Etapas con mejora", f"{shown} de {n} candidatos explorados", indent=0)
    print("-" * WIDTH)


def print_gepa_search_stats(
    *,
    num_candidates: int,
    total_metric_calls: int,
    best_idx: int | None = None,
    best_score: float | None = None,
    num_full_val_evals: int | None = None,
) -> None:
    """
    Bloque de estadisticas de la busqueda de GEPA, comun a ambos motores.

    Resume cuanto exploro GEPA (candidatos, metric calls, evaluaciones completas
    de validacion) y cual fue el mejor candidato.
    """
    print_section("ESTADISTICAS DE BUSQUEDA GEPA")
    print_kv("Candidatos explorados", num_candidates)
    print_kv("Metric calls totales", total_metric_calls)
    if num_full_val_evals is not None:
        print_kv("Evals completas de val", num_full_val_evals)
    if best_idx is not None:
        print_kv("Mejor candidato (idx)", best_idx)
    if best_score is not None:
        print_kv("Mejor score de val", _fmt_score(best_score))
    print("-" * WIDTH)


def _truncate(text: str, max_len: int) -> str:
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def _zip(a: Iterable, b: Iterable):
    return zip(a, b, strict=False)
