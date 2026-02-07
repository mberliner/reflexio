"""
Base utilities for analysis modules.

Provides common data loading and formatting functions.
Agnostic to project directory names.
"""

import csv
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterator
from datetime import datetime

METRICS_FILENAME = "metricas_optimizacion.csv"
RESULTS_SUBPATH = Path("results") / "experiments" / METRICS_FILENAME


def get_shared_root() -> Path:
    """Returns the root directory containing shared/."""
    return Path(__file__).parent.parent.parent


def find_all_metrics_csv(search_root: Path = None) -> List[Path]:
    """
    Find all metrics CSV files in sibling projects of shared/.

    Searches for: {project}/results/experiments/metricas_optimizacion.csv

    Args:
        search_root: Root directory to search. Defaults to parent of shared/.

    Returns:
        List of paths to found CSV files, sorted alphabetically by project name.
    """
    if search_root is None:
        search_root = get_shared_root()

    found = []
    for project_dir in search_root.iterdir():
        if project_dir.is_dir() and project_dir.name not in ("shared", "docs", ".git", "__pycache__"):
            candidate = project_dir / RESULTS_SUBPATH
            if candidate.exists():
                found.append(candidate)

    return sorted(found, key=lambda p: p.parent.parent.parent.name)


def get_output_dir(project_filter: str = None) -> Path:
    """
    Get output directory for analysis results.

    Args:
        project_filter: If specified, use that project's results dir.
                       Otherwise use shared/analysis/output/

    Returns:
        Path to output directory (created if needed).
    """
    if project_filter:
        search_root = get_shared_root()
        for project_dir in search_root.iterdir():
            if project_dir.is_dir() and project_filter.lower() in project_dir.name.lower():
                output_dir = project_dir / "results"
                output_dir.mkdir(parents=True, exist_ok=True)
                return output_dir

    # Default: shared/analysis/output/
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def load_metrics(
    csv_path: Optional[Path] = None,
    project: Optional[str] = None,
    merge: bool = True
) -> List[Dict[str, Any]]:
    """
    Load metrics from CSV file(s).

    Args:
        csv_path: Explicit path to CSV. If provided, uses only this file.
        project: Filter to specific project (partial name match).
        merge: If True and multiple CSVs found, combines them.
               If False and multiple found, raises error.

    Returns:
        List of dicts with metrics data. Each dict has a 'source' key
        indicating which project it came from.

    Raises:
        FileNotFoundError: If no CSV files found.
        ValueError: If multiple CSVs found and merge=False.
    """
    # Case 1: Explicit path provided
    if csv_path and csv_path.exists():
        return _load_single_csv(csv_path)

    # Case 2: Find CSVs automatically
    found = find_all_metrics_csv()

    # Filter by project name if specified
    if project:
        found = [p for p in found if project.lower() in p.parent.parent.parent.name.lower()]

    if not found:
        raise FileNotFoundError(
            f"No se encontro {METRICS_FILENAME}. "
            "Usa --csv para especificar ruta o verifica que existan resultados."
        )

    if len(found) == 1:
        return _load_single_csv(found[0])

    # Multiple CSVs found
    print(f"CSVs encontrados: {len(found)}")
    for p in found:
        print(f"  - {p.parent.parent.parent.name}: {p}")

    if merge:
        print("Combinando para analisis conjunto...\n")
        all_data = []
        for p in found:
            all_data.extend(_load_single_csv(p))
        return all_data
    else:
        raise ValueError(
            f"Multiples CSVs encontrados ({len(found)}). "
            "Usa --csv para especificar o --project para filtrar."
        )


def _load_single_csv(csv_path: Path) -> List[Dict[str, Any]]:
    """Load a single CSV file and add source metadata."""
    project_name = csv_path.parent.parent.parent.name
    data = []

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            # Skip invalid rows
            if not row.get('Run ID') or row.get('Run ID') == 'PROMEDIO':
                continue
            if not row.get('Caso'):
                continue

            row['source'] = project_name
            data.append(row)

    return data


def parse_float(value: str) -> float:
    """Convert European decimal format (comma) to float."""
    if not value:
        return 0.0
    try:
        return float(value.replace(',', '.'))
    except (ValueError, TypeError):
        return 0.0


def format_float(value: float, decimals: int = 4) -> str:
    """Format float to European decimal string (comma)."""
    return f"{value:.{decimals}f}".replace('.', ',')


def format_currency(amount: float) -> str:
    """Format amount as USD currency."""
    return f"${amount:,.2f}"


def format_percentage(value: float) -> str:
    """Format value as percentage."""
    return f"{value:,.1f}%"


def get_timestamp() -> str:
    """Get current timestamp string."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def print_table(headers: List[str], rows: List[List[str]], col_widths: List[int] = None):
    """Print a formatted table to console."""
    if col_widths is None:
        # Auto-calculate widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))

    separator = "+" + "+".join(["-" * (w + 2) for w in col_widths]) + "+"

    print(separator)
    header_str = "|"
    for h, w in zip(headers, col_widths):
        header_str += f" {h:<{w}} |"
    print(header_str)
    print(separator)

    for row in rows:
        row_str = "|"
        for item, w in zip(row, col_widths):
            row_str += f" {str(item):<{w}} |"
        print(row_str)

    print(separator)


def detect_scale(scores: List[float]) -> float:
    """Detect if scores are on 0-1 or 0-100 scale."""
    if any(s > 1.0 for s in scores):
        return 100.0
    return 1.0


def parse_notas(notas: str) -> Dict[str, Any]:
    """
    Parse the Notas column from CSV.

    Handles formats like:
      "Budget: 30, Strategy: medium, Few-Shot: Yes (k=3)"
      "Budget: 30, Strategy: medium, Few-Shot: No"
      "" (empty)

    Returns:
        Dict with {budget, strategy, few_shot, few_shot_k}. Missing values are None.
    """
    result: Dict[str, Any] = {
        "budget": None,
        "strategy": None,
        "few_shot": None,
        "few_shot_k": None,
    }
    if not notas or not notas.strip():
        return result

    budget_match = re.search(r'Budget:\s*(\d+)', notas)
    if budget_match:
        result["budget"] = int(budget_match.group(1))

    strategy_match = re.search(r'Strategy:\s*(\w+)', notas)
    if strategy_match:
        result["strategy"] = strategy_match.group(1)

    fewshot_match = re.search(r'Few-Shot:\s*(Yes|No)', notas, re.IGNORECASE)
    if fewshot_match:
        result["few_shot"] = fewshot_match.group(1).lower() == "yes"

    k_match = re.search(r'k=(\d+)', notas)
    if k_match:
        result["few_shot_k"] = int(k_match.group(1))

    return result


def extract_budget_from_rows(rows: List[Dict[str, Any]], fallback: int) -> int:
    """
    Extract Budget value from a group of rows.

    Checks the dedicated 'Budget' column first. Falls back to parsing
    the 'Notas' column for backwards compatibility with pre-migration data.

    Args:
        rows: List of CSV row dicts from a group
        fallback: Value to return if no Budget found in any row

    Returns:
        The extracted budget or the fallback value.
    """
    for row in rows:
        # Prefer dedicated Budget column
        budget_col = row.get('Budget', '')
        if budget_col and budget_col.strip():
            try:
                return int(budget_col.strip())
            except (ValueError, TypeError):
                pass

        # Fallback: parse from Notas (backwards compat)
        parsed = parse_notas(row.get('Notas', ''))
        if parsed["budget"] is not None:
            return parsed["budget"]
    return fallback


def format_md_table(headers: List[str], rows: List[List[str]]) -> str:
    """Generate a Markdown table."""
    md = "| " + " | ".join(headers) + " |\n"
    md += "| " + " | ".join(["---"] * len(headers)) + " |\n"
    for row in rows:
        md += "| " + " | ".join([str(item) for item in row]) + " |\n"
    return md
