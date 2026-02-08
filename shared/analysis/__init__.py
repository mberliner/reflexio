"""
Shared Analysis Utilities

Utilidades de analisis compartidas entre proyectos.
Agnosticas a nombres de directorios.
"""

from . import budget_breakdown, leaderboard, roi_calculator, stats_evolution
from .base import (
    detect_scale,
    extract_budget_from_rows,
    find_all_metrics_csv,
    format_currency,
    format_float,
    get_output_dir,
    load_metrics,
    parse_float,
    parse_notas,
)

__all__ = [
    "load_metrics",
    "find_all_metrics_csv",
    "get_output_dir",
    "parse_float",
    "format_float",
    "format_currency",
    "detect_scale",
    "parse_notas",
    "extract_budget_from_rows",
    "leaderboard",
    "roi_calculator",
    "stats_evolution",
    "budget_breakdown",
]
