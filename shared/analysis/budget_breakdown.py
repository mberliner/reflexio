"""
Budget Breakdown - Cost analysis per case and model combination.

Calculates estimated cost spent on each demo case based on:
- Number of experiments run
- Max metric calls per case
- Models used
"""

from collections import defaultdict
from pathlib import Path

from .base import (
    extract_budget_from_rows,
    format_currency,
    load_metrics,
)
from .roi_calculator import (
    FALLBACK_MAX_CALLS,
    calculate_optimization_cost,
)


def run(csv_path: Path = None, project: str = None, case_filter: str = None, sort_by: str = "cost"):
    """
    Run budget breakdown analysis.

    Args:
        csv_path: Explicit path to CSV file
        project: Filter to specific project
        case_filter: Filter to specific case
        sort_by: Sort results by 'cost', 'count', or 'name'
    """
    data = load_metrics(csv_path=csv_path, project=project, merge=True)

    if case_filter:
        data = [d for d in data if case_filter.lower() in d.get("Caso", "").lower()]

    if not data:
        print("No hay datos para analizar.")
        return

    # Group by case
    case_stats = defaultdict(
        lambda: {
            "count": 0,
            "total_cost": 0.0,
            "by_model_combo": defaultdict(lambda: {"count": 0, "cost": 0.0}),
            "sources": set(),
        }
    )

    for exp in data:
        case_name = exp.get("Caso", "Unknown")
        task_model = exp.get("Modelo Tarea", "gpt-4o-mini")
        reflection_model = exp.get("Modelo Profesor", "gpt-4o")
        source = exp.get("source", "unknown")

        # Extract budget (dedicated column, fallback to Notas)
        max_calls = extract_budget_from_rows([exp], FALLBACK_MAX_CALLS)

        # Calculate cost using SSOT formula from roi_calculator
        cost_data = calculate_optimization_cost(
            case_name, task_model, reflection_model, max_calls=max_calls
        )
        cost = cost_data["total_cost"]

        # Accumulate
        case_stats[case_name]["count"] += 1
        case_stats[case_name]["total_cost"] += cost
        case_stats[case_name]["sources"].add(source)

        model_combo = f"{task_model} + {reflection_model}"
        case_stats[case_name]["by_model_combo"][model_combo]["count"] += 1
        case_stats[case_name]["by_model_combo"][model_combo]["cost"] += cost

    # Print results
    print("=" * 100)
    print("PRESUPUESTO GASTADO POR CASO")
    print("=" * 100)
    print()

    total_all_cases = 0.0
    total_experiments = 0

    # Sort cases
    if sort_by == "cost":
        sorted_cases = sorted(case_stats.items(), key=lambda x: x[1]["total_cost"], reverse=True)
    elif sort_by == "count":
        sorted_cases = sorted(case_stats.items(), key=lambda x: x[1]["count"], reverse=True)
    else:
        sorted_cases = sorted(case_stats.items(), key=lambda x: x[0])

    for case_name, stats in sorted_cases:
        sources_str = ", ".join(sorted(stats["sources"]))

        print(f"\n{'-' * 100}")
        print(f"CASO: {case_name}")
        print(f"Fuente(s): {sources_str}")
        print(f"{'-' * 100}")
        print(f"Total Experimentos: {stats['count']}")
        print(f"Costo Total: {format_currency(stats['total_cost'])}")
        print(f"Costo Promedio/Exp: {format_currency(stats['total_cost'] / stats['count'])}")
        print()

        print("Desglose por Combinacion de Modelos:")
        print(f"{'Combinacion':<45} {'Exps':>8} {'Costo':>15} {'%':>8}")
        print(f"{'-' * 45} {'-' * 8} {'-' * 15} {'-' * 8}")

        for combo, combo_data in sorted(
            stats["by_model_combo"].items(), key=lambda x: x[1]["cost"], reverse=True
        ):
            percentage = (
                (combo_data["cost"] / stats["total_cost"] * 100) if stats["total_cost"] > 0 else 0
            )
            print(
                f"{combo:<45} {combo_data['count']:>8} "
                f"{format_currency(combo_data['cost']):>15} {percentage:>7.1f}%"
            )

        total_all_cases += stats["total_cost"]
        total_experiments += stats["count"]

    # Global summary
    print()
    print("=" * 100)
    print("RESUMEN GLOBAL")
    print("=" * 100)
    print(f"Total Experimentos: {total_experiments}")
    print(f"Total Presupuesto: {format_currency(total_all_cases)}")
    if total_experiments > 0:
        print(f"Costo Promedio/Exp: {format_currency(total_all_cases / total_experiments)}")
    print()

    # Ranking table
    print("RANKING DE CASOS POR COSTO TOTAL:")
    print(f"{'Caso':<30} {'Exps':>10} {'Costo Total':>15} {'% del Total':>12}")
    print(f"{'-' * 30} {'-' * 10} {'-' * 15} {'-' * 12}")

    for case_name, stats in sorted(
        case_stats.items(), key=lambda x: x[1]["total_cost"], reverse=True
    ):
        percentage = (stats["total_cost"] / total_all_cases * 100) if total_all_cases > 0 else 0
        print(
            f"{case_name:<30} {stats['count']:>10} "
            f"{format_currency(stats['total_cost']):>15} {percentage:>11.1f}%"
        )

    print()
    print("=" * 100)
    print("NOTAS:")
    print("  - Precios basados en Azure OpenAI")
    print("  - Budget (max_calls) extraido de columna Budget del CSV")
    print(f"  - Fallback: {FALLBACK_MAX_CALLS} cuando no hay Budget disponible")
    print("  - Task calls = (max_calls + 1) * val_size")
    print("  - Reflection calls = 0.5x max_calls")
    print("=" * 100)


if __name__ == "__main__":
    run()
