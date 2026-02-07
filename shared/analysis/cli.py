"""
CLI - Unified command line interface for analysis utilities.

Usage:
    ./analyze leaderboard [options]
    ./analyze roi [options]
    ./analyze stats [options]
    ./analyze budget [options]
"""

import argparse
import sys
from pathlib import Path


def add_common_args(parser: argparse.ArgumentParser):
    """Add common arguments to a parser."""
    parser.add_argument(
        "--csv",
        type=Path,
        help="Ruta explicita al archivo CSV de metricas"
    )
    parser.add_argument(
        "--project",
        type=str,
        help="Filtrar por nombre de proyecto (match parcial)"
    )
    parser.add_argument(
        "--case",
        type=str,
        help="Filtrar por nombre de caso (match parcial)"
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="No combinar multiples CSVs (error si hay mas de uno)"
    )


def cmd_leaderboard(args):
    """Run leaderboard analysis."""
    from . import leaderboard
    leaderboard.run(
        csv_path=args.csv,
        project=args.project,
        case_filter=args.case,
        output=args.output,
        graphs=args.graphs
    )


def cmd_roi(args):
    """Run ROI analysis."""
    from . import roi_calculator
    roi_calculator.run(
        csv_path=args.csv,
        project=args.project,
        case_filter=args.case,
        volume=args.volume
    )


def cmd_stats(args):
    """Run stats evolution analysis."""
    from . import stats_evolution
    stats_evolution.run(
        csv_path=args.csv,
        project=args.project,
        case_filter=args.case,
        num_batches=args.batches,
        cuts=args.cuts
    )


def cmd_budget(args):
    """Run budget breakdown analysis."""
    from . import budget_breakdown
    budget_breakdown.run(
        csv_path=args.csv,
        project=args.project,
        case_filter=args.case,
        sort_by=args.sort
    )


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Utilidades de analisis para experimentos GEPA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  ./analyze leaderboard                    # Analisis completo
  ./analyze leaderboard --graphs           # Con graficos PNG
  ./analyze leaderboard --project dspy     # Solo proyecto dspy_*
  ./analyze roi --volume 5000              # ROI para 5000 llamadas
  ./analyze stats --batches 4              # Evolucion en 4 lotes
  ./analyze budget --sort cost             # Presupuesto ordenado por costo
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    # Leaderboard
    p_leader = subparsers.add_parser(
        "leaderboard",
        aliases=["lb"],
        help="Tabla ranking + anomalias + ROI"
    )
    add_common_args(p_leader)
    p_leader.add_argument(
        "--output", "-o",
        type=Path,
        help="Ruta de salida para archivo Markdown"
    )
    p_leader.add_argument(
        "--graphs", "-g",
        action="store_true",
        help="Generar graficos PNG (requiere matplotlib)"
    )
    p_leader.set_defaults(func=cmd_leaderboard)

    # ROI
    p_roi = subparsers.add_parser(
        "roi",
        help="Calculo de retorno de inversion"
    )
    add_common_args(p_roi)
    p_roi.add_argument(
        "--volume", "-v",
        type=int,
        default=1000,
        help="Volumen de llamadas en produccion (default: 1000)"
    )
    p_roi.set_defaults(func=cmd_roi)

    # Stats Evolution
    p_stats = subparsers.add_parser(
        "stats",
        help="Evolucion temporal por lotes"
    )
    add_common_args(p_stats)
    p_stats.add_argument(
        "--batches", "-b",
        type=int,
        default=3,
        help="Numero de lotes temporales (default: 3)"
    )
    p_stats.add_argument(
        "--cuts",
        type=str,
        help="Fechas de corte manuales (comma-separated: '2026-01-01,2026-02-01')"
    )
    p_stats.set_defaults(func=cmd_stats)

    # Budget
    p_budget = subparsers.add_parser(
        "budget",
        help="Desglose de presupuesto por caso"
    )
    add_common_args(p_budget)
    p_budget.add_argument(
        "--sort",
        choices=["cost", "count", "name"],
        default="cost",
        help="Ordenar resultados por (default: cost)"
    )
    p_budget.set_defaults(func=cmd_budget)

    # Parse and execute
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(130)


if __name__ == "__main__":
    main()
