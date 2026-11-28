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
    parser.add_argument("--csv", type=Path, help="Ruta explicita al archivo CSV de metricas")
    parser.add_argument(
        "--project",
        type=str,
        help="Filtrar a un solo proyecto (match por prefijo): 'dspy' -> dspy_gepa_poc, "
        "'gepa' -> gepa_standalone",
    )
    parser.add_argument(
        "--case",
        type=str,
        default=None,
        help=(
            "Filtrar por nombre de caso / columna 'Caso' "
            "(busqueda progresiva: subcadena case-insensitive; combinable con AND)"
        ),
    )
    parser.add_argument(
        "--student",
        "--task",
        dest="student",
        type=str,
        default=None,
        help=(
            "Filtrar por modelo estudiante / columna 'Modelo Tarea' "
            "(busqueda progresiva: subcadena case-insensitive; combinable con AND)"
        ),
    )
    parser.add_argument(
        "--teacher",
        "--reflection",
        dest="teacher",
        type=str,
        default=None,
        help=(
            "Filtrar por modelo profesor / columna 'Modelo Profesor' "
            "(busqueda progresiva: subcadena case-insensitive; combinable con AND)"
        ),
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="No combinar multiples CSVs (error si hay mas de uno)",
    )


def cmd_leaderboard(args):
    """Run leaderboard analysis."""
    from . import leaderboard

    leaderboard.run(
        csv_path=args.csv,
        project=args.project,
        case_filter=args.case,
        output=args.output,
        graphs=args.graphs,
        student_filter=args.student,
        teacher_filter=args.teacher,
        merge=not args.no_merge,
    )


def cmd_roi(args):
    """Run ROI analysis."""
    from . import roi_calculator

    roi_calculator.run(
        csv_path=args.csv,
        project=args.project,
        case_filter=args.case,
        volume=args.volume,
        student_filter=args.student,
        teacher_filter=args.teacher,
        merge=not args.no_merge,
    )


def cmd_stats(args):
    """Run stats evolution analysis."""
    from . import stats_evolution

    stats_evolution.run(
        csv_path=args.csv,
        project=args.project,
        case_filter=args.case,
        num_batches=args.batches,
        cuts=args.cuts,
        student_filter=args.student,
        teacher_filter=args.teacher,
        merge=not args.no_merge,
    )


def cmd_budget(args):
    """Run budget breakdown analysis."""
    from . import budget_breakdown

    budget_breakdown.run(
        csv_path=args.csv,
        project=args.project,
        case_filter=args.case,
        sort_by=args.sort,
        student_filter=args.student,
        teacher_filter=args.teacher,
        merge=not args.no_merge,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build and configure the unified analysis argument parser."""
    parser = argparse.ArgumentParser(
        description="Utilidades de analisis para experimentos GEPA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  ./analyze leaderboard                                         # Analisis completo
  ./analyze leaderboard --graphs                                # Con graficos PNG
  ./analyze leaderboard --project dspy                          # Solo proyecto dspy_gepa_poc
  ./analyze leaderboard --case CV --student 4.1-mini --teacher claude
  ./analyze leaderboard --teacher claude                  # Todos los casos con profesor Claude
  ./analyze roi --task 4.1-mini --reflection gpt-4o --volume 5000
  ./analyze stats --student gpt-4.1-mini --batches 4            # Evolucion en 4 lotes filtrados
  ./analyze budget --teacher gpt-5.4 --sort cost                # Presupuesto filtrado

Filtros comunes a todos los subcomandos (combinables con AND logico):
  --project {dspy,gepa}           Aislar un solo proyecto (match por prefijo)
  --case <texto>                  Filtrar por 'Caso' (busqueda progresiva)
  --student / --task <texto>      Filtrar por 'Modelo Tarea' (busqueda progresiva)
  --teacher / --reflection <txt>  Filtrar por 'Modelo Profesor' (busqueda progresiva)
  --csv <ruta>                    CSV de metricas explicito
  --no-merge                      No combinar multiples CSVs (error si hay mas de uno)

Busqueda progresiva (subcadena case-insensitive):
  Acota el resultado extendiendo la cadena: gpt -> gpt-4 -> gpt-4.1 -> gpt-4.1-mini.
  Nota: 'gpt-4o' coincide con 'azure/gpt-4o' y 'azure/gpt-4o-mini'; 'claude' con
  toda la familia 'anthropic/claude-*'. Limite conocido: si un nombre completo es
  subcadena de otro (p. ej. 'azure/gpt-5' en 'azure/gpt-5.4'), '--teacher gpt-5'
  devuelve ambos; '--teacher gpt-5.4' aisla solo 'azure/gpt-5.4'.
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    # Leaderboard
    p_leader = subparsers.add_parser(
        "leaderboard", aliases=["lb"], help="Tabla ranking + anomalias + ROI"
    )
    add_common_args(p_leader)
    p_leader.add_argument("--output", "-o", type=Path, help="Ruta de salida para archivo Markdown")
    p_leader.add_argument(
        "--graphs", "-g", action="store_true", help="Generar graficos PNG (requiere matplotlib)"
    )
    p_leader.set_defaults(func=cmd_leaderboard)

    # ROI
    p_roi = subparsers.add_parser("roi", help="Calculo de retorno de inversion")
    add_common_args(p_roi)
    p_roi.add_argument(
        "--volume",
        "-v",
        type=int,
        default=1000,
        help="Volumen de llamadas en produccion (default: 1000)",
    )
    p_roi.set_defaults(func=cmd_roi)

    # Stats Evolution
    p_stats = subparsers.add_parser("stats", help="Evolucion temporal por lotes")
    add_common_args(p_stats)
    p_stats.add_argument(
        "--batches", "-b", type=int, default=3, help="Numero de lotes temporales (default: 3)"
    )
    p_stats.add_argument(
        "--cuts",
        type=str,
        help="Fechas de corte manuales (comma-separated: '2026-01-01,2026-02-01')",
    )
    p_stats.set_defaults(func=cmd_stats)

    # Budget
    p_budget = subparsers.add_parser("budget", help="Desglose de presupuesto por caso")
    add_common_args(p_budget)
    p_budget.add_argument(
        "--sort",
        choices=["cost", "count", "name"],
        default="cost",
        help="Ordenar resultados por (default: cost)",
    )
    p_budget.set_defaults(func=cmd_budget)

    return parser


def main(argv: list[str] | None = None):
    """Main CLI entry point."""
    parser = build_parser()

    # Parse and execute
    args = parser.parse_args(argv)

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
