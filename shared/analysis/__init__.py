"""
Shared Analysis Utilities

Utilidades de analisis compartidas entre proyectos.
Agnosticas a nombres de directorios.
"""

from .base import (
    load_metrics,
    find_all_metrics_csv,
    get_output_dir,
    parse_float,
    format_float,
    format_currency,
    detect_scale,
    parse_notas,
    extract_budget_from_rows,
)

from . import leaderboard
from . import roi_calculator
from . import stats_evolution
from . import budget_breakdown

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
