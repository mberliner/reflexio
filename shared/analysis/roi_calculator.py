"""
ROI Calculator for GEPA Optimizations

Calculates return on investment for using GEPA to optimize prompts,
considering optimization cost vs production savings with cheaper models.

PRICING REFERENCE (Azure OpenAI Global Standard, equivalente a precios de
lista de OpenAI - May 2026):
-------------------------------------------------
Model             | Input (1M tokens) | Output (1M tokens)
------------------+-------------------+-------------------
gpt-4o            | $2.50             | $10.00
gpt-4o-mini       | $0.15             | $0.60
gpt-4.1-mini      | $0.15             | $0.60
gpt-4.1-nano      | $0.10             | $0.40
gpt-5             | $1.25             | $10.00
gpt-5-mini        | $0.25             | $2.00
gpt-5.5           | $5.00             | $30.00
gpt-5.4           | $2.50             | $15.00
gpt-5.4-mini      | $0.75             | $4.50
-------------------------------------------------
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from .base import (
    extract_budget_from_rows,
    format_currency,
    format_percentage,
    load_metrics,
    parse_float,
    parse_real_cost,
)

logger = logging.getLogger(__name__)


@dataclass
class ModelPricing:
    """Pricing per 1M tokens (Azure OpenAI, Global Standard)"""

    name: str
    input_price: float  # USD per 1M tokens
    output_price: float  # USD per 1M tokens

    def cost_per_call(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost of a single call"""
        return (
            input_tokens * self.input_price / 1_000_000
            + output_tokens * self.output_price / 1_000_000
        )


# Default pricing (can be overridden)
# Azure OpenAI Global Standard, equivalente a precios de lista de OpenAI (May 2026).
DEFAULT_PRICING = {
    "gpt-4o": ModelPricing("GPT-4o", 2.50, 10.00),
    "gpt-4.1-mini": ModelPricing("GPT-4.1-mini", 0.15, 0.60),
    "gpt-4.1-nano": ModelPricing("GPT-4.1-nano", 0.10, 0.40),
    "gpt-4o-mini": ModelPricing("GPT-4o-mini", 0.15, 0.60),
    "gpt-5": ModelPricing("GPT-5", 1.25, 10.00),
    "gpt-5-mini": ModelPricing("GPT-5-mini", 0.25, 2.00),
    "gpt-5.5": ModelPricing("GPT-5.5", 5.00, 30.00),
    "gpt-5.4": ModelPricing("GPT-5.4", 2.50, 15.00),
    "gpt-5.4-mini": ModelPricing("GPT-5.4-mini", 0.75, 4.50),
}

# Rough token estimates per use-case family, keyed by a substring that appears
# in the real case names ("CV Extraction v3 (...)" matches "CV Extraction").
# Only the ESTIMATE path uses these (legacy rows without measured cost); new
# runs report the real cost, so these are best-effort fallbacks, not precise.
# CV families carry long inputs (full CV text), hence the higher figures.
DEFAULT_TOKEN_ESTIMATES = {
    "CV Profile": {"input": 3000, "output": 250},
    "CV Triage": {"input": 3500, "output": 200},
    "CV Extraction": {"input": 2500, "output": 250},
    "Order Extraction": {"input": 600, "output": 200},
    "Email Urgency": {"input": 300, "output": 50},
    "Sentiment": {"input": 300, "output": 50},
    "Text-to-SQL": {"input": 400, "output": 150},
    "RAG": {"input": 600, "output": 300},
    "Fast Gate": {"input": 300, "output": 40},
    "Triage": {"input": 400, "output": 80},
    "default": {"input": 500, "output": 150},
}

# Overhead de tokens que el prompt optimizado por GEPA agrega al input en
# produccion (respecto al prompt inicial). Medido empiricamente sobre 272 pares
# initial_prompt/final_prompt de runs reales (delta de tokens ~= chars/4):
# las familias CV crecen ~1100, RAG ~1080, Text-to-SQL ~720, Email ~380. El
# +500 fijo anterior subestimaba a la mitad en CV y sobreestimaba en Email.
# Mismo matching por subcadena (longest-first) que DEFAULT_TOKEN_ESTIMATES.
DEFAULT_PROMPT_OVERHEAD = {
    "CV Profile": 1100,
    "CV Triage": 1150,
    "CV Extraction": 1120,
    "Order Extraction": 600,
    "Email Urgency": 380,
    "Sentiment": 380,
    "Text-to-SQL": 720,
    "RAG": 1080,
    "Fast Gate": 975,
    "Triage": 1150,
    "default": 780,  # mediana global del delta medido
}

# Fallback max metric calls (used when Budget column is empty)
FALLBACK_MAX_CALLS = 30

# Fallback validation set size (not available in CSV)
FALLBACK_VAL_SIZE = 5

# Validation set sizes per use-case family (same substring matching as above).
DEFAULT_VAL_SIZES = {
    "CV Profile": 5,
    "CV Triage": 5,
    "CV Extraction": 5,
    "Order Extraction": 6,
    "Email Urgency": 10,
    "Sentiment": 8,
    "Text-to-SQL": 6,
    "RAG": 4,
    "Fast Gate": 6,
    "Triage": 6,
}


def normalize_model(model_name: str) -> str:
    """Normalize a model name for comparison (drops the ``azure/`` prefix)."""
    return (model_name or "").lower().replace("azure/", "")


def lookup_by_case(case_name: str, table: dict, default):
    """Match a case name to a table entry by substring (longest key first).

    Real case names carry suffixes ("CV Extraction v3 (DSPy...)"), so exact
    lookup misses. We scan keys longest-first so a specific family like
    "CV Triage" wins over the generic "Triage". Returns the table's "default"
    entry when present, else the provided default.
    """
    name = (case_name or "").lower()
    for key in sorted((k for k in table if k != "default"), key=len, reverse=True):
        if key.lower() in name:
            return table[key]
    return table.get("default", default)


def get_model_pricing(model_name: str, pricing: dict = None) -> ModelPricing:
    """Get pricing for a model, warning (not silently guessing) when unknown.

    An unknown model falls back to gpt-4o-mini only to keep the calculation
    running, but emits a warning: that fallback is the cheapest entry, so a
    silent miss would understate cost. Add the model to DEFAULT_PRICING to fix.
    """
    pricing = pricing or DEFAULT_PRICING
    model_key = model_name.lower().replace("azure/", "")
    if model_key in pricing:
        return pricing[model_key]
    logger.warning(
        "Modelo sin precio configurado: '%s'. Usando gpt-4o-mini como fallback "
        "(el mas barato): el costo puede quedar subestimado. Agregalo a DEFAULT_PRICING.",
        model_name,
    )
    return pricing.get("gpt-4o-mini", DEFAULT_PRICING["gpt-4o-mini"])


def cost_from_usage(
    usage: dict,
    task_model: str,
    reflection_model: str,
    pricing: dict = None,
) -> float:
    """Compute real USD cost from a measured usage snapshot.

    Uses the same pricing table as the estimated path, but applied to the
    real token counts captured by ``shared.llm.usage.UsageTracker`` instead
    of fixed per-case estimates.

    Args:
        usage: Snapshot with ``task`` and ``reflection`` buckets, each holding
            ``prompt_tokens`` and ``completion_tokens``.
        task_model: Model used for the task bucket.
        reflection_model: Model used for the reflection bucket.
        pricing: Custom pricing dict (defaults to DEFAULT_PRICING).

    Returns:
        Total cost in USD.
    """
    task_pricing = get_model_pricing(task_model, pricing)
    reflection_pricing = get_model_pricing(reflection_model, pricing)

    task = usage.get("task", {})
    reflection = usage.get("reflection", {})

    task_cost = task_pricing.cost_per_call(
        task.get("prompt_tokens", 0), task.get("completion_tokens", 0)
    )
    reflection_cost = reflection_pricing.cost_per_call(
        reflection.get("prompt_tokens", 0), reflection.get("completion_tokens", 0)
    )
    return task_cost + reflection_cost


def calculate_optimization_cost(
    case_name: str,
    task_model: str,
    reflection_model: str,
    max_calls: int = FALLBACK_MAX_CALLS,
    val_size: int = None,
    token_estimates: dict = None,
    pricing: dict = None,
) -> dict:
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
        val_size = lookup_by_case(case_name, DEFAULT_VAL_SIZES, FALLBACK_VAL_SIZE)

    tokens = token_estimates or lookup_by_case(
        case_name, DEFAULT_TOKEN_ESTIMATES, DEFAULT_TOKEN_ESTIMATES["default"]
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
    token_estimates: dict = None,
    pricing: dict = None,
) -> dict | None:
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
        Dict with ROI analysis, or ``None`` when there is no model
        substitution (``expensive_model`` and ``cheap_model`` are the same):
        without a cheaper production model there are no token savings to
        measure, so the ROI by cost does not apply.
    """
    # Sin sustitucion de modelo (Tarea == Profesor) no hay ahorro de tokens que
    # medir: el unico "ahorro" seria el sobrecosto del prompt optimizado, un
    # artefacto negativo sin sentido de negocio. Es el criterio compartido por
    # el comando ROI y el leaderboard.
    if normalize_model(expensive_model) == normalize_model(cheap_model):
        return None

    tokens = token_estimates or lookup_by_case(
        case_name, DEFAULT_TOKEN_ESTIMATES, DEFAULT_TOKEN_ESTIMATES["default"]
    )

    # Overhead real del prompt optimizado (por familia), no una constante fija.
    prompt_overhead = lookup_by_case(
        case_name, DEFAULT_PROMPT_OVERHEAD, DEFAULT_PROMPT_OVERHEAD["default"]
    )

    expensive_pricing = get_model_pricing(expensive_model, pricing)
    cheap_pricing = get_model_pricing(cheap_model, pricing)

    # Cost without GEPA (using expensive model)
    cost_without_gepa = production_calls * expensive_pricing.cost_per_call(
        tokens["input"], tokens["output"]
    )

    # Cost with GEPA: el prompt optimizado agrega prompt_overhead tokens al input.
    cost_per_call_with_gepa = cheap_pricing.cost_per_call(
        tokens["input"] + prompt_overhead, tokens["output"]
    )
    cost_with_gepa_production = production_calls * cost_per_call_with_gepa
    cost_with_gepa_total = cost_with_gepa_production + optimization_cost

    # Savings and ROI
    savings = cost_without_gepa - cost_with_gepa_total
    roi_percentage = (savings / optimization_cost * 100) if optimization_cost > 0 else 0

    # Break-even: usa el mismo costo por llamada con overhead que el ahorro, para
    # que ambos sean coherentes (antes el break-even ignoraba el prompt mas largo).
    cost_per_call_diff = (
        expensive_pricing.cost_per_call(tokens["input"], tokens["output"]) - cost_per_call_with_gepa
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


def run(csv_path: Path = None, project: str = None, case_filter: str = None, volume: int = 1000):
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
        data = [d for d in data if case_filter.lower() in d.get("Caso", "").lower()]

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
    for _key, price in DEFAULT_PRICING.items():
        if price.name not in seen:
            print(
                f"{price.name:<15} | {format_currency(price.input_price):>12} | "
                f"{format_currency(price.output_price):>12}"
            )
            seen.add(price.name)
    print()

    # Group by (caso, task_model, reflection_model)
    groups = defaultdict(list)
    for exp in data:
        gkey = (
            exp.get("Caso", "Unknown"),
            exp.get("Modelo Tarea", "gpt-4o-mini"),
            exp.get("Modelo Profesor", "gpt-4o"),
        )
        groups[gkey].append(exp)

    results = []
    skipped_same_model = 0
    for (case_name, task_model, reflection_model), rows in groups.items():
        # El ROI mide ahorro por sustitucion de modelo (Profesor caro en
        # produccion -> Tarea barato gracias al prompt optimizado). Si Tarea y
        # Profesor son el mismo modelo no hay sustitucion posible y la funcion
        # de ROI devuelve None; aqui los omitimos del listado con un aviso.
        if normalize_model(task_model) == normalize_model(reflection_model):
            skipped_same_model += 1
            continue
        # Extract budget from Notas (scan all rows in group)
        max_calls = extract_budget_from_rows(rows, FALLBACK_MAX_CALLS)

        # Calculate average delta (robustez - baseline) to determine if optimization helped
        base_scores = [parse_float(r.get("Baseline Score", "0")) for r in rows]
        rob_scores = [parse_float(r.get("Robustez Score", "0")) for r in rows]
        avg_delta = mean(rob_scores) - mean(base_scores)

        # Estimated breakdown (kept for display/fallback)
        opt_cost = calculate_optimization_cost(
            case_name, task_model, reflection_model, max_calls=max_calls
        )

        # Prefer the measured optimization cost: average real cost per run in
        # the group. Fall back to the estimate for legacy rows without it.
        real_costs = [c for c in (parse_real_cost(r) for r in rows) if c is not None]
        if real_costs:
            opt_total = mean(real_costs)
            cost_source = "real"
        else:
            opt_total = opt_cost["total_cost"]
            cost_source = "estimado"

        common = {
            "case_name": case_name,
            "task_model": task_model,
            "reflection_model": reflection_model,
            "max_calls": max_calls,
            "avg_delta": avg_delta,
            "opt_cost": opt_cost,
            "opt_total": opt_total,
            "cost_source": cost_source,
            "n_real": len(real_costs),
            "n_runs": len(rows),
        }

        # ROI only meaningful when optimization improved results
        if avg_delta <= 0:
            results.append({**common, "roi_data": None, "breakeven": None})
        else:
            roi_data = calculate_production_roi(
                case_name, opt_total, reflection_model, task_model, volume
            )
            breakeven = roi_data["breakeven_calls"] if roi_data else None
            results.append({**common, "roi_data": roi_data, "breakeven": breakeven})

    if skipped_same_model:
        print(
            f"[NOTA] Omitidos {skipped_same_model} grupo(s) con Modelo Tarea == "
            "Modelo Profesor: sin sustitucion de modelo no hay ahorro de tokens "
            "que medir (el ROI por costo no aplica a ese escenario).\n"
        )

    if not results:
        print(
            "No hay grupos con sustitucion de modelo (Tarea distinto de Profesor) "
            "para calcular ROI."
        )
        print("=" * 100)
        return

    # Sort: profitable first (by breakeven ascending), then N/A
    results.sort(key=lambda x: (x["breakeven"] is None, x["breakeven"] or 0))

    # Print results
    for res in results:
        print(f"\n{'-' * 100}")
        print(f"CASO: {res['case_name']}")
        print(f"{'-' * 100}")
        print(f"Modelo Tarea: {res['task_model']}")
        print(f"Modelo Profesor: {res['reflection_model']}")
        print(f"Budget (max_calls): {res['max_calls']}")
        print()

        if res["cost_source"] == "real":
            print(
                f"COSTO DE OPTIMIZACION (real, medido - promedio de "
                f"{res['n_real']}/{res['n_runs']} runs):"
            )
            print(f"  - TOTAL: {format_currency(res['opt_total'])}")
        else:
            opt = res["opt_cost"]
            print("COSTO DE OPTIMIZACION (estimado):")
            print(
                f"  - Llamadas Task Model: {opt['task_calls']:,} = "
                f"{format_currency(opt['task_cost'])}"
            )
            print(
                f"  - Llamadas Reflection: {opt['reflection_calls']:,} = "
                f"{format_currency(opt['reflection_cost'])}"
            )
            print(f"  - TOTAL: {format_currency(opt['total_cost'])}")
        print()

        if res["roi_data"] is None:
            print(
                f"ROI EN PRODUCCION: N/A "
                f"(delta promedio: {res['avg_delta']:+.2f}, optimizacion no mejoro)"
            )
            print("PUNTO DE EQUILIBRIO: N/A")
        else:
            print(f"ROI EN PRODUCCION (volumen: {volume:,} llamadas):")
            roi = res["roi_data"]
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
