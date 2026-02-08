"""
Stats Evolution - Batch Evolution Analysis

Analyzes performance evolution across time periods (batches).
Divides experiments into temporal batches and shows trends.
"""

import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .base import (
    detect_scale,
    load_metrics,
    parse_float,
)


def parse_date(date_str: str) -> datetime | None:
    """Parse date string to datetime."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def format_trend(val_prev: float | None, val_curr: float | None) -> str:
    """Format trend indicator between two values (expects % scale)."""
    if val_prev is None or val_curr is None:
        return "N/A"
    diff = val_curr - val_prev
    if diff > 0.5:
        return "^"  # Improved (using ^ instead of triangle for compatibility)
    if diff < -0.5:
        return "v"  # Worsened
    return "="  # Equal


def calculate_batch_boundaries(data: list[dict], num_batches: int = 3) -> list[datetime]:
    """
    Calculate batch boundaries based on data timestamps.

    Divides data into equal time periods.

    Args:
        data: List of experiment dicts with 'Fecha' field
        num_batches: Number of batches to create

    Returns:
        List of datetime boundaries (num_batches - 1 items)
    """
    dates = []
    for row in data:
        dt = parse_date(row.get("Fecha", ""))
        if dt:
            dates.append(dt)

    if not dates:
        return []

    dates.sort()
    min_date = dates[0]
    max_date = dates[-1]

    if min_date == max_date:
        return []

    total_span = (max_date - min_date).total_seconds()
    batch_span = total_span / num_batches

    boundaries = []
    for i in range(1, num_batches):
        min_date + (datetime.fromtimestamp(min_date.timestamp() + batch_span * i) - min_date)
        boundaries.append(datetime.fromtimestamp(min_date.timestamp() + batch_span * i))

    return boundaries


def assign_batch(dt: datetime, boundaries: list[datetime]) -> int:
    """Assign a datetime to a batch number."""
    for i, boundary in enumerate(boundaries):
        if dt < boundary:
            return i
    return len(boundaries)


def run(
    csv_path: Path = None,
    project: str = None,
    case_filter: str = None,
    num_batches: int = 3,
    cuts: str = None,
):
    """
    Run batch evolution analysis.

    Args:
        csv_path: Explicit path to CSV file
        project: Filter to specific project
        case_filter: Filter to specific case
        num_batches: Number of batches to divide data into
        cuts: Manual cut dates (comma-separated: "2026-01-01,2026-02-01")
    """
    data = load_metrics(csv_path=csv_path, project=project, merge=True)

    if case_filter:
        data = [d for d in data if case_filter.lower() in d.get("Caso", "").lower()]

    if not data:
        print("No hay datos para analizar.")
        return

    # Determine batch boundaries
    if cuts:
        # Manual cuts provided
        boundaries = []
        for cut in cuts.split(","):
            try:
                dt = datetime.strptime(cut.strip(), "%Y-%m-%d")
                boundaries.append(dt)
            except ValueError:
                print(f"Formato de fecha invalido: {cut}")
                return
        boundaries.sort()
    else:
        # Auto-calculate boundaries
        boundaries = calculate_batch_boundaries(data, num_batches)

    if not boundaries:
        print("No se pueden calcular lotes (datos insuficientes o mismo timestamp).")
        return

    # Initialize batch data structures
    batch_data = [defaultdict(lambda: {"opt": [], "rob": []}) for _ in range(len(boundaries) + 1)]

    # Assign data to batches
    for row in data:
        dt = parse_date(row.get("Fecha", ""))
        if not dt:
            continue

        batch_idx = assign_batch(dt, boundaries)
        key = (
            row.get("Caso", "Unknown"),
            row.get("Modelo Tarea", "Unknown"),
            row.get("Modelo Profesor", "Unknown"),
        )

        opt_score = parse_float(row.get("Optimizado Score", "0"))
        rob_score = parse_float(row.get("Robustez Score", "0"))

        batch_data[batch_idx][key]["opt"].append(opt_score)
        batch_data[batch_idx][key]["rob"].append(rob_score)

    # Collect all keys and detect scale per key for normalization
    all_keys = set()
    for bd in batch_data:
        all_keys.update(bd.keys())

    # Detect scale per key using all scores across batches
    key_scales = {}
    for key in all_keys:
        all_scores = []
        for bd in batch_data:
            all_scores.extend(bd[key]["opt"])
            all_scores.extend(bd[key]["rob"])
        key_scales[key] = detect_scale(all_scores) if all_scores else 1.0

    # Print header
    print("=" * 140)
    print("EVOLUCION POR LOTES TEMPORALES")
    print("=" * 140)
    print()
    print("Limites de lotes:")
    for i, boundary in enumerate(boundaries):
        print(f"  Lote {i} -> Lote {i + 1}: {boundary.strftime('%Y-%m-%d %H:%M')}")
    print()

    # Build headers
    [f"L{i}" for i in range(len(boundaries) + 1)]

    # Calculate dynamic column widths from data
    col_case = max(len("Caso"), *(len(k[0]) for k in all_keys)) if all_keys else len("Caso")
    col_models = (
        max(len("Modelos"), *(len(f"{k[1]}/{k[2]}") for k in all_keys))
        if all_keys
        else len("Modelos")
    )
    col_scores = 40

    total_width = col_case + col_models + col_scores * 2 + 9  # 9 for separators
    print("-" * total_width)
    print(
        f"{'Caso':<{col_case}} | {'Modelos':<{col_models}} | "
        f"{'Optimizado %':<{col_scores}} | {'Robustez %':<{col_scores}}"
    )
    print("-" * total_width)

    # Sort and print
    for key in sorted(all_keys, key=lambda x: x[0]):
        case, task, reflect = key
        scale = key_scales[key]
        to_pct = (100.0 / scale) if scale > 0 else 1.0

        # Calculate averages per batch, normalized to %
        opt_avgs = []
        rob_avgs = []
        for bd in batch_data:
            if bd[key]["opt"]:
                opt_avgs.append(statistics.mean(bd[key]["opt"]) * to_pct)
            else:
                opt_avgs.append(None)
            if bd[key]["rob"]:
                rob_avgs.append(statistics.mean(bd[key]["rob"]) * to_pct)
            else:
                rob_avgs.append(None)

        # Format display strings with trends
        def fmt(val):
            return f"{val:.1f}%" if val is not None else "  -  "

        opt_parts = []
        rob_parts = []
        for i in range(len(opt_avgs)):
            opt_parts.append(fmt(opt_avgs[i]))
            rob_parts.append(fmt(rob_avgs[i]))
            if i < len(opt_avgs) - 1:
                opt_parts.append(format_trend(opt_avgs[i], opt_avgs[i + 1]))
                rob_parts.append(format_trend(rob_avgs[i], rob_avgs[i + 1]))

        opt_display = " ".join(opt_parts)
        rob_display = " ".join(rob_parts)

        models_str = f"{task}/{reflect}"

        print(
            f"{case:<{col_case}} | {models_str:<{col_models}} | "
            f"{opt_display:<{col_scores}} | {rob_display:<{col_scores}}"
        )

    print("-" * total_width)
    print("Leyenda: ^ Mejoro | v Empeoro | = Igual | - Sin datos")
    print()


if __name__ == "__main__":
    run()
