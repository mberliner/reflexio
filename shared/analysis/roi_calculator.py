"""
ROI Calculator for GEPA Optimizations

Calculates return on investment for using GEPA to optimize prompts,
considering optimization cost vs production savings with cheaper models.

PRICING REFERENCE (Azure OpenAI - January 2026):
-------------------------------------------------
Model           | Input (1M tokens) | Output (1M tokens)
----------------+-------------------+-------------------
gpt-4o          | $2.50             | $10.00
gpt-4o-mini     | $0.15             | $0.60
gpt-4.1-mini    | $0.15             | $0.60
-------------------------------------------------
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from pathlib import Path

from .base import (
    load_metrics,
    parse_float,
    format_currency,
    format_percentage,
    get_output_dir,
    print_table,
    extract_budget_from_rows,
)


@dataclass
class ModelPricing:
    """Pricing per 1M tokens (Azure OpenAI, Global Standard)"""
    name: str
    input_price: float   # USD per 1M tokens
    output_price: float  # USD per 1M tokens

    def cost_per_call(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost of a single call"""
        return (input_tokens * self.input_price / 1_000_000 +
                output_tokens * self.output_price / 1_000_000)


# Default pricing (can be overridden)
DEFAULT_PRICING = {
    "gpt-4o": ModelPricing("GPT-4o", 2.50, 10.00),
    "gpt-4.1-mini": ModelPricing("GPT-4.1-mini", 0.15, 0.60),
    "gpt-4o-mini": ModelPricing("GPT-4o-mini", 0.15, 0.60),
}

# Default token estimates per use case
DEFAULT_TOKEN_ESTIMATES = {
    "Email Urgency": {"input": 300, "output": 50},
    "CV Extraction": {"input": 800, "output": 200},
    "Text-to-SQL": {"input": 400, "output": 150},
    "RAG Optimization": {"input": 600, "output": 300},
    "default": {"input": 500, "output": 150},
}

# Fallback max metric calls (used when Budget column is empty)
FALLBACK_MAX_CALLS = 30

# Fallback validation set size (not available in CSV)
FALLBACK_VAL_SIZE = 5

# Default validation set sizes per use case
DEFAULT_VAL_SIZES = {
    "Email Urgency": 10,
    "CV Extraction": 5,
    "Text-to-SQL": 6,
    "RAG Optimization": 4,
}


def get_model_pricing(model_name: str, pricing: Dict = None) -> ModelPricing:
    """Get pricing for a model, with fallback to defaults."""
    pricing = pricing or DEFAULT_PRICING
    model_key = model_name.lower().replace("azure/", "")
    return pricing.get(model_key, pricing.get("gpt-4o-mini", DEFAULT_PRICING["gpt-4o-mini"]))


def calculate_optimization_cost(
    case_name: str,
    task_model: str,
    reflection_model: str,
    max_calls: int = FALLBACK_MAX_CALLS,
    val_size: int = None,
    token_estimates: Dict = None,
    pricing: Dict = None
) -> Dict:
    """
    Calculate the cost of GEPA optimization.

    Args:
        case_name: Name of the use case
        task_model: Model used for task execution
        reflection_model: Model used for reflection/mutation
        max_calls: Maximum metric calls during optimization
        val_size: Size of validation set (None = auto-lookup by case_name)
        token_estimates: Dict with 'input' and 'output' token counts
        pricing: Custom pricing dict

    Returns:
        Dict with cost breakdown
    """
    if val_size is None:
        val_size = DEFAULT_VAL_SIZES.get(case_name, FALLBACK_VAL_SIZE)

    tokens = token_estimates or DEFAULT_TOKEN_ESTIMATES.get(
        case_name, DEFAULT_TOKEN_ESTIMATES["default"]
    )

    task_pricing = get_model_pricing(task_model, pricing)
    reflection_pricing = get_model_pricing(reflection_model, pricing)

    # Task model: runs on each evaluation (baseline + validations per candidate)
    task_calls = (max_calls + 1) * val_size

    # Reflection model: generates mutations (approx half of metric calls)
    reflection_calls = max_calls // 2

    task_cost = task_calls * task_pricing.cost_per_call(tokens["input"], tokens["output"])

    # Reflection uses more tokens (analyzes errors + generates variants)
    reflection_tokens_in = tokens["input"] * 3
    reflection_tokens_out = tokens["output"] * 2
    reflection_cost = reflection_calls * reflection_pricing.cost_per_call(
        reflection_tokens_in, reflection_tokens_out
    )

    return {
        "task_calls": task_calls,
        "task_cost": task_cost,
        "reflection_calls": reflection_calls,
        "reflection_cost": reflection_cost,
        "total_cost": task_cost + reflection_cost,
        "task_pricing": task_pricing,
        "reflection_pricing": reflection_pricing,
    }


def calculate_production_roi(
    case_name: str,
    optimization_cost: float,
    expensive_model: str,
    cheap_model: str,
    production_calls: int,
    token_estimates: Dict = None,
    pricing: Dict = None
) -> Dict:
    """
    Calculate ROI for a given production volume.

    Args:
        case_name: Name of the use case
        optimization_cost: Total cost of optimization
        expensive_model: Model that would be used without GEPA
        cheap_model: Model used with GEPA optimization
        production_calls: Number of production calls to analyze
        token_estimates: Dict with 'input' and 'output' token counts
        pricing: Custom pricing dict

    Returns:
        Dict with ROI analysis
    """
    tokens = token_estimates or DEFAULT_TOKEN_ESTIMATES.get(
        case_name, DEFAULT_TOKEN_ESTIMATES["default"]
    )

    expensive_pricing = get_model_pricing(expensive_model, pricing)
    cheap_pricing = get_model_pricing(cheap_model, pricing)

    # Cost without GEPA (using expensive model)
    cost_without_gepa = production_calls * expensive_pricing.cost_per_call(
        tokens["input"], tokens["output"]
    )

    # Cost with GEPA (cheap model + optimization cost)
    # Note: optimized prompts are typically longer (+500 tokens approx)
    cost_with_gepa_production = production_calls * cheap_pricing.cost_per_call(
        tokens["input"] + 500, tokens["output"]
    )
    cost_with_gepa_total = cost_with_gepa_production + optimization_cost

    # Savings and ROI
    savings = cost_without_gepa - cost_with_gepa_total
    roi_percentage = (savings / optimization_cost * 100) if optimization_cost > 0 else 0

    # Break-even point
    cost_per_call_diff = (
        expensive_pricing.cost_per_call(tokens["input"], tokens["output"]) -
        cheap_pricing.cost_per_call(tokens["input"], tokens["output"])
    )
    breakeven_calls = int(optimization_cost / cost_per_call_diff) if cost_per_call_diff > 0 else 0

    return {
        "production_calls": production_calls,
        "cost_without_gepa": cost_without_gepa,
        "cost_with_gepa_total": cost_with_gepa_total,
        "cost_with_gepa_production": cost_with_gepa_production,
        "optimization_cost": optimization_cost,
        "savings": savings,
        "roi_percentage": roi_percentage,
        "breakeven_calls": breakeven_calls,
    }


def run(
    csv_path: Path = None,
    project: str = None,
    case_filter: str = None,
    volume: int = 1000
):
    """
    Run ROI analysis on experiment data.

    Args:
        csv_path: Explicit path to CSV file
        project: Filter to specific project
        case_filter: Filter to specific case
        volume: Production volume to analyze (default 1000)
    """
    from collections import defaultdict
    from statistics import mean

    data = load_metrics(csv_path=csv_path, project=project, merge=True)

    if case_filter:
        data = [d for d in data if case_filter.lower() in d.get('Caso', '').lower()]

    if not data:
        print("No hay datos para analizar.")
        return

    print("=" * 100)
    print("ANALISIS DE ROI - OPTIMIZACION GEPA")
    print("=" * 100)
    print()

    # Show pricing table
    print("PRECIOS CONFIGURADOS (por 1M de tokens):")
    print(f"{'Modelo':<15} | {'Input (USD)':>12} | {'Output (USD)':>12}")
    print("-" * 45)
    seen = set()
    for key, price in DEFAULT_PRICING.items():
        if price.name not in seen:
            print(f"{price.name:<15} | {format_currency(price.input_price):>12} | {format_currency(price.output_price):>12}")
            seen.add(price.name)
    print()

    # Group by (caso, task_model, reflection_model)
    groups = defaultdict(list)
    for exp in data:
        gkey = (
            exp.get('Caso', 'Unknown'),
            exp.get('Modelo Tarea', 'gpt-4o-mini'),
            exp.get('Modelo Profesor', 'gpt-4o'),
        )
        groups[gkey].append(exp)

    results = []
    for (case_name, task_model, reflection_model), rows in groups.items():
        # Extract budget from Notas (scan all rows in group)
        max_calls = extract_budget_from_rows(rows, FALLBACK_MAX_CALLS)

        # Calculate average delta (robustez - baseline) to determine if optimization helped
        base_scores = [parse_float(r.get('Baseline Score', '0')) for r in rows]
        rob_scores = [parse_float(r.get('Robustez Score', '0')) for r in rows]
        avg_delta = mean(rob_scores) - mean(base_scores)

        opt_cost = calculate_optimization_cost(
            case_name, task_model, reflection_model, max_calls=max_calls
        )

        # ROI only meaningful when optimization improved results
        if avg_delta <= 0:
            results.append({
                "case_name": case_name,
                "task_model": task_model,
                "reflection_model": reflection_model,
                "max_calls": max_calls,
                "avg_delta": avg_delta,
                "opt_cost": opt_cost,
                "roi_data": None,
                "breakeven": None,
            })
        else:
            roi_data = calculate_production_roi(
                case_name,
                opt_cost['total_cost'],
                reflection_model,
                task_model,
                volume
            )
            results.append({
                "case_name": case_name,
                "task_model": task_model,
                "reflection_model": reflection_model,
                "max_calls": max_calls,
                "avg_delta": avg_delta,
                "opt_cost": opt_cost,
                "roi_data": roi_data,
                "breakeven": roi_data['breakeven_calls'],
            })

    # Sort: profitable first (by breakeven ascending), then N/A
    results.sort(key=lambda x: (x['breakeven'] is None, x['breakeven'] or 0))

    # Print results
    for res in results:
        print(f"\n{'-' * 100}")
        print(f"CASO: {res['case_name']}")
        print(f"{'-' * 100}")
        print(f"Modelo Tarea: {res['task_model']}")
        print(f"Modelo Profesor: {res['reflection_model']}")
        print(f"Budget (max_calls): {res['max_calls']}")
        print()

        opt = res['opt_cost']
        print("COSTO DE OPTIMIZACION:")
        print(f"  - Llamadas Task Model: {opt['task_calls']:,} = {format_currency(opt['task_cost'])}")
        print(f"  - Llamadas Reflection: {opt['reflection_calls']:,} = {format_currency(opt['reflection_cost'])}")
        print(f"  - TOTAL: {format_currency(opt['total_cost'])}")
        print()

        if res['roi_data'] is None:
            print(f"ROI EN PRODUCCION: N/A (delta promedio: {res['avg_delta']:+.2f}, optimizacion no mejoro)")
            print(f"PUNTO DE EQUILIBRIO: N/A")
        else:
            print(f"ROI EN PRODUCCION (volumen: {volume:,} llamadas):")
            roi = res['roi_data']
            print(f"  - Sin GEPA: {format_currency(roi['cost_without_gepa'])}")
            print(f"  - Con GEPA: {format_currency(roi['cost_with_gepa_total'])}")
            print(f"  - Ahorro: {format_currency(roi['savings'])}")
            print(f"  - ROI: {format_percentage(roi['roi_percentage'])}")
            print()
            print(f"PUNTO DE EQUILIBRIO: {res['breakeven']:,} llamadas")

    print()
    print("=" * 100)


if __name__ == "__main__":
    run()
